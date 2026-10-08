import tempfile
import unittest
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_compounds.py"
spec = importlib.util.spec_from_file_location("validate_compounds", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class InputTests(unittest.TestCase):
    def test_example(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "compounds.csv"
        rows = module.validate(example)
        self.assertEqual(len(rows), 17)
        self.assertEqual(rows[0]["status"], "PENDING")

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.csv"
            p.write_text("compound_id,smiles\na,CCO\na,CCC\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                module.validate(p)

    def test_empty_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.csv"
            p.write_text("compound_id,smiles\n")
            with self.assertRaisesRegex(ValueError, "No input"):
                module.validate(p)

if __name__ == "__main__":
    unittest.main()
