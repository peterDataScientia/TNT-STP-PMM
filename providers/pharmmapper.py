"""Real result collection for known PharmMapper A0–A16 jobs."""
import csv
import io
import zipfile
import requests

JOB_IDS = {
    "A0":"261006070604","A1":"261006070634","A2":"261006070700",
    "A3":"261006070727","A4":"261006070757","A5":"261006070826",
    "A6":"261006070854","A7":"261006070919","A8":"261006070946",
    "A9":"261006071017","A10":"261006074735","A11":"261006081553",
    "A12":"261006081635","A13":"261006081705","A14":"261006081740",
    "A15":"261006081812","A16":"261006081851"
}

def collect_pharmmapper(progress=None):
    """Fetch actual existing job results; never claim new jobs were submitted."""
    buf = io.BytesIO()
    failures = {}
    successes = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for index, (panel, job_id) in enumerate(JOB_IDS.items(), 1):
            try:
                source = f"https://www.lilab-ecust.cn/pharmmapper/results/{job_id}/{job_id}.csv"
                resp = requests.get(source, timeout=40, headers={"Accept":"text/csv,text/plain,*/*"})
                resp.raise_for_status()
                data = resp.content.decode("utf-8-sig", errors="replace")
                if "Pharma Model" not in data or "zscore" not in data:
                    raise ValueError("Response was not a PharmMapper CSV")
                z.writestr(f"raw/{panel}_{job_id}.csv", resp.content)
                successes.append((panel,job_id,source))
                status="COLLECTED"
            except Exception as exc:
                failures[panel]=str(exc)
                status="FAILED"
            if progress:
                progress(index,len(JOB_IDS),panel,status)
        manifest=io.StringIO()
        writer=csv.writer(manifest)
        writer.writerow(["panel_id","job_id","status","result_csv_url","error"])
        for panel, job_id in JOB_IDS.items():
            matching=next((x for x in successes if x[0]==panel),None)
            writer.writerow([panel,job_id,"COLLECTED" if matching else "FAILED",matching[2] if matching else "",failures.get(panel,"")])
        z.writestr("manifest.csv",manifest.getvalue())
    return buf.getvalue(),len(successes),failures
