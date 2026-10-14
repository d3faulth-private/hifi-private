"""Selected-adapter ownership, mode preparation and verified restoration."""
from dataclasses import asdict, dataclass
from pathlib import Path
import fcntl
import json
import os
import re
import shutil
import subprocess
from threading import Event

from . import adapters
from .access import require_root
from .models import Command, Scope, clean
from .runner import run

LOCK_ROOT = Path("/run/lock")


def read(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=8,
                                env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError as exc:
        raise ValueError(f"Missing {argv[0]}. Open Settings & Help > Dependencies.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{argv[0]} did not respond within 8 seconds. Check the USB adapter and driver.") from exc
    if result.returncode:
        raise ValueError(clean(result.stderr or result.stdout).strip() or f"{argv[0]} failed")
    return result.stdout


@dataclass
class State:
    interface: str
    phy: str
    mode: str
    up: bool
    channel: int = 0
    managed: str = ""


def snapshot(interface):
    Scope(interface=interface).validate()
    selected = next((a for a in adapters.discover() if a.name == interface), None)
    if selected is None:
        raise ValueError(f"Wireless interface {interface} is no longer present. Refresh adapters.")
    info = read(["iw", "dev", interface, "info"])
    links = json.loads(read(["ip", "-j", "link", "show", "dev", interface]))
    channel = re.search(r"\bchannel\s+(\d+)", info)
    managed = ""
    if shutil.which("nmcli"):
        try:
            value = read(["nmcli", "-g", "GENERAL.NM-MANAGED", "device", "show", interface]).strip()
            managed = value if value in {"yes", "no"} else ""
        except ValueError:
            pass  # NetworkManager may not own this adapter or be running.
    return State(interface, selected.phy, selected.mode,
                 any(x.get("ifname") == interface and "UP" in x.get("flags", []) for x in links),
                 int(channel[1]) if channel else 0, managed)


class Radio:
    """A lease lasts for one operation. Only the selected phy is changed.

    Kernel flock prevents two HIFI processes using the same phy. A journal
    survives crashes; normal completion/cancellation restores in __exit__.
    """
    def __init__(self, interface, cwd, stop=None, emit=None, demo=False):
        self.interface, self.cwd = interface, Path(cwd)
        self.stop, self.emit = stop or Event(), emit or (lambda _: None)
        self.demo = demo
        self.original = None
        self.steps, self.restore_errors = [], []
        self.lock = None
        self.changed = False
        self.journal = self.cwd / "adapter-recovery.json"

    def __enter__(self):
        require_root(self.demo)
        if self.demo:
            self.original = State(self.interface, "phy-demo", "monitor", True, 6)
            return self
        self.original = snapshot(self.interface)
        if self.original.mode not in {"managed", "monitor"}:
            raise ValueError("Choose a managed or monitor interface. AP/mesh interfaces are not modified.")
        if not re.fullmatch(r"phy\d+", self.original.phy):
            raise ValueError("Cannot identify the physical wireless adapter.")
        path = LOCK_ROOT / ("d3faulth-hifi-" + self.original.phy + ".lock")
        self.lock = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.lock)
            self.lock = None
            raise ValueError("Another HIFI operation owns this adapter. Stop it before continuing.") from exc
        return self

    def execute(self, argv, recovery=False):
        if self.demo:
            self.emit("[DEMO] " + " ".join(argv) + "\n")
            return
        if self.stop.is_set() and not recovery:
            raise InterruptedError("Cancelled before the next adapter change.")
        command = Command("Adapter state", argv, "Selected adapter only", "LOCAL ADAPTER", timeout=12, root=True)
        record = run(command, self.cwd, Event() if recovery else self.stop, self.emit)
        self.steps.append(record)
        if record["status"] != "ok":
            raise ValueError("Adapter command failed: " + " ".join(argv) + "\n" + record["output"])

    def identify(self):
        if self.demo:
            return
        rows = [a for a in adapters.discover() if a.phy == self.original.phy]
        same = next((a for a in rows if a.name == self.interface), None)
        if same:
            return
        if len(rows) == 1:
            self.interface = rows[0].name
        else:
            raise ValueError("Adapter disappeared or its interface identity became ambiguous.")

    def monitor(self, channel=0):
        if not self.original:
            raise ValueError("Acquire the adapter before preparing it.")
        if not self.demo:
            self.journal.write_text(json.dumps(asdict(self.original), indent=2))
            self.journal.chmod(0o600)
        self.changed = True
        if self.original.managed == "yes":
            self.execute(["nmcli", "device", "set", self.interface, "managed", "no"])
        if self.original.mode != "monitor":
            self.execute(["ip", "link", "set", "dev", self.interface, "down"])
            self.execute(["iw", "dev", self.interface, "set", "type", "monitor"])
            self.identify()
        self.execute(["ip", "link", "set", "dev", self.interface, "up"])
        if channel:
            self.execute(["iw", "dev", self.interface, "set", "channel", str(channel)])
        if not self.demo:
            current = snapshot(self.interface)
            if current.mode != "monitor" or not current.up or (channel and current.channel != channel):
                raise ValueError("Driver did not enter the requested monitor mode/channel.")
        self.emit(f"Adapter ready: {self.interface} / monitor / channel {channel or 'hopping'}\n")

    def restore(self):
        if not self.changed:
            return
        try:
            self.identify()
        except (ValueError, OSError) as exc:
            self.restore_errors.append(str(exc))
            return
        state = self.original
        commands = [["ip", "link", "set", "dev", self.interface, "down"],
                    ["iw", "dev", self.interface, "set", "type", state.mode]]
        if state.mode == "monitor" and state.channel:
            commands += [["iw", "dev", self.interface, "set", "channel", str(state.channel)]]
        commands += [["ip", "link", "set", "dev", self.interface, "up" if state.up else "down"]]
        if state.managed:
            commands += [["nmcli", "device", "set", self.interface, "managed", state.managed]]
        for argv in commands:
            try:
                self.execute(argv, recovery=True)
            except (OSError, ValueError) as exc:
                self.restore_errors.append(str(exc))
        if not self.demo:
            try:
                final = snapshot(self.interface)
                if (final.mode != state.mode or final.up != state.up
                        or (state.mode == "monitor" and state.channel and final.channel != state.channel)
                        or (state.managed and final.managed != state.managed)):
                    self.restore_errors.append("Final adapter state does not match its saved state.")
            except (OSError, ValueError) as exc:
                self.restore_errors.append(str(exc))
        if self.restore_errors:
            self.emit("RESTORATION INCOMPLETE: " + "; ".join(self.restore_errors) + "\n")
        else:
            self.journal.unlink(missing_ok=True)
            self.emit("Restored previous adapter mode, link state and NetworkManager ownership.\n")

    def __exit__(self, *_):
        try:
            self.restore()
        finally:
            if self.lock is not None:
                os.close(self.lock)
                self.lock = None
