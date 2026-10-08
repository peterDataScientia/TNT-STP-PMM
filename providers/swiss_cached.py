"""Fast reuse of confirmed SwissTargetPrediction A0–A16 results.

Fetches completed result pages in parallel; does NOT submit new predictions.
Refuses to reuse any result for a different SMILES or compound panel.
"""
import csv
import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

JOB_FILE = Path(__file__).resolve().parents[1] / "data" / "swiss_a0_a16_jobs.csv"
HEADERS = ["compound_id", "smiles", "Target", "Common_name", "Uniprot_ID",
           "ChEMBL_ID", "Target_Class", "Probability", "Known_actives_3D_2D",
           "Job_ID", "Result_URL"]


def known_jobs():
    with JOB_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return {r["compound_id"]: r for r in csv.DictReader(handle)}


def is_reference_batch(records):
    jobs = known_jobs()
    return (
        len(records) == len(jobs) == 17
        and all(r.get("compound_id") in jobs
                and r.get("smiles") == jobs[r["compound_id"]]["smiles"]
                for r in records)
        and len({r["compound_id"] for r in records}) == 17
    )


def parse_result_html(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table#resultTable")
    if table is None:
        raise ValueError("SwissTargetPrediction resultTable absent or expired")
    rows = []
    for tr in table.select("tr"):
        cells = tr.find_all("td")
        if len(cells) >= 7:
            rows.append([c.get_text(" ", strip=True) for c in cells[:7]])
    if len(rows) != 100:
        raise ValueError(f"Expected 100 archived targets, obtained {len(rows)}")
    return rows


def _collect_one(record, job):
    url = job["result_url"]
    errors = []
    for attempt in range(2):
        try:
            response = requests.get(
                url, timeout=(8, 25), headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/html,application/xhtml+xml,*/*",
                },
            )
            response.raise_for_status()
            rows = parse_result_html(response.text)
            csv_data = io.StringIO()
            writer = csv.writer(csv_data)
            writer.writerow(HEADERS)
            for row in rows:
                writer.writerow([
                    record["compound_id"], record["smiles"], *row,
                    job["job_id"], url
                ])
            return record["compound_id"], csv_data.getvalue(), len(rows), url
        except (requests.RequestException, ValueError) as exc:
            errors.append(str(exc))
            if attempt == 0:
                time.sleep(1)
    raise RuntimeError("; ".join(errors))


def collect_existing_swiss(compounds, progress=None):
    """Return ZIP, collected compound count, errors; no new site submissions."""
    if not is_reference_batch(compounds):
        raise ValueError(
            "Fast reuse applies only to the original A0–A16 identifiers and exact SMILES."
        )
    jobs = known_jobs()
    found, failures = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_collect_one, item, jobs[item["compound_id"]]): item["compound_id"]
            for item in compounds
        }
        for completed, future in enumerate(as_completed(futures), 1):
            cid = futures[future]
            try:
                _, body, nrows, url = future.result()
                found[cid] = (body, nrows, url)
                status = "COLLECTED"
            except Exception as exc:
                failures[cid] = str(exc)
                status = "FAILED"
            if progress:
                progress(completed, len(compounds), cid, status)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(["compound_id", "job_id", "status", "target_count", "result_url", "error"])
        for compound in compounds:
            cid = compound["compound_id"]
            job = jobs[cid]
            if cid in found:
                csv_body, nrows, url = found[cid]
                archive.writestr(f"SwissTargetPrediction/{cid}.csv", csv_body)
                writer.writerow([cid, job["job_id"], "COLLECTED", nrows, url, ""])
            else:
                writer.writerow([
                    cid, job["job_id"], "FAILED", 0, job["result_url"],
                    failures[cid]
                ])
        archive.writestr("manifest.csv", manifest.getvalue())
        archive.writestr("README.txt",
                         "Previously completed A0–A16 SwissTargetPrediction jobs.\n"
                         "Retrieved from confirmed result URLs; no fresh predictions submitted.\n")
    return buf.getvalue(), len(found), failures
