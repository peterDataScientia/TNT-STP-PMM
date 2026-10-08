"""PharmMapper live submit/collect adapters.

Each browser submission is explicitly tied to a compound and a confirmed job ID.
Never resubmit after the final click if its outcome is uncertain.
"""
import csv
import io
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

import requests

from providers.swiss import _launch_browser

SUBMIT_SITES = (
    "https://www.lilab-ecust.cn/pharmmapper/submitfile.html",
    "https://lilab-ecust.cn/pharmmapper/submitfile.html",
)
RESULT_BASE = "https://www.lilab-ecust.cn/pharmmapper/results"
LIMIT = 10


def _local_text(element):
    return element.evaluate("""el => {
      let node=el;
      for(let i=0;i<5 && node;i++,node=node.parentElement){
        let s=(node.innerText||'').replace(/\s+/g,' ').trim();
        if(s && s.length<600) return s;
      }
      return '';
    }""")


def _button(page, names):
    for name in names:
        button = page.get_by_role("button", name=re.compile("^" + name + "$", re.I))
        if button.count():
            return button.last
        inp = page.locator('input[type="submit"]')
        for i in range(inp.count()):
            el = inp.nth(i)
            if (el.get_attribute("value") or "").lower() == name.lower():
                return el
    return None


def _email_field(page):
    for selector in ('input[type="email"]', 'input[placeholder*="@"]',
                     'input[name*="mail" i]', 'input[id*="mail" i]'):
        loc = page.locator(selector)
        if loc.count():
            return loc.first
    for i in range(page.locator('input[type="text"]').count()):
        item = page.locator('input[type="text"]').nth(i)
        if "email" in _local_text(item).lower():
            return item
    raise ValueError("PharmMapper Email Address field was not found")


def _human_only(page):
    for i in range(page.locator("select").count()):
        dropdown = page.locator("select").nth(i)
        choices = dropdown.locator("option")
        for j in range(choices.count()):
            option = choices.nth(j)
            label = option.inner_text().strip()
            if "human" in label.lower() and "only" in label.lower():
                val = option.get_attribute("value")
                dropdown.select_option(value=val) if val is not None else dropdown.select_option(label=label)
                return True
    for i in range(page.locator("label").count()):
        label = page.locator("label").nth(i)
        name = label.inner_text()
        if "human" in name.lower() and "only" in name.lower():
            label.click()
            return True
    return False


def _set_near(page, phrase, value):
    for i in range(page.locator('input[type="text"], input[type="number"]').count()):
        inp = page.locator('input[type="text"], input[type="number"]').nth(i)
        if phrase.lower() in _local_text(inp).lower():
            inp.fill(str(value))
            return True
    return False


def _select_near(page, phrase, word):
    for i in range(page.locator("select").count()):
        dropdown = page.locator("select").nth(i)
        if phrase.lower() not in _local_text(dropdown).lower():
            continue
        options = dropdown.locator("option")
        for j in range(options.count()):
            option = options.nth(j)
            label = option.inner_text().strip()
            if label.lower() == word.lower():
                val = option.get_attribute("value")
                dropdown.select_option(value=val) if val is not None else dropdown.select_option(label=label)
                return True
    for i in range(page.locator('input[type="radio"]').count()):
        element = page.locator('input[type="radio"]').nth(i)
        if phrase.lower() in _local_text(element).lower() and word.lower() in _local_text(element).lower():
            element.check(force=True)
            return True
    return False


