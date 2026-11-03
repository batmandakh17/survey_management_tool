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
# default: the manual; `python3 manual/make_pdf.py examples.html RTM_interview_tool_examples.pdf 9353` prints another page
SRC = sys.argv[1] if len(sys.argv) > 1 else "manual.html"
OUT = os.path.join(HERE, sys.argv[2] if len(sys.argv) > 2 else "RTM_interview_tool_manual.pdf")
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 9347


def main():
    b = Browser(os.path.join(WORK, f"pdfprofile_{time.strftime('%H%M%S')}"), port=PORT, width=1200, height=900)
    try:
        b.goto("file://" + os.path.join(HERE, SRC))
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
