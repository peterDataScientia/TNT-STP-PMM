"""Tests that results are complete before SwissTargetPrediction export."""
import unittest
from providers.swiss import _extract_all_rows

class Locator:
    def __init__(self, text): self.text = text
    def count(self): return 1
    def inner_text(self): return self.text

class Page:
    def __init__(self, n): self.n = n
    def evaluate(self, script): return [["T","name","P12345","CHEMBL1","class","0.2","2 / 3"] for _ in range(self.n)]
    def locator(self, selector): return Locator("Showing 1 to 15 of 100 entries")

class Tests(unittest.TestCase):
    def test_all_100_rows(self):
        self.assertEqual(len(_extract_all_rows(Page(100))), 100)
    def test_partial_15_rows_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Incomplete export"):
            _extract_all_rows(Page(15))

if __name__ == "__main__":
    unittest.main()
