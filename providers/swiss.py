"""SwissTargetPrediction backend using the preserved v2 HTTP workflow."""
import csv
import html
import io
import re
import time
import zipfile
from urllib.parse import urljoin
import requests

BASE = "https://swisstargetprediction.ch"
INDEX = BASE + "/index.php"
PREDICT = BASE + "/predict.php"

def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", s))).strip()

def _job_url(page):
    cleaned=html.unescape(page).replace("\\/", "/")
    patterns=[
        r"""location\.replace\(\s*["']([^"']*result\.php\?[^"']+)["']\s*\)""",
        r"""location\.href\s*=\s*["']([^"']*result\.php\?[^"']+)["']""",
        r"""["']([^"']*result\.php\?job=[^"']+)["']""",
    ]
    for pattern in patterns:
        m=re.search(pattern,cleaned,re.I)
        if m:
            u=urljoin(BASE+"/",m.group(1))
            if u.startswith(BASE+"/"):
                return u
    return None

def _rows(page):
    m=re.search(r"""<table[^>]*id=["']resultTable["'][^>]*>(.*?)</table>""",page,re.I|re.S)
    if not m:
        raise ValueError("SwissTargetPrediction result table missing")
    rows=[]
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",m.group(1),re.I|re.S):
        cells=re.findall(r"<td[^>]*>(.*?)</td>",tr,re.I|re.S)
        if len(cells)>=7:
            rows.append([_clean(c) for c in cells[:7]])
    if not rows:
        raise ValueError("No target rows parsed")
    return rows

def run_swiss(compounds, progress=None):
    out=io.BytesIO()
    failures={}
    count=0
    with requests.Session() as session, zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        session.headers.update({"User-Agent":"Mozilla/5.0","Accept":"text/html,*/*"})
        for i, item in enumerate(compounds,1):
            cid=item["compound_id"]
            try:
                session.get(INDEX,timeout=45).raise_for_status()
                form={"smiles":item["smiles"],"organism":"Homo_sapiens","ioi":"2"}
                response=session.post(PREDICT,data=form,headers={"Referer":INDEX,"Origin":BASE},timeout=180,allow_redirects=False)
                if response.is_redirect:
                    location=urljoin(PREDICT,response.headers.get("Location",""))
                    if not location.startswith(BASE+"/"):
                        raise ValueError("Unexpected prediction redirect")
                    response=session.post(location,data=form,headers={"Referer":INDEX,"Origin":BASE},timeout=180)
                response.raise_for_status()
                url=_job_url(response.text)
                if not url:
                    # Preserve the actual response for troubleshooting; never fabricate a job URL.
                    diagnostic = f"SwissTargetPrediction/debug/{cid}_predict_response.html"
                    z.writestr(diagnostic, response.text)
                    raise ValueError(
                        f"No result URL (HTTP {response.status_code}; "
                        f"final URL {response.url}; response saved to {diagnostic})"
                    )
                last_error=None
                for attempt in range(12):
                    try:
                        result=session.get(url,timeout=80)
                        result.raise_for_status()
                        rows=_rows(result.text)
                        break
                    except Exception as exc:
                        last_error=exc
                        if attempt==11:
                            raise RuntimeError(str(last_error))
                        time.sleep(8)
                content=io.StringIO()
                writer=csv.writer(content)
                writer.writerow(["compound_id","query_smiles","target","common_name","uniprot_id","chembl_id","target_class","probability","known_actives","result_url"])
                for row in rows:
                    writer.writerow([cid,item["smiles"],*row,url])
                z.writestr(f"SwissTargetPrediction/{cid}.csv",content.getvalue())
                count+=1
                status="COLLECTED"
            except Exception as exc:
                failures[cid]=str(exc)
                status="FAILED"
            if progress:
                progress(i,len(compounds),cid,status)
        z.writestr("errors.csv","compound_id,error\n"+"\n".join(f"{k},{v.replace(',', ';')}" for k,v in failures.items()))
    return out.getvalue(),count,failures
