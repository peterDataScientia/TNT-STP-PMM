#!/usr/bin/env python3
"""Validate compound inputs and initialize a safe, resumable manifest (standard library)."""
import argparse
import csv
import os
from pathlib import Path

FIELDS = ("compound_id", "smiles")
OUT_FIELDS = ("compound_id", "smiles", "status", "job_id", "result_url", "error")

def validate(source: Path):
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("CSV must have compound_id and smiles headers")
        records, seen = [], set()
        for line, row in enumerate(reader, start=2):
            compound_id = (row.get("compound_id") or "").strip()
            smiles = (row.get("smiles") or "").strip()
            if not compound_id or not smiles:
                raise ValueError(f"Line {line}: blank compound_id or smiles")
            if compound_id in seen:
                raise ValueError(f"Line {line}: duplicate compound_id {compound_id!r}")
            if any(ch in compound_id for ch in "/\\\\\x00\r\n"):
                raise ValueError(f"Line {line}: unsafe compound_id")
            seen.add(compound_id)
            records.append({"compound_id": compound_id, "smiles": smiles,
                            "status": "PENDING", "job_id": "", "result_url": "", "error": ""})
    if not records:
        raise ValueError("No input compounds")
    return records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = validate(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit("Manifest already exists: refusing to overwrite resumable state")
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUT_FIELDS)
            writer.writeheader()
            writer.writerows(records)
        os.replace(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Created {args.output} for {len(records)} compounds")

if __name__ == "__main__":
    main()
