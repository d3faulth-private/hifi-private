"""Selected-network integration, with synthetic observations and no radio access."""
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
from threading import Event
import time
import unittest
from unittest.mock import patch

from hifi.app import App
from hifi.discovery import Network
from hifi.models import Scope, Session
from hifi.reports import report_data
from hifi.selected import Job, command_for, read_recovery, result_text
from hifi.storage import Store


class FakeRadio:
    def __init__(self, interface="wlan0", restore_errors=()):
        self.interface = interface
        self.changed = False
        self.restore_errors = list(restore_errors)
        self.steps = []
        self.restored = False
    def __enter__(self): return self
    def monitor(self, channel): self.changed = True
    def __exit__(self, *_): self.restored = True


class SelectedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.network = Network("02:11:22:33:44:55", "HIFI-LAB", 6, -42, "WPA2", "CCMP", "PSK")
        self.app = App(Store(self.folder / "state"), Session(scope=Scope("wlan0", self.network.bssid, 6)))
        self.words = self.folder / "words.txt"
        self.words.write_text("synthetic-wordlist-candidate\n")
        self.app.session.exploit_settings["wordlist"] = str(self.words)

    def tearDown(self): self.tmp.cleanup()

    def fixture(self, source, kind="wpa", radio=None, stop=None, emit=None):
        script = self.folder / "fixture.py"
        script.write_text(source)
        radio = radio or FakeRadio()
        with patch("hifi.selected.Radio", return_value=radio), patch("hifi.selected.missing_tools", return_value=[]), \
             patch("hifi.selected.engine_argv", side_effect=lambda args: [sys.executable, str(script), *args]), \
             patch("os.geteuid", return_value=0):
            job = Job(self.app, self.network, kind)
            result = job.execute(stop, emit)
        return job, result, radio

    def test_both_profiles_preserve_selection_and_ignore_advanced_engine_arguments(self):
        self.app.session.engine_args = ["-b", "02:00:00:00:00:99", "-p", "1", "--infinite"]
        for kind in ("wpa", "wps"):
            cmd = Job(self.app, self.network, kind).command
            args = cmd.argv
            for flag, value in [("-b", self.network.bssid), ("-i", "wlan0"), ("-c", "6"), ("--first", "1")]:
                self.assertEqual(args[args.index(flag) + 1], value)
            self.assertNotIn("-p", args)
            self.assertNotIn("--infinite", args)
            self.assertIn("--no-pmkid", args)
            self.assertEqual(cmd.timeout, 600)
            self.assertEqual("--dict" in args, kind == "wpa")
            self.assertEqual("--wps-only" in args, kind == "wps")

    def test_generated_arguments_are_understood_by_the_bundled_engine(self):
        from hifi.engine.config import Configuration
        for kind in ("wpa", "wps"):
            args = Job(self.app, self.network, kind).command.argv[2:]
            with patch.object(Configuration, "initialized", False), patch.object(sys, "argv", ["hifi", *args]):
                Configuration.initialize(load_interface=False)
            self.assertEqual(Configuration.target_bssid, self.network.bssid)
            self.assertEqual(str(Configuration.target_channel), "6")
            self.assertEqual(Configuration.wps_only, kind == "wps")
            self.assertTrue(Configuration.dont_use_pmkid)
            self.assertEqual(Configuration.no_wps, kind == "wpa")

    def test_mismatched_scope_unsupported_security_and_bad_wordlists_are_rejected(self):
        for changed in [Network("02:11:22:33:44:99", channel=6, security="WPA2"),
                        Network(self.network.bssid, channel=11, security="WPA2"),
                        Network(self.network.bssid, channel=6, security="WPA3"),
                        Network(self.network.bssid, channel=6, security="WPA2", authentication="MGT")]:
            with self.assertRaises(ValueError): Job(self.app, changed, "wpa")
        self.words.write_text("")
        with self.assertRaisesRegex(ValueError, "empty"): Job(self.app, self.network, "wpa")

    def test_passive_capture_option_is_preserved(self):
        self.app.session.exploit_settings["deauth"] = False
        self.assertIn("--nodeauths", Job(self.app, self.network, "wpa").command.argv)

    def test_missing_tools_do_not_enter_monitor_mode(self):
        with patch("hifi.selected.missing_tools", return_value=["hashcat"]), patch("hifi.selected.Radio", return_value=FakeRadio()) as radio, patch("os.geteuid", return_value=0):
            result = Job(self.app, self.network, "wpa").execute()
            self.assertFalse(radio.return_value.changed)
        self.assertEqual(result["status"], "error")
        self.assertIn("Missing: hashcat", result["output"])

    def test_real_child_streams_result_and_restores_renamed_adapter(self):
        evidence = dict(type="WPA", bssid=self.network.bssid, key="synthetic-recovered-value")
        source = "import json,sys\nfrom pathlib import Path\nprint('fixture progress', flush=True)\nPath('args.json').write_text(json.dumps(sys.argv[1:]))\nPath('cracked.json').write_text(" + repr(json.dumps([evidence])) + ")\n"
        emitted = []
        job, result, radio = self.fixture(source, radio=FakeRadio("wlan0mon"), emit=emitted.append)
        self.assertTrue(radio.restored)
        self.assertEqual(result["adapter_restoration"], "restored")
        self.assertEqual(result["status"], "recovered")
        self.assertIn("fixture progress", "".join(emitted))
        args = json.loads((job.directory / "args.json").read_text())
        self.assertEqual(args[args.index("-i") + 1], "wlan0mon")
        self.assertEqual(args[args.index("-b") + 1], self.network.bssid)
        self.assertEqual(job.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((job.directory / "cracked.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn(evidence["key"], json.dumps(report_data(self.app.session)))
        self.assertNotIn(self.network.bssid, json.dumps(report_data(self.app.session)))
        self.assertIn(evidence["key"], json.dumps(report_data(self.app.session, True)))

    def test_exit_zero_or_printed_success_without_matching_fresh_evidence_is_not_recovery(self):
        for source in ["print('Password recovered')", "from pathlib import Path\nPath('cracked.json').write_text('[{\"type\":\"WPA\",\"bssid\":\"02:00:00:00:00:99\",\"key\":\"wrong-network\"}]')"]:
            with self.subTest(source=source):
                _, result, radio = self.fixture(source)
                self.assertEqual(result["status"], "no-recovery")
                self.assertIsNone(result["recovery"])
                self.assertTrue(radio.restored)

    def test_failure_and_cancel_restore_adapter_without_success(self):
        _, result, radio = self.fixture("import sys\nprint('backend failed')\nsys.exit(7)")
        self.assertEqual((result["status"], result["returncode"]), ("failed", 7))
        self.assertTrue(radio.restored)
        stop = Event()
        _, result, radio = self.fixture("import time\nprint('waiting for cancellation', flush=True)\ntime.sleep(30)",
                                       stop=stop, emit=lambda text: stop.set() if "waiting for cancellation" in text else None)
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(radio.restored)

    def test_pin_only_and_incomplete_restoration_are_explicit(self):
        evidence = dict(type="WPS", bssid=self.network.bssid, pin="12345670", psk=None)
        source = "from pathlib import Path\nPath('cracked.json').write_text(" + repr(json.dumps([evidence])) + ")"
        _, result, _ = self.fixture(source, kind="wps", radio=FakeRadio(restore_errors=["USB removed"]))
        self.assertEqual(result["status"], "error")
        self.assertIn("PASSWORD NOT RECOVERED", result_text(result))
        self.assertIn("Adapter: incomplete", result_text(result))
        self.assertEqual(result["recovery"], {"pin": "12345670"})

    def test_demo_never_runs_backends_and_has_no_recovered_credentials(self):
        self.app.session.demo = True
        with patch("hifi.selected.run", side_effect=AssertionError("backend")), patch("hifi.radio.run", side_effect=AssertionError("radio")):
            result = Job(self.app, self.network, "wps").execute()
        self.assertEqual(result["status"], "simulated")
        self.assertIsNone(result["recovery"])

    def test_invalid_result_does_not_become_success(self):
        _, result, radio = self.fixture("from pathlib import Path\nPath('cracked.json').write_text('invalid json')")
        self.assertEqual(result["status"], "error")
        self.assertTrue(radio.restored)


class SelectedTerminalTests(unittest.TestCase):
    def test_selected_wpa_and_wps_stay_in_hifi_and_return_to_network_actions(self):
        import pyte
        with tempfile.TemporaryDirectory() as home:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
            proc = subprocess.Popen([sys.executable, "-m", "hifi", "--home", home, "--demo"],
                                    stdin=slave, stdout=slave, stderr=slave,
                                    env={**os.environ, "TERM": "xterm-256color"}, cwd=Path(__file__).resolve().parents[1])
            os.close(slave)
            screen = pyte.Screen(100, 24)
            stream = pyte.ByteStream(screen)
            def wait(text):
                deadline = time.monotonic() + 6
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], .05)
                    if ready:
                        try: stream.feed(os.read(master, 65536))
                        except OSError: break
                    if text in "\n".join(screen.display):
                        self.assertIn("D3FAULTH", "\n".join(screen.display))
                        return
                self.fail(text + "\n" + "\n".join(screen.display))
            def send(value): os.write(master, value.encode())
            try:
                wait("COMMAND CENTER"); send("\n"); wait("[Hidden]")
                send("01\n"); wait("NETWORK ACTIONS / HIFI-LAB")
                send("06\n"); wait("ASSESSMENT / HIFI-LAB")
                send("01\n"); wait("NETWORK EVIDENCE"); send("\n")
                wait("ASSESSMENT / HIFI-LAB"); send("00\n"); wait("NETWORK ACTIONS / HIFI-LAB")
                send("07\n"); wait("NETWORK ADAPTER /"); send("00\n"); wait("NETWORK ACTIONS / HIFI-LAB")
                send("01\n"); wait("Choose a local text wordlist"); send("\n")
                wait("RUN SELECTED NETWORK WORKFLOW"); send("\n")
                wait("SELECTED NETWORK RESULT"); wait("DEMO ONLY / NO RECOVERY")
                send("\n"); wait("NETWORK ACTIONS / HIFI-LAB")
                send("02\n"); wait("RUN SELECTED NETWORK WORKFLOW"); send("\n")
                wait("DEMO ONLY / NO RECOVERY"); send("\n"); wait("NETWORK ACTIONS / HIFI-LAB")
                send("00\n"); wait("SAVED"); send("q"); wait("COMMAND CENTER")
                send("04\n"); wait("NETWORK ACTIONS / HIFI-LAB"); send("00\n")
                wait("COMMAND CENTER"); send("00\n"); proc.wait(timeout=5)
                self.assertEqual(proc.returncode, 0)
                saved = json.loads(next(Path(home).glob("*/session.json")).read_text())
                results = [r for r in saved["records"] if r.get("mode") == "selected-network"]
                self.assertEqual(len(results), 2)
                self.assertTrue(all(r["status"] == "simulated" and r["recovery"] is None for r in results))
                self.assertTrue(all(r["selected_target"]["bssid"] == "02:11:22:33:44:55" for r in results))
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()
                os.close(master)
