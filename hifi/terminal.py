"""Native interactive terminal relay; HIFI retains its own prompts and timing."""
import errno
import fcntl
import os
import pty
import select
import shutil
import signal
import sys
import termios
import time
import tty

from .models import clean, now
from .runner import OUTPUT_LIMIT


class TerminalStopped(Exception):
    pass


def _signal(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def _write(fd, data):
    while data:
        count = os.write(fd, data)
        data = data[count:]


def run_interactive(command, cwd):
    """Run on the main thread. Ctrl+C goes to the child PTY, not HIFI's UI."""
    started = time.monotonic()
    record = {"title": command.title, "argv": command.argv, "effect": command.effect,
              "started": now(), "status": "error", "returncode": None, "output": "",
              "mode": "native-engine", "cwd": str(cwd)}
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        record.update(output="Full HIFI Exploit needs an interactive terminal. Preview without --run, or open HIFI in a terminal.", elapsed=0)
        return record
    if not shutil.which(command.argv[0]):
        record.update(output="HIFI engine runtime is missing. Reinstall this HIFI package.", elapsed=0)
        return record

    input_fd, output_fd = sys.stdin.fileno(), sys.stdout.fileno()
    attributes = termios.tcgetattr(input_fd)
    initial_size = fcntl.ioctl(input_fd, termios.TIOCGWINSZ, b"\0" * 8)
    saved_handlers = {}
    pid = master = status = None
    tail = bytearray()
    pending = bytearray()
    truncated = False
    error = ""
    child_exited_at = None

    def resize(*_):
        try:
            size = fcntl.ioctl(input_fd, termios.TIOCGWINSZ, b"\0" * 8)
            fcntl.ioctl(master, termios.TIOCSWINSZ, size)
        except OSError:
            pass

    def forward_interrupt(*_):
        _signal(pid, signal.SIGINT)

    def terminate(*_):
        raise TerminalStopped("HIFI terminal session interrupted.")

    try:
        sys.stdout.flush()
        sys.stderr.flush()
        pid, master = pty.fork()
        if pid == 0:
            try:
                os.umask(0o077)
                fcntl.ioctl(0, termios.TIOCSWINSZ, initial_size)
                os.chdir(cwd)
                os.execvpe(command.argv[0], command.argv, os.environ)
            except BaseException as exc:
                os.write(2, ("HIFI: " + clean(exc) + "\n").encode("utf-8", "replace"))
                os._exit(127)
        # PTY input preserves HIFI's target picker, Ctrl+C handling and prompts.
        os.set_blocking(master, False)
        for sig, handler in [(signal.SIGWINCH, resize), (signal.SIGINT, forward_interrupt),
                             (signal.SIGTERM, terminate), (signal.SIGHUP, terminate)]:
            saved_handlers[sig] = signal.signal(sig, handler)
        resize()
        tty.setraw(input_fd)
        while True:
            if status is None:
                found, value = os.waitpid(pid, os.WNOHANG)
                if found:
                    status, child_exited_at = value, time.monotonic()
            # Do not hang if an orphaned descendant keeps the slave PTY open.
            if child_exited_at is not None and time.monotonic() - child_exited_at > 0.2:
                break
            readers = [master]
            if status is None and len(pending) < 65536:
                readers.append(input_fd)
            ready, writable, _ = select.select(readers, [master] if pending else [], [], 0.1)
            if master in ready:
                try:
                    data = os.read(master, 8192)
                except OSError as exc:
                    if exc.errno == errno.EIO:  # Linux signals slave close this way.
                        break
                    raise
                if not data:
                    break
                tail.extend(data)
                if len(tail) > OUTPUT_LIMIT:
                    del tail[:-OUTPUT_LIMIT]
                    truncated = True
                _write(output_fd, data)
            if input_fd in ready:
                data = os.read(input_fd, 4096)
                if not data:
                    raise TerminalStopped("Terminal input closed.")
                pending.extend(data)
            if master in writable:
                try:
                    count = os.write(master, pending)
                    del pending[:count]
                except BlockingIOError:
                    pass
        # Closing the PTY can precede process exit by a few scheduler ticks.
        deadline = time.monotonic() + 1
        while status is None and time.monotonic() < deadline:
            found, value = os.waitpid(pid, os.WNOHANG)
            if found:
                status = value
            else:
                time.sleep(0.01)
        if status is None:
            raise TerminalStopped("HIFI closed its terminal without exiting.")
        code = os.waitstatus_to_exitcode(status)
        record.update(returncode=code, status="ok" if code == 0 else (
            "cancelled" if code in {-signal.SIGINT, -signal.SIGTERM, -signal.SIGHUP} else "failed"))
    except (TerminalStopped, KeyboardInterrupt) as exc:
        error = str(exc) or "Terminal session interrupted."
        record["status"] = "cancelled"
    except (OSError, ValueError) as exc:
        error = str(exc)
    finally:
        # Restore the user's terminal even after a launch/relay error.
        try:
            termios.tcsetattr(input_fd, termios.TCSADRAIN, attributes)
        except OSError:
            pass
        if pid:
            _signal(pid, signal.SIGTERM)
            if status is None:
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    found, value = os.waitpid(pid, os.WNOHANG)
                    if found:
                        status = value
                        break
                    time.sleep(0.01)
            _signal(pid, signal.SIGKILL)
            if status is None:
                _, status = os.waitpid(pid, 0)
            if record["returncode"] is None:
                record["returncode"] = os.waitstatus_to_exitcode(status)
        if master is not None:
            os.close(master)
        for sig, handler in saved_handlers.items():
            signal.signal(sig, handler)
    record["elapsed"] = round(time.monotonic() - started, 2)
    record["output"] = ("[Earlier output truncated]\n" if truncated else "") + clean(tail.decode("utf-8", "replace"))
    if error:
        record["output"] += "\nHIFI: " + clean(error)
    return record
