"""Locate this installation's bundled engine, including inside a zipapp."""
from pathlib import Path
import sys


def engine_argv(arguments):
    archive = getattr(__loader__, "archive", None)
    if archive:
        return [sys.executable, str(Path(archive).resolve()), "engine", *arguments]
    return [sys.executable, str(Path(__file__).with_name("engine_entry.py").resolve()), *arguments]
