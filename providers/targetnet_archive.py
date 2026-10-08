"""Convert the previously completed TargetNet A0–A16 ZIP into a verified app result.

This is historical data reuse, not a new prediction. Only the exact original
17 reference molecules can use the mapping from Comp.1 through Comp.17.
"""
import base64
import bz2
import csv
import hashlib
import io
import zipfile
from pathlib import Path

from providers.targetnet import split_tsv

ARCHIVE_B64 = Path(__file__).resolve().parents[1] / "data" / "TargetNet_A0_A16_raw.tsv.bz2.b64"
RAW_SHA256 = "831603065abb9448d26cab8a33d1dfdf97822a83b7c89e908b5132f623abcbdc"


def load_bundled_targetnet():
    """Read immutable original TargetNet result matrix and verify exact SHA-256."""
    raw = bz2.decompress(base64.b64decode(ARCHIVE_B64.read_text(encoding="ascii")))
    if len(raw) != 83814 or hashlib.sha256(raw).hexdigest() != RAW_SHA256:
        raise ValueError("Bundled TargetNet matrix is corrupted or altered")
    return raw



def is_reference_targetnet(records):
    from providers.swiss_cached import is_reference_batch
    return is_reference_batch(records)


def reuse_targetnet_zip(source, records):
    if not is_reference_targetnet(records):
        raise ValueError("Historical TargetNet results are only for exact A0–A16 reference SMILES")
    if len(source) > 20_000_000:
        raise ValueError("Archive exceeds 20 MB input limit")
    try:
        with zipfile.ZipFile(io.BytesIO(source)) as original:
            info = original.getinfo("TargetNet_A0_A16_raw.tsv")
            if info.file_size > 3_000_000:
                raise ValueError("TargetNet raw matrix exceeds validation limit")
            raw = original.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("Expected the original TargetNet_A0_A16_raw.tsv in the ZIP") from exc
    if len(raw) < 1000:
        raise ValueError("Archive contains an incomplete TargetNet matrix")
    mapped = split_tsv(raw, records, "https://nanx.app/targetnet/")
    if len(mapped) != 17:
        raise ValueError("Not all 17 compounds were represented")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as result:
        result.writestr("TargetNet_raw.tsv", raw)
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(["compound_id", "status", "target_rows", "method"])
        for record in records:
            cid = record["compound_id"]
            body, count = mapped[cid]
            result.writestr(f"per_compound_csv/{cid}_TargetNet.csv", body)
            writer.writerow([cid, "COLLECTED", count, "HISTORICAL_ZIP_REUSE"])
        result.writestr("manifest.csv", manifest.getvalue())
        result.writestr("README.txt", "Validated original A0–A16 TargetNet matrix; no new server prediction.\n")
    return result.getvalue(), len(mapped), {}


def collect_existing_targetnet(records):
    """Return 17/17 historical target CSVs immediately, without server calls."""
    if not is_reference_targetnet(records):
        raise ValueError("Fast historical TargetNet retrieval requires exact A0–A16 SMILES")
    raw = load_bundled_targetnet()
    mapped = split_tsv(raw, records, "https://nanx.app/targetnet/")
    if len(mapped) != 17 or any(count != 623 for _, count in mapped.values()):
        raise ValueError("Original historical matrix must have 623 target predictions for each of 17 compounds")
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("TargetNet_raw.tsv", raw)
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(["compound_id", "status", "target_rows", "provenance", "raw_sha256"])
        for record in records:
            cid = record["compound_id"]
            body, count = mapped[cid]
            archive.writestr(f"per_compound_csv/{cid}_TargetNet.csv", body)
            writer.writerow([cid, "COLLECTED", count, "EXISTING_PREDICTION", RAW_SHA256])
        archive.writestr("manifest.csv", manifest.getvalue())
        archive.writestr("README.txt",
                         "Original TargetNet A0–A16 results; these are NOT new predictions.\\n"
                         "Raw data SHA-256 verified. Source: nanx.app/targetnet.\\n")
    return result.getvalue(), len(mapped), {}
