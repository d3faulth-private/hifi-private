"""A dependency-free curses terminal interface with editable command previews."""
import curses
import shlex
import textwrap
import threading
from collections import deque

from . import __version__, catalog
from .advisor import local_explanation, suggest, recommended_commands
from .demo import HELP
from .models import Scope, clean


class UI:
    def __init__(self, screen, app):
        self.screen, self.app = screen, app
        self.screen.keypad(True)
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            for i, fg in enumerate([curses.COLOR_GREEN, curses.COLOR_CYAN, curses.COLOR_WHITE, curses.COLOR_YELLOW], 1):
                curses.init_pair(i, fg, -1)

    def put(self, y, x, value, color=3, bold=False):
        h, w = self.screen.getmaxyx()
        if 0 <= y < h - 1 and 0 <= x < w - 1:
            attr = (curses.color_pair(color) if curses.has_colors() else 0) | (curses.A_BOLD if bold else 0)
            try:
                self.screen.addnstr(y, x, clean(value).replace("\n", " "), max(0, w - x - 2), attr)
            except curses.error:
                pass

    def frame(self, title, footer="UP/DOWN select   ENTER open   ESC back"):
        self.screen.erase()
        h, w = self.screen.getmaxyx()
        self.put(1, 3, "D3FAULTH  /  H I F I", 1, True)
        self.put(2, 3, f"WIRELESS WORKBENCH   v{__version__}   {'DEMO / SIMULATED' if self.app.session.demo else 'LIVE / LOCAL'}", 2)
        self.put(4, 3, title, 3, True)
        scope = self.app.session.scope
        self.put(h - 3, 3, f"{scope.interface or 'no interface'}  |  {scope.bssid or 'no BSSID'}  |  ch {scope.channel or '-'}  |  {scope.duration}s", 2)
        self.put(h - 2, 3, footer, 4)
        return h, w

    def menu(self, title, entries):
        selected = 0
        while True:
            h, w = self.frame(title)
            visible = max(1, h - 10)
            start = max(0, selected - visible + 1)
            for offset, label in enumerate(entries[start:start + visible]):
                i = start + offset
                self.put(6 + offset, 4, ("> " if i == selected else "  ") + label, 1 if i == selected else 3, i == selected)
            self.screen.refresh()
            key = self.screen.getch()
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(entries)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(entries)
            elif key in (10, 13, curses.KEY_ENTER):
                return selected
            elif key in (27, ord("q")):
                return None

    def view(self, title, value):
        offset = 0
        while True:
            h, w = self.frame(title, "UP/DOWN scroll   PgUp/PgDn page   ESC/ENTER back")
            lines = []
            for line in clean(value).expandtabs(4).splitlines():
                lines.extend(textwrap.wrap(line, max(12, w - 8), replace_whitespace=False) or [""])
            count = max(1, h - 10)
            offset = min(offset, max(0, len(lines) - count))
            for i, line in enumerate(lines[offset:offset + count]):
                self.put(6 + i, 4, line)
            self.screen.refresh()
            key = self.screen.getch()
            if key in (27, 10, 13, ord("q")):
                return key in (10, 13)
            if key in (curses.KEY_DOWN, ord("j")):
                offset += 1
            if key in (curses.KEY_UP, ord("k")):
                offset = max(0, offset - 1)
            if key == curses.KEY_NPAGE:
                offset += count
            if key == curses.KEY_PPAGE:
                offset = max(0, offset - count)

    def prompt(self, title, value=""):
        value = str(value)
        cursor = len(value)
        curses.curs_set(1)
        try:
            while True:
                h, w = self.frame(title, "Edit with arrows/Home/End   ENTER accept   ESC cancel")
                width = max(8, w - 10)
                start = max(0, cursor - width + 1)
                self.put(7, 4, value[start:start + width], 1)
                try:
                    self.screen.move(min(7, h - 2), min(4 + cursor - start, w - 2))
                except curses.error:
                    pass
                self.screen.refresh()
                key = self.screen.get_wch()
                if key in ("\n", "\r", curses.KEY_ENTER):
                    return value.strip()
                if key == "\x1b":
                    return None
                if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if cursor:
                        value = value[:cursor - 1] + value[cursor:]
                        cursor -= 1
                elif key == curses.KEY_DC:
                    value = value[:cursor] + value[cursor + 1:]
                elif key == curses.KEY_LEFT:
                    cursor = max(0, cursor - 1)
                elif key == curses.KEY_RIGHT:
                    cursor = min(len(value), cursor + 1)
                elif key in (curses.KEY_HOME, "\x01"):
                    cursor = 0
                elif key in (curses.KEY_END, "\x05"):
                    cursor = len(value)
                elif key == "\x15":
                    value, cursor = "", 0
                elif isinstance(key, str) and key.isprintable() and len(value) < 8192:
                    value = value[:cursor] + key + value[cursor:]
                    cursor += 1
        finally:
            curses.curs_set(0)

    def scope(self):
        previous = self.app.session.scope
        values = []
        for title, current in [("Wireless interface", previous.interface), ("Selected access point BSSID", previous.bssid),
                               ("Channel (0 means unset)", previous.channel), ("Time limit in seconds", previous.duration)]:
            answer = self.prompt(title, current)
            if answer is None:
                return
            values.append(answer)
        self.app.session.scope = Scope(values[0], values[1], int(values[2]), int(values[3])).validate()
        self.app.store.save(self.app.session)

    def background(self, title, action, cancellable=True):
        stop = threading.Event()
        output = deque(maxlen=240)
        result, errors = [], []
        def emit(value):
            output.extend(clean(value).splitlines())
        def target():
            try:
                result.append(action(stop, emit))
            except Exception as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=target, daemon=False)
        thread.start()
        self.screen.timeout(100)
        try:
            while thread.is_alive():
                h, w = self.frame(title, "ESC stops the running command and its children" if cancellable else "Waiting for local model / network timeout 45 seconds")
                self.put(6, 4, "STOPPING..." if stop.is_set() else "RUNNING...", 4)
                for i, line in enumerate(list(output)[-max(1, h - 12):]):
                    self.put(8 + i, 4, line)
                self.screen.refresh()
                if self.screen.getch() == 27 and cancellable:
                    stop.set()
        finally:
            stop.set()
            thread.join()
            self.screen.timeout(-1)
        if errors:
            raise ValueError(errors[0])
        return result[0] if result else None

    def command(self, command):
        while True:
            timing = "Native HIFI timing; no HIFI timeout" if command.interactive else f"Timeout: {command.timeout}s"
            location = f"\n\nWorking directory: {command.cwd}" if command.interactive else ""
            choice = self.menu(command.title, ["Run command", "Edit command", "Purpose, effect and command", "Back"])
            if choice in (None, 3):
                return
            if choice == 2:
                self.view(command.title, f"{command.effect}\n\n{command.purpose}\n\n{timing}{location}\n\n{shlex.join(command.argv)}")
            elif choice == 1:
                edited = self.prompt("Edit native HIFI options" if command.interactive else "Edit command (profile and scope stay enforced)", shlex.join(command.argv))
                if edited is not None:
                    try:
                        command = catalog.validate_edit(edited, command, self.app.session.scope)
                    except ValueError as exc:
                        self.view("Command needs adjustment", str(exc))
            elif choice == 0:
                # Preview is part of manual operation, not a repeated approval gate.
                if not self.view("Command preview / ENTER run, ESC cancel", f"{command.effect}\n\n{command.purpose}{location}\n\n{shlex.join(command.argv)}\n\n{timing}\nENTER starts the command. ESC cancels this preview."):
                    continue
                if command.interactive:
                    curses.def_prog_mode()
                    curses.endwin()
                    try:
                        record = self.app.execute(command)
                    finally:
                        curses.reset_prog_mode()
                        self.screen.clearok(True)
                        self.screen.refresh()
                else:
                    record = self.background(command.title, lambda stop, emit: self.app.execute(command, stop, emit))
                self.view(record["status"].upper(), record["output"] or "No output. See exit status in session history.")
                return

    def engine(self):
        while True:
            mode = self.menu("HIFI Exploit", ["Full HIFI Exploit / all bundled features",
                             "HIFI engine help / all options", "HIFI working directory",
                             "Reset saved HIFI arguments", "Passive capture only / interface changes",
                             "Active capture only / may disconnect clients", "Inspect selected interface", "Back"])
            if mode in (None, 7):
                return
            if mode == 0:
                self.command(self.app.native_engine())
            elif mode == 1:
                text = HELP + "\n[Demo placeholder. Live mode reads the bundled engine help.]" if self.app.session.demo else catalog.engine_help()
                self.view("HIFI engine options", text)
            elif mode == 2:
                command = self.app.native_engine()
                directory = self.prompt("HIFI working directory (relative file paths resolve here)", command.cwd)
                if directory:
                    checked = self.app.native_engine(workdir=directory)
                    self.app.session.engine_workdir = checked.cwd
                    self.app.store.save(self.app.session)
            elif mode == 3:
                self.app.session.engine_args = []
                self.app.store.save(self.app.session)
                self.view("HIFI defaults restored", "The next Full HIFI Exploit starts with no extra arguments.")
            elif mode == 6:
                self.command(catalog.interface_info(self.app.session.scope))
            else:
                self.command(catalog.engine_capture(self.app.session.scope, HELP if self.app.session.demo else None, active=mode == 5))

    def capture_inspection(self):
        path = self.prompt("Capture file path (.cap / .pcap / .pcapng)")
        if not path:
            return
        while True:
            choice = self.menu("Capture inspector", ["File metadata", "EAPOL frame view", "Disconnect frame view", "Run all three views", "Offline wordlist Exploit", "Back"])
            if choice in (None, 5):
                return
            if choice < 3:
                self.command(catalog.inspect_capture(path, ["metadata", "eapol", "management"][choice]))
            elif choice == 3:
                commands = [catalog.inspect_capture(path, k) for k in ["metadata", "eapol", "management"]]
                rows = self.background("Automatic capture inspection", lambda stop, emit: self.app.workflow(commands, stop, emit))
                self.view("Workflow results", "\n".join(f"{r['title']}: {r['status']}" for r in rows))
            else:
                words = self.prompt("Local wordlist file path")
                if words:
                    self.command(catalog.offline_audit(self.app.session.scope, path, words))

    def history(self):
        rows = list(reversed(self.app.session.records))
        if not rows:
            self.view("Session history", "No commands have run in this session.")
            return
        choice = self.menu("Session history", [f"{r['status']:10} {r['title']}" for r in rows])
        if choice is not None:
            r = rows[choice]
            directory = f"\nWorking directory: {r['cwd']}" if r.get("cwd") else ""
            self.view(r["title"], f"{r['started']}{directory}\n{shlex.join(r['argv'])}\n\n{r['output']}")

    def main(self):
        entries = ["Session scope / interface / BSSID", "Adapter diagnostics", "Cached network list",
                   "Guided next steps", "Capture inspector", "Passive capture (existing monitor interface)",
                   "HIFI Exploit", "Session history and notes", "Export session report", "Local AI explanation", "Quit"]
        while True:
            choice = self.menu("INSPECT. UNDERSTAND. EXPLOIT.", entries)
            if choice in (None, 10):
                return
            try:
                if choice == 0:
                    self.scope()
                elif choice == 1:
                    options = ["Dependency status", "Run diagnostic workflow"] + [c.title for c in catalog.diagnostics()]
                    n = self.menu("Adapter diagnostics", options)
                    if n == 0:
                        self.view("Dependencies", "\n".join(f"{r['name']:12} {r['path'] or 'MISSING'}\n  {r['purpose']}" for r in catalog.inventory()))
                    elif n == 1:
                        commands = catalog.diagnostics()
                        rows = self.background("Adapter diagnostic workflow", lambda stop, emit: self.app.workflow(commands, stop, emit))
                        self.view("Workflow results", "\n".join(f"{r['title']}: {r['status']}" for r in rows))
                    elif n is not None:
                        self.command(catalog.diagnostics()[n - 2])
                elif choice == 2:
                    self.command(catalog.cached_networks())
                elif choice == 3:
                    recommendations = recommended_commands(self.app.session)
                    n = self.menu("Guided next steps", ["Read evidence and diagnosis"] + ["Suggested: " + c.title for _, c in recommendations])
                    if n == 0:
                        self.view("Evidence and diagnosis", "\n\n".join(f"[{a}] {b}\nNext: {c}" for a, b, c in suggest(self.app.session)))
                    elif n is not None:
                        reason, command = recommendations[n - 1]
                        command.purpose = reason + " " + command.purpose
                        self.command(command)
                elif choice == 4:
                    self.capture_inspection()
                elif choice == 5:
                    self.command(catalog.passive_capture(self.app.session.scope, self.app.output_path("pcapng")))
                elif choice == 6:
                    self.engine()
                elif choice == 7:
                    n = self.menu("Session evidence", ["Command history", "Add a note", "View notes"])
                    if n == 0:
                        self.history()
                    elif n == 1:
                        note = self.prompt("Session note")
                        if note:
                            self.app.note(note)
                    elif n == 2:
                        self.view("Notes", "\n\n".join(self.app.session.notes) or "No notes yet.")
                elif choice == 8:
                    n = self.menu("Report export", ["HTML summary / omit sensitive details", "JSON summary / omit sensitive details", "Full private HTML / includes raw output", "Full private JSON / includes raw output"])
                    if n is not None:
                        path = self.app.export("html" if n % 2 == 0 else "json", sensitive=n >= 2)
                        self.view("Report saved", str(path))
                elif choice == 9:
                    question = self.prompt("Ask your local model (sends recent session output to local Ollama)")
                    if question:
                        answer = self.background("Local AI / response pending", lambda stop, emit: local_explanation(question, self.app.session), cancellable=False)
                        self.view("Model explanation / verify against evidence", answer)
            except (ValueError, OSError, TypeError, KeyError) as exc:
                self.view("Action could not finish", str(exc))


def launch(app):
    curses.wrapper(lambda screen: UI(screen, app).main())
