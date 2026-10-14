"""Regression coverage for piped terminals and assessment data boundaries."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from hifi.advisor import network_assessment, local_explanation
from hifi.discovery import Network
from hifi.models import Session, Command
from hifi.runner import run

class PolishTests(unittest.TestCase):
    def test_size_helpers_without_terminal(self):
        code = "from hifi.engine.util.scanner import Scanner; from hifi.engine.util.color import Color; assert Scanner.get_terminal_height() > 0; assert Scanner.get_terminal_width() > 0; Color.clear_entire_line()"
        result = subprocess.run([sys.executable, '-c', code], stdin=subprocess.DEVNULL, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b'stty', result.stderr)

    def test_dead_parent_does_not_hold_ui_open(self):
        code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); sys.exit(3)"
        with tempfile.TemporaryDirectory() as directory:
            result = run(Command('fixture', [sys.executable, '-c', code], 'fixture', 'none', timeout=5), directory)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['returncode'], 3)
        self.assertLess(result['elapsed'], 4)

    def test_assessment_is_scoped_and_excludes_credentials(self):
        network = Network('02:00:00:00:00:01', '', 6, -50, 'WPA2')
        session = Session()
        session.records = [dict(selected_target={'bssid': network.bssid}, status='failed', output='SECRET', recovery={'key':'SECRET'}),
                           dict(selected_target={'bssid':'02:00:00:00:00:02'}, status='OTHER-NETWORK')]
        evidence = network_assessment(network, session)
        self.assertIn('Hidden SSID', evidence)
        self.assertIn('PIN lock state: Unknown', evidence)
        self.assertIn('failed', evidence)
        self.assertNotIn('SECRET', evidence)
        self.assertNotIn('OTHER-NETWORK', evidence)

    def test_selected_model_context_has_no_raw_session_data(self):
        session = Session()
        session.records = [dict(title='secret', status='ok', output='DO-NOT-SEND')]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"response":"Explanation"}'
        with patch('hifi.advisor.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = Response()
            self.assertEqual(local_explanation('Explain', session, model='local', evidence='SAFE EVIDENCE'), 'Explanation')
            request = opener.return_value.open.call_args.args[0]
            prompt = json.loads(request.data)['prompt']
            self.assertIn('SAFE EVIDENCE', prompt)
            self.assertNotIn('DO-NOT-SEND', prompt)
