"""PharmMapper Step 2: Generate Conformers regression coverage."""
import unittest
from providers.pharmmapper_live import configure_generate_conformers


class MockPage:
    def __init__(self, answer):
        self.answer = answer
        self.script = ""

    def evaluate(self, script):
        self.script = script
        return self.answer


class ConformerSettingTests(unittest.TestCase):
    def test_checked_yes(self):
        page = MockPage("YES_CONFIRMED")
        self.assertEqual(configure_generate_conformers(page), "YES_CONFIRMED")
        self.assertIn("selected.click()", page.script)

    def test_site_documented_default(self):
        page = MockPage("DOCUMENTED_SITE_DEFAULT_TRUE")
        self.assertEqual(
            configure_generate_conformers(page), "DOCUMENTED_SITE_DEFAULT_TRUE"
        )

    def test_not_on_step_2(self):
        with self.assertRaisesRegex(ValueError, "GROUP_NOT_FOUND"):
            configure_generate_conformers(MockPage("GROUP_NOT_FOUND"))

    def test_yes_control_did_not_update(self):
        with self.assertRaisesRegex(ValueError, "YES_CONTROL_FAILED"):
            configure_generate_conformers(MockPage("YES_CONTROL_FAILED"))


if __name__ == "__main__":
    unittest.main()
