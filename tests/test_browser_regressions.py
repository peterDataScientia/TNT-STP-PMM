"""Regression tests for the two observed browser failures."""
import unittest
from providers.targetnet import configure_auc_filter
from providers.pharmmapper_live import submit_pending

class MockPage:
    def __init__(self):
        self.selector = None
        self.javascript = None

    def eval_on_selector(self, selector, javascript):
        self.selector = selector
        self.javascript = javascript
        return "auc"

class BrowserRegressionTests(unittest.TestCase):
    def test_targetnet_uses_selectize_api_not_hidden_native_select(self):
        page = MockPage()
        self.assertEqual(configure_auc_filter(page), "auc")
        self.assertEqual(page.selector, "#criterionupload")
        self.assertIn("element.selectize.setValue(option.value)", page.javascript)
        self.assertIn("new Event('change'", page.javascript)

    def test_pharmmapper_email_required_before_browser_starts(self):
        with self.assertRaisesRegex(ValueError, "email"):
            submit_pending([{"compound_id": "A0", "smiles": "CCO"}], "", {})

    def test_pharmmapper_malformed_email_rejected(self):
        with self.assertRaisesRegex(ValueError, "email"):
            submit_pending([{"compound_id": "A0", "smiles": "CCO"}], "invalid", {})

if __name__ == "__main__":
    unittest.main()
