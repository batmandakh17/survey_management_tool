"""Step 6: walk through the tool as a new enumerator and as a new leader, capturing every screen a newcomer meets.

Run from the tool folder:  python3 tests/usability_walkthrough.py 1     (the round number of the usability pass)
Screens go to tests/screens/usability_r<n>/; the findings are written by hand into USABILITY.md.
"""
import glob
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from cdp import Browser  # noqa: E402

PASS = sys.argv[1] if len(sys.argv) > 1 else "1"
OUT = os.path.join(HERE, "screens", f"usability_r{PASS}")
os.makedirs(OUT, exist_ok=True)
SCRATCH = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
STAMP = time.strftime("%H%M%S")
DL = os.path.join(SCRATCH, f"udl_{STAMP}")
S = os.path.join(ROOT, "samples")
n = [0]


def shot(b, name, full=False):
    n[0] += 1
    b.shot(os.path.join(OUT, f"{n[0]:02d}_{name}.png"), full=full)


def main():
    b = Browser(os.path.join(SCRATCH, f"uprofile_{STAMP}"), port=9348, width=1280, height=860)
    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId="Asia/Ulaanbaatar")
        b.downloads_to(DL)
        b.goto("file://" + os.path.join(ROOT, "rtm_interview_tool.html"))
        b.js("RTM.setNow('2026-10-27T10:05:00+08:00'); APP.noFSA = true; APP.render(); true")
        # ---------------- the enumerator, who has just received their file ----------------
        shot(b, "enum_start")
        if PASS != "1":  # added in round 2: the protected file asks for its passphrase; cancelling leaves the start page
            b.set_files("#f-assign", [os.path.join(S, "round05", "E07_assignment_R05_protected.json")]); b.wait("APP.modal && APP.modal.kind === 'passphrase'")
            shot(b, "enum_passphrase")
            b.click('[data-act="closemodal"]'); time.sleep(0.2)
        b.set_files("#f-assign", [os.path.join(S, "round05", "E07_assignment_R05.json")]); b.wait("!!APP.S")
        shot(b, "enum_today")
        h = b.js("RTM.queue(APP.C, RTM.now(), '2026-10-27').due[0].hhid")
        b.click(f'[data-act="open"][data-hh="{h}"]'); b.wait(f"APP.sel === '{h}'")
        shot(b, "enum_household")
        if PASS != "1":
            b.click(".drawer details.why summary"); time.sleep(0.2)
            shot(b, "enum_why_with_me")
        b.click('[data-act="call"][data-slot="1"]'); b.wait("APP.call && !APP.call.end")
        shot(b, "enum_on_call")
        b.js("RTM.setNow('2026-10-27T10:09:00+08:00'); true")
        b.click('[data-act="endcall"]'); b.wait("!!document.querySelector('#callform')")
        shot(b, "enum_call_result")
        b.js("document.querySelector('input[name=status][value=APPOINTMENT]').checked = true; true")
        b.click('[data-act="savecall"]'); time.sleep(0.3)
        shot(b, "enum_after_save_without_time")
        b.js("document.querySelector('#callform [name=appointment]').value = '2026-10-27T18:30'; true")
        b.click('[data-act="savecall"]'); time.sleep(0.3)
        shot(b, "enum_after_appointment")
        b.click('[data-act="save"]'); time.sleep(0.8)
        shot(b, "enum_saved")
        b.click('[data-act="export"]'); b.wait("APP.modal")
        shot(b, "enum_export")
        b.click('[data-act="closemodal"]')
        if PASS != "1":
            # a correction of the logged call, then the release and the call logged after the fact, each cancelled
            b.click('[data-act="correct"]'); b.wait("!!document.querySelector('#corrform')")
            b.click('[data-act="savecorr"]'); time.sleep(0.3)
            shot(b, "enum_correction_without_reason")
            b.click('[data-act="cancelcorr"]'); time.sleep(0.2)
            b.click('[data-act="manual"]'); b.wait("!!APP.manual")
            shot(b, "enum_manual_form")
            b.click('[data-act="cancelmanual"]'); time.sleep(0.2)
            b.click('[data-act="release"]'); b.wait("APP.modal")
            shot(b, "enum_release_modal")
            b.click('[data-act="closemodal"]'); time.sleep(0.2)
            b.click('[data-act="tab"][data-t="households"]'); time.sleep(0.2)
            shot(b, "enum_households", full=True)
        b.click('[data-act="tab"][data-t="performance"]'); time.sleep(0.2)
        shot(b, "enum_performance", full=True)
        b.click('[data-act="tab"][data-t="calendar"]'); time.sleep(0.2)
        shot(b, "enum_calendar")
        b.ws.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        b.click('[data-act="tab"][data-t="today"]'); time.sleep(0.2)
        h2 = b.js("RTM.queue(APP.C, RTM.now(), '2026-10-27').due.map(c => c.hhid).find(x => x !== '" + h + "')")
        b.click(f'[data-act="open"][data-hh="{h2}"]'); time.sleep(0.2)
        shot(b, "enum_phone_household")
        b.ws.call("Emulation.clearDeviceMetricsOverride")
        b.click('[data-act="closehh"]')
        b.click('[data-act="close"]'); b.wait("APP.modal")
        if PASS not in ("1", "2", "3"):
            shot(b, "enum_close_prompt")
        b.click('[data-act="modalok"]'); b.wait("APP.S === null")
        if PASS not in ("1", "2", "3"):  # added in round 4: the session saved mid-round is opened again
            saved = sorted(glob.glob(os.path.join(DL, "E07_project_R05_*.json")), key=os.path.getmtime)
            b.set_files("#f-project", [saved[-1]]); b.wait("!!APP.S")
            shot(b, "enum_session_reopened")
            b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        # ---------------- the leader, preparing round 5 ----------------
        b.click('[data-act="view"][data-v="leader"]'); b.wait("!!document.querySelector('#lstart')")
        shot(b, "lead_start")
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        shot(b, "lead_prepare_empty")
        b.set_files("#lf-hh", [os.path.join(S, "leader", "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", sorted(glob.glob(os.path.join(S, "leader", "history", "*")))); b.wait("LEAD.state().inputs.history.length === 12")
        b.set_files("#lf-repl", [os.path.join(S, "leader", "selection.csv")]); b.wait("!!LEAD.state().inputs.replacements")
        shot(b, "lead_inputs_open", full=True)
        b.click('[data-lact="apply"]'); time.sleep(0.3)
        shot(b, "lead_apply_too_early", full=True)

        def setv(sel, v):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")
        setv('[data-lset="cal.window_start"]', "2026-10-26"); setv('[data-lset="cal.window_end"]', "2026-11-20")
        b.js("(() => { const el = document.querySelector('[data-lteam=\"2\"][data-f=\"available\"]'); el.checked = false; el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()")
        setv('[data-lset="rule.rotation_share"]', "10")
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        shot(b, "lead_check", full=True)
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        shot(b, "lead_files_ready", full=True)
        b.click('[data-lact="tab"][data-t="risk"]'); time.sleep(0.3)
        if PASS == "1":
            shot(b, "lead_risk", full=True)
        else:  # the long model card made one very tall capture; the top of the tab, then the backtest result
            shot(b, "lead_risk")
            b.click('[data-lact="backtest"][data-k="dropout"]'); b.wait("!!LEAD.ui.bt_dropout", timeout=60)
            b.js("document.querySelector('[data-lact=\"backtest\"][data-k=\"dropout\"]').scrollIntoView({block: 'start'}); true"); time.sleep(0.2)
            shot(b, "lead_risk_backtest")
        # ---------------- the leader, a week later: importing the round's logs ----------------
        b.click('[data-lact="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("!LEAD.state()")
        b.js("RTM.setNow('2026-11-07T09:00:00+08:00'); true")
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        b.click('[data-lact="tab"][data-t="import"]')
        shot(b, "lead_import_empty")
        b.set_files("#lf-manifest", [os.path.join(S, "leader", "L2MN-DEMO_R05_manifest.json")]); b.wait("!!LEAD.state().manifest")
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "leader", "exports_R05", "*"))) + sorted(glob.glob(os.path.join(S, "leader", "merge_cases", "conflict", "*"))))
        b.wait("LEAD.state().imports.length >= 10")
        shot(b, "lead_import_questions", full=True)
        if PASS != "1":
            b.click('[data-lact="resolve"]'); time.sleep(0.3)
            shot(b, "lead_import_one_decided")
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.2)
        shot(b, "lead_progress", full=PASS != "1")
        b.click('[data-lact="tab"][data-t="calllog"]'); time.sleep(0.2)
        shot(b, "lead_calllog")
        b.click('[data-lact="tab"][data-t="analytics"]'); time.sleep(0.3)
        shot(b, "lead_analytics_no_history")
        b.click('[data-lact="save"]'); b.wait("APP.modal")
        shot(b, "lead_save_dialog")
        b.click('[data-act="closemodal"]')
        print(f"{n[0]} screens in {OUT}")
    finally:
        b.close()


if __name__ == "__main__":
    main()
