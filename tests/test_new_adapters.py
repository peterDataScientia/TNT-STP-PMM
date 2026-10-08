import unittest
from providers.targetnet import split_tsv
from providers.pharmmapper_live import _valid_job

class RealAdapterTests(unittest.TestCase):
    def test_targetnet_compound_mapping(self):
        data = b"Target\tUniProt.Name\tComp.1\tComp.2\nP12345\tENZYME\t0.2\t0.8\n"
        inputs = [{"compound_id":"A0","smiles":"CCO"},
                  {"compound_id":"A1","smiles":"CCC"}]
        parsed = split_tsv(data, inputs, "https://nanx.app/targetnet/")
        self.assertIn("A0", parsed)
        self.assertIn("A1", parsed)
        self.assertEqual(parsed["A0"][1], 1)
        self.assertIn("0.8", parsed["A1"][0])
    def test_targetnet_refuses_missing_compounds(self):
        with self.assertRaisesRegex(ValueError, "Invalid TargetNet"):
            split_tsv(b"Target\tComp.1\nP12345\t0.2\n",
                      [{"compound_id":"A0","smiles":"CCO"},{"compound_id":"A1","smiles":"CCC"}],
                      "https://nanx.app/targetnet/")
    def test_pharmmapper_job_ids(self):
        self.assertTrue(_valid_job("261006070604"))
        self.assertFalse(_valid_job("12345"))
        self.assertFalse(_valid_job("991399999999"))

if __name__ == "__main__":
    unittest.main()
