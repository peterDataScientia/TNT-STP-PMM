"""TNT–STP–PMM: submit new compounds, track jobs and collect actual target predictions."""
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import streamlit as st
from providers.swiss_http import run_swiss
from providers.swiss_cached import collect_existing_swiss, is_reference_batch
from providers.targetnet import run_targetnet
from providers.targetnet_archive import collect_existing_targetnet
from providers.pharmmapper import collect_pharmmapper, JOB_IDS
from providers.pharmmapper_live import submit_pending, collect_jobs, LIMIT

st.set_page_config(page_title="TNT–STP–PMM", page_icon="🧬", layout="wide")
ROOT = Path(__file__).resolve().parent
EXAMPLE = ROOT / "examples" / "compounds.csv"

def parse_csv(raw):
    if len(raw) > 5_000_000:
        raise ValueError("Maximum CSV size is 5 MB")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or not {"compound_id", "smiles"}.issubset(reader.fieldnames):
        raise ValueError("CSV must contain compound_id and smiles columns")
    data = [{"compound_id": (row.get("compound_id") or "").strip(),
             "smiles": (row.get("smiles") or "").strip()} for row in reader]
    names = [row["compound_id"] for row in data]
    if not data or any(not r["compound_id"] or not r["smiles"] for r in data):
        raise ValueError("Every row needs an ID and SMILES")
    if len(set(names)) != len(names):
        raise ValueError("Duplicate compound IDs")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", name) for name in names):
        raise ValueError("IDs may contain only letters, numbers, _, - and .")
    return data

@st.cache_data(ttl=3600, show_spinner=False)
def get_existing_pharmmapper():
    return collect_pharmmapper()

@st.cache_data(ttl=3600, show_spinner=False)
def get_existing_swiss(items):
    return collect_existing_swiss([{"compound_id": cid, "smiles": smi} for cid, smi in items])

def show_result(name, key, filename):
    record = st.session_state.get(key)
    if not record:
        return
    binary, successes, problems = record[:3]
    st.metric("Successfully collected", successes)
    if problems:
        st.error(f"{len(problems)} failed; see errors or ZIP manifest")
        st.json(problems)
    st.download_button(f"Download {name} ZIP", binary,
                       file_name=filename, mime="application/zip", key=f"download_{key}")

def progress_view():
    bar = st.progress(0)
    line = st.empty()
    def update(done, total, compound, stage):
        if total:
            bar.progress(min(1.0, done / total))
        line.caption(f"{compound}: {stage}")
    return update

st.title("TNT–STP–PMM")
st.caption("TargetNet · SwissTargetPrediction · PharmMapper | Human target prediction")

left, right = st.columns(2)
with left:
    st.download_button("Download Example CSV (EMNE A0–A16)",
                       EXAMPLE.read_bytes(), file_name="EMNE_A0_A16.csv", mime="text/csv")
with right:
    use_reference = st.checkbox("Use built-in EMNE A0–A16 compounds", value=True)

uploaded = st.file_uploader("Upload different compounds (CSV: compound_id,smiles)",
                            type=["csv"], disabled=use_reference)
try:
    if use_reference:
        records = parse_csv(EXAMPLE.read_bytes())
        label = "Original EMNE A0–A16"
    elif uploaded:
        records = parse_csv(uploaded.getvalue())
        label = uploaded.name
    else:
        records, label = [], "No input"
except (UnicodeError, csv.Error, ValueError) as exc:
    st.error(str(exc))
    records, label = [], "Invalid input"

fingerprint = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
if st.session_state.get("panel_signature") != fingerprint:
    for key in ("swiss_output", "targetnet_output", "pmm_jobs", "pmm_output", "pmm_historical"):
        st.session_state.pop(key, None)
    st.session_state["panel_signature"] = fingerprint

if records:
    st.success(f"{len(records)} compounds loaded — {label}")
    with st.expander("View loaded compounds", expanded=False):
        st.dataframe(records, use_container_width=True, hide_index=True)

swiss_tab, target_tab, pharm_tab = st.tabs([
    "SwissTargetPrediction", "TargetNet", "PharmMapper"
])

