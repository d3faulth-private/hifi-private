"""A dependency-free curses terminal interface with editable command previews."""
import curses
import shlex
import textwrap
import threading
import time
from collections import deque

from . import __version__, access, adapters, catalog, discovery
from .advisor import local_explanation, suggest, recommended_commands
from .demo import HELP
from .models import Scope, clean


class UI:
    def __init__(self, screen, app):
        self.screen, self.app = screen, app
        self.screen.keypad(True)
        self.adapter_rows = []
        self.adapter_notice = ""
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            for i, fg in enumerate([curses.COLOR_GREEN, curses.COLOR_CYAN, curses.COLOR_WHITE, curses.COLOR_YELLOW], 1):
                curses.init_pair(i, fg, curses.COLOR_BLACK)
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_GREEN)
            self.screen.bkgd(" ", curses.color_pair(3))
        self.refresh_adapters()

    def refresh_adapters(self):
        try:
            self.adapter_rows = adapters.discover(self.app.session.demo)
            self.adapter_notice = "" if self.adapter_rows else "No wireless adapter detected"
            if not self.app.session.scope.interface and len(self.adapter_rows) == 1:
                self.app.session.scope.interface = self.adapter_rows[0].name
                self.app.store.save(self.app.session)
        except (ValueError, OSError) as exc:
            self.adapter_rows = []
            self.adapter_notice = str(exc)

    def box(self, top, left, bottom, right):
        if bottom <= top or right <= left:
            return
        try:
            self.screen.addstr(top, left + 1, "─" * (right - left - 1))
            self.screen.addstr(bottom, left + 1, "─" * (right - left - 1))
            for y in range(top + 1, bottom):
                self.screen.addstr(y, left, "│")
                self.screen.addstr(y, right, "│")
            for y, x, corner in [(top, left, "┌"), (top, right, "┐"),
                                 (bottom, left, "└"), (bottom, right, "┘")]:
                self.screen.addstr(y, x, corner)
        except curses.error:
            pass

    def separator(self, y):
        _, w = self.screen.getmaxyx()
        try:
            self.screen.addstr(y, 2, "─" * max(0, w - 4))
            self.screen.addstr(y, 1, "├")
            self.screen.addstr(y, w - 2, "┤")
        except curses.error:
            pass

    def put(self, y, x, value, color=3, bold=False):
        h, w = self.screen.getmaxyx()
        if 0 <= y < h - 1 and 0 <= x < w - 1:
            attr = (curses.color_pair(color) if curses.has_colors() else 0) | (curses.A_BOLD if bold else 0)
            try:
                self.screen.addnstr(y, x, clean(value).replace("\n", " "), max(0, w - x - 3), attr)
            except curses.error:
                pass

    def frame(self, title, footer="NUMBER + ENTER open   UP/DOWN select   ESC back"):
        self.screen.erase()
        h, w = self.screen.getmaxyx()
        self.box(0, 1, h - 2, w - 2)
        self.put(1, 4, "D3FAULTH", 1, True)
        self.put(1, max(20, w - 18), f"HIFI  v{__version__}", 2)
        self.put(2, 4, "H I F I   /   WIRELESS CONTROL", 3, True)
        privilege = "DEMO / SIMULATED" if self.app.session.demo else ("ROOT / PRIVILEGED" if access.is_root() else "USER / ROOT NEEDED FOR RADIO")
        self.put(3, 4, privilege, 2 if self.app.session.demo or access.is_root() else 4)
        self.separator(4)
        self.put(5, 4, title, 3, True)
        scope = self.app.session.scope
        selected = next((a for a in self.adapter_rows if a.name == scope.interface), None)
        mode = selected.mode if selected else "not detected"
        self.separator(h - 6)
        self.put(h - 5, 4, f"ADAPTER  {scope.interface or 'not selected'}  /  {mode}  |  CHANNEL  {scope.channel or '-'}", 2)
        self.put(h - 4, 4, f"SESSION  {self.app.session.id}  |  RECORDS  {len(self.app.session.records)}", 3)
        self.put(h - 3, 4, footer, 4)
        return h, w

    def menu(self, title, entries, descriptions=None):
        selected = 0
        digits = ""
        codes = list(range(1, len(entries) + 1))
        if entries[-1] in {"Back", "Exit", "Quit"}:
            codes[-1] = 0
        width = max(2, len(str(max(codes))))
        while True:
            footer = f"OPEN NUMBER: {digits}   ENTER confirm   BACKSPACE edit" if digits else "NUMBER + ENTER open   UP/DOWN select   ESC back"
            h, w = self.frame(title, footer)
            visible = max(1, h - 14)
            if h < 20 or w < 70:
                self.put(7, 4, "Resize terminal to at least 70 x 20. ESC exits.", 4)
                self.screen.refresh()
                if self.screen.getch() in (27, ord("q")):
                    return None
                continue
            start = max(0, selected - visible + 1)
            for offset, label in enumerate(entries[start:start + visible]):
                i = start + offset
                self.put(7 + offset, 4, f" {codes[i]:0{width}d}  {label}".ljust(w - 9), 5 if i == selected else 3, i == selected)
            if descriptions and h >= 24:
                self.put(h - 8, 4, descriptions[selected], 2)
            self.screen.refresh()
            key = self.screen.getch()
            if key in (curses.KEY_UP, ord("k")):
                digits = ""
                selected = (selected - 1) % len(entries)
            elif key in (curses.KEY_DOWN, ord("j")):
                digits = ""
                selected = (selected + 1) % len(entries)
            elif key in (10, 13, curses.KEY_ENTER):
                if digits:
                    number = int(digits)
                    digits = ""
                    if number not in codes:
                        continue
                    return codes.index(number)
                return selected
            elif ord("0") <= key <= ord("9"):
                digits = (digits + chr(key))[-width:]
                if int(digits) in codes:
                    selected = codes.index(int(digits))
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                digits = digits[:-1]
            elif key in (27, ord("q")):
                return None

    def view(self, title, value):
        offset = 0
        while True:
            h, w = self.frame(title, "UP/DOWN scroll   PgUp/PgDn page   ESC/ENTER back")
            lines = []
            for line in clean(value).expandtabs(4).splitlines():
                lines.extend(textwrap.wrap(line, max(12, w - 8), replace_whitespace=False) or [""])
            count = max(1, h - 14)
            offset = min(offset, max(0, len(lines) - count))
            for i, line in enumerate(lines[offset:offset + count]):
                self.put(7 + i, 4, line)
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
                self.put(7, 4, "STOPPING / RESTORING ADAPTER IF NEEDED..." if stop.is_set() else "RUNNING...", 4)
                for i, line in enumerate(list(output)[-max(1, h - 16):]):
                    self.put(9 + i, 4, line)
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
                try:
                    self.app.preflight(command)
                except PermissionError as exc:
                    self.view("ROOT ACCESS REQUIRED", str(exc))
                    continue
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
                self.refresh_adapters()
                return

    def adapter_controls(self):
        while True:
            self.refresh_adapters()
            scope = self.app.session.scope
            selected = next((a for a in self.adapter_rows if a.name == scope.interface), None)
            label = f"{selected.name} / {selected.mode}" if selected else "choose an adapter"
            choice = self.menu("NETWORK ADAPTER / " + label, ["Select detected adapter", "Restart selected adapter",
                               "Restore normal Wi-Fi / managed mode", "Refresh adapter list", "Adapter details", "Diagnostics", "Back"])
            if choice in (None, 6):
                return
            if choice == 0:
                if not self.adapter_rows:
                    self.view("NO ADAPTER DETECTED", self.adapter_notice + "\nConnect a USB Wi-Fi adapter to the Kali guest, then refresh.")
                    continue
                index = self.menu("SELECT NETWORK ADAPTER", [f"{a.name}  /  {a.mode}  /  {a.phy}" for a in self.adapter_rows] + ["Back"])
                if index is not None and index < len(self.adapter_rows):
                    scope.interface = self.adapter_rows[index].name
                    self.app.store.save(self.app.session)
            elif choice == 3:
                continue
            elif choice == 5:
                self.diagnostics()
            elif not selected:
                self.view("SELECT AN ADAPTER", "Choose option 01 to select a detected wireless interface.")
            elif choice == 4:
                self.command(catalog.interface_info(scope))
            else:
                restore = choice == 2
                try:
                    access.require_root(self.app.session.demo)
                except PermissionError as exc:
                    self.view("ROOT ACCESS REQUIRED", str(exc))
                    continue
                plan = adapters.restart_plan(selected.name, restore)
                detail = (f"ADAPTER     {selected.name}\nCURRENT MODE  {selected.mode}\n\n"
                          + ("Return to managed mode and bring the interface up." if restore else "Bring this interface down and up, preserving its mode.")
                          + "\nThis interrupts its current connection. No other adapter or network service is restarted."
                          + "\nReconnect using your desktop network menu afterward.\n\nCOMMANDS\n"
                          + "\n".join(f"{n:02d}  {shlex.join(c.argv)}" for n, c in enumerate(plan, 1))
                          + "\n\nENTER runs this plan. ESC returns without changes.")
                if self.view("RESTORE NORMAL WI-FI" if restore else "RESTART NETWORK ADAPTER", detail):
                    record = self.background("ADAPTER RECOVERY", lambda stop, emit: self.app.restart_adapter(selected.name, restore, stop, emit))
                    self.refresh_adapters()
                    self.view("ADAPTER / " + record["status"].upper(), record["output"])

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
        choice = self.menu("Session history", [f"{r['status']:10} {r['title']}" for r in rows] + ["Back"])
        if choice is not None and choice < len(rows):
            r = rows[choice]
            directory = f"\nWorking directory: {r['cwd']}" if r.get("cwd") else ""
            self.view(r["title"], f"{r['started']}{directory}\n{shlex.join(r['argv'])}\n\n{r['output']}")

    def diagnostics(self):
        commands = catalog.diagnostics()
        n = self.menu("ADAPTER / DIAGNOSTICS", ["Dependency status", "Run diagnostic workflow"] + [c.title for c in commands] + ["Back"])
        if n == 0:
            self.dependencies()
        elif n == 1:
            rows = self.background("Adapter diagnostic workflow", lambda stop, emit: self.app.workflow(commands, stop, emit))
            self.view("Workflow results", "\n".join(f"{r['title']}: {r['status']}" for r in rows))
        elif n is not None and 2 <= n < len(commands) + 2:
            self.command(commands[n - 2])

    def dependencies(self):
        self.view("DEPENDENCIES", "\n".join(f"{r['name']:12} {r['path'] or 'MISSING'}\n  {r['purpose']}" for r in catalog.inventory()))

    def guidance(self):
        recommendations = recommended_commands(self.app.session)
        n = self.menu("GUIDED NEXT STEPS", ["Read evidence and diagnosis"] + ["Suggested: " + c.title for _, c in recommendations] + ["Back"])
        if n == 0:
            self.view("Evidence and diagnosis", "\n\n".join(f"[{a}] {b}\nNext: {c}" for a, b, c in suggest(self.app.session)))
        elif n is not None and 1 <= n <= len(recommendations):
            reason, command = recommendations[n - 1]
            command.purpose = reason + " " + command.purpose
            self.command(command)

    def dashboard(self):
        while True:
            choice = self.menu("DASHBOARD", ["Session overview", "Edit session scope", "Guided next steps", "Local AI explanation", "Back"])
            if choice in (None, 4):
                return
            if choice == 0:
                session, scope = self.app.session, self.app.session.scope
                last = session.records[-1] if session.records else None
                self.view("SESSION OVERVIEW", f"Session: {session.id}\nMode: {'Simulated demo' if session.demo else 'Live'}\n"
                          f"Adapter: {scope.interface or 'Not selected'}\nChannel: {scope.channel or 'Unset'}\n"
                          f"BSSID: {scope.bssid or 'Unset'}\nCapture time limit: {scope.duration}s\n"
                          f"Completed records: {len(session.records)}\nNotes: {len(session.notes)}\n\n"
                          + (f"Last operation: {last['title']}\nStatus: {last['status']}" if last else "No operations have run.")
                          + "\n\nThe saved scope applies to bounded profiles. Full Exploit uses its own target selection.")
            elif choice == 1:
                self.scope()
            elif choice == 2:
                self.guidance()
            else:
                question = self.prompt("Ask your local model (sends recent session output to local Ollama)")
                if question:
                    answer = self.background("Local AI / response pending", lambda stop, emit: local_explanation(question, self.app.session), cancellable=False)
                    self.view("Model explanation / verify against evidence", answer)

    def discovery(self):
        while True:
            choice = self.menu("NETWORK DISCOVERY", ["Live scan / include hidden networks", "Latest network table / select a network",
                               "Scan duration and bands", "Passive capture / existing monitor interface",
                               "Edit capture scope", "Inspect a capture file", "Back"])
            if choice in (None, 6):
                return
            if choice == 0:
                self.network_table(live=True)
            elif choice == 1:
                self.network_table()
            elif choice == 2:
                self.discovery_options()
            elif choice == 3:
                self.command(catalog.passive_capture(self.app.session.scope, self.app.output_path("pcapng")))
            elif choice == 4:
                self.scope()
            else:
                self.capture_inspection()

    def discovery_options(self):
        settings = self.app.session.discovery_settings
        answer = self.prompt("Discovery window in seconds (5–3600)", settings["seconds"])
        if answer is None:
            return
        seconds = int(answer)
        if not 5 <= seconds <= 3600:
            raise ValueError("Choose a discovery window between 5 and 3600 seconds.")
        selected = self.menu("DISCOVERY BANDS", ["2.4 GHz and 5 GHz", "2.4 GHz", "5 GHz", "Back"])
        if selected is None or selected == 3:
            return
        settings.update(seconds=seconds, band=["abg", "bg", "a"][selected])
        self.app.store.save(self.app.session)

    def network_details(self, network):
        clients = [c for c in self.app.session.clients if c.get("bssid") == network.bssid]
        frequency = f"{network.frequency} MHz (derived from channel)" if network.frequency else "Unknown"
        text = (f"NETWORK      {network.name}\nBSSID / MAC  {network.bssid}\nCHANNEL      {network.channel}\n"
                f"FREQUENCY    {frequency}\nSIGNAL       {network.signal if network.signal is not None else 'Unavailable'} (driver RSSI)\n"
                f"SECURITY     {network.security}\nCIPHER       {network.cipher or 'Unknown'}\n"
                f"AUTH         {network.authentication or 'Unknown'}\nWPS          {network.wps}\n"
                f"LAST SEEN    {network.last_seen}\nBEACONS      {network.beacons}\nDATA PACKETS {network.packets}\n\n"
                "OBSERVED CLIENTS\n" + ("\n".join(f"{c['mac']}  signal {c['signal']}  packets {c['packets']}  last {c['last_seen']}" for c in clients)
                or "None observed in this scan.") + "\n\n"
                "The selected interface, BSSID and channel are saved in session scope.\n"
                "Hidden names appear only when observed traffic reveals them. No disconnects or SSID guessing are used.\n"
                "RSSI units depend on the driver. WPS is Unknown because this CSV source does not report it.\n"
                "Observed clients are not a complete router client list.")
        self.view("SELECTED NETWORK / " + network.name, text)

    def network_table(self, live=False):
        session = self.app.session
        rows = [discovery.Network(**row) for row in session.networks]
        scan, thread, errors = None, None, []
        selected, digits, query = 0, "", ""
        chosen = None
        if live:
            access.require_root(session.demo)
            if not session.scope.interface:
                raise ValueError("Select a detected adapter in Network Adapter before discovery.")
            settings = session.discovery_settings
            scan = discovery.Scan(self.app, int(settings["seconds"]), settings["band"])
            def worker():
                try:
                    scan.execute()
                except Exception as exc:
                    errors.append(str(exc))
            thread = threading.Thread(target=worker, daemon=False)
            rows = []
            thread.start()
        self.screen.timeout(150)
        try:
            while True:
                active = bool(thread and thread.is_alive())
                if scan:
                    rows, _, message = scan.snapshot()
                else:
                    message = "Saved observations / start a live scan to refresh"
                visible = [(i, row) for i, row in enumerate(rows, 1)
                           if query.lower() in (row.name + " " + row.bssid + " " + row.security).lower()]
                selected = min(selected, max(0, len(visible) - 1))
                h, w = self.frame("LIVE NETWORKS / INCLUDING HIDDEN" if active else "NETWORKS / INCLUDING HIDDEN",
                                  "ENTER select   S stop   / filter   ESC back")
                if h < 20 or w < 70:
                    self.put(7, 4, "Resize terminal to at least 70 x 20. ESC stops.", 4)
                    self.screen.refresh()
                    if self.screen.getch() in (27, ord("q")):
                        break
                    continue
                if active and scan:
                    self.put(h - 5, 4, f"ADAPTER  {session.scope.interface}  /  {scan.mode}  /  passive discovery", 2)
                state = "STOPPING / RESTORING" if scan and scan.stop.is_set() and active else "SCANNING" if active else "SCAN STOPPED" if scan else "SAVED"
                elapsed = int(time.monotonic() - scan.started) if scan else 0
                self.put(6, 4, f"{state}  {elapsed}s   {len(rows)} networks   Filter: {query or 'all'}", 2)
                name_width = max(8, min(28, w - 65))
                header = f" NO  {'NETWORK':<{name_width}}  BSSID / MAC        CH  RSSI SECURITY  CLI"
                self.put(8, 4, header, 2, True)
                count = max(1, h - 18)
                start = max(0, selected - count + 1)
                for line, (number, network) in enumerate(visible[start:start + count]):
                    signal = str(network.signal) if network.signal is not None else "?"
                    label = (f" {number:02d}  {network.name[:name_width]:<{name_width}}  {network.bssid} "
                             f"{network.channel:3} {signal:>5} {network.security[:8]:8} {len(network.clients):3}")
                    self.put(9 + line, 4, label.ljust(w - 9), 5 if start + line == selected else 3)
                if not visible:
                    self.put(10, 4, "Waiting for observations…" if active else "No matching networks observed.", 4)
                if digits:
                    message = "NETWORK NUMBER: " + digits + " / Enter selects"
                elif errors:
                    message = errors[0]
                elif scan and scan.record and scan.record["status"] == "error":
                    message = "Scan error / press E for details"
                self.put(h - 8, 4, message, 4)
                self.put(h - 7, 4, "Signal: driver RSSI | Hidden names require revealing traffic", 2)
                self.screen.refresh()
                key = self.screen.getch()
                if key in (27, ord("q")):
                    break
                if key in (ord("s"), ord("S")) and scan:
                    scan.stop.set()
                elif key in (curses.KEY_DOWN, ord("j")) and visible:
                    selected = (selected + 1) % len(visible)
                    digits = ""
                elif key in (curses.KEY_UP, ord("k")) and visible:
                    selected = (selected - 1) % len(visible)
                    digits = ""
                elif ord("0") <= key <= ord("9"):
                    digits = (digits + chr(key))[-4:]
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    digits = digits[:-1]
                elif key in (10, 13, curses.KEY_ENTER) and visible:
                    if digits:
                        entry = next((row for number, row in visible if number == int(digits)), None)
                        if entry is None:
                            digits = ""
                            continue
                        chosen = entry
                    else:
                        chosen = visible[selected][1]
                    break
                elif key == ord("/"):
                    self.screen.timeout(-1)
                    value = self.prompt("Filter by network name, BSSID or security", query)
                    if value is not None:
                        query, selected = value, 0
                    self.screen.timeout(150)
                elif key in (ord("e"), ord("E")) and not active:
                    self.screen.timeout(-1)
                    self.view("DISCOVERY DETAILS", "\n".join(errors) or (scan.record["output"] if scan and scan.record else message))
                    self.screen.timeout(150)
        finally:
            if scan:
                scan.stop.set()
            while thread and thread.is_alive():
                self.frame("STOPPING DISCOVERY / RESTORING ADAPTER", "Waiting for adapter recovery")
                self.put(8, 4, scan.message, 4)
                self.screen.refresh()
                thread.join(timeout=0.1)
            self.screen.timeout(-1)
            self.refresh_adapters()
        if chosen:
            if scan:
                chosen = next((row for row in scan.snapshot()[0] if row.bssid == chosen.bssid), chosen)
            discovery.select(self.app, chosen)
            self.network_details(chosen)
        elif errors:
            self.view("DISCOVERY COULD NOT START", "\n".join(errors))
        elif scan and scan.record and scan.record["status"] == "error":
            self.view("DISCOVERY ERROR", scan.record["output"])

    def manual_commands(self):
        while True:
            choice = self.menu("MANUAL COMMANDS / SELECT A PROFILE", ["Diagnostic command profiles", "Selected interface details",
                               "Cached network command", "Capture file commands", "Full HIFI command editor", "Back"])
            if choice in (None, 5):
                return
            if choice == 0:
                self.diagnostics()
            elif choice == 1:
                self.command(catalog.interface_info(self.app.session.scope))
            elif choice == 2:
                self.command(catalog.cached_networks())
            elif choice == 3:
                self.capture_inspection()
            else:
                self.command(self.app.native_engine())

    def sessions_reports(self):
        while True:
            choice = self.menu("SESSIONS & REPORTS", ["Command history", "Add a note", "View notes", "Export report", "Resume instructions", "Back"])
            if choice in (None, 5):
                return
            if choice == 0:
                self.history()
            elif choice == 1:
                note = self.prompt("Session note")
                if note:
                    self.app.note(note)
            elif choice == 2:
                self.view("Notes", "\n\n".join(self.app.session.notes) or "No notes yet.")
            elif choice == 3:
                n = self.menu("REPORT EXPORT", ["HTML summary / omit sensitive details", "JSON summary / omit sensitive details",
                              "Full private HTML / includes raw output", "Full private JSON / includes raw output", "Back"])
                if n is not None and n < 4:
                    path = self.app.export("html" if n % 2 == 0 else "json", sensitive=n >= 2)
                    self.view("Report saved", str(path))
            else:
                self.view("RESUME A SESSION", f"Current session: {self.app.session.id}\n\n"
                          "List saved sessions: hifi sessions\n"
                          f"Resume this session: hifi --session {self.app.session.id}\n\n"
                          "Use the same user and --home directory, if set. Root and normal users have separate default storage.\n"
                          "Resume restores saved evidence and settings, not running processes.")

    def settings_help(self):
        while True:
            choice = self.menu("SETTINGS & HELP", ["Dependencies", "Keyboard controls", "Command reference", "About D3FAULTH HIFI", "Back"])
            if choice in (None, 4):
                return
            if choice == 0:
                self.dependencies()
            elif choice == 1:
                self.view("KEYBOARD CONTROLS", "Number + Enter: open an option\nArrows or j/k: select\n00: Back in submenus; Exit on the main screen\n"
                          "Escape or q: Back; Exit on the main screen\n\nEditor: arrows, Home/End, Backspace/Delete, Ctrl+U\n"
                          "Result views: arrows and Page Up/Page Down\nBounded commands: Escape stops the process\n\n"
                          "Inside the native engine, keys belong to that engine. Ctrl+C reaches its workflow. Exit it to return to HIFI.")
            elif choice == 2:
                self.view("COMMAND REFERENCE", "hifi                     Open terminal\nhifi --demo              Explore simulated workflows\n"
                          "hifi doctor              Check dependencies and access\nhifi adapter list        List wireless interfaces\n"
                          "hifi sessions            List saved sessions\nhifi --help              All CLI commands\n\n"
                          "Adapter restart preview:\nhifi adapter restart --interface INTERFACE\n\n"
                          "Privileged launch:\n" + access.launch_command())
            else:
                self.view("D3FAULTH / HIFI", f"Version {__version__}\nWireless control terminal\n\n"
                          "Original D3FAULTH menus, command previews and session reporting.\n"
                          "GPL-2.0-only. Source credits and inherited engine provenance are included in CREDITS.md.\n\n"
                          "Software-verified alpha. Physical adapter and radio validation remain pending.")

    def main(self):
        entries = ["Dashboard", "Network Adapter", "Network Discovery", "Exploit", "Manual Commands",
                   "Sessions & Reports", "Settings & Help", "Exit"]
        descriptions = ["Session overview, scope and evidence-based next steps.", "Select, inspect, restart or restore a wireless adapter.",
                        "Live discovery, hidden networks, client details and selection.", "Existing engine workflows and editable options.",
                        "Choose a command profile, edit its arguments and preview.", "Review history, add notes and export saved evidence.",
                        "Dependencies, navigation, CLI reference and project details.", "Save the session and return to your shell."]
        actions = [self.dashboard, self.adapter_controls, self.discovery, self.engine,
                   self.manual_commands, self.sessions_reports, self.settings_help]
        while True:
            choice = self.menu("HIFI / COMMAND CENTER", entries, descriptions)
            if choice in (None, 7):
                self.app.store.save(self.app.session)
                return
            try:
                actions[choice]()
            except (ValueError, OSError, TypeError, KeyError) as exc:
                self.view("Action could not finish", str(exc))


def launch(app):
    curses.wrapper(lambda screen: UI(screen, app).main())
