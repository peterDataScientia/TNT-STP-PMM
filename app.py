"""TNT-STP-PMM Streamlit front end.

This app prepares auditable manifests and imports existing provider results.
Provider execution is disabled until migrated runners pass live verification.
"""
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import streamlit as st

PROVIDERS = ("TargetNet", "SwissTargetPrediction", "PharmMapper")
FIELDS = ("compound_id", "smiles")
st.set_page_config(page_title="TNT–STP–PMM", page_icon="🧬", layout="wide")
st.title("TNT–STP–PMM")
st.caption("TargetNet · SwissTargetPrediction · PharmMapper | Multi-platform human target prediction")
st.info("Preparation and results collection workspace. Automated live submissions are not enabled until provider runners have been audited and tested.")

def parse_compounds(name: str, raw: bytes):
    if len(raw) > 5_000_000:
        raise ValueError("Input exceeds 5 MB limit.")
    if name.lower().endswith(".smi"):
        lines = raw.decode("utf-8-sig").splitlines()
        records = []
        for i, line in enumerate(lines, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            pieces = line.split()
            if not pieces:
                continue
            records.append({"compound_id": pieces[1] if len(pieces) > 1 else f"compound_{i:04d}", "smiles": pieces[0]})
    else:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("CSV requires compound_id and smiles columns.")
        records = [{"compound_id": (r.get("compound_id") or "").strip(), "smiles": (r.get("smiles") or "").strip()} for r in reader]
    if not records:
        raise ValueError("No compounds found.")
    seen = set()
    for r in records:
        cid = r["compound_id"]
        if not cid or not r["smiles"]:
            raise ValueError("Blank compound ID or SMILES.")
        if cid in seen:
            raise ValueError(f"Duplicate compound ID: {cid}")
        if any(ch in cid for ch in "/\\\x00\n\r"):
            raise ValueError(f"Unsafe compound ID: {cid!r}")
        seen.add(cid)
    return records

def create_package(records, providers, digest):
    buf = io.BytesIO()
    manifest = io.StringIO()
    writer = csv.DictWriter(manifest, fieldnames=["provider", "compound_id", "smiles", "status", "job_id", "result_url", "error"])
    writer.writeheader()
    for provider in providers:
        for r in records:
            writer.writerow({"provider": provider, **r, "status": "PENDING", "job_id": "", "result_url": "", "error": ""})
    metadata = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(), "input_sha256": digest, "providers": list(providers), "compound_count": len(records), "execution": "NOT_STARTED"}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.csv", manifest.getvalue())
        z.writestr("metadata.json", json.dumps(metadata, indent=2))
    return buf.getvalue()

tab1, tab2, tab3 = st.tabs(["Prepare batch", "Import results", "About / status"])
with tab1:
    st.subheader("1. Upload compounds")
    uploaded = st.file_uploader("CSV columns: compound_id, smiles; or .smi (SMILES ID)", type=["csv", "smi"])
    selected = st.multiselect("2. Select prediction platforms", PROVIDERS, default=list(PROVIDERS))
    if uploaded:
        raw = uploaded.getvalue()
        try:
            records = parse_compounds(uploaded.name, raw)
            st.success(f"Validated {len(records)} unique compound IDs.")
            st.dataframe(records, use_container_width=True, hide_index=True)
            if selected:
                package = create_package(records, selected, hashlib.sha256(raw).hexdigest())
                st.download_button("Download job manifest ZIP", package, file_name="TNT_STP_PMM_batch.zip", mime="application/zip", type="primary")
                st.caption("Job status is PENDING; downloading does not submit any prediction.")
            else:
                st.warning("Select at least one provider.")
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            st.error(str(exc))
    st.divider()
    st.button("Run predictions", disabled=True, help="Requires verified adapters and persistent worker infrastructure.")

with tab2:
    st.subheader("Import existing completed results")
    st.write("Download raw CSV/ZIP files for local analysis or import an existing archive to inspect its contents. Importing does not create new predictions.")
    results = st.file_uploader("Results ZIP", type=["zip"], key="result_zip")
    if results:
        try:
            data = results.getvalue()
            if len(data) > 100_000_000:
                raise ValueError("Results archive exceeds 100 MB.")
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                valid = [i for i in z.infolist() if not i.is_dir()]
                if len(valid) > 2000 or sum(i.file_size for i in valid) > 500_000_000:
                    raise ValueError("Archive contains too many files or too much decompressed data.")
                names = [i.filename for i in valid]
                st.success(f"Archive inspected: {len(names)} files.")
                st.dataframe([{"file": n} for n in names], hide_index=True, use_container_width=True)
                st.download_button("Download original archive", data, file_name=results.name, mime="application/zip")
        except (zipfile.BadZipFile, ValueError) as exc:
            st.error(str(exc))

with tab3:
    st.markdown("""
    **Working strategy:** Validate → Submit → Track → Collect → Preserve raw exports.

    - **TargetNet:** legacy runner available; live submission not verified in this deployment.
    - **SwissTargetPrediction:** legacy v2 runner available; live submission not verified in this deployment.
    - **PharmMapper:** previous A0–A16 direct result collection succeeded; new submissions not verified.

    Streamlit Community Cloud is suitable for the UI and bounded validation, not guaranteed durable background Playwright execution. A persistent worker, database and storage will be required before enabling job submission.
    """)
