from datetime import datetime
from dataclasses import replace
from pathlib import Path
from threading import Event

from . import access, adapters, catalog
from .backend import engine_argv
from .demo import simulate
from .models import clean
from .reports import export
from .runner import run
from .terminal import run_interactive


class App:
    def __init__(self, store, session):
        self.store, self.session = store, session
        self.store.save(session)

    def execute(self, command, stop=None, emit=None):
        self.preflight(command)
        # Live profiles are always validated, including generated commands.
        import shlex
        catalog.validate_edit(shlex.join(command.argv), command, self.session.scope)
        if command.argv[0] == "dumpcap" and not self.session.demo:
            catalog.monitor_preflight(self.session.scope)
        if command.interactive:
            self.session.engine_args = command.argv[2:]
            self.session.engine_workdir = command.cwd
            self.store.save(self.session)
        execution = replace(command, argv=engine_argv(command.argv[2:])) if command.argv[:2] == ["hifi", "engine"] else command
        if self.session.demo:
            record = simulate(command)
        elif command.interactive:
            record = run_interactive(execution, command.cwd)
        else:
            record = run(execution, self.store.folder(self.session), stop, emit)
        record["argv"] = command.argv
        self.session.records.append(record)
        self.store.save(self.session)
        return record

    def preflight(self, command):
        if command.root:
            access.require_root(self.session.demo)

    def restart_adapter(self, interface, restore_managed=False, stop=None, emit=None):
        record = adapters.restart(interface, self.store.folder(self.session), restore_managed,
                                  self.session.demo, stop, emit)
        self.session.records.append(record)
        self.store.save(self.session)
        return record

    def native_engine(self, arguments=None, workdir=None):
        directory = workdir or self.session.engine_workdir
        if not directory:
            path = self.store.folder(self.session) / "engine"
            path.mkdir(mode=0o700, exist_ok=True)
            directory = str(path)
        args = self.session.engine_args if arguments is None else arguments
        return catalog.engine_exploit(args, directory)

    def note(self, text):
        self.session.notes.append(clean(text)[:10000])
        self.store.save(self.session)

    def output_path(self, suffix):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        return self.store.folder(self.session) / f"hifi-{stamp}.{suffix}"

    def export(self, kind="html", sensitive=False):
        return export(self.session, self.output_path(kind), sensitive)

    def workflow(self, commands, stop=None, emit=None):
        stop = stop or Event()
        records = []
        for command in commands:
            if stop.is_set():
                break
            record = self.execute(command, stop, emit)
            records.append(record)
            if record["status"] not in {"ok", "simulated"}:
                break
        return records
