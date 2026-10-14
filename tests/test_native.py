"""Exercise the actual PTY relay using a local fixture; no radio operations."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import patch

from hifi import catalog
from hifi.app import App
from hifi.demo import create_demo
from hifi.models import Session
from hifi.reports import report_data
from hifi.storage import Store

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = '''import json, os, signal, subprocess, sys, time
from pathlib import Path
print("FIXTURE_ARGS=" + json.dumps(sys.argv[1:]), flush=True)
print("FIXTURE_CWD=" + os.getcwd(), flush=True)
print("FIXTURE_TTY=" + str(os.isatty(0) and os.isatty(1)), flush=True)
def size(*_):
    s = os.get_terminal_size()
    print("FIXTURE_SIZE=%sx%s" % (s.columns, s.lines), flush=True)
signal.signal(signal.SIGWINCH, size)
signal.signal(signal.SIGINT, lambda *_: print("FIXTURE_INTERRUPT_MENU", flush=True))
size()
if "--fail" in sys.argv:
    print("\\x1b[31mFIXTURE_FAILED\\x1b[0m", flush=True)
    sys.exit(7)
if "--child" in sys.argv:
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path("child.pid").write_text(str(p.pid))
if "--flood" in sys.argv:
    print("x" * 700000, flush=True)
print("FIXTURE_READY", flush=True)
answer = input("Select target: ")
Path("native-artifact.txt").write_text(answer)
print("FIXTURE_SELECTED=" + answer, flush=True)
'''


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.home = self.path / "state"
        self.workspace = self.path / "native workspace"
        self.workspace.mkdir()
        self.bin = self.path / "bin"
        self.bin.mkdir()
        fake = self.bin / "engine"
        fake.write_text(f"#!{sys.executable}\n" + FIXTURE)
        fake.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""), "TERM": "xterm"}
        self.proc = None
        self.master = self.slave = None
        self.output = bytearray()
        self.cursor = 0

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for fd in [self.master, self.slave]:
            if fd is not None:
                os.close(fd)
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "hifi", "--home", str(self.home), *args],
                              cwd=ROOT, capture_output=True, text=True, env=self.env, timeout=5)

    def launch(self, *args):
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
        self.original_termios = termios.tcgetattr(self.slave)
        fixture_launcher = ("import sys; from hifi import app,cli; app.access.is_root=lambda: True; "
                            "app.engine_argv=lambda args: [sys.executable, " + repr(str(self.bin / "engine")) + ", *args]; "
                            "raise SystemExit(cli.main(sys.argv[1:]))")
        self.proc = subprocess.Popen([sys.executable, "-c", fixture_launcher, "--home", str(self.home), *args],
                                     cwd=ROOT, stdin=self.slave, stdout=self.slave, stderr=self.slave, env=self.env)

    def await_text(self, text, timeout=5):
        wanted = text.encode()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            index = self.output.find(wanted, self.cursor)
            if index >= 0:
                self.cursor = index + len(wanted)
                return
            ready, _, _ = select.select([self.master], [], [], 0.05)
            if ready:
                self.output.extend(os.read(self.master, 65536))
            elif self.proc.poll() is not None:
                break
        self.fail(f"Missing {text!r}: {bytes(self.output)[-2000:]!r}")

    def session(self):
        return json.loads(next(self.home.glob("*/session.json")).read_text())

    def test_full_options_are_passed_unchanged_and_capture_profiles_stay_scoped(self):
        options = ["--wps-only", "--pmkid", "--wep", "--dict", "/path with spaces/words", "--future-option=value"]
        command = catalog.engine_exploit(options, self.workspace)
        edited = catalog.validate_edit(shlex.join(command.argv), command, Session().scope)
        self.assertEqual(edited.argv, ["hifi", "engine", *options])
        self.assertIsNone(edited.timeout)
        self.assertTrue(edited.interactive)
        for text in ["sh -c id", "hifi engine ; id", "hifi engine --help\nanything"]:
            with self.assertRaises(ValueError):
                catalog.validate_edit(text, command, Session().scope)
        self.assertEqual(catalog.engine_exploit([], self.workspace).argv, ["hifi", "engine"])

    def test_cli_preview_demo_resume_reset_and_summary_privacy(self):
        preview = self.cli("exploit", "--workdir", str(self.workspace), "--", "--wps-only", "--dict", "/private/word list")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("Preview only", preview.stdout)
        self.assertNotIn("FIXTURE", preview.stdout)
        self.assertEqual(self.session()["records"], [])
        demo = self.cli("--demo", "exploit", "--workdir", str(self.workspace), "--run", "--", "--wps-only")
        self.assertEqual(demo.returncode, 0, demo.stderr)
        sessions = [json.loads(p.read_text()) for p in self.home.glob("*/session.json")]
        data = next(s for s in sessions if s["demo"])
        self.assertEqual(data["engine_args"], ["--wps-only"])
        self.assertEqual(data["engine_workdir"], str(self.workspace))
        resumed = self.cli("--session", data["id"], "exploit")
        self.assertIn("hifi engine --wps-only", resumed.stdout)
        fresh = self.cli("--session", data["id"], "exploit", "--fresh", "--run")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        stored = Store(self.home).load(data["id"])
        self.assertEqual(stored.engine_args, [])
        summary = json.dumps(report_data(stored))
        self.assertNotIn(str(self.workspace), summary)
        self.assertNotIn("--wps-only", summary)
        self.assertIn(str(self.workspace), json.dumps(report_data(stored, True)))

    def test_native_demo_never_forks(self):
        app = App(Store(self.home), create_demo())
        with patch("hifi.app.run_interactive", side_effect=AssertionError("must not launch")):
            record = app.execute(app.native_engine(["--wps-only"]))
        self.assertEqual(record["status"], "simulated")

    def test_native_run_rejects_redirected_terminal(self):
        result = self.cli("exploit", "--run", "--", "--help")
        self.assertEqual(result.returncode, 1)
        self.assertIn("needs an interactive terminal", result.stdout)
        self.assertEqual(self.session()["records"][0]["status"], "error")

    def test_real_pty_input_interrupt_resize_and_saved_artifact(self):
        args = ["--dict", "/private/word list", "--future-native-option"]
        self.launch("exploit", "--workdir", str(self.workspace), "--run", "--", *args)
        self.await_text("FIXTURE_READY")
        self.assertIn(b"FIXTURE_TTY=True", self.output)
        self.assertIn(b"FIXTURE_SIZE=120x30", self.output)
        self.assertIn(("FIXTURE_ARGS=" + json.dumps(args)).encode(), self.output)
        os.write(self.master, b"\x03")
        self.await_text("FIXTURE_INTERRUPT_MENU")
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 100, 0, 0))
        self.proc.send_signal(signal.SIGWINCH)
        self.await_text("FIXTURE_SIZE=100x36")
        os.write(self.master, b"selected-lab\n")
        self.await_text("Result: ok")
        self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode, 0)
        self.assertEqual(termios.tcgetattr(self.slave), self.original_termios)
        artifact = self.workspace / "native-artifact.txt"
        self.assertEqual(artifact.read_text(), "selected-lab")
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        record = self.session()["records"][0]
        self.assertEqual(record["argv"], ["hifi", "engine", *args])
        self.assertEqual(record["cwd"], str(self.workspace))
        self.assertIn("FIXTURE_SELECTED=selected-lab", record["output"])

    def test_nonzero_exit_restores_terminal_and_sanitizes_output(self):
        self.launch("exploit", "--run", "--", "--fail")
        self.await_text("Result: failed")
        self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode, 1)
        self.assertEqual(termios.tcgetattr(self.slave), self.original_termios)
        record = self.session()["records"][0]
        self.assertEqual(record["returncode"], 7)
        self.assertIn("FIXTURE_FAILED", record["output"])
        self.assertNotIn("\x1b", record["output"])

    def test_parent_termination_saves_cancellation_and_cleans_descendants(self):
        self.launch("exploit", "--workdir", str(self.workspace), "--run", "--", "--child")
        self.await_text("FIXTURE_READY")
        child = int((self.workspace / "child.pid").read_text())
        self.proc.terminate()
        self.await_text("Result: cancelled")
        self.proc.wait(timeout=5)
        self.assertEqual(self.session()["records"][0]["status"], "cancelled")
        self.assertEqual(termios.tcgetattr(self.slave), self.original_termios)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                state = Path(f"/proc/{child}/stat").read_text().split()[2]
            except (FileNotFoundError, ProcessLookupError):
                return
            if state == "Z":
                return
            time.sleep(0.01)
        self.fail("Native descendant is still running")

    def test_native_output_tail_is_bounded(self):
        self.launch("exploit", "--run", "--", "--flood")
        self.await_text("FIXTURE_READY")
        os.write(self.master, b"done\n")
        self.await_text("Result: ok")
        self.proc.wait(timeout=5)
        record = self.session()["records"][0]
        self.assertLess(len(record["output"]), 512 * 1024 + 100)
        self.assertIn("Earlier output truncated", record["output"])

    def test_curses_handoff_returns_to_menu(self):
        self.launch("tui")
        self.await_text("/ COMMAND CENTER")
        os.write(self.master, b"04\n")
        self.await_text("Full HIFI Exploit / all bundled features")
        os.write(self.master, b"\n")
        self.await_text("Run command")
        os.write(self.master, b"\n")
        self.await_text("Command preview / ENTER run, ESC cancel")
        os.write(self.master, b"\n")
        self.await_text("FIXTURE_READY")
        os.write(self.master, b"lab\n")
        self.await_text("FIXTURE_SELECTED=lab")
        self.await_text("UP/DOWN scroll")
        os.write(self.master, b"\n")
        self.await_text("Full HIFI Exploit / all bundled features")
        os.write(self.master, b"q")
        self.await_text("/ COMMAND CENTER")
        os.write(self.master, b"q")
        self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode, 0)
        self.assertEqual(self.session()["records"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
