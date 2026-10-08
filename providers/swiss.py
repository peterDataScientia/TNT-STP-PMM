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
from urllib.parse import parse_qs, urlparse

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
    from playwright.sync_api import sync_playwright
    if not compounds:
        raise ValueError("No compounds supplied")
    output = io.BytesIO()
    failures = {}
    collected = 0
    log = io.StringIO()
    manifest = csv.writer(log)
    manifest.writerow(["compound_id", "status", "job_id", "result_url", "row_count", "error"])
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            try:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(45000)
                for number, compound in enumerate(compounds, 1):
                    cid, smiles = compound["compound_id"], compound["smiles"]
                    if progress:
                        progress(number-1, len(compounds), cid, "SUBMITTING")
                    result_url = ""
                    job_id = ""
                    try:
                        page.goto(SITE, wait_until="domcontentloaded", timeout=90000)
                        human = page.locator('input[value="Homo_sapiens"]')
                        if human.count():
                            human.first.check()
                        field = page.locator('input[name="smiles"], textarea[name="smiles"]').first
                        field.fill(smiles)
                        submit = page.get_by_role("button", name=re.compile("Predict targets", re.I))
                        if submit.count() and submit.first.is_visible() and submit.first.is_enabled():
                            submit.first.click()
                        else:
                            field.press("Enter")
                        page.wait_for_url(re.compile(r"/result\.php\?job="), timeout=240000)
                        result_url = page.url
                        job_id = parse_qs(urlparse(result_url).query).get("job", [""])[0]
                        if not job_id:
                            raise RuntimeError("Result URL did not contain a job ID")
                        page.locator("#resultTable tbody tr").first.wait_for(timeout=90000)
                        rows = _extract_all_rows(page)
                        table = io.StringIO()
                        writer = csv.writer(table)
                        writer.writerow(HEADERS)
                        for values in rows:
                            writer.writerow([cid, smiles, *values, job_id, result_url])
                        archive.writestr(f"SwissTargetPrediction/{cid}.csv", table.getvalue())
                        manifest.writerow([cid, "COLLECTED", job_id, result_url, len(rows), ""])
                        collected += 1
                        if progress:
                            progress(number, len(compounds), cid, "COLLECTED")
                    except Exception as exc:
                        error = str(exc)
                        failures[cid] = error
                        archive.writestr(f"debug/{cid}_page.html", page.content()[:500000])
                        manifest.writerow([cid, "FAILED", job_id, result_url, 0, error.replace("\n", " ")[:900]])
                        if progress:
                            progress(number, len(compounds), cid, "FAILED")
                        # Stop immediately on a site/automation failure rather than
                        # repeatedly submitting the other compounds into an unknown state.
                        break
            finally:
                browser.close()
        archive.writestr("manifest.csv", log.getvalue())
    return output.getvalue(), collected, failures
