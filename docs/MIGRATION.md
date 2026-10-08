# Legacy source preservation and audit

Source packages were found in the user's ChatGPT Library (created October 6, 2026). They are **not yet committed** in this repository.

| Source archive | Relevant components |
| --- | --- |
| `SwissTarget_A0_A16_runner_v2.zip` | `run_swisstarget_fast_v2.py`, example input and README |
| `TargetNet_A0_A16_runner.zip` | `run_targetnet_playwright.py`, input and README |
| `PharmMapper_A0_A16_runner_v5_fresh.zip` | `run_pharmmapper.py`, 17 SDF structures and metadata |
| `PharmMapper-Automation-v0.1.0.zip` | package modules (submitter, collector, db, parser, CLI), configuration and unit tests |
| `PharmMapper_collection_code.zip` | `collect_pharmmapper_A0_A16.py` and collection assets |

## What was verified historically

- PharmMapper collected CSV for each of the 17 existing A0–A16 job IDs using direct requests.
- SwissTargetPrediction and TargetNet produced A0–A16 results ZIPs; this does **not** establish that every submit/track step is reproducible.
- Existing PharmMapper automated submission and job-ID recovery require stricter live end-to-end verification.

## Migration acceptance checklist

- [ ] Import original source files *unchanged* under `legacy/` for provenance.
- [ ] Review dependencies, licenses, secrets and filesystem assumptions.
- [ ] Compare every input compound ID, SMILES and SDF mapping.
- [ ] Unit-test parsing, URL capture, request retry and database resume.
- [ ] Run opt-in, rate-limited smoke tests for each public provider.
- [ ] Preserve raw CSVs and report failed compounds without fabrication.
- [ ] Only then promote provider implementations to `src/` as stable.

Never upload provider credentials, browser profiles, access cookies, local state databases or unpublished sensitive datasets.
