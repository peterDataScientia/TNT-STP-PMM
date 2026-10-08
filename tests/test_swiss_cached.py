import csv
import unittest
from pathlib import Path
from providers.swiss_cached import is_reference_batch, parse_result_html

ROOT = Path(__file__).resolve().parents[1]

class FastSwissTests(unittest.TestCase):
    def test_original_panel_uses_completed_jobs(self):
        with (ROOT / "examples" / "compounds.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertTrue(is_reference_batch(rows))

    def test_changed_smiles_cannot_reuse_old_predictions(self):
        with (ROOT / "examples" / "compounds.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows[0]["smiles"] = "CCO"
        self.assertFalse(is_reference_batch(rows))

    def test_exactly_hundred_rows(self):
        row = "<tr>" + "".join(f"<td>{i}</td>" for i in range(7)) + "</tr>"
        html = '<table id="resultTable"><tbody>' + row * 100 + '</tbody></table>'
        self.assertEqual(len(parse_result_html(html)), 100)

    def test_partial_table_rejected(self):
        row = "<tr>" + "".join(f"<td>{i}</td>" for i in range(7)) + "</tr>"
        with self.assertRaisesRegex(ValueError, "Expected 100"):
            parse_result_html('<table id="resultTable">' + row * 15 + '</table>')
