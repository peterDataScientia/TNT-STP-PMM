# TNT–STP–PMM

Reusable compound-to-human-target prediction workflows for **TargetNet (TNT)**, **SwissTargetPrediction (STP)**, and **PharmMapper (PMM)**.

## Status

This repository is being migrated from preserved October 2026 runner packages. **Do not interpret the presence of a runner as proof of successful live submission.**

| Provider | Preserved runner | Evidence | Status |
| --- | --- | --- | --- |
| TargetNet | `TargetNet_A0_A16_runner.zip` | A0–A16 results archive exists | Historical output; live automation not revalidated |
| SwissTargetPrediction | `SwissTarget_A0_A16_runner_v2.zip` | A0–A16 results archive exists | Historical output; live automation not revalidated |
| PharmMapper | `PharmMapper_A0_A16_runner_v5_fresh.zip`; `PharmMapper-Automation-v0.1.0.zip` | Direct collection succeeded for 17/17 existing job IDs | Collector verified historically; submission still needs validation |

## Proven strategy

1. Validate compound identifier, original SMILES and source file.
2. Persist a durable manifest **before** network activity.
3. Submit via the provider's actual supported interface, using Playwright only where necessary.
4. Capture verified job IDs and results URLs. Never infer IDs from time or the order of submissions.
5. Resume polling and download artifacts using direct HTTP endpoints where reliable.
6. Preserve **raw** provider exports, record source/provenance, and generate normalized tables separately.
7. Package raw outputs, per-compound results, manifest, errors and checksums.

## Layout

- `docs/MIGRATION.md`: exact preserved source packages and verification requirements
- `docs/ARCHITECTURE.md`: workflow contracts and safety constraints
- `examples/compounds.csv`: generic example input
- `scripts/validate_compounds.py`: dependency-free input validation and manifest initialization
- `.github/workflows/ci.yml`: offline validation CI

## First run

```bash
python scripts/validate_compounds.py examples/compounds.csv --output runs/demo/manifest.csv
python -m unittest discover -s tests -v
```

**Important:** This initial repository bootstrap is not a functional 3-provider submitter. The original packages still need to be imported and live-tested before this label is warranted.

## Scientific and operational safeguards

Use public provider interfaces in accordance with terms and rate limits. No CAPTCHA bypass, credential collection, or speculative job completion claims. Retain original inputs and output provenance. Do not silently mix protein-level predictions with harmonized unique human gene symbols.


## Streamlit application

The Streamlit frontend is implemented in `app.py` (batch input inspection, provider selection, downloadable audit manifest ZIP, and read-only ZIP inspection).

### Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

### Deploy on Streamlit Community Cloud

1. Open [share.streamlit.io](https://share.streamlit.io) and choose **Create app**.
2. Select `peterDataScientia/TNT-STP-PMM`, branch `main`, and entrypoint `app.py`.
3. Deploy and use the **Prepare batch** tab to produce an auditable manifest.
4. Treat the disabled **Run predictions** control as intentional. A persistent worker plus audited provider adapters must be added before allowing live jobs.

There is **no deployed URL until the app is created on Streamlit Community Cloud**. GitHub pushes alone do not create a Streamlit deployment.

The interface does not upload compounds anywhere except to the Streamlit instance running it. A public Streamlit deployment should not be used for confidential chemical structures unless appropriate access controls are configured.
