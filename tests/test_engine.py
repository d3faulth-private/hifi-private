"""Bundled-engine integration checks without wireless devices or radio activity."""
import argparse
import json
import importlib
import os
from pathlib import Path
import subprocess
import pkgutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from hifi.backend import engine_argv
from hifi.catalog import engine_help, engine_capture, validate_edit
from hifi.engine.args import Arguments
from hifi.engine.config import Configuration
from hifi.engine.util.process import Process
import hifi.engine
from hifi.models import Scope, Session
from hifi.reports import report_data


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def engine(self, *args):
        return subprocess.run(engine_argv(list(args)), cwd=self.path,
                              capture_output=True, text=True, timeout=10,
                              env={**os.environ, "PATH": ""})

    def test_bundled_help_works_without_external_engine_or_radio_tools(self):
        result = self.engine("--help", "-v")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D3FAULTH", result.stdout)
        self.assertNotIn("wifite", (result.stdout + result.stderr).lower())
        for option in ["--wps-only", "--dict", "--pmkid", "--wep", "--cracked"]:
            self.assertIn(option, result.stdout)

    def test_all_baseline_option_names_and_aliases_are_retained(self):
        with patch.object(Configuration, "load_from_arguments"), patch.object(Configuration, "initialized", False):
            Configuration.initialize(load_interface=False)
        captured = []
        def capture(parser, *args, **kwargs):
            captured.append(parser)
            return argparse.Namespace()
        with patch.object(argparse.ArgumentParser, "parse_args", autospec=True, side_effect=capture):
            Arguments(Configuration)
        actual = sorted({s for action in captured[0]._actions for s in action.option_strings})
        expected = json.loads((Path(__file__).parent / "fixtures/engine-options.json").read_text())
        self.assertEqual(actual, expected)

    def test_argument_errors_keep_nonzero_exit_code(self):
        result = self.engine("--not-a-real-option")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_saved_results_command_needs_no_radio_backend(self):
        (self.path / "cracked.json").write_text("[]")
        result = self.engine("--cracked")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Required app", result.stdout)

    def test_bundled_capture_profile_uses_real_engine_help(self):
        scope = Scope("wlan0mon", "02:11:22:33:44:55", 6, 30)
        command = engine_capture(scope, engine_help())
        self.assertEqual(command.argv[:2], ["hifi", "engine"])
        import shlex
        validate_edit(shlex.join(command.argv), command, scope)

    def test_process_call_preserves_arguments_and_drains_large_output(self):
        marker = "spaces ; $(touch should-not-exist)"
        out, err = Process.call([sys.executable, "-c", "import sys; print(sys.argv[1]); print('x'*100000)", marker], cwd=self.path)
        self.assertEqual(out.splitlines()[0], marker)
        self.assertEqual(len(out.splitlines()[1]), 100000)
        self.assertFalse((self.path / "should-not-exist").exists())
        self.assertEqual(err, "")

    def test_process_streams_drain_without_waiting_for_full_pipes(self):
        with Process([sys.executable, "-c", "print('x'*100000)"]) as process:
            self.assertEqual(len(process.stdout().strip()), 100000)

    def test_previous_session_settings_migrate_and_stay_private(self):
        data = Session().to_dict()
        del data["engine_args"], data["engine_workdir"]
        data.update(wifite_args=["--dict", "/private/words"], wifite_workdir="/private/workspace")
        loaded = Session.from_dict(data)
        self.assertEqual(loaded.engine_args, ["--dict", "/private/words"])
        self.assertEqual(loaded.engine_workdir, "/private/workspace")
        self.assertNotIn("/private", json.dumps(report_data(loaded)))

    def test_every_bundled_module_imports_with_declared_dependencies(self):
        modules = list(pkgutil.walk_packages(hifi.engine.__path__, "hifi.engine."))
        self.assertEqual(len(modules), 46)
        for module in modules:
            with self.subTest(module=module.name):
                importlib.import_module(module.name)


if __name__ == "__main__":
    unittest.main()
