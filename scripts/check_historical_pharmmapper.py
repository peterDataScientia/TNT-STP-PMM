"""Collect previously completed PharmMapper jobs; never submit predictions."""
from pathlib import Path
import csv
import io
import json
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providers.pharmmapper import collect_pharmmapper, JOB_IDS

def main():
    payload, n, errors = collect_pharmmapper()
    dest = Path("artifacts")
    dest.mkdir(exist_ok=True)
    (dest / "PharmMapper_A0_A16_collected.zip").write_bytes(payload)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith("_PharmMapper.csv")]
        manifest = list(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode())))
    print(json.dumps({"collected": n, "expected": len(JOB_IDS), "csv_files": len(names), "errors": errors}, indent=2))
    if len(manifest) != 17 or n != 17 or len(names) != 17:
        sys.exit(1)

if __name__ == "__main__":
    main()
