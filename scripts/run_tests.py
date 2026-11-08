"""Run local contracts with mocked providers; stop the backend first."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['GIANA_ROUTER_MODE'] = 'rules'

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'scripts'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
