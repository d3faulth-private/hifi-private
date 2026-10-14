"""Recovery and privilege checks use synthetic interfaces; never alter the host."""
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from hifi import adapters, catalog
from hifi.app import App
from hifi.models import Session
from hifi.reports import report_data
from hifi.storage import Store


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Store(Path(self.tmp.name) / "state"), Session())
        self.commands = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake_run(self, command, cwd, stop, emit):
        self.commands.append(command.argv)
        output = ""
        if command.argv[-1] == "info":
            output = "Interface wlan0\n  type managed\n"
        elif command.argv[:2] == ["ip", "-j"]:
            output = '[{"ifname":"wlan0","flags":["UP","BROADCAST"]}]'
        return {"title": command.title, "argv": command.argv, "status": "ok", "returncode": 0,
                "output": output, "elapsed": 0, "effect": command.effect}

    def test_parse_multiple_adapters_without_assuming_names(self):
        rows = adapters.parse_interfaces("phy#3\n Interface wlxaabbcc\n  type managed\nphy#7\n Interface wlan1mon\n  type monitor\n")
        self.assertEqual([(x.name, x.mode, x.phy) for x in rows],
                         [("wlxaabbcc", "managed", "phy3"), ("wlan1mon", "monitor", "phy7")])
        for name in ["", "wlan0;id", "-a", "../../etc"]:
            with self.assertRaises(ValueError):
                adapters.restart_plan(name)

    def test_root_preflight_blocks_engine_before_child_launch_or_session_change(self):
        command = self.app.native_engine()
        with patch("hifi.access.is_root", return_value=False), patch("hifi.app.run_interactive") as child:
            with self.assertRaisesRegex(PermissionError, "No command was started"):
                self.app.execute(command)
            child.assert_not_called()
        self.assertEqual(self.app.session.records, [])
        self.assertFalse(catalog.engine_exploit(["--help"], self.tmp.name).root)

    def test_unprivileged_restart_does_not_touch_the_adapter(self):
        with patch("hifi.access.is_root", return_value=False), patch("hifi.adapters.discover") as discover, patch("hifi.adapters.run") as run:
            with self.assertRaises(PermissionError):
                self.app.restart_adapter("wlan0")
            discover.assert_not_called()
            run.assert_not_called()

    def test_disconnected_or_non_wireless_interface_is_rejected(self):
        with patch("hifi.access.is_root", return_value=True), patch("hifi.adapters.discover", return_value=[]), patch("hifi.adapters.run") as run:
            with self.assertRaisesRegex(ValueError, "no longer present"):
                self.app.restart_adapter("eth0")
            run.assert_not_called()

    def test_restart_verifies_state_and_keeps_raw_step_data_out_of_summary(self):
        with patch("hifi.access.is_root", return_value=True), patch("hifi.adapters.discover", return_value=[adapters.Adapter("wlan0", "managed")]), patch("hifi.adapters.run", side_effect=self.fake_run):
            result = self.app.restart_adapter("wlan0")
        self.assertEqual(result["status"], "ok")
        self.assertIn("Verified: interface is UP", result["output"])
        self.assertFalse(any("set" in x and "type" in x for x in self.commands))
        self.assertEqual(len(self.app.session.records), 1)
        summary = json.dumps(report_data(self.app.session))
        self.assertNotIn("wlan0", summary)
        self.assertNotIn("steps", summary)
        self.assertIn("wlan0", json.dumps(report_data(self.app.session, True)))

    def test_restore_mode_failure_still_brings_interface_up_and_reports_failure(self):
        def failing(command, cwd, stop, emit):
            row = self.fake_run(command, cwd, stop, emit)
            if "type" in command.argv:
                row.update(status="failed", returncode=1, output="driver refused mode change")
            return row
        with patch("hifi.access.is_root", return_value=True), patch("hifi.adapters.discover", return_value=[adapters.Adapter("wlan0", "monitor")]), patch("hifi.adapters.run", side_effect=failing):
            result = self.app.restart_adapter("wlan0", restore_managed=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.commands[2], ["ip", "link", "set", "dev", "wlan0", "up"])
        self.assertIn("driver refused", result["output"])

    def test_cancel_during_down_still_restores_link_with_fresh_cancellation_token(self):
        stop = Event()
        def cancel(command, cwd, cancellation, emit):
            if command.argv[-1] == "down":
                stop.set()
            elif command.argv[-1] == "up":
                self.assertFalse(cancellation.is_set())
            return self.fake_run(command, cwd, cancellation, emit)
        with patch("hifi.access.is_root", return_value=True), patch("hifi.adapters.discover", return_value=[adapters.Adapter("wlan0", "managed")]), patch("hifi.adapters.run", side_effect=cancel):
            result = self.app.restart_adapter("wlan0", restore_managed=True, stop=stop)
        self.assertEqual(result["status"], "cancelled")
        self.assertIn(["ip", "link", "set", "dev", "wlan0", "up"], self.commands)
        self.assertFalse(any("type" in x for x in self.commands))

    def test_successful_commands_do_not_hide_failed_final_state(self):
        def wrong_state(command, cwd, stop, emit):
            row = self.fake_run(command, cwd, stop, emit)
            if command.argv[:2] == ["ip", "-j"]:
                row["output"] = '[{"ifname":"wlan0","flags":[]}]'
            return row
        with patch("hifi.access.is_root", return_value=True), patch("hifi.adapters.discover", return_value=[adapters.Adapter("wlan0", "managed")]), patch("hifi.adapters.run", side_effect=wrong_state):
            result = self.app.restart_adapter("wlan0")
        self.assertEqual(result["status"], "failed")
        self.assertIn("could not be verified", result["output"])

    def test_demo_recovery_never_launches_system_commands(self):
        self.app.session.demo = True
        with patch("hifi.adapters.run", side_effect=AssertionError("must not run")), patch("hifi.adapters.subprocess.run", side_effect=AssertionError("must not discover")):
            result = self.app.restart_adapter("wlan0mon", restore_managed=True)
        self.assertEqual(result["status"], "simulated")
        self.assertIn("set type managed", result["output"])


if __name__ == "__main__":
    unittest.main()
