import argparse
import json
import shlex
import sys
from threading import Event

from . import __version__, access, adapters, catalog
from .advisor import local_explanation, suggest, recommended_commands
from .app import App
from .demo import HELP, create_demo
from .models import Scope, Session, clean
from .reports import export
from .storage import Store


def parser():
    p = argparse.ArgumentParser(prog="hifi", description="D3FAULTH HIFI — interactive wireless Exploit workbench")
    p.add_argument("--version", action="version", version=f"D3FAULTH HIFI {__version__}")
    p.add_argument("--home", help="Session storage directory")
    p.add_argument("--session", help="Resume a saved session ID")
    p.add_argument("--demo", action="store_true", help="Simulate workflows; never run radio commands")
    sub = p.add_subparsers(dest="action")
    sub.add_parser("tui", help="Open the interactive terminal (default)")
    sub.add_parser("doctor", help="List required/optional system tools")
    sub.add_parser("sessions", help="List saved sessions")
    sub.add_parser("diagnose", help="Run adapter diagnostics")
    adapter = sub.add_parser("adapter", help="List, restart or restore a selected wireless adapter")
    adapter_sub = adapter.add_subparsers(dest="adapter_action", required=True)
    adapter_sub.add_parser("list", help="Show detected wireless interfaces")
    restart = adapter_sub.add_parser("restart", help="Preview a selected adapter restart; add --run to execute")
    restart.add_argument("--interface", required=True)
    restart.add_argument("--restore-managed", action="store_true", help="Return monitor mode to normal managed Wi-Fi")
    restart.add_argument("--run", action="store_true")
    scope = sub.add_parser("scope", help="Create/update a session's selected network")
    scope.add_argument("--interface", required=True)
    scope.add_argument("--bssid", required=True)
    scope.add_argument("--channel", required=True, type=int)
    scope.add_argument("--duration", type=int, default=60)
    native = sub.add_parser("exploit", help="Full HIFI Exploit with session history and interactive prompts",
                            description="Run the bundled HIFI engine. Put engine arguments after --. Without --run, preview only.")
    native.add_argument("--run", action="store_true")
    native.add_argument("--workdir", help="Existing HIFI directory; relative HIFI paths resolve here")
    native.add_argument("--fresh", action="store_true", help="Reset saved HIFI arguments to its defaults")
    native.add_argument("engine_args", nargs=argparse.REMAINDER, help="HIFI arguments after --, e.g. -- -h -v")
    direct = sub.add_parser("engine", help="Run the bundled engine directly; use engine --help for all options")
    direct.add_argument("engine_args", nargs=argparse.REMAINDER)
    for action in ("capture", "capture-engine"):
        cmd = sub.add_parser(action, help="Build a selected-network capture command")
        cmd.add_argument("--run", action="store_true", help="Execute the command; otherwise preview only")
        if action == "capture-engine":
            cmd.add_argument("--active", action="store_true", help="Allow client deauthentication for this selected-network capture")
    ins = sub.add_parser("inspect", help="Inspect an existing capture")
    ins.add_argument("file")
    ins.add_argument("--view", choices=["metadata", "eapol", "management", "all"], default="all")
    offline = sub.add_parser("offline", help="Preview/run an offline wordlist Exploit")
    offline.add_argument("file")
    offline.add_argument("--wordlist", required=True)
    offline.add_argument("--run", action="store_true")
    sub.add_parser("suggest", help="Explain evidence-based next steps")
    ask = sub.add_parser("ask", help="Ask an installed local Ollama model; sends recent output to localhost")
    ask.add_argument("question")
    ask.add_argument("--model")
    report = sub.add_parser("report", help="Export saved evidence")
    report.add_argument("--output", required=True)
    report.add_argument("--include-sensitive", action="store_true", help="Include identifiers, notes, commands, raw output")
    return p


