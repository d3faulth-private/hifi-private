from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(text):
    """Render external output as text, never as terminal control sequences."""
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", str(text))
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(c for c in text if c in "\n\t" or (c.isprintable() and c != "\x1b"))


@dataclass
class Scope:
    interface: str = ""
    bssid: str = ""
    channel: int = 0
    duration: int = 60

    def validate(self, target=False):
        if self.interface and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}", self.interface):
            raise ValueError("Interface must be a Linux interface name, at most 15 characters.")
        if self.bssid:
            if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", self.bssid):
                raise ValueError("BSSID must look like 02:11:22:33:44:55.")
            if int(self.bssid[:2], 16) & 1 or self.bssid.lower() == "00:00:00:00:00:00":
                raise ValueError("Select an individual access point's unicast BSSID.")
            self.bssid = self.bssid.lower()
        if not 0 <= self.channel <= 233:
            raise ValueError("Channel must be between 1 and 233 (0 means unset).")
        if not 5 <= self.duration <= 3600:
            raise ValueError("Duration must be between 5 and 3600 seconds.")
        if target and not (self.interface and self.bssid and self.channel):
            raise ValueError("Set interface, BSSID, and channel first.")
        return self


@dataclass
class Command:
    title: str
    argv: list[str]
    purpose: str
    effect: str = "READ ONLY"
    timeout: int | None = 20
    root: bool = False
    interactive: bool = False
    cwd: str | None = None


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: str = field(default_factory=now)
    scope: Scope = field(default_factory=Scope)
    demo: bool = False
    records: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    engine_args: list[str] = field(default_factory=list)
    engine_workdir: str = ""

    def to_dict(self):
        return {"schema": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if data.get("schema") != 1:
            raise ValueError("Unsupported session schema.")
        if not re.fullmatch(r"[a-f0-9]{12}", data.get("id", "")):
            raise ValueError("Invalid session identifier.")
        scope = Scope(**data["scope"]).validate()
        return cls(id=data["id"], created=data["created"], scope=scope,
                   demo=bool(data.get("demo")), records=data.get("records", []),
                   notes=data.get("notes", []), engine_args=data.get("engine_args", data.get("wifite_args", [])),
                   engine_workdir=data.get("engine_workdir", data.get("wifite_workdir", "")))
