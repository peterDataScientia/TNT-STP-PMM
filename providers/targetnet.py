"""TargetNet: real Shiny batch upload and verified download (legacy-tested selectors)."""
import csv
import io
import tempfile
import zipfile
from pathlib import Path

from providers.swiss import _launch_browser

MIRRORS = ("https://nanx.app/targetnet/", "https://nanx.shinyapps.io/targetnet/")
FIELDS = [
    "compound_id", "smiles", "Target_UniProt_ID", "UniProt_Name",
    "Probability", "Model_Criterion", "Model_Threshold", "Source_URL"
]

def split_tsv(raw, compounds, source_url):
    """Validate TargetNet's exact Comp.N mapping before creating per-compound CSVs."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
    fields = reader.fieldnames or []
    expected = [f"Comp.{i}" for i in range(1, len(compounds) + 1)]
    if "Target" not in fields or any(col not in fields for col in expected):
        raise ValueError(f"Invalid TargetNet download: expected Target and {expected}; got {fields}")
    rows = list(reader)
    if not rows:
        raise ValueError("TargetNet returned no target predictions")
    result = {}
    for index, compound in enumerate(compounds, 1):
        col = f"Comp.{index}"
        document = io.StringIO()
        writer = csv.writer(document)
        writer.writerow(FIELDS)
        count = 0
        for row in rows:
            value = (row.get(col) or "").strip()
            try:
                score = float(value)
            except ValueError:
                continue
            if not (0 <= score <= 1):
                continue
            writer.writerow([
                compound["compound_id"], compound["smiles"],
                row.get("Target", ""), row.get("UniProt.Name", ""),
                score, "AUC", "0.75", source_url,
            ])
            count += 1
        if not count:
            raise ValueError(f"No numeric target scores for {compound['compound_id']}")
        result[compound["compound_id"]] = (document.getvalue(), count)
    return result



def configure_auc_filter(page):
    """Configure hidden Selectize-backed Shiny input without select_option().

    Selectize hides the underlying <select>, which Playwright refuses to act on
    as a visible control. Shiny's input binding receives change from setValue.
    """
    return page.eval_on_selector(
        "#criterionupload",
        """element => {
            const options = Array.from(element.options);
            const option = options.find(o => o.value.toLowerCase() === 'auc');
            if (!option) throw new Error('AUC is not an available criterion');
            const before = element.selectize
                ? element.selectize.getValue()
                : element.value;
            if (String(before).toLowerCase() !== 'auc') {
                if (element.selectize) {
                    element.selectize.setValue(option.value);
                } else {
                    element.value = option.value;
                    element.dispatchEvent(new Event('change', {bubbles:true}));
                }
            }
            const after = element.selectize
                ? element.selectize.getValue()
                : element.value;
            if (String(after).toLowerCase() !== 'auc')
                throw new Error('AUC selection failed');
            return String(after);
        }""",
    )


def run_targetnet(compounds, progress=None):
    """One real TargetNet server batch; no result is declared until the TSV validates."""
    from playwright.sync_api import sync_playwright
    if not compounds:
        raise ValueError("No compounds")
    with tempfile.TemporaryDirectory(prefix="tnt_") as folder:
        path = Path(folder) / "compounds.smi"
        # The TargetNet file format requires one SMILES per line, no IDs.
        path.write_text("\n".join(r["smiles"] for r in compounds) + "\n", encoding="utf-8")
        with sync_playwright() as playwright:
            if progress:
                progress(0, 1, "TargetNet", "OPENING")
            browser = _launch_browser(playwright)
            try:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(20000)
                last_error = None
                active_url = None
                for url in MIRRORS:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=50000)
                        page.get_by_role("link", name="Upload", exact=True).click(timeout=12000)
                        page.locator("#file1").wait_for(state="attached", timeout=25000)
                        active_url = url
                        break
                    except Exception as exc:
                        last_error = str(exc)
                if not active_url:
                    raise RuntimeError(f"TargetNet mirrors unavailable: {last_error}")

                page.locator("#file1").set_input_files(str(path))
                # Actual widget is Selectize-enhanced; the original select is hidden.
                configure_auc_filter(page)
                if progress:
                    progress(0, 1, "TargetNet", "PREDICTING")
                page.locator("#netButtonUpload").click()
                page.wait_for_function(
                    """() => {
                      const el = document.querySelector('#tablepred');
                      if (!el) return false;
                      const rows = el.querySelectorAll('table tbody tr');
                      const text = (el.innerText || '').toLowerCase();
                      return rows.length > 0 && !text.includes('processing');
                    }""",
                    timeout=900000,
                )
                with page.expect_download(timeout=90000) as download_event:
                    page.locator("#downloadpredTSV").click()
                download = download_event.value
                destination = Path(folder) / "raw.tsv"
                download.save_as(str(destination))
                raw = destination.read_bytes()
                per_compound = split_tsv(raw, compounds, active_url)

                result = io.BytesIO()
                with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("TargetNet_raw.tsv", raw)
                    manifest = io.StringIO()
                    writer = csv.writer(manifest)
                    writer.writerow(["compound_id", "status", "target_rows", "source_url"])
                    for compound in compounds:
                        cid = compound["compound_id"]
                        data, count = per_compound[cid]
                        archive.writestr(f"per_compound_csv/{cid}_TargetNet.csv", data)
                        writer.writerow([cid, "COLLECTED", count, active_url])
                    archive.writestr("manifest.csv", manifest.getvalue())
                if progress:
                    progress(1, 1, "TargetNet", "COLLECTED")
                return result.getvalue(), len(compounds), {}
            finally:
                browser.close()
