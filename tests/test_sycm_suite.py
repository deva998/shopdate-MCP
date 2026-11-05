"""Run Alibaba regressions in a separate process from the JD package named tb."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SycmSuite(unittest.TestCase):
    def test_isolated_sycm_regressions(self):
        env = {**os.environ, 'PYTHONPATH':str(ROOT/'components/ali'),
            'PYTHONUTF8':'1', 'PYTHONDONTWRITEBYTECODE':'1'}
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
            '-s', str(ROOT/'tests/sycm')], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stderr.strip())
