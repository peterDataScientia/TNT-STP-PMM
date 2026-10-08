"""Provider-response classification using actual HTML observed in live QA."""
import unittest

from providers.pharmmapper_live import _server_rejection, SubmissionRejected


class PharmMapperResponseTests(unittest.TestCase):
    def test_live_email_error(self):
        raw = """<html><body><h2>ERROR</h2>
        <p>Email address is invalid.</p>
        <p>Please check your email address again.</p>
        <p>The page will roll back in 5 seconds.</p></body></html>"""
        reason = _server_rejection(raw)
        self.assertIsNotNone(reason)
        self.assertIn("Email address is invalid", reason)

    def test_invalid_request(self):
        self.assertIn(
            "Invalid request detected",
            _server_rejection("<h2>ERROR</h2><p>Invalid request detected</p>"),
        )

    def test_normal_submit_page_not_rejected(self):
        body = """<h3>Step 2: Specify Parameters</h3>
        <label>Generate Conformers</label>
        <button>Submit</button>"""
        self.assertIsNone(_server_rejection(body))

    def test_rejection_redacts_email(self):
        reason = _server_rejection(
            "<h2>ERROR</h2>email address is invalid: myprivate@example.org")
        self.assertNotIn("myprivate@example.org", reason)

    def test_class_carries_diagnostics(self):
        obj = SubmissionRejected("Server rejected", {"status": 400})
        self.assertEqual(obj.diagnostics["status"], 400)


if __name__ == "__main__":
    unittest.main()
