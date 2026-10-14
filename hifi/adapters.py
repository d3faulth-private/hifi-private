"""Selected-device recovery. No scans, service-wide restarts or automatic sudo."""
from dataclasses import dataclass
import json
import os
import re
import shlex
import subprocess
from threading import Event

from .access import require_root
from .models import Command, Scope, clean, now
from .runner import run


@dataclass(frozen=True)
class Adapter:
    name: str
    mode: str = "unknown"
    phy: str = "unknown"


def parse_interfaces(output):
    result, current, phy = [], None, "unknown"
    for line in output.splitlines():
        line = line.strip()
        if re.fullmatch(r"phy#\d+", line):
            phy = line.replace("#", "")
        elif line.startswith("Interface "):
            name = line.split(None, 1)[1]
            Scope(interface=name).validate()
            current = Adapter(name, phy=phy)
            result.append(current)
        elif line.startswith("type ") and current:
            current = Adapter(current.name, line.split(None, 1)[1], current.phy)
            result[-1] = current
    return result


def discover(demo=False):
    if demo:
        return [Adapter("wlan0mon", "monitor", "phy0")]
    try:
        result = subprocess.run(["iw", "dev"], capture_output=True, text=True,
                                timeout=5, env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError as exc:
        raise ValueError("Adapter discovery needs iw. Install it with: sudo apt install iw") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Adapter discovery timed out. Check the USB connection and driver.") from exc
    if result.returncode:
        raise ValueError("Could not read wireless interfaces: " + clean(result.stderr).strip())
    return parse_interfaces(result.stdout)


def restart_plan(interface, restore_managed=False):
    Scope(interface=interface).validate()
    if not interface:
        raise ValueError("Select a wireless adapter first.")
    purpose = "Temporarily interrupt this adapter's connection."
    effect = "LOCAL ADAPTER / CONNECTION INTERRUPTION"
    commands = [Command("Bring adapter down", ["ip", "link", "set", "dev", interface, "down"], purpose, effect, root=True)]
    if restore_managed:
        commands.append(Command("Restore managed mode", ["iw", "dev", interface, "set", "type", "managed"], purpose, effect, root=True))
    commands.append(Command("Bring adapter up", ["ip", "link", "set", "dev", interface, "up"], purpose, effect, root=True))
    commands.append(Command("Verify adapter mode", ["iw", "dev", interface, "info"], "Read the resulting wireless mode."))
    commands.append(Command("Verify link state", ["ip", "-j", "link", "show", "dev", interface], "Check the administrative UP flag."))
    return commands


def restart(interface, cwd, restore_managed=False, demo=False, stop=None, emit=None):
    commands = restart_plan(interface, restore_managed)
    require_root(demo)
    stop, emit = stop or Event(), emit or (lambda _: None)
    selected = next((a for a in discover(demo) if a.name == interface), None)
    if selected is None:
        raise ValueError(f"Wireless adapter {interface} is no longer present. Refresh the adapter list.")
    if restore_managed and selected.mode not in {"managed", "monitor"}:
        raise ValueError("Restore mode is available for managed/monitor interfaces only.")
    argv = ["hifi", "adapter", "restart", "--interface", interface]
    if restore_managed:
        argv.append("--restore-managed")
    record = {"title": "Restore normal Wi-Fi" if restore_managed else "Restart network adapter",
              "argv": argv, "effect": commands[0].effect, "started": now(),
              "status": "simulated" if demo else "ok", "returncode": 0, "elapsed": 0, "output": "", "steps": []}
    if demo:
        record["output"] = "[DEMO: NO COMMAND EXECUTED]\n" + "\n".join(shlex.join(c.argv) for c in commands)
        return record
    if stop.is_set():
        record.update(status="cancelled", returncode=None, output="Cancelled before adapter changes.")
        return record

    def execute(command, cancellation=stop):
        emit("$ " + shlex.join(command.argv) + "\n")
        row = run(command, cwd, cancellation, emit)
        record["steps"].append(row)
        record["elapsed"] += row.get("elapsed", 0)
        if row["status"] != "ok" and record["status"] == "ok":
            record.update(status=row["status"], returncode=row["returncode"])
        return row

    # Always attempt link-up once link-down has been attempted, even if a
    # cancellation or driver error leaves an uncertain intermediate state.
    up_index = 2 if restore_managed else 1
    try:
        down = execute(commands[0])
        if restore_managed and down["status"] == "ok" and not stop.is_set():
            execute(commands[1])
    finally:
        execute(commands[up_index], Event())
    if stop.is_set() and record["status"] == "ok":
        record.update(status="cancelled", returncode=None)
    mode = execute(commands[-2], Event())
    state = execute(commands[-1], Event())
    mode_match = re.search(r"^\s*type\s+(\S+)", mode["output"], re.MULTILINE)
    wanted_mode = "managed" if restore_managed else selected.mode
    try:
        links = json.loads(state["output"])
        up = any(x.get("ifname") == interface and "UP" in x.get("flags", []) for x in links)
    except (ValueError, TypeError, AttributeError):
        up = False
    verified = bool(mode_match and mode_match[1] == wanted_mode and up)
    if not verified and record["status"] == "ok":
        record.update(status="failed", returncode=1)
    lines = [f"$ {shlex.join(s['argv'])}\n[{s['status']}] {s['output']}" for s in record["steps"]]
    lines.append("Verified: interface is UP in " + wanted_mode + " mode." if verified else "Adapter state could not be verified. Review the command output above.")
    lines.append("Link UP does not verify an internet connection. Use your network menu to reconnect.\n"
                 "No NetworkManager service or other adapter was restarted.")
    record["output"] = "\n\n".join(lines)
    return record
