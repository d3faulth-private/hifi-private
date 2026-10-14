"""Bounded subprocess execution with no shell and whole-process-group cleanup."""
from collections import deque
import os
import selectors
import signal
import subprocess
import time
from threading import Event

from .models import clean, now

OUTPUT_LIMIT = 512 * 1024


def _signal_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def run(command, cwd, stop=None, emit=None):
    stop = stop or Event()
    emit = emit or (lambda text: None)
    started = time.monotonic()
    record = {"title": command.title, "argv": command.argv, "effect": command.effect,
              "started": now(), "status": "error", "returncode": None, "output": ""}
    if command.root and os.geteuid() != 0:
        record["output"] = "This radio operation needs root. Relaunch HIFI with sudo using its full Python path; see README."
        record["elapsed"] = 0
        return record
    proc = None
    chunks = deque()
    kept = 0
    truncated = False
    selector = selectors.DefaultSelector()
    try:
        proc = subprocess.Popen(command.argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True, env={**os.environ, "LC_ALL": "C", "TERM": "dumb"})
        os.set_blocking(proc.stdout.fileno(), False)
        selector.register(proc.stdout, selectors.EVENT_READ)
        reason = None
        signal_at = None
        stage = 0
        while selector.get_map() or proc.poll() is None:
            elapsed = time.monotonic() - started
            if reason is None and (stop.is_set() or elapsed >= command.timeout):
                reason = "cancelled" if stop.is_set() else "timeout"
                _signal_group(proc, signal.SIGINT)
                signal_at = time.monotonic()
            if reason and time.monotonic() - signal_at > 1.0 and stage == 0:
                _signal_group(proc, signal.SIGTERM)
                stage = 1
            if reason and time.monotonic() - signal_at > 2.0 and stage == 1:
                _signal_group(proc, signal.SIGKILL)
                stage = 2
            for key, _ in selector.select(0.1):
                data = os.read(key.fd, 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                value = clean(data.decode("utf-8", errors="replace"))
                chunks.append(value)
                kept += len(value)
                while kept > OUTPUT_LIMIT and chunks:
                    kept -= len(chunks.popleft())
                    truncated = True
                emit(value)
            if reason and stage == 2 and time.monotonic() - signal_at > 3:
                break
        code = proc.wait(timeout=2)
        record.update(returncode=code, status=reason or ("ok" if code == 0 else "failed"))
    except (OSError, subprocess.SubprocessError) as exc:
        chunks.append(str(exc))
    finally:
        if proc is not None:
            # Also clean up descendants if the direct child exits before them.
            _signal_group(proc, signal.SIGKILL)
            proc.wait()
            proc.stdout.close()
        selector.close()
    record["elapsed"] = round(time.monotonic() - started, 2)
    record["output"] = ("[Earlier output truncated]\n" if truncated else "") + "".join(chunks)
    return record
