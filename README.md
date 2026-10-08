# TNT–STP–PMM

Streamlit web app for **real target prediction and result collection** through **TargetNet**, **SwissTargetPrediction**, and **PharmMapper**. The example CSV contains the original **17 EMNE analogues (A0–A16)**.

## Use the app

1. Open the Streamlit deployment and keep **Use built-in EMNE A0–A16** selected, or uncheck it and upload any CSV with `compound_id,smiles`.
2. **SwissTargetPrediction:** choose **Collect existing 17** to reuse previously computed A0–A16 jobs, or expand **Submit NEW SwissTargetPrediction jobs** for new predictions. The new-job adapter drives Chromium and captures confirmed result IDs, target tables, and CSVs.
3. **TargetNet:** click **Run TargetNet** to upload the selected SMILES as a single batch; only after a verified raw TSV download does the app create per-compound CSVs.
4. **PharmMapper:** provide your own notification email, click **Submit pending PharmMapper jobs**, save the downloadable **job checkpoint JSON**, and later click **Check and collect completed jobs**. The app builds 3D SDF V2000 from SMILES using RDKit and will not exceed ten potentially active jobs.
5. Download ZIP archives of **actual returned** results; incomplete or unknown submissions must not be mistaken for successful predictions.

### What is new

- `providers/targetnet.py`: actual Playwright upload → model evaluation → raw TSV → per-compound CSVs
- `providers/swiss.py`: actual browser-driven predictions for arbitrary SMILES; fail-fast reporting with no fabricated URLs
- `providers/swiss_cached.py`: fast *reuse* for the exact historical A0–A16 inputs (this is **not a new prediction**)
- `providers/pharmmapper_live.py`: new SDF preparation, Human Protein Targets Only selection, guarded submission, job ID capture, collection and checkpoint support
- `providers/pharmmapper.py`: previous job collector for the original A0–A16 panel
- `examples/compounds.csv`: A0–A16 SMILES used by the original study

## Deploy on Streamlit Community Cloud

At [share.streamlit.io](https://share.streamlit.io), create or update the app using:

- Repository: `peterDataScientia/TNT-STP-PMM`
- Branch: `main`
- Main file: `app.py`

The `requirements.txt` installs Streamlit, Playwright, Requests, BeautifulSoup, RDKit. `packages.txt` requests Linux Chromium. Code pushed to GitHub is **not by itself proof of live Streamlit deployment**.

### Run on a suitable Linux/Windows server

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
streamlit run app.py
```

Chromium must be installed and permitted on the hosting environment.

## Performance and persistence

Remote computation has no instant shortcut for **new** SMILES. TargetNet computes a batch on its server; SwissTargetPrediction calculates a job per compound; PharmMapper queues remote 3D predictions. Browser startup, provider queues and network latency may make these tasks take minutes. The **FAST** Swiss option only retrieves already-completed A0–A16 results.

**Streamlit Community Cloud is not a durable job worker.** PharmMapper checkpoint JSON protects recognized job IDs across sessions when the user downloads it. If the server restarts while a final submission is in flight, confirm the result from the provider before resubmitting. Do not claim completion from a `PENDING` manifest or any arbitrary HTTP response.

## Tests and verification

GitHub Actions checks Python compilation, example validation and unit tests of TargetNet column mapping, Swiss target-row completeness and PharmMapper job ID rules. **Live end-to-end execution of all three providers on the user's deployment remains to be confirmed**; third-party site markup, rate limits and Cloud browser support can change.

The original local runner ZIPs are inventoried in [docs/MIGRATION.md](docs/MIGRATION.md). The new adapters are based on their working workflows; no claim is made that every legacy source file has been imported unchanged.

## Research integrity

Store raw outputs and source URLs. Keep species, provider, model threshold, job ID and errors with each result. Swiss/TargetNet probability and PharmMapper z-score are separate quantities. A submitted job is not a completed prediction. Follow each provider's terms, don't bypass access checks, and don't expose unpublished molecular structures or email addresses on public deployments.
