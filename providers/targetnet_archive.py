"""Convert the previously completed TargetNet A0–A16 ZIP into a verified app result.

This is historical data reuse, not a new prediction. Only the exact original
17 reference molecules can use the mapping from Comp.1 through Comp.17.
"""
import csv
import io
import zipfile

from providers.targetnet import split_tsv


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
