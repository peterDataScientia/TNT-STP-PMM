"""Extract PharmMapper's Job ID from the actual success confirmation markup.

PharmMapper prints 'Submit complete ! Your job has been submitted. Your JOB ID
is : [COPY]'. The ID can be in a non-labelled INPUT value, clipboard target,
button data, or script instead of visible innerText. Only inspect these when
the provider explicitly confirms submission. Never infer an ID from wall time.
"""
import re
from bs4 import BeautifulSoup
from datetime import datetime

JOB = re.compile(r"(?<!\d)(\d{12})(?!\d)")
SUCCESS = re.compile(r"your\s+job\s+has\s+been\s+submitted", re.I)


def valid_job_id(value):
    if not re.fullmatch(r"\d{12}", str(value or "")):
        return False
    try:
        datetime.strptime(value, "%y%m%d%H%M%S")
        return True
    except ValueError:
        return False


def is_submission_confirmed(document):
    soup = BeautifulSoup(str(document or ""), "html.parser")
    return bool(SUCCESS.search(soup.get_text(" ", strip=True)))


def _ids(value):
    return [m.group(1) for m in JOB.finditer(str(value or ""))
            if valid_job_id(m.group(1))]


def job_id_from_confirmation(document):
    """Best-effort, safe markup extraction; ambiguous candidates are rejected."""
    soup = BeautifulSoup(str(document or ""), "html.parser")
    if not is_submission_confirmed(document):
        return None

    # 1. Copy button's explicit target / attribute, without clicking anything.
    copy = [e for e in soup.select("button, a, span, input")
            if ("copy" in e.get_text(" ", strip=True).lower()
                or "copy" in (e.get("title", "") or "").lower()
                or e.has_attr("data-clipboard-target")
                or e.has_attr("data-clipboard-text"))]
    for element in copy:
        for field in ("data-clipboard-text", "data-job-id",
                      "data-jobid", "onclick", "value", "data-clipboard-action"):
            matches = _ids(element.get(field))
            if len(set(matches)) == 1:
                return matches[0]
        target = element.get("data-clipboard-target")
        if target:
            try:
                linked = soup.select_one(target)
                if linked is not None:
                    for string in (linked.get("value"), linked.get("content"),
                                   linked.get_text(" ", strip=True)):
                        matches = _ids(string)
                        if len(set(matches)) == 1:
                            return matches[0]
            except Exception:
                pass

    # 2. Directly-labelled job IDs in input, button, span, hidden and metadata.
    for element in soup.select("input, textarea, span, button, label, meta"):
        attrs = element.attrs
        descriptor = " ".join(str(attrs.get(k, "")) for k in
                              ("id", "name", "class", "aria-label", "title", "data-role"))
        if not re.search(r"job|copy|clipboard|result", descriptor, re.I):
            continue
        for value in (attrs.get("value"), attrs.get("content"),
                      attrs.get("data-job-id"), element.get_text(" ", strip=True)):
            matches = _ids(value)
            if len(set(matches)) == 1:
                return matches[0]

    # 3. The success page can have an unlabelled readonly input next to COPY.
    # Enforce uniqueness, so unrelated dates/timestamps never become job IDs.
    inputs = set()
    for element in soup.select("input, textarea"):
        for field in ("value", "data-value", "data-clipboard-text"):
            inputs.update(_ids(element.get(field)))
        if element.name == "textarea":
            inputs.update(_ids(element.get_text(" ", strip=True)))
    if len(inputs) == 1:
        return next(iter(inputs))

    # 4. Last resort: unambiguous 12-digit ID near 'Your JOB ID is' inside
    # complete HTML, which often contains a nested value element.
    raw = str(document)
    match = re.search(r"your.{0,25}job\s*id.{0,300}", raw, re.I | re.S)
    if match:
        candidates = set(_ids(match.group(0)))
        if len(candidates) == 1:
            return next(iter(candidates))
    return None


def job_id_from_live_page(page):
    """Inspect live value properties (not only HTML attributes).

    Some PharmMapper confirmation fields have their input.value assigned by
    JavaScript; page.content() does not necessarily serialize that property.
    """
    try:
        snapshot = page.evaluate("""() => {
          const text = document.body?.innerText || '';
          if (!/your\s+job\s+has\s+been\s+submitted/i.test(text))
            return {success:false, values:[], html:''};
          const els = Array.from(document.querySelectorAll(
            'input, textarea, button, span, a, [data-clipboard-text], [data-clipboard-target]'
          ));
          const attrs=['value','data-clipboard-text','data-job-id',
                       'data-jobid','data-value','onclick','title'];
          const values=[];
          for (const el of els) {
            if ('value' in el) values.push(String(el.value||''));
            for (const key of attrs) values.push(String(el.getAttribute(key)||''));
          }
          return {success:true, values, html:document.documentElement.outerHTML};
        }""")
    except Exception:
        return None
    if not snapshot or not snapshot.get("success"):
        return None
    confirmed = job_id_from_confirmation(snapshot.get("html", ""))
    if confirmed:
        return confirmed
    candidates = set()
    for value in snapshot.get("values", []):
        candidates.update(_ids(value))
    return next(iter(candidates)) if len(candidates) == 1 else None


def job_id_from_copy_button(page):
    """As a final fallback, activate site's COPY control in isolated Chromium.

    This reads only the automated browser's clipboard, not the user's device.
    It is attempted solely on an explicitly confirmed success page.
    """
    try:
        text = page.locator("body").inner_text(timeout=3000)
        if not SUCCESS.search(text):
            return None
        origin = "https://www.lilab-ecust.cn"
        try:
            page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"], origin=origin
            )
        except Exception:
            pass
        copy = page.get_by_text("COPY", exact=True)
        if not copy.count():
            return None
        copy.first.click(timeout=3000)
        value = page.evaluate("""async () => {
          try { return await navigator.clipboard.readText(); }
          catch (_) { return ''; }
        }""")
        value = str(value or "").strip()
        if valid_job_id(value):
            return value
        candidates = set(_ids(value))
        return next(iter(candidates)) if len(candidates) == 1 else None
    except Exception:
        return None
