"""Regression tests for recovering unknown PharmMapper submissions safely."""
import unittest
from providers.pharmmapper_live import _confirmed_job_id, submit_pending, _valid_job


class Locator:
    def __init__(self, values=None, *, attrs=None):
        self.values = values or []
        self.attrs = attrs or {}
    def evaluate_all(self, script):
        return self.values
    @property
    def first(self):
        return self
    def get_attribute(self, key):
        return self.attrs.get(key)
    def input_value(self):
        return self.attrs.get("value", "")
    def inner_text(self, timeout=None):
        return self.attrs.get("text", "")
    def text_content(self):
        return self.attrs.get("text", "")


class FakePage:
    url = "https://www.lilab-ecust.cn/pharmmapper/submitfile.html"
    def __init__(self, *, clips=None, inputs=None, targets=None, target_value=None, html="", body_text=""):
        self._clips = clips or []
        self._inputs = inputs or []
        self._targets = targets or []
        self._target_value = target_value
        self._html = html
        self._body_text = body_text
        self.context = type("Context", (), {"pages": [self]})()
    def locator(self, selector):
        if selector == "a[href]":
            return Locator()
        if selector == "[data-clipboard-text]":
            return Locator(self._clips)
        if selector == "[data-clipboard-target]":
            return Locator(self._targets)
        if selector == "input, textarea":
            return Locator(self._inputs)
        if selector == "#job-id":
            return Locator(attrs={"value": self._target_value or ""})
        if selector == "body":
            return Locator(attrs={"text": self._body_text})
        return Locator()
    def content(self):
        return self._html


class JobRecoveryTests(unittest.TestCase):
    def test_result_url(self):
        page = FakePage()
        job = _confirmed_job_id(page, [
            "https://www.lilab-ecust.cn/pharmmapper/results/261006081553.html"
        ])
        self.assertEqual(job, "261006081553")

    def test_clipboard_text(self):
        self.assertEqual(_confirmed_job_id(FakePage(clips=["261006081553"]), []),
                         "261006081553")

    def test_clipboard_target(self):
        page = FakePage(targets=["#job-id"], target_value="261006081553")
        self.assertEqual(_confirmed_job_id(page, []), "261006081553")

    def test_hidden_labelled_input(self):
        page = FakePage(inputs=[{"context": "job_id", "value": "261006081553"}])
        self.assertEqual(_confirmed_job_id(page, []), "261006081553")

    def test_visible_job_id_confirmation(self):
        page = FakePage(body_text="Successfully submitted. Your Job ID: 261006081553")
        self.assertEqual(_confirmed_job_id(page, []), "261006081553")

    def test_result_in_network_response(self):
        page = FakePage()
        self.assertEqual(
            _confirmed_job_id(page, [], [
                '{"message":"job submission succeeded","jobId":"261006081553"}'
            ]),
            "261006081553",
        )

    def test_unrelated_timestamps_rejected(self):
        page = FakePage(html="<p>Server build time 261006081553</p>")
        self.assertIsNone(_confirmed_job_id(page, []))

    def test_unknown_submission_never_resubmitted(self):
        entries = [{"compound_id": "A0", "smiles": "CCO"}]
        old = {"A0": {"status": "SUBMISSION_UNKNOWN", "job_id": "", "error": "Unknown"}}
        self.assertEqual(submit_pending(entries, "person@example.org", old), old)

    def test_validation(self):
        self.assertTrue(_valid_job("261006081553"))
        self.assertFalse(_valid_job("999999999999"))


if __name__ == "__main__":
    unittest.main()
