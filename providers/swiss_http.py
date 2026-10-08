"""SwissTargetPrediction real HTTP workflow.

The site computes predictions in predict.php and sends a JavaScript redirect
to result.php?job=... in the POST response. Do not wait for a Playwright URL
change and do not retry uncertain POSTs: doing so can duplicate server jobs.

This adapter uses only publicly available website forms, modest sequential
submission and verifiable results.
"""
from __future__ import annotations

import csv
import html
import io
import re
import time
import zipfile
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

ENTRYPOINT = "https://www.swisstargetprediction.ch/index.php"
BASE_HOSTS = frozenset({"www.swisstargetprediction.ch", "swisstargetprediction.ch"})
CSV_HEADER = (
    "compound_id", "smiles", "Target", "Common_name", "Uniprot_ID",
    "ChEMBL_ID", "Target_Class", "Probability", "Known_actives_3D_2D",
    "Job_ID", "Result_URL"
)
REDIRECT_PATTERNS = (
    r"""(?:window\.)?location\.replace\(\s*['"]([^'"]*result\.php\?[^'"]+)['"]\s*\)""",
    r"""(?:window\.)?location(?:\.href)?\s*=\s*['"]([^'"]*result\.php\?[^'"]+)['"]""",
    r"""['"]([^'"]*result\.php\?job=\d+[^'"]*)['"]""",
)

class SubmissionUnconfirmed(RuntimeError):
    """Submission may have been received. Never retry without confirming."""


def extract_job_url(body: str, current_url: str) -> str | None:
    cleaned = html.unescape(body).replace("\\/", "/")
    for expression in REDIRECT_PATTERNS:
        found = re.search(expression, cleaned, re.I | re.S)
        if not found:
            continue
        candidate = urljoin(current_url, found.group(1))
        parsed = urlparse(candidate)
        if parsed.hostname not in BASE_HOSTS or parsed.path != "/result.php":
            continue
        job = parse_qs(parsed.query).get("job", [""])[0]
        if not re.fullmatch(r"\d+", job):
            continue
        # Honor the result from the server; force TLS, avoid mixed-content.
        return parsed._replace(scheme="https").geturl()
    return None


def extract_targets(body: str) -> list[list[str]]:
    soup = BeautifulSoup(body, "html.parser")
    table = soup.select_one("table#resultTable")
    if table is None:
        raise ValueError("SwissTargetPrediction resultTable was not returned")
    parsed = []
    for tr in table.select("tr"):
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue
        values = [cell.get_text(" ", strip=True) for cell in cells[:7]]
        try:
            score = float(values[5])
        except ValueError:
            continue
        if not (0 <= score <= 1):
            continue
        parsed.append(values)
    if not parsed:
        raise ValueError("No valid prediction rows were returned")
    return parsed


