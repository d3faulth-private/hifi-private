import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hifi import catalog
from hifi.advisor import suggest, local_explanation
from hifi.app import App
from hifi.demo import HELP, create_demo
from hifi.models import Command, Scope, Session, clean
from hifi.reports import export, report_data
from hifi.runner import run, OUTPUT_LIMIT
from hifi.storage import Store


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.scope = Scope("wlan0mon", "02:11:22:33:44:55", 6, 5)
        self.cap = self.path / "capture with spaces.pcap"
        self.cap.write_bytes(b"fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_scope_rejects_injection_and_broadcast(self):
        for bad in ["wlan0;id", "--help", "wlan0\n", "a" * 16]:
            with self.assertRaises(ValueError):
                Scope(interface=bad).validate()
        for bad in ["ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", "02:11:22:33:44:55;id"]:
            with self.assertRaises(ValueError):
                Scope(bssid=bad).validate()

    def test_store_roundtrip_and_private_permissions(self):
        store = Store(self.path / "state")
        s = Session(scope=self.scope)
        s.notes.append("test")
        store.save(s)
        self.assertEqual(store.load(s.id).to_dict(), s.to_dict())
        self.assertEqual((store.folder(s) / "session.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(store.list()), 1)
        with self.assertRaises(ValueError):
            store.load("../etc/passwd")

    def test_store_keeps_existing_file_on_serialization_error(self):
        store = Store(self.path / "state")
        s = Session()
        store.save(s)
        original = (store.folder(s) / "session.json").read_text()
        s.notes.append(object())
        with self.assertRaises(TypeError):
            store.save(s)
        self.assertEqual((store.folder(s) / "session.json").read_text(), original)

    def test_engine_profiles_require_local_supported_flags(self):
        passive = catalog.engine_capture(self.scope, HELP)
        self.assertIn("--nodeauths", passive.argv)
        self.assertIn(self.scope.bssid, passive.argv)
        self.assertNotIn("--nodeauths", catalog.engine_capture(self.scope, HELP, True).argv)
        with self.assertRaises(ValueError):
            catalog.engine_capture(self.scope, HELP.replace("--no-wps", ""))
        alternate = catalog.engine_capture(self.scope, HELP.replace("--nodeauths", "--no-deauths"))
        self.assertIn("--no-deauths", alternate.argv)

    def test_capture_has_target_time_and_size_limits(self):
        c = catalog.passive_capture(self.scope, self.path / "out.pcapng")
        self.assertIn("filesize:51200", c.argv)
        self.assertIn("duration:5", c.argv)
        self.assertIn(self.scope.bssid, c.argv[c.argv.index("-f") + 1])
        with self.assertRaises(ValueError):
            catalog.passive_capture(self.scope, self.cap)

    def test_monitor_preflight_checks_mode_and_channel(self):
        with patch("hifi.catalog.shutil.which", return_value="/usr/sbin/iw"):
            for output in ["type managed\nchannel 6", "type monitor\nchannel 11"]:
                with patch("hifi.catalog.subprocess.run", return_value=subprocess.CompletedProcess([], 0, output, "")):
                    with self.assertRaises(ValueError):
                        catalog.monitor_preflight(self.scope)
            with patch("hifi.catalog.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "type monitor\nchannel 6", "")):
                catalog.monitor_preflight(self.scope)

    def test_command_edits_allow_display_filters_but_reject_code_loading(self):
        import shlex
        cmd = catalog.inspect_capture(self.cap, "eapol")
        text = shlex.join(cmd.argv).replace("eapol", "wlan")
        self.assertIn("wlan", catalog.validate_edit(text, cmd, self.scope).argv)
        for suffix in [" -X lua_script:evil.lua", " ; id", " -i wlan9", " -r /etc/passwd"]:
            with self.assertRaises(ValueError):
                catalog.validate_edit(shlex.join(cmd.argv) + suffix, cmd, self.scope)

    def test_scoped_radio_command_cannot_be_redirected(self):
        import shlex
        cmd = catalog.engine_capture(self.scope, HELP)
        for text in [shlex.join(cmd.argv).replace(self.scope.bssid, "02:aa:bb:cc:dd:ee"),
                     shlex.join(cmd.argv) + " --kill"]:
            with self.assertRaises(ValueError):
                catalog.validate_edit(text, cmd, self.scope)

    def test_demo_never_invokes_a_subprocess(self):
        app = App(Store(self.path), create_demo())
        with patch("hifi.app.run", side_effect=AssertionError("must not execute")):
            r = app.execute(catalog.engine_capture(app.session.scope, HELP, True))
        self.assertEqual(r["status"], "simulated")
        self.assertTrue(app.session.records)

    def test_summary_report_omits_raw_identifiers_and_notes(self):
        session = Session(scope=self.scope, notes=["private secret"])
        session.records = [{"title": "Test", "status": "ok", "output": "KEY FOUND! [ secret ]", "argv": ["tool", "/private/file"]}]
        data = json.dumps(report_data(session))
        for secret in [self.scope.bssid, "private secret", "KEY FOUND", "/private/file"]:
            self.assertNotIn(secret, data)
        self.assertIn("private secret", json.dumps(report_data(session, True)))

    def test_html_escapes_raw_output_and_does_not_overwrite(self):
        s = Session(notes=["<script>alert(1)</script>"])
        dest = export(s, self.path / "report.html", True)
        self.assertIn("&lt;script&gt;", dest.read_text())
        self.assertNotIn("<script>", dest.read_text())
        with self.assertRaises(FileExistsError):
            export(s, dest)

    def test_advice_does_not_equate_timeout_with_security(self):
        s = Session(records=[{"title": "test", "status": "timeout", "output": ""}])
        self.assertIn("does not establish network security", str(suggest(s)))

    def test_local_model_failure_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                local_explanation("explain", Session(), model="")

    def test_terminal_control_sequences_are_removed(self):
        self.assertEqual(clean("\x1b[31mred\x1b[0m\x00\x1b]0;evil\x07"), "red")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, script, timeout=5):
        return Command("Fixture", [sys.executable, "-c", script], "Test", timeout=timeout)

    def test_real_subprocess_success_and_nonzero(self):
        r = run(self.command("print('working')"), self.tmp.name)
        self.assertEqual(r["status"], "ok")
        self.assertIn("working", r["output"])
        r = run(self.command("raise SystemExit(7)"), self.tmp.name)
        self.assertEqual(r["returncode"], 7)
        self.assertEqual(r["status"], "failed")

    def test_timeout_reaps_process_group(self):
        script = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); print(p.pid,flush=True); time.sleep(60)"
        r = run(self.command(script, timeout=0.2), self.tmp.name)
        self.assertEqual(r["status"], "timeout")
        pid = int(r["output"].splitlines()[0])
        stat = Path(f"/proc/{pid}/stat")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                state = stat.read_text().split()[2]
            except (FileNotFoundError, ProcessLookupError):
                return  # The kernel may reap it between opening and reading /proc.
            if state == "Z":
                return
            time.sleep(0.01)
        self.fail("descendant is still running after the cancellation grace period")

    def test_stop_event_cancels(self):
        stop = threading.Event()
        timer = threading.Timer(0.15, stop.set)
        timer.start()
        try:
            r = run(self.command("import time;time.sleep(60)"), self.tmp.name, stop)
        finally:
            timer.cancel()
        self.assertEqual(r["status"], "cancelled")

    def test_output_is_bounded(self):
        r = run(self.command("print('x'*1000000)"), self.tmp.name)
        self.assertLess(len(r["output"]), OUTPUT_LIMIT + 100)
        self.assertIn("truncated", r["output"])

    def test_missing_program_is_recorded(self):
        r = run(Command("Missing", ["/no/such/program"], "Test"), self.tmp.name)
        self.assertEqual(r["status"], "error")
        self.assertIn("No such file", r["output"])

    def test_root_requirement_has_actionable_error(self):
        with patch("os.geteuid", return_value=1000):
            r = run(Command("Radio", ["anything"], "Test", root=True), self.tmp.name)
        self.assertIn("needs root", r["output"])


if __name__ == "__main__":
    unittest.main()
