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
    fast_button = next(
        (button for button in app.button
         if button.label == "Get 17 completed TargetNet results (FAST)"),
        None,
    )
    if fast_button is None:
        raise AssertionError("Fast TargetNet collection button missing")
    fast_button.click().run()
    if app.exception:
        raise AssertionError("TargetNet FAST action crashed: " +
                             "; ".join(str(exc.message) for exc in app.exception))
    collected = [metric.value for metric in app.metric
                 if metric.label == "Successfully collected"]
    if "17" not in collected:
        raise AssertionError(f"TargetNet FAST did not display 17/17: {collected}")
    print("Streamlit FAST TargetNet button: PASS (17/17); tabs:", headings)

if __name__ == "__main__":
    main()