with swiss_tab:
    st.subheader("SwissTargetPrediction — Homo sapiens")
    reference = bool(records) and is_reference_batch(records)
    if reference:
        st.caption("The exact A0–A16 predictions have already been computed; their original jobs can be retrieved without new submissions.")
        if st.button("Collect existing 17 Swiss results (FAST)", type="primary"):
            st.session_state.pop("swiss_output", None)
            try:
                with st.spinner("Fetching existing Swiss target tables"):
                    bundle, ok, failed = get_existing_swiss(
                        tuple((item["compound_id"], item["smiles"]) for item in records))
                st.session_state["swiss_output"] = (bundle, ok, failed)
            except Exception as exc:
                st.error(f"Retrieval error: {exc}")
    with st.expander("Submit NEW SwissTargetPrediction jobs", expanded=not reference):
        st.caption("Requires remote calculation by SwissTargetPrediction. No local shortcut exists for new molecules.")
        if records and st.button(f"Submit {len(records)} new Swiss predictions"):
            st.session_state.pop("swiss_output", None)
            try:
                bundle, ok, failed = run_swiss(records, progress_view())
                st.session_state["swiss_output"] = (bundle, ok, failed)
            except Exception as exc:
                st.error(f"Submission error: {exc}")
    show_result("SwissTargetPrediction", "swiss_output", "SwissTargetPrediction_targets.zip")

with target_tab:
    st.subheader("TargetNet — Human target prediction")
    if records and is_reference_batch(records):
        st.success("Original A0–A16 TargetNet results are bundled in the app (623 targets per compound).")
        if st.button("Get 17 completed TargetNet results (FAST)", type="primary"):
            try:
                st.session_state["targetnet_output"] = collect_existing_targetnet(records)
            except Exception as exc:
                st.error(f"Cannot validate archived TargetNet matrix: {exc}")
    with st.expander("Run a NEW TargetNet prediction batch", expanded=bool(records) and not is_reference_batch(records)):
        st.caption("One batch upload to the TargetNet server. Source models are filtered by AUC ≥ 0.75; raw matrix and per-compound CSVs are retained.")
        if records and st.button(f"Run TargetNet for {len(records)} compounds", type="primary"):
            st.session_state.pop("targetnet_output", None)
            try:
                bundle, ok, failed = run_targetnet(records, progress_view())
                st.session_state["targetnet_output"] = (bundle, ok, failed)
            except Exception as exc:
                st.error(f"TargetNet execution failed: {exc}")
    show_result("TargetNet", "targetnet_output", "TargetNet_predictions.zip")

