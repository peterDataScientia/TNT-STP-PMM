# Architecture

**Input** (`compound_id,smiles`, optional SDF path) → **validated manifest** → **provider-specific submit adapter** → **poll adapter** → **raw collector** → **normalizer** → **provenance-preserving ZIP**.

State transitions: `PENDING → SUBMITTING → SUBMITTED → RUNNING → COMPLETE → COLLECTED`. Alternative states: `SUBMISSION_UNKNOWN`, `FAILED`, `EXPIRED`.

`SUBMISSION_UNKNOWN` must be resolved by inspecting provider history rather than resubmitting blindly. Duplicate prevention keys are based on provider, canonical input identifier, configuration and external job ID—not wall-clock timestamps.

Respect concurrency limits and exponential backoff. Use atomic file writes and record immutable raw responses with checksums. Browser automation selectors must be checked against current interfaces. Keep platform-specific files separate and log all transformed targets with tool/version/taxonomy/threshold.
