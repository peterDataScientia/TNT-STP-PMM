"""Offline tests for streamed SwissTargetPrediction redirect protocol."""
import unittest
from providers.swiss_http import extract_job_url, extract_targets, predict_one

class FakeResponse:
    def __init__(self, *, url, text, status_code=200, chunks=None, headers=None):
        self.url = url
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.headers = headers or {}
        self.chunks = chunks
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("Unexpected response")
    def iter_content(self, chunk_size, decode_unicode):
        for chunk in self.chunks or []:
            yield chunk
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False

class FakeSession:
    def __init__(self, redirect):
        self.redirect=redirect
        self.posts=0
    def get(self, url, **kwargs):
        if url.endswith("index.php"):
            return FakeResponse(url="https://swisstargetprediction.ch/index.php", text="Ready")
        assert url.endswith("job=987&organism=Homo_sapiens"), url
        row = "<tr>" + "".join("<td>{}</td>".format(v) for v in (
            "Fatty-acid amide hydrolase 1", "FAAH", "O00519",
            "CHEMBL2243", "Hydrolase", "0.88", "2 / 3")) + "</tr>"
        return FakeResponse(url=url, text='<table id="resultTable">' + row + '</table>')
    def post(self, url, **kwargs):
        self.posts += 1
        assert url == "https://swisstargetprediction.ch/predict.php"
        return FakeResponse(url=url, text="", chunks=[
            b'<script>showProgress(30)</script>',
            self.redirect.encode("utf-8")
        ])

class SwissHTTPTests(unittest.TestCase):
    def test_javascript_redirect(self):
        body = '<script>location.replace("http://www.swisstargetprediction.ch/result.php?job=123&organism=Homo_sapiens");</script>'
        url = extract_job_url(body, "https://swisstargetprediction.ch/predict.php")
        self.assertEqual(url, "https://www.swisstargetprediction.ch/result.php?job=123&organism=Homo_sapiens")
    def test_no_cross_site_redirect(self):
        body = "location.replace('https://malicious.example/result.php?job=42')"
        self.assertIsNone(extract_job_url(body, "https://swisstargetprediction.ch/predict.php"))
    def test_streamed_prediction(self):
        content = '<script>location.replace("https://swisstargetprediction.ch/result.php?job=987&organism=Homo_sapiens")</script>'
        client = FakeSession(content)
        url, rows = predict_one(client, "CCO")
        self.assertEqual(len(rows), 1)
        self.assertEqual(client.posts, 1)
        self.assertIn("987", url)
    def test_no_ambiguous_retry(self):
        from providers.swiss_http import SubmissionUnconfirmed
        client=FakeSession("<script>still loading...</script>")
        with self.assertRaises(SubmissionUnconfirmed):
            predict_one(client, "CCO")
        self.assertEqual(client.posts, 1)
    def test_expected_columns(self):
        row = "<tr>" + "".join("<td>{}</td>".format(v) for v in (
            "Target", "Gene", "P12345", "CHEMBL1", "Enzyme", "0.50", "6 / 2")) + "</tr>"
        self.assertEqual(len(extract_targets('<table id="resultTable">' + row + '</table>')), 1)

if __name__ == "__main__":
    unittest.main()
