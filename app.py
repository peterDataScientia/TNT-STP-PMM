"""TNT-STP-PMM Streamlit dashboard."""
import csv
import io
from pathlib import Path
import streamlit as st
from providers.swiss import run_swiss
from providers.pharmmapper import collect_pharmmapper, JOB_IDS

st.set_page_config(page_title="TNT-STP-PMM", page_icon="🧬", layout="wide")
st.title("TNT–STP–PMM")
st.caption("TargetNet · SwissTargetPrediction · PharmMapper")

EXAMPLE = Path(__file__).resolve().parent / "examples" / "compounds.csv"

def read_compounds(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or not {"compound_id", "smiles"}.issubset(reader.fieldnames):
        raise ValueError("CSV requires compound_id and smiles columns")
    rows = [{"compound_id": (x.get("compound_id") or "").strip(),
             "smiles": (x.get("smiles") or "").strip()} for x in reader]
    ids = [x["compound_id"] for x in rows]
    if not rows or any(not x["compound_id"] or not x["smiles"] for x in rows):
        raise ValueError("Compound IDs and SMILES must not be empty")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate compound IDs")
    return rows

st.subheader("Compounds | EMNE and analogues A0–A16")
st.write("The 17 original research compounds are loaded by default. Upload a CSV to replace them.")
col1, col2 = st.columns(2)
with col1:
    st.download_button("Download Example CSV (EMNE A0–A16)", EXAMPLE.read_bytes(),
                       file_name="example_compounds_A0_A16.csv", mime="text/csv")
with col2:
    if st.button("Load original A0–A16 compounds"):
        st.session_state.pop("swiss_result", None)
        st.session_state.pop("pharm_result", None)
        st.session_state["use_reference"] = True
        st.rerun()

uploaded = st.file_uploader("Or upload your own CSV (compound_id, smiles)", type=["csv"])
try:
    if uploaded is not None and not st.session_state.get("use_reference", False):
        if uploaded.size > 5_000_000:
            raise ValueError("Upload exceeds 5 MB")
        records = read_compounds(uploaded.getvalue())
        source = "Uploaded CSV"
    else:
        records = read_compounds(EXAMPLE.read_bytes())
        source = "EMNE reference A0–A16"
    st.success(f"{len(records)} compounds loaded — {source}")
    st.dataframe(records, use_container_width=True, hide_index=True, height=440)
except (ValueError, UnicodeDecodeError, csv.Error) as exc:
    st.error(str(exc))
    records = []

if uploaded is None:
    st.session_state["use_reference"] = False

swiss_tab, pharm_tab, target_tab = st.tabs(["SwissTargetPrediction", "PharmMapper", "TargetNet"])
with swiss_tab:
    st.subheader("SwissTargetPrediction")
    st.caption("Attempts actual target prediction; external website compatibility is not guaranteed.")
    if records and st.button(f"Run SwissTargetPrediction for {len(records)} compounds", type="primary"):
        st.session_state.pop("swiss_result", None)
        bar = st.progress(0)
        status = st.empty()
        def update(done, total, cid, state):
            bar.progress(done / total)
            status.info(f"{done}/{total} — {cid}: {state}")
        try:
            archive, count, errors = run_swiss(records, update)
            st.session_state["swiss_result"] = (archive, count, errors)
        except Exception as exc:
            st.error(f"Prediction request failed: {exc}")
    if "swiss_result" in st.session_state:
        archive, count, errors = st.session_state["swiss_result"]
        st.write(f"Results collected: {count}; failures: {len(errors)}")
        if errors:
            st.error(errors)
        st.download_button("Download SwissTargetPrediction ZIP", archive,
                           file_name="SwissTargetPrediction_results.zip", mime="application/zip")
with pharm_tab:
    st.subheader("PharmMapper | Existing A0–A16 jobs")
    st.caption("Downloads existing job results only. Does not submit new jobs.")
    if st.button("Collect the 17 historical PharmMapper jobs"):
        bar = st.progress(0)
        status = st.empty()
        def update_p(done, total, cid, state):
            bar.progress(done / total)
            status.info(f"{done}/{total} — {cid}: {state}")
        try:
            st.session_state["pharm_result"] = collect_pharmmapper(update_p)
        except Exception as exc:
            st.error(f"Collection failed: {exc}")
    if "pharm_result" in st.session_state:
        archive, count, errors = st.session_state["pharm_result"]
        st.write(f"Collected {count}/{len(JOB_IDS)} CSVs")
        if errors:
            st.error(errors)
        st.download_button("Download PharmMapper results ZIP", archive,
                           file_name="PharmMapper_A0_A16_results.zip", mime="application/zip")
with target_tab:
    st.subheader("TargetNet")
    st.warning("Live TargetNet Playwright runner has not yet been integrated.")
st.caption("Collection status is based on actual responses, not assumed completion.")
