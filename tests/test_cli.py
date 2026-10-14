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
import time
import unittest
from unittest.mock import patch

from hifi.advisor import local_explanation, recommended_commands, NoRedirect
from hifi.catalog import validate_edit
from hifi.demo import create_demo
from hifi.models import Session
import shlex

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "hifi", "--home", str(self.home), *args],
                              cwd=ROOT, text=True, capture_output=True, timeout=10)

    def test_cli_demo_session_report_end_to_end(self):
        result = self.cli("--demo", "diagnose")
        self.assertEqual(result.returncode, 0, result.stderr)
        sessions = self.cli("sessions")
        self.assertIn("5 commands", sessions.stdout)
        identifier = sessions.stdout.split()[0]
        path = Path(self.tmp.name) / "report.json"
        result = self.cli("--session", identifier, "report", "--output", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(path.read_text())
        self.assertTrue(report["demo"])
        self.assertEqual(len(report["records"]), 5)
        self.assertNotIn("output", report["records"][0])
        suggestions = self.cli("--session", identifier, "suggest")
        self.assertIn("Suggested command:", suggestions.stdout)

    def test_missing_scope_is_actionable(self):
        result = self.cli("capture")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Set interface, BSSID, and channel", result.stderr)

    def test_preview_does_not_create_capture(self):
        result = self.cli("--demo", "capture")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Preview only", result.stdout)
        self.assertEqual(list(self.home.rglob("*.pcapng")), [])

    def test_no_tty_explains_how_to_proceed(self):
        result = self.cli("tui")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs a terminal", result.stderr)

    def test_demo_flag_does_not_change_live_session(self):
        self.cli("scope", "--interface", "wlan0", "--bssid", "02:11:22:33:44:55", "--channel", "6")
        identifier = self.cli("sessions").stdout.split()[0]
        result = self.cli("--session", identifier, "--demo", "diagnose")
        self.assertEqual(result.returncode, 2)

    def test_recommendations_are_valid_profile_commands(self):
        session = create_demo()
        choices = recommended_commands(session)
        self.assertTrue(choices)
        for reason, command in choices:
            self.assertTrue(reason)
            validate_edit(shlex.join(command.argv), command, session.scope)

    def test_ollama_explanation_uses_loopback_and_never_executes(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"response":"Check the channel."}'
        with patch("hifi.advisor.urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = Response()
            answer = local_explanation("Why?", Session(), "local-test-model")
            self.assertEqual(answer, "Check the channel.")
            req = factory.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/generate")
            self.assertFalse(json.loads(req.data)["stream"])
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_terminal_menu_and_editable_scope_smoke(self):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        proc = subprocess.Popen([sys.executable, "-m", "hifi", "--home", str(self.home), "--demo"],
                                cwd=ROOT, stdin=slave, stdout=slave, stderr=slave,
                                env={**os.environ, "TERM": "xterm-256color"})
        os.close(slave)
        output = bytearray()
        def await_text(text):
            deadline = time.monotonic() + 6
            recent = bytearray()
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], .1)
                if ready:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    output.extend(data)
                    recent.extend(data)
                    if text.encode() in recent:
                        return
                if proc.poll() is not None:
                    break
            self.fail(f"Terminal did not show {text!r}: {bytes(output)[-2000:]!r}")
        try:
            await_text("/ COMMAND CENTER")
            os.write(master, b"01\n")
            await_text("Edit session scope")
            os.write(master, b"02\n")
            await_text("Wireless interface")
            os.write(master, b"\x15wlan1mon\n")
            await_text("Selected access point BSSID")
            os.write(master, b"\n")
            await_text("Channel (0 means unset)")
            os.write(master, b"\n")
            await_text("Time limit in seconds")
            os.write(master, b"\x1560\n")
            await_text("Edit session scope")
            os.write(master, b"00\n")
            await_text("/ COMMAND CENTER")
            os.write(master, b"02\n")
            await_text("Restart selected adapter")
            os.write(master, b"06\n")
            await_text("Dependency status")
            os.write(master, b"02\n")
            await_text("Workflow results")
            os.write(master, b"\n")
            await_text("Restart selected adapter")
            os.write(master, b"00\n")
            await_text("/ COMMAND CENTER")
            os.write(master, b"00\n")
            proc.wait(timeout=5)
            self.assertEqual(proc.returncode, 0)
            session_file = next(self.home.glob("*/session.json"))
            scope = json.loads(session_file.read_text())["scope"]
            self.assertEqual(scope["interface"], "wlan1mon")
            self.assertEqual(scope["duration"], 60)
            self.assertEqual(len(json.loads(session_file.read_text())["records"]), 5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            os.close(master)


if __name__ == "__main__":
    unittest.main()
