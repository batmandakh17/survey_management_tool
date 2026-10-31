"""Print the user manual to PDF with headless Chrome: manual/manual.html -> manual/RTM_interview_tool_manual.pdf.

Run from the tool folder, after manual/make_screens.py:  python3 manual/make_pdf.py
A4, the page's own @page margins, backgrounds printed. Needs Google Chrome.
"""
import base64
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from cdp import Browser  # noqa: E402

WORK = os.environ.get("RTM_SCRATCH", os.path.join(ROOT, "tests", "_work"))
OUT = os.path.join(HERE, "RTM_interview_tool_manual.pdf")


def main():
    b = Browser(os.path.join(WORK, f"pdfprofile_{time.strftime('%H%M%S')}"), port=9347, width=1200, height=900)
    try:
        b.goto("file://" + os.path.join(HERE, "manual.html"))
        b.wait("Array.from(document.images).every(i => i.complete)", timeout=60)
        time.sleep(0.5)
        data = b.ws.call("Page.printToPDF", printBackground=True, preferCSSPageSize=True, displayHeaderFooter=False)["data"]
        with open(OUT, "wb") as f:
            f.write(base64.b64decode(data))
        print(f"written {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB, {len(list(b.js('Array.from(document.images)')) or [])} images)")
    finally:
        b.close()


if __name__ == "__main__":
    main()