def sdf_from_smiles(smiles, compound_id):
    """Prepare a 3D MDL SDF V2000 input for PharmMapper."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Invalid SMILES")
    if mol.GetNumHeavyAtoms() > 100:
        raise ValueError("PharmMapper supports <=100 heavy atoms")
    mol = Chem.AddHs(mol)
    mol.SetProp("_Name", compound_id[:40])
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise ValueError("Could not generate 3D SDF conformer")
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=150)
    except Exception:
        pass
    block = Chem.MolToMolBlock(mol, forceV3000=False)
    if "V3000" in block:
        raise ValueError("PharmMapper requires SDF V2000")
    return (block + "\n$$$$\n").encode("utf-8")


def _valid_job(value):
    if not value or not re.fullmatch(r"\d{12}", value):
        return False
    try:
        datetime.strptime(value, "%y%m%d%H%M%S")
        return True
    except ValueError:
        return False


def _confirmed_job_id(page, urls):
    candidates = list(urls) + [page.url]
    try:
        candidates.extend(page.locator("a[href]").evaluate_all("es=>es.map(e=>e.href||'')"))
        candidates.extend(page.locator("[data-clipboard-text]").evaluate_all(
            "es=>es.map(e=>e.getAttribute('data-clipboard-text')||'')"))
    except Exception:
        pass
    candidates.append(page.content())
    for text in candidates:
        for pattern in (
            r"/results/(\d{12})(?:\.html|/|\?|[\"'])",
            r"data-clipboard-text=[\"'](\d{12})[\"']",
            r"(?:job(?:_|-)?id|jobid)[^0-9]{0,120}(\d{12})",
        ):
            for match in re.finditer(pattern, str(text), re.I):
                if _valid_job(match.group(1)):
                    return match.group(1)
    return None


def _submit_one(page, record, email):
    cid = record["compound_id"]
    data = sdf_from_smiles(record["smiles"], cid)
    last = None
    for site in SUBMIT_SITES:
        try:
            page.goto(site, wait_until="domcontentloaded", timeout=45000)
            filefield = page.locator('input[type="file"]').first
            filefield.wait_for(state="attached", timeout=10000)
            break
        except Exception as exc:
            last = str(exc)
    else:
        raise RuntimeError("Cannot open PharmMapper submission page: " + str(last))
    filefield.set_input_files({"name": cid[:38] + ".sdf",
                               "mimeType": "chemical/x-mdl-sdfile", "buffer": data})
    # PharmMapper uses the submitted address for validation and job tracking.
    _email_field(page).fill(email)
    cont = _button(page, ["Continue", "Next"])
    if cont is None:
        raise ValueError("Cannot find Step 1 Continue button")
    cont.click(timeout=20000)
    page.wait_for_timeout(700)
    if not _human_only(page):
        raise ValueError("Human Protein Targets Only setting not found")
    # Reproduce the settings used for the successful A0–A16 project.
    if not _set_near(page, "Maximum Generated Conformations", 300):
        raise ValueError("Cannot configure maximum conformations")
    if not _set_near(page, "Number of Reserved Matched Targets", 300):
        raise ValueError("Cannot configure matched targets")
    if not _select_near(page, "Generate Conformers", "Yes"):
        raise ValueError("Cannot set Generate Conformers to Yes")
    _select_near(page, "Perform GA Match", "No")
    final = _button(page, ["Submit", "Run", "OK"])
    if final is None:
        raise ValueError("Cannot find final Submit button")
    network = []
    page.on("response", lambda response: network.append(response.url))
    # Point of no return: do not retry this compound if confirmation is missing.
    try:
        final.click(timeout=25000)
    except Exception as exc:
        raise SubmissionUnknown("Submit was clicked but completion is unknown") from exc
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        job = _confirmed_job_id(page, network)
        if job:
            return job
        page.wait_for_timeout(750)
    raise SubmissionUnknown("Final Submit was clicked, but no 12-digit job ID was confirmed")


class SubmissionUnknown(RuntimeError):
    pass


def submit_pending(compounds, email, jobs=None, progress=None, on_checkpoint=None):
    """Submit at most 10 potentially active jobs, including unknown submissions."""
    from playwright.sync_api import sync_playwright
    jobs = dict(jobs or {})
    active = sum(row.get("status") in ("SUBMITTED", "SUBMISSION_UNKNOWN")
                 for row in jobs.values())
    slots = max(0, LIMIT - active)
    pending = [r for r in compounds if r["compound_id"] not in jobs or jobs[r["compound_id"]].get("status") == "FAILED"][:slots]
    if not pending:
        return jobs
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""):
        raise ValueError("A valid PharmMapper email address is required")
    with sync_playwright() as p:
        browser = _launch_browser(p)
        try:
            page = browser.new_page()
            page.set_default_timeout(20000)
            for index, item in enumerate(pending, 1):
                cid = item["compound_id"]
                if progress:
                    progress(index-1, len(pending), cid, "PREPARING")
                try:
                    job = _submit_one(page, item, email)
                    jobs[cid] = {"job_id": job, "status": "SUBMITTED", "error": ""}
                    if on_checkpoint:
                        on_checkpoint(dict(jobs))
                    if progress:
                        progress(index, len(pending), cid, "SUBMITTED")
                except SubmissionUnknown as exc:
                    jobs[cid] = {"job_id": "", "status": "SUBMISSION_UNKNOWN",
                                 "error": str(exc)}
                    if on_checkpoint:
                        on_checkpoint(dict(jobs))
                    if progress:
                        progress(index, len(pending), cid, "SUBMISSION_UNKNOWN")
                    break
                except Exception as exc:
                    jobs[cid] = {"job_id": "", "status": "FAILED",
                                 "error": f"{type(exc).__name__}: {exc}"[:500]}
                    if on_checkpoint:
                        on_checkpoint(dict(jobs))
                    if progress:
                        progress(index, len(pending), cid, "FAILED")
                    break
        finally:
            browser.close()
    return jobs


def _fetch_job(cid, job):
    for prefix in ("https://www.lilab-ecust.cn", "https://lilab-ecust.cn"):
        url = f"{prefix}/pharmmapper/results/{job}/{job}.csv"
        try:
            response = requests.get(url, timeout=(8, 25))
            if not response.ok:
                continue
            data = response.content
            text = data.decode("utf-8-sig", errors="replace")
            if "<html" in text[:500].lower():
                continue
            records = list(csv.reader(io.StringIO(text)))
            if not any(row and row[0].strip() == "Pharma Model" for row in records):
                continue
            if not any(row and row[0].strip().endswith("_v") for row in records):
                continue
            return data
        except requests.RequestException:
            continue
    return None


def collect_jobs(jobs, progress=None):
    """Check server-generated job IDs, download valid CSVs and return an auditable ZIP."""
    updated = {k: dict(v) for k, v in jobs.items()}
    candidates = [(cid, j["job_id"]) for cid, j in updated.items()
                  if j.get("job_id") and j.get("status") != "COLLECTED"]
    raw = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_job, cid, job): cid for cid, job in candidates}
        for ix, future in enumerate(as_completed(futures), 1):
            cid = futures[future]
            data = future.result()
            if data:
                raw[cid] = data
                updated[cid]["status"] = "COLLECTED"
            if progress:
                progress(ix, len(candidates), cid, updated[cid]["status"])
    # Previously collected rows need original bytes again on subsequent clicks.
    for cid, row in updated.items():
        if row.get("status") == "COLLECTED" and cid not in raw:
            data = _fetch_job(cid, row["job_id"])
            if data:
                raw[cid] = data
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for cid, data in raw.items():
            archive.writestr(f"raw/{cid}_PharmMapper.csv", data)
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(["compound_id", "job_id", "status", "error"])
        for cid, job in updated.items():
            writer.writerow([cid, job.get("job_id", ""), job.get("status", ""),
                             job.get("error", "")])
        archive.writestr("manifest.csv", manifest.getvalue())
    return out.getvalue(), len(raw), updated