with pharm_tab:
    st.subheader("PharmMapper — Human target prediction")
    if reference:
        st.success("All 17 original A0–A16 PharmMapper job IDs are already confirmed.")
        if st.button("Get 17 completed PharmMapper results (FAST)", type="primary"):
            try:
                archive, count, errors = get_existing_pharmmapper()
                st.session_state["pmm_historical"] = (archive, count, errors)
            except Exception as exc:
                st.error(f"PharmMapper retrieval failed: {exc}")
        show_result("Historical PharmMapper", "pmm_historical",
                    "PharmMapper_A0_A16_historical.zip")
        st.divider()
        allow_submit = st.checkbox(
            "Submit NEW PharmMapper jobs for the same A0–A16 compounds",
            value=False,
            help="These original molecules already have completed jobs. Enabling this will make new submissions.",
        )
    else:
        allow_submit = True
    st.caption("For new jobs: prepare 3D SDF V2000, submit at most 10 active jobs, save job IDs and collect results later.")
    email = st.text_input("Required PharmMapper notification email", value="",
                          placeholder="you@example.com", key="pmm_email")
    st.caption("PharmMapper requires a valid email address before accepting a new job; it is not included in result downloads.")
    if not email.strip():
        st.info("Enter your email to enable new PharmMapper submissions. Completed historical A0–A16 results can be downloaded below without resubmitting.")
    jobs = st.session_state.get("pmm_jobs", {})
    if not isinstance(jobs, dict):
        jobs = {}

    restore = st.file_uploader("Restore your previous job checkpoint (JSON)",
                               type=["json"], key="restore_jobs")
    if restore and st.button("Load saved PharmMapper jobs"):
        try:
            parsed = json.loads(restore.getvalue())
            if parsed.get("input_sha256") != fingerprint:
                raise ValueError("Checkpoint does not match the currently loaded compounds")
            recovered = parsed.get("jobs", {})
            if not isinstance(recovered, dict):
                raise ValueError("Invalid checkpoint")
            for cid, entry in recovered.items():
                if cid not in {r["compound_id"] for r in records}:
                    raise ValueError("Unexpected compound ID")
                if entry.get("status") not in ("SUBMITTED", "SUBMISSION_UNKNOWN", "COLLECTED", "FAILED"):
                    raise ValueError("Invalid status")
                job = entry.get("job_id", "")
                if job and not re.fullmatch(r"\d{12}", job):
                    raise ValueError("Invalid job ID")
            st.session_state["pmm_jobs"] = recovered
            st.success("Saved job IDs recovered without resubmission")
            jobs = recovered
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            st.error(str(exc))

    active = sum(j.get("status") in ("SUBMITTED", "SUBMISSION_UNKNOWN") for j in jobs.values())
    pending = sum(r["compound_id"] not in jobs or jobs[r["compound_id"]].get("status") == "FAILED" for r in records)
    if allow_submit:
        st.write(f"New-job queue: {pending} · Active/unknown: {active}/{LIMIT} · Recorded: {len(jobs)}")
    else:
        st.caption("New submissions disabled. Use FAST collection above for the existing 17 results.")
    c1, c2 = st.columns(2)
    with c1:
        if records and st.button("Submit pending PharmMapper jobs", type="primary",
                                 disabled=(not allow_submit) or (not email.strip()) or pending == 0 or active >= LIMIT):
            try:
                jobs = submit_pending(records, email, jobs, progress_view(),
                                      on_checkpoint=lambda snapshot: st.session_state.__setitem__("pmm_jobs", snapshot))
                st.session_state["pmm_jobs"] = jobs
                failed_now = [(cid, entry.get("error", "")) for cid, entry in jobs.items()
                              if entry.get("status") in ("FAILED", "SUBMISSION_UNKNOWN")]
                if failed_now:
                    st.error(f"{failed_now[0][0]} submission failed: {failed_now[0][1]}")
            except Exception as exc:
                st.error(f"PharmMapper submission error: {exc}")
    with c2:
        if jobs and st.button("Check and collect completed jobs"):
            try:
                archive, collected, jobs = collect_jobs(jobs, progress_view())
                st.session_state["pmm_jobs"] = jobs
                st.session_state["pmm_output"] = (archive, collected, {})
            except Exception as exc:
                st.error(f"PharmMapper collection error: {exc}")

    jobs = st.session_state.get("pmm_jobs", {})
    if jobs:
        st.dataframe([
            {"compound_id": cid,
             "job_id": details.get("job_id", ""),
             "status": details.get("status", ""),
             "error": details.get("error", "")}
            for cid, details in jobs.items()
        ], hide_index=True, use_container_width=True)
        # Recovery does not submit another job. Confirm IDs only from the
        # provider's job page or notification email; do not infer from time.
        unknown_ids = [cid for cid, row in jobs.items()
                       if row.get("status") == "SUBMISSION_UNKNOWN"]
        if unknown_ids:
            st.warning(
                "PharmMapper may already have accepted these jobs. "
                "Do NOT resubmit. Check the confirmation email or Job Check page."
            )
            with st.expander("Recover previously submitted job (NO resubmission)",
                             expanded=True):
                recover_cid = st.selectbox("Compound with unknown submission",
                                            unknown_ids, key="recover_cid")
                recovered_id = st.text_input(
                    "Job ID copied from PharmMapper (12 digits)",
                    max_chars=12, key="recover_job_id"
                )
                if st.button("Attach recovered job ID without resubmitting"):
                    from providers.pharmmapper_live import _valid_job
                    if not _valid_job(recovered_id):
                        st.error("Invalid 12-digit PharmMapper job ID.")
                    elif any(r.get("job_id") == recovered_id
                             for k, r in jobs.items() if k != recover_cid):
                        st.error("The job ID is already attached to another compound.")
                    else:
                        jobs[recover_cid]["job_id"] = recovered_id
                        jobs[recover_cid]["verification"] = "user_provided"
                        jobs[recover_cid]["error"] = (
                            "Recovered job ID entered manually; "
                            "verify by collecting the actual server result."
                        )
                        st.session_state["pmm_jobs"] = dict(jobs)
                        st.success(
                            "Job ID attached. No new job submitted. "
                            "Use Check and collect completed jobs."
                        )
            details = jobs.get(unknown_ids[0], {}).get("diagnostics")
            if details:
                with st.expander("Why job ID confirmation failed"):
                    st.json(details)
        snapshot = json.dumps({"input_sha256": fingerprint, "jobs": jobs}, indent=2)
        st.download_button("Save PharmMapper job checkpoint", snapshot,
                           file_name="PharmMapper_jobs.json", mime="application/json")
        unknown = [cid for cid, row in jobs.items() if row.get("status") == "SUBMISSION_UNKNOWN"]
        if unknown:
            st.error("Job ID not confirmed for " + ", ".join(unknown) +
                     ". Check PharmMapper email/job history before any resubmission.")
    show_result("PharmMapper", "pmm_output", "PharmMapper_collected_jobs.zip")


st.divider()
st.caption("Only server-confirmed predictions are marked COLLECTED. Streamlit Community Cloud is not a durable background worker: download PharmMapper checkpoints to resume after a server restart.")
