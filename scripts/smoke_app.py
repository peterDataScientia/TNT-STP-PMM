"""Offline Streamlit startup smoke-test: no third-party submissions are made."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

def main():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
    if app.exception:
        raise AssertionError("Streamlit startup exceptions: " +
                             "; ".join(str(exc.message) for exc in app.exception))
    # Presence of all three controls verifies a renderable application.
    headings = [x.value for x in app.subheader]
    for provider in ("SwissTargetPrediction", "TargetNet", "PharmMapper"):
        if not any(provider in heading for heading in headings):
            raise AssertionError(f"{provider} tab was not rendered")
    print("Streamlit startup smoke test: PASS; tabs:", headings)

if __name__ == "__main__":
    main()
