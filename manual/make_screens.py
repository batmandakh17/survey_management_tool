"""Screenshots for the user manual: every function of both views, with the synthetic L2MN-DEMO sample files.

Run from the tool folder:  python3 manual/make_screens.py
Writes manual/img/*.png. The control each picture explains is outlined in orange. Needs Google Chrome.
"""
import base64
import glob
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from cdp import Browser  # noqa: E402

IMG = os.path.join(HERE, "img")
os.makedirs(IMG, exist_ok=True)
WORK = os.environ.get("RTM_SCRATCH", os.path.join(ROOT, "tests", "_work"))
STAMP = time.strftime("%H%M%S")
S = os.path.join(ROOT, "samples")
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


def main():
    b = Browser(os.path.join(WORK, f"mprofile_{STAMP}"), port=9346, width=1280, height=900)

    def viewport(w, h, dsf=DSF, mobile=False):
        b.ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=dsf, mobile=mobile)

    def prep():
        b.js(HELPERS)

    def hl(exprs):
        b.js("(() => { document.querySelectorAll('.mhl').forEach(e => e.classList.remove('mhl')); "
             + "".join(f"{{ const el = {e}; if (el) el.classList.add('mhl'); }}" for e in exprs) + " return true; })()")

    def save(name, clip=None, beyond=True):
        args = {"format": "png", "captureBeyondViewport": beyond}
        if clip:
            args["clip"] = clip
        data = b.ws.call("Page.captureScreenshot", **args)["data"]
        with open(os.path.join(IMG, name + ".png"), "wb") as f:
            f.write(base64.b64decode(data))
        print("  ", name)

    def view(name, hls=()):
        prep(); hl(hls); b.js("window.scrollTo(0, 0); true"); time.sleep(0.15)
        save(name, beyond=False)

    def crop(name, exprs, hls=(), pad=10, max_h=None, scroll=True, inside=False):
        """The union of the elements the expressions return, scrolled into view. Inside the household panel or a dialog
        (inside=True) the page's own scrolling must stay as it is, so the window is made tall instead of captured beyond."""
        if inside:
            viewport(1280, 1300)
        prep(); hl(hls); time.sleep(0.1)
        r = b.js("(() => { const els = [" + ",".join(exprs) + "].filter(Boolean); if (!els.length) return null;"
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
        save(name, {"x": max(0, x - pad), "y": max(0, y - pad), "width": w + 2 * pad, "height": h + 2 * pad, "scale": 1}, beyond=not inside)
        if inside:
            viewport(1280, 900)

    def setv(sel, v):
        b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

    def tick(sel, on):
        b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.checked = {str(bool(on)).lower()}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

    def close_without_saving():
        b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true")

    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId="Asia/Ulaanbaatar")
        b.downloads_to(os.path.join(WORK, f"mdl_{STAMP}"))
        viewport(1280, 800)
        b.goto("file://" + os.path.join(ROOT, "rtm_interview_tool.html"))
        b.js("RTM.setNow('2026-10-27T10:05:00+08:00'); APP.noFSA = true; APP.render(); true")

        # ======================================== the enumerator ========================================
        print("enumerator")
        view("e01_start", ["document.querySelectorAll('.bigpick')[0]"])
        b.set_files("#f-assign", [os.path.join(S, "round05", "E07_assignment_R05_protected.json")])
        b.wait("APP.modal && APP.modal.kind === 'passphrase'")
        crop("e02_passphrase", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        b.click('[data-act="closemodal"]')
        b.set_files("#f-assign", [os.path.join(S, "round05", "E07_assignment_R05.json")]); b.wait("!!APP.S")
        viewport(1280, 900)
        view("e03_today")
        crop("e04_summary", ["document.querySelector('header.topbar')", "document.querySelector('section.summary')"], pad=0,
             hls=["document.querySelector('[data-act=\"save\"]')", "document.querySelector('[data-act=\"export\"]')"])
        crop("e05_columns", ["document.querySelector('nav.tabs')", "__col('Due now')", "__col('Later today')"], max_h=520, scroll=False)
        due = b.js("RTM.queue(APP.C, RTM.now(), '2026-10-27').due.map(c => c.hhid)")
        h = due[0]
        b.click(f'[data-act="open"][data-hh="{h}"]'); b.wait(f"APP.sel === '{h}'")
        crop("e06_household", ["document.querySelector('.drawer .dhead')", "document.querySelector('.drawer dl.facts')"],
             hls=["document.querySelector('.drawer details.why summary')"], inside=True)
        b.click(".drawer details.why summary"); time.sleep(0.1)
        crop("e07_why", ["document.querySelector('.drawer details.why')"], inside=True)
        crop("e08_numbers", ["__sec('Phone numbers')"], hls=["document.querySelector('[data-act=\"call\"]')"], inside=True)
        b.click('[data-act="call"][data-slot="1"]'); b.wait("APP.call && !APP.call.end")
        crop("e09_on_call", ["document.querySelector('.callbox')"], hls=["document.querySelector('[data-act=\"endcall\"]')"], inside=True)
        b.js("RTM.setNow('2026-10-27T10:09:00+08:00'); true")
        b.click('[data-act="endcall"]'); b.wait("!!document.querySelector('#callform')")
        crop("e10_result", ["document.querySelector('.callbox')"], hls=["document.querySelector('[data-act=\"savecall\"]')"], inside=True)
        b.js("document.querySelector('input[name=status][value=APPOINTMENT]').checked = true; true")
        b.click('[data-act="savecall"]'); time.sleep(0.3)
        crop("e11_missing_time", ["document.querySelector('.callbox')"], inside=True)
        b.js("document.querySelector('#callform [name=appointment]').value = '2026-10-27T18:30'; true")
        b.click('[data-act="savecall"]'); b.wait("!document.querySelector('#callform')")
        b.click('[data-act="closehh"]'); time.sleep(0.2)
        crop("e12_callback", ["__col('Later today')"], hls=[f"document.querySelector('section.col [data-hh=\"{h}\"]')"], max_h=560, scroll=False)
        # a complete under 3 minutes
        h2 = due[1]
        b.click(f'[data-act="open"][data-hh="{h2}"]'); b.wait(f"APP.sel === '{h2}'")
        b.js("RTM.setNow('2026-10-27T10:20:00+08:00'); true")
        b.click('[data-act="call"][data-slot="1"]'); b.wait("APP.call && !APP.call.end")
        b.js("RTM.setNow('2026-10-27T10:22:00+08:00'); true")
        b.click('[data-act="endcall"]'); b.wait("!!document.querySelector('#callform')")
        b.js("document.querySelector('input[name=status][value=COMPLETE]').checked = true; true")
        b.click('[data-act="savecall"]'); b.wait("!document.querySelector('#callform')")
        crop("e13_short_complete", ["document.querySelector('.drawer .alert.warn')"], inside=True)
        # a call made earlier, a correction, the actions
        b.click('[data-act="manual"]'); b.wait("!!APP.manual")
        crop("e14_logged_later", ["document.querySelector('.drawer .callbox')"], inside=True)
        b.click('[data-act="cancelmanual"]'); time.sleep(0.2)
        b.click('[data-act="correct"]'); b.wait("!!document.querySelector('#corrform')")
        crop("e15_correct", ["__sec('Calls this round')"], hls=["document.querySelector('#corrform [name=void]')"], inside=True)
        b.click('[data-act="cancelcorr"]'); time.sleep(0.2)
        crop("e16_actions", ["__sec('Actions')"], hls=["document.querySelector('[data-act=\"release\"]')"], inside=True)
        b.click('[data-act="release"]'); b.wait("APP.modal")
        crop("e17_release", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        b.click('[data-act="closemodal"]')
        b.click('[data-act="contact"]'); b.wait("!!document.querySelector('#contactform')")
        crop("e18_number", ["document.querySelector('#contactform')"], inside=True)
        b.click('[data-act="cancelcontact"]'); time.sleep(0.2)
        # a hard refusal opens the way to a replacement
        h3 = b.js(f"APP.C.list.find(c => c.open && c.n === 0 && c.replacements.length && ![{json.dumps(h)}, {json.dumps(h2)}].includes(c.hhid)).hhid")
        b.click('[data-act="closehh"]'); time.sleep(0.1)
        b.js(f"APP.sel = {json.dumps(h3)}; APP.render(); true"); b.wait(f"APP.sel === '{h3}'")
        b.js("RTM.setNow('2026-10-27T10:40:00+08:00'); true")
        b.click('[data-act="call"][data-slot="1"]'); b.wait("APP.call && !APP.call.end")
        b.js("RTM.setNow('2026-10-27T10:42:00+08:00'); true")
        b.click('[data-act="endcall"]'); b.wait("!!document.querySelector('#callform')")
        b.js("document.querySelector('input[name=status][value=REFUSAL_HARD]').checked = true; true")
        b.click('[data-act="savecall"]'); b.wait("!document.querySelector('#callform')")
        crop("e19_replacement", ["__sec('Replacements')"], hls=["document.querySelector('[data-act=\"replace\"]')"], inside=True)
        b.click('[data-act="replace"]'); b.wait("APP.modal")
        crop("e20_replacement_confirm", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        b.click('[data-act="closemodal"]')
        b.click('[data-act="closehh"]'); time.sleep(0.1)
        # the other tabs
        b.click('[data-act="tab"][data-t="households"]'); time.sleep(0.2)
        view("e21_households", ["document.querySelector('#hh-search')"])
        b.click('[data-act="tab"][data-t="calendar"]'); time.sleep(0.2)
        view("e22_calendar")
        b.set_files("#f-past", [os.path.join(S, "past", "E07_2026-10-21.json")]); time.sleep(0.6)
        b.click('[data-act="tab"][data-t="performance"]'); time.sleep(0.2)
        view("e23_performance")
        b.click('[data-act="tab"][data-t="log"]'); time.sleep(0.2)
        view("e24_log")
        b.click('[data-act="tab"][data-t="today"]'); time.sleep(0.2)
        # saving, exporting, closing
        b.click('[data-act="save"]'); time.sleep(0.8)
        crop("e25_saved", ["document.querySelector('section.summary')"], pad=0, hls=["document.querySelector('.savestate')"])
        b.click('[data-act="export"]'); b.wait("APP.modal")
        crop("e26_export", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        b.click('[data-act="closemodal"]')
        b.click('[data-act="close"]'); b.wait("APP.modal")
        crop("e27_close", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        b.click('[data-act="closemodal"]')
        # on a phone
        viewport(390, 844, dsf=2, mobile=True)
        b.js("window.scrollTo(0, 0); true"); time.sleep(0.2)
        view("e28_phone_today")
        b.click(f'[data-act="open"][data-hh="{due[2]}"]'); time.sleep(0.3)
        view("e29_phone_household")
        viewport(1280, 900)
        b.click('[data-act="closehh"]')
        b.click('[data-act="close"]'); b.wait("APP.modal"); close_without_saving(); b.wait("APP.S === null")

        # ======================================== the team leader: preparing round 5 ========================================
        print("leader")
        b.js("RTM.setNow('2026-10-23T15:00:00+08:00'); true")
        b.click('[data-act="view"][data-v="leader"]'); b.wait("!!document.querySelector('#lstart')")
        # the leader's cards are cropped after scrolling: the sticky top bar would cover their titles
        b.js("document.head.insertAdjacentHTML('beforeend', '<style>.topbar{position:static !important}</style>'); true")
        viewport(1280, 800)
        view("l01_start", ["document.querySelector('#lstart')"])
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        viewport(1280, 1000)
        view("l02_prepare")
        b.set_files("#lf-hh", [os.path.join(S, "leader", "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", sorted(glob.glob(os.path.join(S, "leader", "history", "*")))); b.wait("LEAD.state().inputs.history.length === 12")
        b.set_files("#lf-repl", [os.path.join(S, "leader", "selection.csv")]); b.wait("!!LEAD.state().inputs.replacements")
        crop("l03_households", ["__card('1 ·')"])
        crop("l04_history", ["__card('2 ·')"])
        crop("l05_replacements", ["__card('3 ·')"])
        setv('[data-lset="cal.window_start"]', "2026-10-26"); setv('[data-lset="cal.window_end"]', "2026-11-20")
        crop("l06_calendar", ["__card('4 ·')"])
        team = b.js("LEAD.state().team.map(t => t.id)")
        tick(f'[data-lteam="{team.index("E03")}"][data-f="available"]', False)
        # the matching criterion of 31 October 2026: two PSUs of the sample speak Kazakh; E01 speaks it
        tick('[data-lcrit="language"]', True)
        for e, v in {"E01": "mn kk", "E02": "mn", "E07": "mn"}.items():
            setv(f'[data-lattr="{team.index(e)}"][data-c="language"]', v)
        crop("l07_team", ["__card('5 ·')"], hls=[f"document.querySelector('[data-lteam=\"{team.index('E03')}\"][data-f=\"available\"]')", "document.querySelector('[data-lcrit=\"language\"]')"])
        setv('[data-lset="rule.rotation_share"]', "10")
        crop("l08_rule", ["__card('6 ·')"], hls=["document.querySelector('[data-lset=\"rule.rotation_share\"]')"])
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        crop("l28_day_list", ["__card('4 ·')"], hls=["document.querySelector('[data-lset=\"cal.day_list\"]')"], max_h=420)
        crop("l09_check", ["__card('7 ·')"], hls=["document.querySelector('[data-lact=\"balance\"]') || __card('7 ·').querySelector('table')"])
        b.js("__card('7 ·').querySelector('details').open = true; true"); time.sleep(0.2)
        crop("l10_by_hand", ["__card('7 ·').querySelector('details')"], max_h=420)
        b.js("__card('7 ·').querySelector('details').open = false; true")
        tick('[data-lset="protect"]', True)
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=60)
        crop("l11_files", ["__card('8 ·')"], hls=["document.querySelector('[data-lact=\"saveall\"]')"])
        b.click('[data-lact="tab"][data-t="analytics"]'); time.sleep(0.5)
        crop("l12_analytics", ["__card('Continuation and retention')"], max_h=700)
        crop("l13_analytics_effort", ["__card('Dials per complete')"], max_h=760)
        b.click('[data-lact="tab"][data-t="risk"]'); time.sleep(0.5)
        crop("l14_risk", ["__card('Risk lists, for the leader only')", "__card('Dropout risk:')"], max_h=900)
        b.click('[data-lact="backtest"][data-k="dropout"]'); b.wait("!!LEAD.ui.bt_dropout", timeout=60)
        crop("l15_backtest", ["__card(\"This program's own data\")"], max_h=760)
        b.click('[data-lact="save"]'); b.wait("APP.modal")
        crop("l16_save", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        b.click('[data-act="closemodal"]')
        b.click('[data-lact="close"]'); b.wait("APP.modal")
        crop("l17_close", ["document.querySelector('.modal')"], pad=0, scroll=False, inside=True)
        close_without_saving(); b.wait("!LEAD.state()")

        # ======================================== the team leader: a week later ========================================
        b.js("RTM.setNow('2026-11-07T09:00:00+08:00'); true")
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        b.click('[data-lact="tab"][data-t="import"]'); time.sleep(0.2)
        crop("l18_import_manifest", ["__card(\"The round's manifest\")"])
        b.set_files("#lf-manifest", [os.path.join(S, "leader", "L2MN-DEMO_R05_manifest.json")]); b.wait("!!LEAD.state().manifest")
        crop("l19_import_add", ["__card('Add exports')"], hls=["document.querySelector('#lf-imports').parentElement"])
        files = sorted(glob.glob(os.path.join(S, "leader", "exports_R05", "*"))) + sorted(glob.glob(os.path.join(S, "leader", "merge_cases", "conflict", "*")))
        b.set_files("#lf-imports", files); b.wait(f"LEAD.state().imports.length === {len(files)}")
        time.sleep(0.4)
        crop("l20_decisions", ["__card('Needs your decision')"])
        crop("l21_files", ["__card('^Files')"], max_h=600)
        crop("l22_report", ["__card('Merge report')"])
        crop("l23_numbers", ["__card('New or corrected phone numbers')"])
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.3)
        crop("l24_progress_team", ["__card('^Team')"])
        crop("l25_progress_chart", ["__card('Completes over the window')"], max_h=640)
        crop("l26_progress_households", ["__card('^Households')"], max_h=520)
        # moving waiting households (31 October 2026): judged a week later, with the household list open for the revised files
        b.click('[data-lact="tab"][data-t="prepare"]'); time.sleep(0.2)
        b.set_files("#lf-hh", [os.path.join(S, "leader", "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.js("RTM.setNow('2026-11-13T09:00:00+08:00'); true")
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.3)
        tick('[data-lset="__movesStale"]', True)
        b.click('[data-lact="propose"]'); time.sleep(0.4)
        crop("l28_moves", ["__card('Move waiting households')"], hls=["document.querySelector('[data-lact=\"propose\"]')"], max_h=760)
        b.click('[data-lact="writemoves"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'moves'", timeout=60)
        crop("l29_moves_files", ["__card('Move waiting households').querySelector('.alert.info')", "__card('Move waiting households').querySelector('ul.files')"], max_h=520)
        b.js("RTM.setNow('2026-11-07T09:00:00+08:00'); true")
        b.click('[data-lact="tab"][data-t="calllog"]'); time.sleep(0.3)
        crop("l27_calllog", ["__card(\"The round's files\")", "__card('Merged call log')"], max_h=760)
        print(f"{len(glob.glob(os.path.join(IMG, '*.png')))} pictures in {IMG}")
    finally:
        b.close()


if __name__ == "__main__":
    main()
