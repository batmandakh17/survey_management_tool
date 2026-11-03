"""Screenshots for the worked examples (manual/examples.html): the situations the manual's pictures do not show, on the
synthetic L2MN-DEMO samples. Reuses the manual's helpers (manual/shots.py); the manual's own pictures are reused as they are.

Run from the tool folder, after build.py:  python3 manual/make_examples.py
Writes manual/img/x*.png. Needs Google Chrome. Port 9352 (the manual's screens use 9346, the tests 9339 to 9347).
"""
import csv
import glob
import json
import os
import sys
import time
import uuid

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, HERE)
from cdp import Browser  # noqa: E402
from shots import Shots  # noqa: E402

IMG = os.path.join(HERE, "img")
WORK = os.environ.get("RTM_SCRATCH", os.path.join(ROOT, "tests", "_work"))
STAMP = time.strftime("%H%M%S")
DL = os.path.join(WORK, f"xdl_{STAMP}")
S = os.path.join(ROOT, "samples")
EXPORTS = sorted(glob.glob(os.path.join(S, "leader", "exports_R05", "*")))


def wait_new(pattern, before, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in sorted(glob.glob(os.path.join(DL, pattern))):
            if not p.endswith(".crdownload") and (p not in before or os.path.getmtime(p) > before[p]):
                time.sleep(0.3)
                return p
        time.sleep(0.2)
    raise RuntimeError(f"no new {pattern} in {DL}")


def snapshot():
    return {p: os.path.getmtime(p) for p in glob.glob(os.path.join(DL, "*"))}


def main():
    os.makedirs(DL, exist_ok=True)
    b = Browser(os.path.join(WORK, f"xprofile_{STAMP}"), port=9352, width=1280, height=900)
    sh = Shots(b, IMG)
    crop, view, setv, tick = sh.crop, sh.view, sh.setv, sh.tick

    def log_call(slot, status, start, end, extra_js=""):
        b.js(f"RTM.setNow('{start}'); true")
        b.click(f'[data-act="call"][data-slot="{slot}"]'); b.wait("APP.call && !APP.call.end")
        b.js(f"RTM.setNow('{end}'); true")
        b.click('[data-act="endcall"]'); b.wait("!!document.querySelector('#callform')")
        b.js(f"document.querySelector('input[name=status][value={status}]').checked = true; {extra_js} true")
        b.click('[data-act="savecall"]'); b.wait("!document.querySelector('#callform')")

    def close_enum():
        b.click('[data-act="close"]'); b.wait("APP.modal"); sh.close_modal_alt(); b.wait("APP.S === null")

    def close_leader():
        b.click('[data-lact="close"]'); b.wait("APP.modal"); sh.close_modal_alt(); b.wait("!LEAD.state()")

    def start_leader(now):
        b.js(f"RTM.setNow('{now}'); true")
        if b.js("APP.view") != "leader":
            b.click('[data-act="view"][data-v="leader"]')
        b.wait("!!document.querySelector('#lstart')")
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        b.js("document.head.insertAdjacentHTML('beforeend', '<style>.topbar{position:static !important}</style>'); true")

    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId="Asia/Ulaanbaatar")
        b.downloads_to(DL)
        sh.viewport(1280, 900)
        b.goto("file://" + os.path.join(ROOT, "rtm_interview_tool.html"))
        b.js("RTM.setNow('2026-10-27T10:05:00+08:00'); APP.noFSA = true; APP.render(); true")

        # ================================ the enumerator: what happens on the phone ================================
        print("enumerator")
        b.set_files("#f-assign", [os.path.join(S, "round05", "E07_assignment_R05.json")]); b.wait("!!APP.S")
        due = b.js("RTM.queue(APP.C, RTM.now(), '2026-10-27').due.map(c => c.hhid)")
        # nobody answers: the household stays in the day's list and comes back
        h = due[0]
        b.click(f'[data-act="open"][data-hh="{h}"]'); b.wait(f"APP.sel === '{h}'")
        log_call(1, "NO_ANSWER", "2026-10-27T10:06:00+08:00", "2026-10-27T10:07:00+08:00")
        crop("x02_no_answer", ["document.querySelector('.drawer .dhead')", "__sec('Calls this round')"], inside=True)
        b.click('[data-act="closehh"]'); time.sleep(0.2)
        crop("x02b_no_answer_queue", ["document.querySelector('nav.tabs')", "__col('Due now')", "__col('Later today')"], hls=[f"document.querySelector('section.col [data-hh=\"{h}\"]')"], max_h=560, scroll=False)
        # a dead number: the next number is tried; with no working number left, the replacement opens
        h2 = b.js(f"(APP.C.list.find(c => c.open && c.n === 0 && (c.h.contact.phones || []).length >= 2 && c.replacements.length && c.hhid !== {json.dumps(h)}) || APP.C.list.find(c => c.open && c.n === 0 && c.replacements.length && c.hhid !== {json.dumps(h)})).hhid")
        b.js(f"APP.sel = {json.dumps(h2)}; APP.render(); true"); b.wait(f"APP.sel === '{h2}'")
        log_call(1, "DEAD_NUMBER", "2026-10-27T10:12:00+08:00", "2026-10-27T10:12:30+08:00")
        crop("x03_dead_number", ["__sec('Phone numbers')"], inside=True)
        n_phones = b.js(f"(APP.C.map.get({json.dumps(h2)}).h.contact.phones || []).length")
        for slot in range(2, n_phones + 1):
            log_call(slot, "DEAD_NUMBER", f"2026-10-27T10:{13 + slot}:00+08:00", f"2026-10-27T10:{13 + slot}:30+08:00")
        crop("x04_all_dead", ["__sec('Phone numbers')", "__sec('Replacements')"], hls=["document.querySelector('[data-act=\"replace\"]')"], inside=True)
        b.click('[data-act="closehh"]'); time.sleep(0.2)
        # a respondent asks for Saturday evening: a callback booked on another day shows in the calendar
        h3 = due[2]
        b.click(f'[data-act="open"][data-hh="{h3}"]'); b.wait(f"APP.sel === '{h3}'")
        log_call(1, "APPOINTMENT", "2026-10-27T10:20:00+08:00", "2026-10-27T10:22:00+08:00", "document.querySelector('#callform [name=appointment]').value = '2026-10-31T18:00';")
        b.click('[data-act="closehh"]'); time.sleep(0.2)
        b.click('[data-act="tab"][data-t="calendar"]'); time.sleep(0.3)
        view("x05_callback_saturday")
        b.click('[data-act="tab"][data-t="today"]'); time.sleep(0.2)
        close_enum()

        # ================================ the leader: a week into the round ================================
        print("leader")
        start_leader("2026-11-07T09:00:00+08:00")
        b.set_files("#lf-hh", [os.path.join(S, "leader", "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.click('[data-lact="tab"][data-t="import"]'); time.sleep(0.2)
        b.set_files("#lf-manifest", [os.path.join(S, "leader", "L2MN-DEMO_R05_manifest.json")]); b.wait("!!LEAD.state().manifest")
        # one enumerator's export has not arrived
        part = [f for f in EXPORTS if os.path.basename(f).startswith(("E01_", "E02_"))]
        b.set_files("#lf-imports", part); b.wait(f"LEAD.state().imports.length === {len(part)}"); time.sleep(0.4)
        crop("x10_missing_export", ["__card('Needs your decision')"], max_h=520)
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        b.set_files("#lf-imports", EXPORTS); b.wait(f"LEAD.state().imports.length === {len(EXPORTS)}"); time.sleep(0.4)
        # an enumerator's own changes reach the leader: E07's export with two moved calls and time off ahead (3 November 2026)
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.2)
        b.js("""(() => { const st = LEAD.state(), f = st.imports.find(x => /E07_2026-11-06\\.json$/.test(x.name)), j = JSON.parse(f.text);
            const S = { assignment: { program: j.program, round: j.round, enumerator_id: j.enumerator_id }, events: j.events, genesis: j.chain_genesis };
            const now0 = RTM.now().toISOString(); RTM.setNow('2026-11-06T17:00:00+08:00');
            const open = [...LEAD.merged().C.values()].filter(c => c.enumerator_id === 'E07' && c.state === 'not_started').map(c => c.hhid);
            RTM.append(S, 'plan', { hhid: open[0], at: '2026-11-09T18:00:00+08:00', reason: 'TOLD', was: '2026-11-02T18:00:00+08:00', first: 1 });
            RTM.append(S, 'plan', { hhid: open[1], at: '2026-11-07T12:00:00+08:00', reason: 'WORKLOAD', was: '2026-11-07T17:00:00+08:00', first: 1 });
            RTM.append(S, 'availability', { date: '2026-11-16', part: 'day' }); RTM.append(S, 'availability', { date: '2026-11-17', part: 'afternoon' });
            RTM.setNow(now0);
            j.events = S.events.map(RTM.exportEvent); j.event_count = j.events.length; j.last_hash = j.events[j.events.length - 1].hash;
            f.orig = f.text; f.text = JSON.stringify(j); LEAD.refresh(); return true; })()"""); time.sleep(0.3)
        crop("x14_self_changes", ["__card('^Team')", "__card('Move waiting households').querySelector('.tablewrap')"], max_h=900)
        b.js("(() => { const f = LEAD.state().imports.find(x => x.orig); f.text = f.orig; delete f.orig; LEAD.refresh(); return true; })()")
        # an enumerator finished early: give them five households
        b.js("RTM.setNow('2026-11-13T09:00:00+08:00'); true")
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.3)
        tick('[data-lset="__movesStale"]', True)
        b.js("document.querySelector('#lmv-n').value = '5'; document.querySelector('#lmv-take').value = 'E02'; true"); b.click('[data-lact="take"]'); time.sleep(0.4)
        crop("x11_give_five", ["__card('Move waiting households')"], hls=["document.querySelector('[data-lact=\"take\"]')"], max_h=1000)
        # and one household by hand, from E07 to E02, so that both sides get a revised file
        moved7 = b.js("""(() => { const C = [...LEAD.merged().C.values()], inList = c => LEAD.ui.moves && LEAD.ui.moves.list.some(m => m.hhid === c.hhid);
            const ok = c => c.enumerator_id === 'E07' && !c.replaces && !inList(c) && (c.state === 'not_started' || (c.state === 'in_progress' && !c.dials.some(d => d.status === 'REFUSAL_HARD') && !(c.dials[c.dials.length - 1] || {}).appointment_ts));
            return (C.find(c => ok(c) && c.state === 'not_started') || C.find(ok)).hhid; })()""")
        b.js(f"document.querySelector('#lmv-hh').value = {json.dumps(moved7)}; document.querySelector('#lmv-to').value = 'E02'; true"); b.click('[data-lact="addmove"]'); time.sleep(0.3)
        before = snapshot()
        b.click('[data-lact="writemoves"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'moves'", timeout=60)
        crop("x12_revised_files", ["__card('Move waiting households').querySelector('.alert.info')", "__card('Move waiting households').querySelector('ul.files')"], max_h=520)
        b.click('[data-lact="dlall"]')
        rev07 = wait_new("E07_assignment_R05.json", before); rev02 = wait_new("E02_assignment_R05.json", before)
        # a call after the move: the previous enumerator's later export dials the moved household
        rows = list(csv.DictReader(open([f for f in EXPORTS if os.path.basename(f) == "E07_2026-11-06.csv"][0], encoding="utf-8")))
        extra = dict(rows[-1]); extra.update({"event_id": str(uuid.uuid4()), "hhid": moved7, "ts": "2026-11-14 10:00:00", "end_ts": "2026-11-14 10:01:00", "utc_offset": "+08:00",
                                              "status": "NO_ANSWER", "attempt": "", "dur_min": "1", "is_cmp_code": "0", "phone_slot": "1", "appointment_ts": "", "action": "", "replaces": "", "note": "",
                                              "logged_at": "2026-11-14T10:01:30+08:00", "corrected": "0", "prev_hash": ""})
        extra = {k: v for k, v in extra.items() if k in rows[0]}
        later = os.path.join(DL, "E07_2026-11-14.csv")
        with open(later, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows + [extra])
        b.js("RTM.setNow('2026-11-14T12:00:00+08:00'); true")
        b.click('[data-lact="tab"][data-t="import"]'); time.sleep(0.2)
        b.set_files("#lf-imports", [later]); b.wait(f"LEAD.state().imports.length === {len(EXPORTS) + 1}"); time.sleep(0.4)
        crop("x13_after_move", ["__card('Needs your decision')"], max_h=520)
        # the KoBoToolbox tab with a submission to look at: a second complete on one household
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        phl = glob.glob(os.path.join(S, "kobo", "L2MN-DEMO_CATI_R05_*.csv"))[0]
        prow = list(csv.DictReader(open(phl, encoding="utf-8"), delimiter=";"))
        src = next(r for r in prow if r["X15"] == "1" and r["start"] < "2026-11-06")
        dup = dict(src); dup.update({"_uuid": str(uuid.uuid4()), "start": "2026-11-13T15:00:00.000+08:00", "end": "2026-11-13T15:20:00.000+08:00", "_submission_time": "2026-11-13T07:21:00", "Z8": "3"})
        phl2 = os.path.join(DL, os.path.basename(phl).replace("2026-11-06", "2026-11-14"))
        with open(phl2, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(prow[0].keys()), delimiter=";", lineterminator="\n"); w.writeheader(); w.writerows(prow + [dup])
        b.click('[data-lact="tab"][data-t="platform"]'); time.sleep(0.3)
        b.set_files("#lf-platform", [phl2]); b.wait("LEAD.state().imports.length === 1"); time.sleep(0.5)
        crop("x20_kobo_review", ["__card('3 · Each day').querySelector('h4')", "__card('5 · Records')"], max_h=1100)
        close_leader()

        # ================================ the enumerator receives and loses households ================================
        print("enumerator, updated")
        b.click('[data-act="view"][data-v="enum"]'); b.wait("!!document.querySelector('#f-assign')")
        b.js("RTM.setNow('2026-11-13T09:30:00+08:00'); true")
        b.set_files("#f-assign", [os.path.join(S, "round05", "E07_assignment_R05.json")]); b.wait("!!APP.S")
        b.set_files("#f-update", [rev07]); b.wait("APP.S.events.some(e => e.what === 'assignment_updated')"); time.sleep(0.4)
        crop("x06_update_loaded", ["document.querySelector('section.summary')", "document.querySelector('.alert') || document.querySelector('nav.tabs')"], pad=0, max_h=420, scroll=False)
        b.click('[data-act="tab"][data-t="households"]'); time.sleep(0.2)
        b.js(f"APP.sel = {json.dumps(moved7)}; APP.render(); true"); b.wait(f"APP.sel === '{moved7}'")
        crop("x07_moved_away", ["document.querySelector('.drawer .dhead')", "document.querySelector('.drawer dl.facts')", "document.querySelector('.drawer .alert')"], inside=True)
        b.click('[data-act="closehh"]'); time.sleep(0.1)
        close_enum()
        b.set_files("#f-assign", [os.path.join(S, "round05", "E02_assignment_R05.json")]); b.wait("!!APP.S")
        b.set_files("#f-update", [rev02]); b.wait("APP.S.events.some(e => e.what === 'assignment_updated')"); time.sleep(0.4)
        b.click('[data-act="tab"][data-t="households"]'); time.sleep(0.2)
        b.js(f"APP.sel = {json.dumps(moved7)}; APP.render(); true"); b.wait(f"APP.sel === '{moved7}'")
        crop("x08_received", ["document.querySelector('.drawer .dhead')", "document.querySelector('.drawer dl.facts')", "document.querySelector('.drawer .alert')"], inside=True)
        b.click('[data-act="closehh"]'); time.sleep(0.1)
        close_enum()
        print(f"{len(glob.glob(os.path.join(IMG, 'x*.png')))} example pictures in {IMG}")
    finally:
        b.close()


if __name__ == "__main__":
    main()