def run_cli(app, command):
    print(f"\n[{command.effect}] {command.title}\n{shlex.join(command.argv)}", flush=True)
    stop = Event()
    # KeyboardInterrupt unwinds runner's finally block, killing its child group.
    record = app.execute(command, stop, lambda text: print(text, end="", flush=True))
    if app.session.demo or record["status"] == "error":
        print(clean(record["output"]))
    print(f"\nResult: {record['status']} | session {app.session.id}")
    if command.interactive:
        print(f"HIFI files: {command.cwd}")
        print("Exit status describes the process, not password recovery. See HIFI output and saved evidence.")
    return 0 if record["status"] in {"ok", "simulated"} else 1


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "engine":
        from .engine_entry import main as engine_main
        return engine_main(raw[1:])
    p = parser()
    args = p.parse_args(raw)
    try:
        if args.action == "doctor":
            print(f"D3FAULTH HIFI {__version__} | Python {sys.version.split()[0]}")
            print("Access: " + ("ROOT / privileged" if access.is_root() else "USER / live radio and adapter restart require root"))
            for row in catalog.inventory():
                print(f"{row['name']:14} {row['path'] or 'MISSING'}")
            print("Core menus/demo need only Python. Live operations need their listed tools and a supported adapter.")
            if not access.is_root():
                print("Privileged launch: " + access.launch_command())
            return 0
        if args.action == "adapter" and args.adapter_action == "list":
            rows = adapters.discover(args.demo)
            print(f"{'INTERFACE':16} {'MODE':12} PHY")
            for row in rows:
                print(f"{row.name:16} {row.mode:12} {row.phy}")
            if not rows:
                print("No wireless adapter detected. Check USB passthrough and the driver.")
            return 0
        store = Store(args.home)
        if args.action == "sessions":
            for identifier, created, demo, records in store.list():
                print(identifier, created, "DEMO" if demo else "LIVE", f"{records} commands")
            return 0
        session = store.load(args.session) if args.session else (create_demo() if args.demo else Session())
        if args.session and args.demo and not session.demo:
            raise ValueError("Use a new --demo session; an existing live session cannot silently become simulated.")
        app = App(store, session)
        if args.action in (None, "tui"):
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                p.error("The interactive UI needs a terminal. Try hifi --demo diagnose or hifi doctor.")
            from .ui import launch
            launch(app)
            print(f"Session saved: {session.id}\nResume: hifi --session {session.id}")
        elif args.action == "adapter":
            plan = adapters.restart_plan(args.interface, args.restore_managed)
            if not args.run:
                print("Preview: selected adapter only; its connection will be interrupted.")
                print("\n".join(f"{i:02d}  {shlex.join(c.argv)}" for i, c in enumerate(plan, 1)))
                print("No changes made. Add --run to execute. Requires root outside demo mode.")
                return 0
            record = app.restart_adapter(args.interface, args.restore_managed, emit=lambda text: print(text, end="", flush=True))
            print(record["output"])
            print(f"Result: {record['status']} | session {session.id}")
            return 0 if record["status"] in {"ok", "simulated"} else 1
        elif args.action == "scope":
            session.scope = Scope(args.interface, args.bssid, args.channel, args.duration).validate(target=True)
            store.save(session)
            print(f"Session: {session.id}\n" + json.dumps(session.to_dict()["scope"], indent=2))
        elif args.action == "diagnose":
            for command in catalog.diagnostics():
                if run_cli(app, command):
                    return 1
        elif args.action == "exploit":
            native_args = args.engine_args
            if native_args and native_args[0] == "--":
                native_args = native_args[1:]
            elif native_args:
                p.error("Place HIFI options after --. Example: hifi exploit --run -- -h -v")
            if args.fresh and native_args:
                p.error("Use --fresh without HIFI arguments, or provide the replacement arguments after --.")
            command = app.native_engine(native_args if args.fresh or args.engine_args else None, args.workdir)
            if args.run:
                return run_cli(app, command)
            print(f"[{command.effect}] {command.purpose}\n{shlex.join(command.argv)}\n"
                  f"Working directory: {command.cwd}\nNative HIFI timing; no HIFI timeout.\n"
                  f"Session: {session.id}\nPreview only. Add --run to execute.")
        elif args.action in {"capture", "capture-engine", "offline"}:
            if args.action == "capture":
                command = catalog.passive_capture(session.scope, app.output_path("pcapng"))
            elif args.action == "capture-engine":
                command = catalog.engine_capture(session.scope, HELP if session.demo else None, args.active)
            else:
                command = catalog.offline_audit(session.scope, args.file, args.wordlist)
            if args.run:
                return run_cli(app, command)
            print(f"[{command.effect}] {command.purpose}\n{shlex.join(command.argv)}\nTimeout: {command.timeout}s\nPreview only. Add --run to execute.")
        elif args.action == "inspect":
            kinds = ["metadata", "eapol", "management"] if args.view == "all" else [args.view]
            for kind in kinds:
                if run_cli(app, catalog.inspect_capture(args.file, kind)):
                    return 1
        elif args.action == "suggest":
            for certainty, evidence, next_step in suggest(session):
                print(f"[{certainty}] {evidence}\n  Next: {next_step}\n")
            for reason, command in recommended_commands(session):
                print(f"Suggested command: {shlex.join(command.argv)}\n  Why: {reason}\n")
        elif args.action == "ask":
            print(clean(local_explanation(args.question, session, args.model)))
        elif args.action == "report":
            print(export(session, args.output, args.include_sensitive))
        return 0
    except KeyboardInterrupt:
        print("\nStopped. Previously completed steps remain saved.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"HIFI: {clean(exc)}", file=sys.stderr)
        return 2
