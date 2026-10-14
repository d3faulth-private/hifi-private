"""Privilege guidance shared by the terminal and command-line entry points."""
import os
from pathlib import Path
import shlex
import sys


def is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def launch_command():
    """Use this interpreter, including a pipx venv, instead of root's PATH."""
    archive = getattr(__loader__, "archive", None)
    if archive:
        argv = [sys.executable, str(Path(archive).resolve())]
    elif Path(sys.argv[0]).name == "hifi":
        argv = [str(Path(sys.argv[0]).absolute())]
    else:
        argv = [sys.executable, "-m", "hifi"]
    return shlex.join(["sudo", *argv])


def require_root(demo=False):
    if not demo and not is_root():
        raise PermissionError(
            "Root access is required for this action. No command was started.\n\n"
            "Exit HIFI and run:\n  " + launch_command() +
            "\n\nDiagnostics, help, demo and saved reports remain available as a normal user.\n"
            "Root uses a separate default session directory."
        )
