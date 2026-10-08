"""Regressions for actual PharmMapper success page and COPY job ID."""
import unittest
from providers.pharmmapper_confirm import (
    is_submission_confirmed, job_id_from_confirmation, job_id_from_live_page
)
from providers.pharmmapper_live import SubmissionAcceptedWithoutId

BODY = (
    "<h2>Submit complete !</h2>"
    "<p>Your job has been submitted.</p>"
    "<p>Your <b>JOB ID</b> is : </p>"
    "<button id='copy'>COPY</button>"
)


class FakePage:
    def __init__(self, snapshot):
        self.snapshot = snapshot
    def evaluate(self, code):
        return self.snapshot


class PharmMapperConfirmationTests(unittest.TestCase):
    def test_real_diagnostic_page_is_accepted(self):
        self.assertTrue(is_submission_confirmed(BODY))

    def test_copy_target(self):
        html = BODY.replace(
            "<button id='copy'>",
            '<button id="copy" data-clipboard-target="#jobNumber">'
        ) + '<input id="jobNumber" readonly value="261008120512">'
        self.assertEqual(job_id_from_confirmation(html), "261008120512")

    def test_unlabelled_input_value_on_success_page(self):
        html = BODY + '<input id="i4" value="261008120512" readonly>'
        self.assertEqual(job_id_from_confirmation(html), "261008120512")

    def test_live_js_input_value_not_serialized_in_markup(self):
        page = FakePage({
            "success": True, "values": ["", "261008120512"],
            "html": BODY
        })
        self.assertEqual(job_id_from_live_page(page), "261008120512")

    def test_success_no_id_still_not_rejection(self):
        self.assertIsNone(job_id_from_confirmation(BODY))
        problem = SubmissionAcceptedWithoutId("Accepted", {"accepted": True})
        self.assertTrue(problem.diagnostics["accepted"])

    def test_multiple_unlabelled_values_not_guessed(self):
        html = BODY + (
            '<input value="261008120512">'
            '<input value="261008120513">'
        )
        self.assertIsNone(job_id_from_confirmation(html))

    def test_unconfirmed_page_does_not_yield_date_as_job(self):
        html = '<h2>ERROR</h2><input value="261008120512">'
        self.assertIsNone(job_id_from_confirmation(html))
        self.assertFalse(is_submission_confirmed(html))

    def test_live_js_value_requires_confirmation(self):
        page = FakePage({"success": False, "values": ["261008120512"],
                         "html": "<h2>ERROR</h2>"})
        self.assertIsNone(job_id_from_live_page(page))


if __name__ == "__main__":
    unittest.main()
