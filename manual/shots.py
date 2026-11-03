"""Screenshot helpers shared by the manual's and the examples' screen scripts: outline a control, crop the union of
some elements, set a form value. Every picture comes from the synthetic L2MN-DEMO samples in headless Chrome."""
import base64
import json
import os
import time

DSF = 1.5

HELPERS = r"""
(() => {
  if (!document.getElementById('mstyle')) {
    const st = document.createElement('style'); st.id = 'mstyle';
    st.textContent = '.mhl{outline:3px solid #e8590c !important;outline-offset:3px !important;border-radius:8px} #toasts{display:none !important}';
    document.head.appendChild(st);
  }
  window.__card = re => [...document.querySelectorAll('.lcard')].find(c => { const h = c.querySelector('h3'); return h && new RegExp(re).test(h.innerText); });
  window.__sec = re => [...document.querySelectorAll('.drawer section.sec')].find(c => { const h = c.querySelector('h4'); return h && new RegExp(re, 'i').test(h.innerText); });
  window.__col = re => [...document.querySelectorAll('section.col')].find(c => new RegExp(re).test(c.querySelector('h3').innerText));
  return true;
})()
"""


class Shots:
    def __init__(self, b, img_dir):
        self.b = b
        self.img = img_dir
        os.makedirs(img_dir, exist_ok=True)

    def viewport(self, w, h, dsf=DSF, mobile=False):
        self.b.ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=dsf, mobile=mobile)

    def prep(self):
        self.b.js(HELPERS)

    def hl(self, exprs):
        self.b.js("(() => { document.querySelectorAll('.mhl').forEach(e => e.classList.remove('mhl')); "
                  + "".join(f"{{ const el = {e}; if (el) el.classList.add('mhl'); }}" for e in exprs) + " return true; })()")

    def save(self, name, clip=None, beyond=True):
        args = {"format": "png", "captureBeyondViewport": beyond}
        if clip:
            args["clip"] = clip
        data = self.b.ws.call("Page.captureScreenshot", **args)["data"]
        with open(os.path.join(self.img, name + ".png"), "wb") as f:
            f.write(base64.b64decode(data))
        print("  ", name)

    def view(self, name, hls=()):
        self.prep(); self.hl(hls); self.b.js("window.scrollTo(0, 0); true"); time.sleep(0.15)
        self.save(name, beyond=False)

    def crop(self, name, exprs, hls=(), pad=10, max_h=None, scroll=True, inside=False):
        """The union of the elements the expressions return, scrolled into view. Inside the household panel or a dialog
        (inside=True) the page's own scrolling must stay as it is, so the window is made tall instead of captured beyond."""
        if inside:
            self.viewport(1280, 1300)
        self.prep(); self.hl(hls); time.sleep(0.1)
        r = self.b.js("(() => { const els = [" + ",".join(exprs) + "].filter(Boolean); if (!els.length) return null;"
                      + (" els[0].scrollIntoView({block: 'start'});" if scroll else "")
                      + " const rs = els.map(e => e.getBoundingClientRect());"
                      + " const x = Math.min(...rs.map(r => r.left)), y = Math.min(...rs.map(r => r.top)), X = Math.max(...rs.map(r => r.right)), Y = Math.max(...rs.map(r => r.bottom));"
                      + " return [x + window.scrollX, y + window.scrollY, X - x, Y - y]; })()")
        if not r:
            raise RuntimeError(f"{name}: nothing to crop")
        x, y, w, h = r
        if max_h:
            h = min(h, max_h)
        time.sleep(0.1)
        self.save(name, {"x": max(0, x - pad), "y": max(0, y - pad), "width": w + 2 * pad, "height": h + 2 * pad, "scale": 1}, beyond=not inside)
        if inside:
            self.viewport(1280, 900)

    def setv(self, sel, v):
        self.b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

    def tick(self, sel, on):
        self.b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.checked = {str(bool(on)).lower()}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

    def close_modal_alt(self):
        self.b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true")
