"""Discovery fixtures are synthetic. These tests never access a real radio."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import fcntl
import pty
import select as io_select
import struct
import subprocess
import sys
import termios
import time
from threading import Event
import unittest
from unittest.mock import patch

from hifi.app import App
from hifi.discovery import Network, Scan, parse_csv, scan_command, select
from hifi.models import Scope, Session
from hifi.radio import Radio, State
from hifi.reports import report_data
from hifi.storage import Store

HEADER = "BSSID, First time seen, Last time seen, channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key\n"
CLIENTS = "\nStation MAC, First time seen, Last time seen, Power, # packets, BSSID, Probed ESSIDs\n"


def observation(name="", power="-63", bssid="02:11:22:33:44:55", channel=6):
    return f"{bssid}, 2026-10-14 10:00:00, 2026-10-14 10:00:02, {channel}, 54, WPA2, CCMP, PSK, {power}, 20, 4, 0.0.0.0, {len(name)}, {name}, \n"


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Store(self.tmp.name), Session(scope=Scope("wlan0", duration=5)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_hidden_ap_is_detected_without_a_name_and_keeps_actual_signal(self):
        networks, _ = parse_csv(HEADER + observation())
        self.assertEqual(len(networks), 1)
        n = networks[0]
        self.assertEqual((n.name, n.bssid, n.channel, n.signal), ("[Hidden]", "02:11:22:33:44:55", 6, -63))
        self.assertEqual(n.frequency, 2437)
        self.assertEqual(n.wps, "Unknown")

    def test_names_with_commas_spaces_and_unavailable_signal(self):
        networks, _ = parse_csv(HEADER + observation(" lab, room ", "-1"))
        self.assertEqual(networks[0].ssid, " lab, room ")
        self.assertIsNone(networks[0].signal)

    def test_incomplete_csv_and_invalid_channels_do_not_create_fake_networks(self):
        text = HEADER + observation(channel=-1) + "02:aa:bb:cc:dd:ee, 2026-10-14\n"
        self.assertEqual(parse_csv(text)[0], [])

    def test_observed_clients_attach_to_the_correct_bssid(self):
        text = HEADER + observation() + CLIENTS + "02:aa:bb:cc:dd:ee, first, last, -70, 9, 02:11:22:33:44:55, lab\n"
        networks, clients = parse_csv(text)
        self.assertEqual(networks[0].clients, ["02:aa:bb:cc:dd:ee"])
        self.assertEqual(clients[0]["packets"], 9)

    def test_revealed_name_updates_same_network_and_survives_later_blank_ssid(self):
        scan = Scan(self.app)
        scan.update(HEADER + observation())
        scan.update(HEADER + observation("HIFI lab") + observation("other", bssid="02:11:22:33:44:66"))
        scan.update(HEADER + observation())
        rows, _, _ = scan.snapshot()
        self.assertEqual([n.bssid for n in rows], ["02:11:22:33:44:55", "02:11:22:33:44:66"])
        self.assertEqual(rows[0].ssid, "HIFI lab")

    def test_selected_hidden_ap_fills_scope_and_summary_omits_observations(self):
        n = Network("02:11:22:33:44:55", channel=36)
        self.app.session.networks = [asdict(n)]
        self.app.session.clients = [{"mac": "02:aa:bb:cc:dd:ee"}]
        select(self.app, n)
        saved = self.app.store.load(self.app.session.id)
        self.assertEqual((saved.scope.bssid, saved.scope.channel), (n.bssid, 36))
        self.assertNotIn(n.bssid, json.dumps(report_data(saved)))
        self.assertNotIn("02:aa:bb:cc:dd:ee", json.dumps(report_data(saved)))
        self.assertIn(n.bssid, json.dumps(report_data(saved, True)))

    def test_scan_is_passive_and_bound_to_selected_interface(self):
        command = scan_command("wlan7", Path(self.tmp.name) / "scan", 8, "bg")
        self.assertEqual(command.argv[-1], "wlan7")
        self.assertEqual(command.timeout, 8)
        self.assertIn("csv", command.argv)
        for args in [("", 30, "abg"), ("wlan0", 0, "bg"), ("wlan0", 30, "bad")]:
            with self.assertRaises(ValueError):
                scan_command(args[0], "unused", args[1], args[2])

    def test_demo_scan_never_launches_a_subprocess(self):
        self.app.session.demo = True
        with patch("hifi.discovery.run", side_effect=AssertionError("radio")), patch("hifi.radio.read", side_effect=AssertionError("radio")):
            record = Scan(self.app, 5).execute()
        self.assertEqual(record["status"], "simulated")
        self.assertTrue(any(not n["ssid"] for n in self.app.session.networks))

    def test_missing_backend_does_not_change_adapter(self):
        with patch("hifi.discovery.shutil.which", return_value=None), patch("hifi.discovery.Radio") as radio:
            with self.assertRaisesRegex(ValueError, "Missing airodump"):
                Scan(self.app).execute()
            radio.assert_not_called()

    def test_streaming_backend_fixture_reveals_hidden_name_and_persists_result(self):
        # A real child process emits two CSV revisions; the radio is entirely mocked.
        binary = Path(self.tmp.name) / "airodump-ng"
        script = ("#!/usr/bin/env python3\nimport sys,time\nfrom pathlib import Path\n"
                  "p=Path(sys.argv[sys.argv.index('--write')+1]+'-01.csv')\n"
                  f"p.write_text({(HEADER + observation())!r})\ntime.sleep(.25)\n"
                  f"p.write_text({(HEADER + observation('Revealed lab'))!r})\ntime.sleep(.25)\n")
        binary.write_text(script)
        binary.chmod(0o700)
        class FakeRadio:
            interface = "wlan0"
            restore_errors = []
            steps = []
            changed = True
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def monitor(self): pass
        with patch("hifi.discovery.Radio", return_value=FakeRadio()), patch.dict(os.environ, {"PATH": self.tmp.name + os.pathsep + os.environ["PATH"]}), patch("os.geteuid", return_value=0):
            scan = Scan(self.app, 5)
            record = scan.execute()
        self.assertEqual(record["status"], "ok", record)
        self.assertEqual(self.app.session.networks[0]["ssid"], "Revealed lab")
        self.assertEqual(record["adapter_restoration"], "restored")

    def test_restore_failure_is_visible_even_with_observed_networks(self):
        self.app.session.demo = True
        with patch.object(Radio, "restore", lambda radio: radio.restore_errors.append("USB disconnected")):
            record = Scan(self.app).execute()
        self.assertEqual(record["status"], "error")
        self.assertIn("USB disconnected", record["output"])


class RadioRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State("wlan0", "phy9", "managed", True, 6, "yes")
        self.commands = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake_run(self, command, cwd, stop, emit):
        argv = command.argv
        self.commands.append(argv)
        if argv[:2] == ["ip", "link"]:
            self.state.up = argv[-1] == "up"
        if "type" in argv:
            self.state.mode = argv[-1]
        if "channel" in argv:
            self.state.channel = int(argv[-1])
        if argv[0] == "nmcli":
            self.state.managed = argv[-1]
        return {"title": "adapter", "argv": argv, "status": "ok", "output": "", "returncode": 0}

    def patches(self):
        from contextlib import ExitStack
        from hifi.adapters import Adapter
        stack = ExitStack()
        stack.enter_context(patch("hifi.radio.require_root"))
        stack.enter_context(patch("hifi.radio.LOCK_ROOT", Path(self.tmp.name)))
        stack.enter_context(patch("hifi.radio.snapshot", side_effect=lambda _: State(**asdict(self.state))))
        stack.enter_context(patch("hifi.radio.adapters.discover", side_effect=lambda: [Adapter("wlan0", self.state.mode, "phy9")]))
        stack.enter_context(patch("hifi.radio.run", side_effect=self.fake_run))
        return stack

    def test_scan_restores_mode_link_and_nm_ownership_after_cancellation(self):
        stop = Event()
        with self.patches():
            with Radio("wlan0", self.tmp.name, stop) as radio:
                radio.monitor()
                self.assertEqual(self.state.mode, "monitor")
                stop.set()
            self.assertEqual(self.state.mode, "managed")
            self.assertTrue(self.state.up)
            self.assertEqual(self.state.managed, "yes")
            self.assertEqual(radio.restore_errors, [])
        self.assertFalse((Path(self.tmp.name) / "adapter-recovery.json").exists())

    def test_failure_halfway_through_preparation_still_restores(self):
        with self.patches():
            original = self.fake_run
            def fail_monitor(command, cwd, stop, emit):
                if command.argv[-2:] == ["type", "monitor"]:
                    return {"status": "failed", "output": "driver refused"}
                return original(command, cwd, stop, emit)
            with patch("hifi.radio.run", side_effect=fail_monitor):
                with self.assertRaisesRegex(ValueError, "driver refused"):
                    with Radio("wlan0", self.tmp.name) as radio:
                        radio.monitor()
            self.assertEqual((self.state.mode, self.state.up, self.state.managed), ("managed", True, "yes"))

    def test_same_phy_cannot_be_owned_by_two_jobs(self):
        with self.patches():
            with Radio("wlan0", self.tmp.name):
                with self.assertRaisesRegex(ValueError, "Another HIFI"):
                    with Radio("wlan0", self.tmp.name):
                        pass


class DiscoveryTerminalTests(unittest.TestCase):
    def test_hidden_row_selection_stays_in_hifi_and_saves_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
            proc = subprocess.Popen([sys.executable, "-m", "hifi", "--home", directory, "--demo"],
                                    stdin=slave, stdout=slave, stderr=slave,
                                    env={**os.environ, "TERM": "xterm-256color"},
                                    cwd=Path(__file__).resolve().parents[1])
            os.close(slave)
            output = bytearray()
            def wait(text):
                recent = bytearray()
                deadline = time.monotonic() + 6
                while time.monotonic() < deadline:
                    ready, _, _ = io_select.select([master], [], [], .1)
                    if ready:
                        try:
                            data = os.read(master, 65536)
                        except OSError:
                            break
                        output.extend(data)
                        recent.extend(data)
                        if text.encode() in recent:
                            return
                self.fail(f"Missing {text}: {bytes(output)[-2000:]!r}")
            try:
                wait("COMMAND CENTER")
                os.write(master, b"03\n")
                wait("Live scan / include hidden networks")
                os.write(master, b"01\n")
                wait("[Hidden]")
                os.write(master, b"02\n")
                wait("SELECTED NETWORK / [Hidden]")
                os.write(master, b"\n")
                wait("Live scan / include hidden networks")
                os.write(master, b"00\n")
                wait("COMMAND CENTER")
                os.write(master, b"00\n")
                proc.wait(timeout=6)
                self.assertEqual(proc.returncode, 0)
                saved = json.loads(next(Path(directory).glob("*/session.json")).read_text())
                self.assertEqual(saved["scope"]["bssid"], "02:11:22:33:44:66")
                self.assertEqual(saved["scope"]["channel"], 36)
                self.assertEqual(saved["records"][-1]["status"], "simulated")
                self.assertEqual(saved["selected_network"]["ssid"], "")
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                os.close(master)


if __name__ == "__main__":
    unittest.main()