def _session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; academic-research-app/1.0)",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def predict_one(session, smiles: str, update=None) -> tuple[str, list[list[str]]]:
    """Do exactly ONE submission. No silent re-POST under any circumstances."""
    landing = session.get(ENTRYPOINT, timeout=(8, 25))
    landing.raise_for_status()
    final = urlparse(landing.url)
    if final.hostname not in BASE_HOSTS or final.scheme != "https":
        raise RuntimeError(f"Unexpected SwissTargetPrediction landing host: {landing.url}")
    base = f"{final.scheme}://{final.netloc}"
    prediction_endpoint = base + "/predict.php"
    params = {"smiles": smiles, "organism": "Homo_sapiens", "ioi": "2"}
    current = prediction_endpoint
    # The first HTTP response is generated over a long-running calculation.
    # stream=True lets us inspect any final JS redirect without browser launch.
    if update:
        update("CALCULATING_ON_SERVER")
    with session.post(
        prediction_endpoint,
        data=params,
        headers={"Referer": base + "/index.php",
                 "Origin": base,
                 "Content-Type": "application/x-www-form-urlencoded"},
        timeout=(12, 100),
        allow_redirects=False,
        stream=True,
    ) as response:
        if response.status_code in (301, 302, 303, 307, 308):
            location = urljoin(prediction_endpoint, response.headers.get("Location", ""))
            possible = extract_job_url('location.replace("' + location + '")', prediction_endpoint)
            if possible:
                job_url = possible
            else:
                raise SubmissionUnconfirmed(
                    f"Unexpected HTTP {response.status_code} redirect to {location}; "
                    "submission was not repeated"
                )
        else:
            response.raise_for_status()
            text_parts = []
            total_size = 0
            job_url = None
            try:
                for part in response.iter_content(chunk_size=4096, decode_unicode=False):
                    if not part:
                        continue
                    total_size += len(part)
                    if total_size > 2_000_000:
                        raise SubmissionUnconfirmed("Prediction response exceeded 2 MB")
                    text_parts.append(part.decode(response.encoding or "utf-8", errors="replace"))
                    job_url = extract_job_url("".join(text_parts), prediction_endpoint)
                    if job_url:
                        break
            except requests.RequestException as exc:
                raise SubmissionUnconfirmed(
                    f"Prediction HTTP stream failed: {type(exc).__name__}: {exc}"
                ) from exc
            if not job_url:
                body = "".join(text_parts)
                if "invalid smiles" in body.lower() or "not valid" in body.lower():
                    raise ValueError("SwissTargetPrediction explicitly rejected SMILES")
                raise SubmissionUnconfirmed(
                    "predict.php completed without a confirmed result.php job URL"
                )

    if update:
        update("FETCHING_TARGETS")
    try:
        result = session.get(job_url, timeout=(8, 45),
                             headers={"Referer": current})
        result.raise_for_status()
        rows = extract_targets(result.text)
    except (requests.RequestException, ValueError) as exc:
        raise SubmissionUnconfirmed(
            f"Job URL confirmed: {job_url}; result retrieval failed: {exc}"
        ) from exc
    return job_url, rows


def run_swiss(compounds, progress=None):
    """Actual new prediction and ZIP export. Stops when result is uncertain."""
    if not compounds:
        raise ValueError("No compounds supplied")
    output = io.BytesIO()
    errors = {}
    completed = 0
    manifest_buffer = io.StringIO()
    manifest = csv.writer(manifest_buffer)
    manifest.writerow(["compound_id", "status", "job_id", "result_url", "target_count", "error"])

    def notify(done, cid, state):
        if progress:
            progress(done, len(compounds), cid, state)

    with _session() as session, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for idx, compound in enumerate(compounds):
            cid = compound["compound_id"]
            smiles = compound["smiles"]
            notify(idx, cid, "SUBMITTING")
            try:
                def update(stage):
                    notify(idx, cid, stage)
                job_url, rows = predict_one(session, smiles, update=update)
                job_id = parse_qs(urlparse(job_url).query)["job"][0]
                content = io.StringIO()
                writer = csv.writer(content)
                writer.writerow(CSV_HEADER)
                for row in rows:
                    writer.writerow([cid, smiles, *row, job_id, job_url])
                archive.writestr(f"per_compound/{cid}_SwissTargetPrediction.csv", content.getvalue())
                manifest.writerow([cid, "COLLECTED", job_id, job_url, len(rows), ""])
                completed += 1
                notify(idx + 1, cid, f"COLLECTED ({len(rows)} targets)")
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                errors[cid] = message
                manifest.writerow([cid, "FAILED_UNCONFIRMED", "", "", 0, message])
                notify(idx + 1, cid, "FAILED_UNCONFIRMED")
                for remaining in compounds[idx + 1:]:
                    manifest.writerow([remaining["compound_id"], "NOT_ATTEMPTED", "", "", 0,
                                       "Submission halted after uncertain result"])
                break
        archive.writestr("manifest.csv", manifest_buffer.getvalue())
        archive.writestr("README.txt",
                         "New SwissTargetPrediction submissions via the public web form.\n"
                         "FAILED_UNCONFIRMED jobs must not be blindly resubmitted.\n")
    return output.getvalue(), completed, errors
