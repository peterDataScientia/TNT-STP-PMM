"""One-off live HTML/control probe. Does NOT click PharmMapper final Submit.
Uses temporary model ethanol and non-deliverable example.com contact; NOT a real job.
Run only through opt-in GitHub Actions diagnostic commit.
"""
import json
import re
from playwright.sync_api import sync_playwright
from rdkit import Chem
from rdkit.Chem import AllChem

URL="https://www.lilab-ecust.cn/pharmmapper/submitfile.html"
def dump(page, stage):
    print("PROBE_STAGE",stage,"URL",page.url,flush=True)
    elements=page.evaluate("""() => Array.from(document.querySelectorAll('form,input,select,textarea,button, a')).map(el=>({
      tag:el.tagName, id:el.id, name:el.name || '',
      type:el.type||'',value:el.value||'',
      checked:el.checked||false, action:el.getAttribute('action')||'',
      method:el.getAttribute('method')||'', title:el.getAttribute('title')||'',
      text:(el.textContent||'').replace(/\\s+/g,' ').trim().slice(0,110),
      onclick:el.getAttribute('onclick')||'',
      options:el.tagName==='SELECT'?Array.from(el.options).map(o=>[o.value,o.textContent.trim()]):undefined
    })).slice(0,200)""")
    for i,el in enumerate(elements):
        if el["name"].lower().find("mail") >=0: el["value"]="[REDACTED]"
        print("FIELD",i,json.dumps(el,ensure_ascii=False)[:650],flush=True)
    text=page.locator("body").inner_text(timeout=7000)
    text=re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}","[REDACTED]",text)
    print("PAGE_TEXT",text[:3500].replace("\n"," || "),flush=True)

def main():
    mol=Chem.AddHs(Chem.MolFromSmiles("CCO"))
    params=AllChem.ETKDGv3()
    params.randomSeed=42
    AllChem.EmbedMolecule(mol,params)
    sdf=(Chem.MolToMolBlock(mol)+"\n$$$$\n").encode()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        try:
            page=browser.new_page()
            page.set_default_timeout(12000)
            page.goto(URL,wait_until="domcontentloaded",timeout=30000)
            dump(page,"INITIAL")
            page.locator('input[type="file"]').first.set_input_files(
                {"name":"probe_ethanol.sdf","mimeType":"chemical/x-mdl-sdfile","buffer":sdf})
            page.locator('input[name*="mail" i], input[id*="mail" i], input[type="email"]').first.fill("research-probe@example.com")
            cont=page.get_by_role("button",name=re.compile("Continue",re.I))
            print("CONTINUE_COUNT",cont.count(),flush=True)
            cont.first.click(timeout=12000)
            page.wait_for_timeout(2500)
            dump(page,"AFTER_CONTINUE__DO_NOT_SUBMIT")
        finally:
            browser.close()
if __name__=="__main__":
    main()
