"""Tests for the demo board in examples/hearth.

Run from the repository root: python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "tbd-board", "scripts", "board.py")
BOARD = os.path.join("examples", "hearth", "board.html")  # relative to ROOT
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "hearth.json")
OPEN_TAG = '<script type="application/json" id="tbd-board-data">'


class HearthExampleTest(unittest.TestCase):
    def test_check_passes_without_warnings(self):
        proc = subprocess.run([sys.executable, "-B", SCRIPT, "check", "--board", BOARD], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("warning:", proc.stdout + proc.stderr)

    def test_data_block_equals_the_fixture(self):
        with open(os.path.join(ROOT, BOARD), encoding="utf-8") as f:
            text = f.read()
        start = text.index(OPEN_TAG) + len(OPEN_TAG)
        block = json.loads(text[start:text.index("</script>", start)])
        with open(FIXTURE, encoding="utf-8") as f:
            self.assertEqual(block, json.load(f))


if __name__ == "__main__":
    unittest.main()
