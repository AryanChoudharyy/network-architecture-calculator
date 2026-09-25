"""Convenient test runner for run.ps1 and standard Python installations."""
from pathlib import Path
import os
import unittest

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover("tests"))
    raise SystemExit(not result.wasSuccessful())
