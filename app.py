"""TNT STP PMM: prediction and result collection dashboard."""
import csv
import io
from pathlib import Path

import streamlit as st
from providers.swiss import run_swiss
from providers.pharmmapper import collect_pharmmapper, JOB_IDS

st.set_page_config(page_title="TNT-STP-PMM", page_icon="🧬", layout="wide")
st.title("TNT–STP–PMM")
st.caption("TargetNet · SwissTargetPrediction · PharmMapper")

example_path = Path(__file__).parent / "examples" / "A0_A16_compounds.csv"
st.download_button(
    "Download A0–A16 Example CSV",
    example_path.read_bytes(),
    file_name="TNT_STP_PMM_A0_A16_compounds.csv",
    mime="text/csv",
)
uploaded = st.file_uploader("Upload compounds CSV (compound_id, smiles)", type=["csv"])
records = []
if uploaded:
    try:
        if uploaded.size > 5_000_000:
            raise ValueError("CSV file exceeds 5 MB limit")
        reader = csv.DictReader(io.StringIO(uploaded.getvalue().decode("utf-8-sig")))
        if not reader.fieldnames or not {"compound_id", "smiles"}.issubset(reader.fieldnames):
            raise ValueError("CSV must have compound_id and smiles columns")
        records = [
            {"compound_id": (row.get("compound_id") or "").strip(),
             "smiles": (row.get("smiles") or "").strip()}
            for row in reader
        ]
        ids = [r["compound_id"] for r in records]
        if not ids or any(not r["compound_id"] or not r["smiles"] for r in records):
            raise ValueError("Compound IDs and SMILES are required")
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate compound IDs found")
        st.success(f"{len(records)} compounds loaded")
        st.dataframe(records, hide_index=True, use_container_width=True)
    except (ValueError, UnicodeDecodeError, csv.Error) as err:
        st.error(str(err))
        records = []

t_swiss, t_pharm, t_target = st.tabs(["SwissTargetPrediction", "PharmMapper", "TargetNet"])
with t_swiss:
    st.subheader("SwissTargetPrediction | Human protein targets")
    st.write("Runs real online submissions and downloads returned predictions for each compound. Allow time for the external service to respond.")
    if records and st.button("Run SwissTargetPrediction", type="primary"):
        bar = st.progress(0)
        status = st.empty()
        def update(done, total, compound, state):
            bar.progress(done / total)
            status.info(f"{done}/{total} — {compound}: {state}")
        try:
            with st.spinner("Submitting compounds and collecting returned target tables"):
                archive, success, failures = run_swiss(records, update)
            st.session_state["swiss_result"] = (archive, success, failures)
        except Exception as exc:
            st.error(f"SwissTargetPrediction execution failed: {exc}")
    if "swiss_result" in st.session_state:
        archive, success, failures = st.session_state["swiss_result"]
        st.write(f"Successfully collected: {success}; Failed: {len(failures)}")
        if failures:
            st.error(failures)
        st.download_button("Download SwissTargetPrediction ZIP", archive, file_name="SwissTargetPrediction_results.zip", mime="application/zip")
with t_pharm:
    st.subheader("PharmMapper | Collect confirmed A0–A16 jobs")
    st.write("This operation downloads real results from previously submitted PharmMapper jobs. It does NOT submit new jobs.")
    st.caption("Only the historical A0–A16 job IDs are supported in this collector.")
    if st.button("Collect A0–A16 PharmMapper results"):
        bar = st.progress(0)
        status = st.empty()
        def update_p(done, total, compound, state):
            bar.progress(done / total)
            status.info(f"{done}/{total} — {compound}: {state}")
        try:
            archive, success, failures = collect_pharmmapper(update_p)
            st.session_state["pharm_result"] = (archive, success, failures)
        except Exception as exc:
            st.error(f"PharmMapper collection failed: {exc}")
    if "pharm_result" in st.session_state:
        archive, success, failures = st.session_state["pharm_result"]
        st.write(f"CSV files collected: {success}/{len(JOB_IDS)}")
        if failures:
            st.error(failures)
        st.download_button("Download PharmMapper ZIP", archive, file_name="PharmMapper_A0_A16_results.zip", mime="application/zip")
with t_target:
    st.subheader("TargetNet")
    st.warning("The historic TargetNet Playwright runner still requires migration and a browser-enabled worker. No live submission is claimed.")
    st.write("The working reference batch is saved as the A0–A16 example CSV above.")

st.divider()
st.caption("Outputs reflect actual remote responses. A failed submission is reported as failed, never as completed.")
