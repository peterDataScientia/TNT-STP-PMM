"""Protect final-submit response handling and deployed UI regression paths."""
import inspect
import unittest
from pathlib import Path

import providers.pharmmapper_live as live


class SubmissionRegressionTests(unittest.TestCase):
    def test_response_body_is_read_in_main_loop(self):
        source = inspect.getsource(live._submit_one)
        self.assertIn("captured_responses", source)
        self.assertIn("for response in list(captured_responses):", source)
        self.assertIn("body = response.text()", source)
        self.assertNotIn("def on_request_finished(request):", source)

    def test_no_automatic_final_submit_retry(self):
        source = inspect.getsource(live._submit_one)
        self.assertEqual(source.count("final.click("), 1)

    def test_submission_is_checkpointed_before_final_click(self):
        source = inspect.getsource(live._submit_one)
        self.assertLess(source.index("on_submit_armed()"), source.index("final.click("))
        wrapper = inspect.getsource(live.submit_pending)
        self.assertIn("on_submit_armed=mark_armed", wrapper)
        self.assertIn('"status": "SUBMISSION_UNKNOWN"', wrapper)

    def test_reference_unknown_can_be_preserved(self):
        # A recorded SUBMISSION_UNKNOWN must never be included in new batch.
        record = [{"compound_id": "A0", "smiles": "CCO"}]
        old = {"A0": {"job_id": "", "status": "SUBMISSION_UNKNOWN"}}
        self.assertEqual(live.submit_pending(record, "test@example.org", old), old)

    def test_ui_build_and_no_stale_banner(self):
        app = (Path(__file__).parents[1] / "app.py").read_text()
        self.assertIn("pmm-response-capture-20261008", app)
        self.assertNotIn("final submission outcome UNKNOWN.", app)
        self.assertIn("historical_existing_job", app)


if __name__ == "__main__":
    unittest.main()
