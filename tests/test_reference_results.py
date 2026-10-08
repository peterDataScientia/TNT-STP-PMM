import csv
import io
import unittest
import zipfile
from pathlib import Path
from providers.targetnet_archive import (
    RAW_SHA256, collect_existing_targetnet, load_bundled_targetnet,
    is_reference_targetnet
)
from providers.pharmmapper import validate_pharmmapper_csv

ROOT = Path(__file__).resolve().parents[1]

class HistoricalResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "examples" / "compounds.csv").open(encoding="utf-8") as file:
            cls.records = list(csv.DictReader(file))
    def test_reference_panel(self):
        self.assertTrue(is_reference_targetnet(self.records))
        self.assertEqual(len(load_bundled_targetnet()), 83814)
    def test_offline_17_623(self):
        raw, count, errors = collect_existing_targetnet(self.records)
        self.assertEqual((count,len(errors)),(17,0))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = [name for name in archive.namelist() if name.startswith("per_compound_csv/")]
            self.assertEqual(len(files),17)
            self.assertEqual(len(list(csv.DictReader(io.StringIO(
                archive.read("per_compound_csv/A0_TargetNet.csv").decode())))),623)
    def test_modified_input_rejected(self):
        copied=[dict(row) for row in self.records]
        copied[0]["smiles"]="CCO"
        with self.assertRaises(ValueError):
            collect_existing_targetnet(copied)
    def test_pharmmapper_real_csv_schema(self):
        body=("Ligand: A0\nPharma Model,Num Feature,zscore,Name\n"
              "1p49_v,3,0.355691,Steryl-sulfatase\n").encode()
        self.assertEqual(validate_pharmmapper_csv(body),1)
        with self.assertRaises(ValueError):
            validate_pharmmapper_csv(b"<html>unavailable</html>")

if __name__ == "__main__":
    unittest.main()
