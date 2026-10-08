"""Fast, validated collection of the original 17 PharmMapper job results.

No jobs are submitted here. HTTP downloads run concurrently and outputs retain
the raw CSV bytes and identifiers from the actual PharmMapper server.
"""
import csv
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

JOB_IDS = {
    "A0": "261006070604", "A1": "261006070634",
    "A2": "261006070700", "A3": "261006070727",
    "A4": "261006070757", "A5": "261006070826",
    "A6": "261006070854", "A7": "261006070919",
    "A8": "261006070946", "A9": "261006071017",
    "A10": "261006074735", "A11": "261006081553",
    "A12": "261006081635", "A13": "261006081705",
    "A14": "261006081740", "A15": "261006081812",
    "A16": "261006081851",
}
HOSTS = ("https://www.lilab-ecust.cn", "https://lilab-ecust.cn")


def validate_pharmmapper_csv(raw):
    """Return the number of actual pharmacophore target records, not HTML."""
    if not raw or len(raw) > 12_000_000:
        raise ValueError("PharmMapper response empty or unexpectedly large")
    body = raw.decode("utf-8-sig", errors="replace")
    if "<html" in body[:500].lower():
        raise ValueError("The server returned HTML instead of a CSV")
    reader = csv.reader(io.StringIO(body))
    header = None
    nrows = 0
    for row in reader:
        if row and row[0].strip().lower() == "pharma model":
            header = [v.strip().lower() for v in row]
            if "zscore" not in header or "name" not in header:
                raise ValueError("Incomplete PharmMapper target header")
            continue
        if header and len(row) >= len(header) and row[0].strip().endswith("_v"):
            score = row[header.index("zscore")].strip()
            try:
                float(score)
            except ValueError:
                continue
            nrows += 1
    if not header or nrows == 0:
        raise ValueError("No valid target rows in PharmMapper result")
    return nrows


def _download(panel, job):
    failures = []
    for host in HOSTS:
        url = f"{host}/pharmmapper/results/{job}/{job}.csv"
        try:
            response = requests.get(
                url, timeout=(7, 18),
                headers={"Accept": "text/csv,text/plain,*/*"},
            )
            response.raise_for_status()
            rows = validate_pharmmapper_csv(response.content)
            return panel, job, url, rows, response.content
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{host}: {str(exc)[:150]}")
    raise RuntimeError("; ".join(failures))


def collect_pharmmapper(progress=None):
    """Return ZIP, completed count, and per-compound failures."""
    completed, failures = {}, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = {
            pool.submit(_download, panel, job): panel
            for panel, job in JOB_IDS.items()
        }
        for index, future in enumerate(as_completed(tasks), start=1):
            panel = tasks[future]
            try:
                _panel, job, url, rows, raw = future.result()
                completed[panel] = (job, url, rows, raw)
                state = "COLLECTED"
            except Exception as exc:
                failures[panel] = str(exc)
                state = "FAILED"
            if progress:
                progress(index, len(JOB_IDS), panel, state)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(["compound_id", "job_id", "status", "target_rows", "result_url", "error"])
        for panel, job in JOB_IDS.items():
            if panel in completed:
                _, url, count, raw = completed[panel]
                archive.writestr(f"raw/{panel}_{job}_PharmMapper.csv", raw)
                writer.writerow([panel, job, "COLLECTED", count, url, ""])
            else:
                writer.writerow([panel, job, "FAILED", 0, "", failures.get(panel, "")])
        archive.writestr("manifest.csv", manifest.getvalue())
        archive.writestr("README.txt",
                         "Original completed A0–A16 PharmMapper jobs. No new submissions.\n"
                         "Raw original target CSVs are retained as downloaded.\n")
    return output.getvalue(), len(completed), failures
