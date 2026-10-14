"""Live discovery from airodump CSV, independent of the legacy controller."""
import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import shutil
from threading import Event, Lock
import time

from .models import Command, Scope, clean, now
from .radio import Radio
from .runner import run

MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\Z")


def number(value, default=0):
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


@dataclass
class Network:
    bssid: str
    ssid: str = ""
    channel: int = 0
    signal: int | None = None
    security: str = "Unknown"
    cipher: str = ""
    authentication: str = ""
    last_seen: str = ""
    beacons: int = 0
    packets: int = 0
    wps: str = "Unknown"
    clients: list[str] = field(default_factory=list)

    @property
    def name(self):
        return self.ssid or "[Hidden]"

    @property
    def frequency(self):
        if self.channel == 14:
            return 2484
        if 1 <= self.channel <= 13:
            return 2407 + self.channel * 5
        if 182 <= self.channel <= 196:
            return 4000 + self.channel * 5
        return 5000 + self.channel * 5 if 32 <= self.channel <= 177 else None


def parse_csv(text):
    """Ignore incomplete writes, preserve comma-containing SSIDs and negative RSSI."""
    networks, clients, section = {}, [], ""
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        head = row[0].strip()
        if head == "BSSID":
            section = "ap"
            continue
        if head == "Station MAC":
            section = "client"
            continue
        if not MAC.fullmatch(head):
            continue
        if section == "ap" and len(row) >= 14:
            channel = number(row[3])
            if not 1 <= channel <= 233:
                continue
            signal = number(row[8], -1)
            # Airodump's PWR is driver-reported RSSI; never convert it to a percentage.
            ssid = ",".join(row[13:-1] if len(row) > 14 else row[13:])
            if ssid.startswith(" "):
                ssid = ssid[1:]  # CSV delimiter padding; preserve actual SSID leading spaces.
            if number(row[12]) == 0 or ssid.startswith("<length:") or re.fullmatch(r"(?:\\x00)+", ssid):
                ssid = ""
            networks[head.lower()] = Network(head.lower(), clean(ssid), channel,
                None if signal == -1 else signal, clean(row[5].strip()) or "Unknown",
                clean(row[6].strip()), clean(row[7].strip()), clean(row[2].strip()),
                number(row[9]), number(row[10]))
        elif section == "client" and len(row) >= 6:
            clients.append({"mac": head.lower(), "bssid": row[5].strip().lower(),
                            "signal": number(row[3], -1), "packets": number(row[4]),
                            "last_seen": clean(row[2].strip()), "probes": clean(",".join(row[6:]).strip())})
    for client in clients:
        if client["bssid"] in networks:
            networks[client["bssid"]].clients.append(client["mac"])
    return list(networks.values()), clients


def scan_command(interface, prefix, seconds, band="abg"):
    Scope(interface=interface).validate()
    if not interface:
        raise ValueError("Select a detected adapter in Network Adapter first.")
    if band not in {"bg", "a", "abg"} or not 5 <= seconds <= 3600:
        raise ValueError("Choose 2.4 GHz, 5 GHz or both, and 5–3600 seconds.")
    return Command("Live network discovery", ["airodump-ng", "--band", band, "--write-interval", "1",
                   "--output-format", "csv", "--write", str(prefix), interface],
                   "Observe access points and clients using the selected adapter.",
                   "PASSIVE SCAN / TEMPORARY MONITOR MODE", timeout=seconds, root=True)


class Scan:
    def __init__(self, app, seconds=30, band="abg"):
        self.app, self.seconds, self.band = app, seconds, band
        self.networks, self.clients = {}, []
        self.lock, self.stop = Lock(), Event()
        self.message, self.record = "Preparing selected adapter…", None
        self.mode = "preparing"
        self.started = time.monotonic()

    def snapshot(self):
        with self.lock:
            return list(self.networks.values()), list(self.clients), self.message

    def update(self, text):
        networks, clients = parse_csv(text)
        with self.lock:
            for network in networks:
                previous = self.networks.get(network.bssid)
                if previous and not network.ssid:
                    network.ssid = previous.ssid
                self.networks[network.bssid] = network
            self.clients = clients
            self.message = f"{len(self.networks)} networks / {len(clients)} observed stations"

    def execute(self):
        app, scope = self.app, self.app.session.scope
        prefix = app.output_path("discovery")
        scan_command(scope.interface, prefix, self.seconds, self.band)
        if not app.session.demo and not shutil.which("airodump-ng"):
            raise ValueError("Missing airodump-ng. Install the aircrack-ng package, then run Discovery again.")
        record = {"title": "Live network discovery", "argv": [], "effect": "PASSIVE DISCOVERY", "started": now(),
                  "status": "error", "output": "", "returncode": None}
        radio = Radio(scope.interface, app.store.folder(app.session), self.stop,
                      lambda value: setattr(self, "message", clean(value).strip()), app.session.demo)
        try:
            with radio:
                radio.monitor()
                self.mode = "monitor"
                scope.interface = radio.interface
                command = scan_command(scope.interface, prefix, self.seconds, self.band)
                if app.session.demo:
                    with self.lock:
                        self.networks = {n.bssid: n for n in [Network("02:11:22:33:44:55", "HIFI-LAB", 6, -42, "WPA2", "CCMP", "PSK", now()),
                            Network("02:11:22:33:44:66", "", 36, -67, "WPA2", "CCMP", "PSK", now())]}
                    record.update(argv=command.argv, status="simulated", output="Synthetic demo networks; no radio commands executed.")
                else:
                    csv_path = Path(str(prefix) + "-01.csv")
                    def tick():
                        if csv_path.exists():
                            if csv_path.stat().st_size > 16 * 1024 * 1024:
                                raise ValueError("Discovery CSV exceeded 16 MiB; stop and start a shorter scan.")
                            self.update(csv_path.read_text(encoding="utf-8", errors="replace"))
                    record = run(command, app.store.folder(app.session), self.stop, tick=tick)
                    tick()
                    if record["status"] == "timeout":
                        record["status"] = "ok"
                        record["output"] += "\nConfigured discovery window completed."
                    if record["status"] == "ok" and not csv_path.exists():
                        record.update(status="error", output=record["output"] + "\nNo discovery CSV was produced. Check adapter/driver output.")
        except InterruptedError as exc:
            record.update(status="cancelled", output=str(exc))
        except (ValueError, OSError, RuntimeError) as exc:
            record.update(status="error", output=record["output"] + "\n" + clean(exc))
        finally:
            scope.interface = radio.interface
            record["adapter_restoration"] = "incomplete" if radio.restore_errors else "restored" if radio.changed else "unchanged"
            self.mode = record["adapter_restoration"]
            record["steps"] = radio.steps
            if radio.restore_errors:
                record.update(status="error", output=record["output"] + "\n" + "\n".join(radio.restore_errors))
            rows, clients, _ = self.snapshot()
            if rows or record["status"] in {"ok", "simulated"}:
                app.session.networks = [asdict(n) for n in rows]
                app.session.clients = clients
            record["networks_observed"] = len(rows)
            record["elapsed"] = round(time.monotonic() - self.started, 2)
            app.session.records.append(record)
            app.store.save(app.session)
            self.record = record
        return record


def select(app, network):
    app.session.scope.bssid = network.bssid
    app.session.scope.channel = network.channel
    app.session.scope.validate(target=True)
    app.session.selected_network = asdict(network)
    app.store.save(app.session)
