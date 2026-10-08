"""SwissTargetPrediction browser workflow (Homo sapiens).

Uses the website's actual browser form instead of guessing a POST redirect.
No predictions are fabricated; a result must contain real table rows.
"""
import csv
import io
import re
import shutil
import subprocess
import sys
import zipfile
from urllib.parse import urlparse

SITE = "https://www.swisstargetprediction.ch/index.php"
HEADERS = ["compound_id", "smiles", "Target", "Common_name", "Uniprot_ID",
           "ChEMBL_ID", "Target_Class", "Probability", "Known_actives_3D_2D",
           "Job_ID", "Result_URL"]

def _launch_browser(playwright):
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                           check=True, capture_output=True, text=True, timeout=180)
        except Exception as exc:
            raise RuntimeError("Chromium unavailable. Configure packages.txt or install Playwright Chromium.") from exc
    kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if binary:
        kwargs["executable_path"] = binary
    return playwright.chromium.launch(**kwargs)

def _extract_all_rows(page):
    rows = page.evaluate("""() => {
        const clean = v => {
            const node = document.createElement('div');
            node.innerHTML = String(v == null ? '' : v);
            return (node.textContent || '').replace(/\s+/g,' ').trim();
        };
        const table = document.querySelector('#resultTable');
        if (!table) return [];
        const jq = window.jQuery;
        if (jq && jq.fn.DataTable && jq.fn.DataTable.isDataTable(table)) {
            return jq(table).DataTable().rows().data().toArray()
              .filter(r => Array.isArray(r) && r.length >= 7)
              .map(r => r.slice(0,7).map(clean));
        }
        return Array.from(table.querySelectorAll('tbody tr'))
          .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))
          .filter(r => r.length >= 7).map(r => r.slice(0,7));
    }""")
    if not rows:
        raise RuntimeError("No target rows in SwissTargetPrediction result table")
    # Avoid quietly exporting only page 1 if the table is paginated.
    count = page.locator("#resultTable_info").inner_text() if page.locator("#resultTable_info").count() else ""
    match = re.search(r"of\s+([0-9,]+)\s+entries", count, re.I)
    if match and int(match.group(1).replace(",", "")) > len(rows):
        raise RuntimeError(f"Incomplete export: {len(rows)} rows, site reports {match.group(1)}")
    return rows

def run_swiss(compounds, progress=None):
    """Submit via the browser and report each stage, with bounded waiting.

    The site may take around a minute per prediction. We never mark submission
    or collection as successful until there is a confirmed result URL and rows.
    """
    from playwright.sync_api import sync_playwright
    import time

    if not compounds:
        raise ValueError("No compounds supplied")

    output = io.BytesIO()
    failures = {}
    collected = 0
    log = io.StringIO()
    manifest = csv.writer(log)
    manifest.writerow(["compound_id", "status", "job_id", "result_url", "row_count", "error"])
    def report(done, cid, status):
        if progress:
            progress(done, len(compounds), cid, status)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        report(0, compounds[0]["compound_id"], "STARTING_BROWSER")
        try:
            with sync_playwright() as p:
                browser = _launch_browser(p)
                try:
                    context = browser.new_context(accept_downloads=True)
                    page = context.new_page()
                    page.set_default_timeout(12000)
                    for number, compound in enumerate(compounds, 1):
                        cid = compound["compound_id"]
                        smiles = compound["smiles"]
                        job_id, result_url = "", ""
                        started = time.monotonic()

                        try:
                            report(number - 1, cid, "OPENING_FORM")
                            page.goto(SITE, wait_until="domcontentloaded", timeout=35000)

                            report(number - 1, cid, "ENTERING_SMILES")
                            field = page.locator(
                                'input[name="smiles"], textarea[name="smiles"]'
                            ).first
                            field.wait_for(state="visible", timeout=12000)
                            human = page.locator('input[value="Homo_sapiens"]')
                            if human.count() and human.first.is_visible():
                                human.first.check(timeout=12000)
                            field.fill(smiles, timeout=12000)

                            # This is the same submission action used by the
                            # preserved legacy Playwright runner.
                            report(number - 1, cid, "SENDING_FORM")
                            field.press("Enter", timeout=12000)
                            report(number - 1, cid, "WAITING_FOR_RESULT")

                            deadline = time.monotonic() + 120
                            last_url = page.url
                            while time.monotonic() < deadline:
                                last_url = page.url
                                match = re.search(r"[?&]job=([0-9]+)", last_url)
                                if ("/result.php" in last_url and match
                                    and page.locator("#resultTable tbody tr").count()):
                                    result_url = last_url
                                    job_id = match.group(1)
                                    break
                                elapsed = int(time.monotonic() - started)
                                report(number - 1, cid,
                                       f"WAITING_FOR_RESULT ({elapsed}s; {urlparse(last_url).path})")
                                page.wait_for_timeout(4000)

                            if not result_url:
                                raise TimeoutError(
                                    "No complete result page after 120s; "
                                    f"last browser URL: {last_url}"
                                )

                            report(number - 1, cid, "EXTRACTING_ALL_TARGETS")
                            # Wait for DataTables to initialize before reading
                            # its whole underlying dataset rather than page 1.
                            page.wait_for_timeout(1500)
                            rows = _extract_all_rows(page)
                            result_csv = io.StringIO()
                            writer = csv.writer(result_csv)
                            writer.writerow(HEADERS)
                            for values in rows:
                                writer.writerow([cid, smiles, *values, job_id, result_url])
                            archive.writestr(
                                f"SwissTargetPrediction/{cid}.csv", result_csv.getvalue()
                            )
                            manifest.writerow(
                                [cid, "COLLECTED", job_id, result_url, len(rows), ""]
                            )
                            collected += 1
                            report(number, cid, f"COLLECTED ({len(rows)} targets)")
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                            failures[cid] = error
                            try:
                                archive.writestr(
                                    f"debug/{cid}_page.html", page.content()[:350000]
                                )
                            except Exception:
                                pass
                            manifest.writerow(
                                [cid, "FAILED", job_id, result_url, 0, error[:900]]
                            )
                            report(number, cid, "FAILED — see manifest and debug HTML")
                            # Never submit remaining compounds when the first
                            # submission's outcome is uncertain.
                            for pending in compounds[number:]:
                                manifest.writerow(
                                    [pending["compound_id"], "NOT_ATTEMPTED",
                                     "", "", 0, "Stopped after earlier failure"]
                                )
                            break
                finally:
                    browser.close()
        except Exception as exc:
            error = f"Browser initialization failed: {exc}"
            failures.setdefault(compounds[0]["compound_id"], error)
            report(0, compounds[0]["compound_id"], "BROWSER_START_FAILED")
            for idx, compound in enumerate(compounds):
                manifest.writerow([
                    compound["compound_id"],
                    "FAILED" if idx == 0 else "NOT_ATTEMPTED",
                    "", "", 0, error if idx == 0 else "Browser failed to initialize"
                ])
        archive.writestr("manifest.csv", log.getvalue())

    return output.getvalue(), collected, failures
