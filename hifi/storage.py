from pathlib import Path
import json
import os
import tempfile

from .models import Session


def default_home():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "d3faulth-hifi"


class Store:
    def __init__(self, home=None):
        self.home = Path(home or default_home()).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)

    def folder(self, session):
        # Validate identifiers even when callers instantiate Session themselves.
        Session.from_dict(session.to_dict())
        path = self.home / session.id
        path.mkdir(exist_ok=True, mode=0o700)
        return path

    def save(self, session):
        folder = self.folder(session)
        fd, name = tempfile.mkstemp(prefix=".session-", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(session.to_dict(), out, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, folder / "session.json")
        finally:
            Path(name).unlink(missing_ok=True)

    def load(self, identifier):
        import re
        if not re.fullmatch(r"[a-f0-9]{12}", identifier):
            raise ValueError("Use a session ID from the session list.")
        path = self.home / identifier / "session.json"
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Session is too large to load.")
        session = Session.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if session.id != identifier:
            raise ValueError("Session ID does not match its directory.")
        return session

    def list(self):
        rows = []
        for path in self.home.glob("*/session.json"):
            try:
                s = self.load(path.parent.name)
                rows.append((s.id, s.created, s.demo, len(s.records)))
            except (OSError, ValueError, TypeError, KeyError):
                continue
        return sorted(rows, key=lambda r: r[1], reverse=True)
