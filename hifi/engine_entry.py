"""Absolute-path entry point that works outside the source checkout directory."""
import os
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(arguments=None):
    from hifi.engine.core import main as run_engine
    sys.argv = ["hifi engine", *(sys.argv[1:] if arguments is None else arguments)]
    os.umask(0o077)
    return run_engine()


if __name__ == "__main__":
    raise SystemExit(main())
