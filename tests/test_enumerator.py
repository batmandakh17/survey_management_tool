"""End-to-end test of the enumerator view (Step 2), in headless Chrome, on the synthetic samples.

Run from the tool folder:  python3 tests/test_enumerator.py
Writes tests/results_enumerator.txt and screenshots in tests/screens/.
"""
import csv
import glob
import hashlib
import io
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from cdp import Browser  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "samples"))
from make_samples import fingerprint as py_fingerprint  # noqa: E402
from make_protected_sample import unseal as py_unseal  # noqa: E402

SCRATCH = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
SCREENS = os.path.join(HERE, "screens")
os.makedirs(SCREENS, exist_ok=True)
STAMP = time.strftime("%H%M%S")
DL = os.path.join(SCRATCH, f"dl_{STAMP}")
TOOL = "file://" + os.path.join(ROOT, "rtm_interview_tool.html")
A07 = os.path.join(ROOT, "samples", "round05", "E07_assignment_R05.json")
P07 = os.path.join(ROOT, "samples", "round05", "E07_project_R05.json")
PAST = os.path.join(ROOT, "samples", "past", "E07_2026-10-21.csv")
COLS = ["program", "round", "hhid", "attempt", "ts", "end_ts", "utc_offset", "dur_min", "status", "is_cmp_code", "operator", "phone_slot",
        "appointment_ts", "action", "replaces", "note", "corrected", "logged_by", "logged_at", "event_id", "prev_hash"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def verify_chain_py(events, genesis):
    prev = genesis
    for i, e in enumerate(events):
        if e["prev_hash"] != prev:
            return False, i
        pub = {k: v for k, v in e.items() if k not in ("hash", "private")}
        if sha(canon(pub)) != e["hash"]:
            return False, i
        prev = e["hash"]
    return True, len(events)


def wait_file(pattern, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        hits = [p for p in glob.glob(os.path.join(DL, pattern)) if not p.endswith(".crdownload")]
        if hits:
            time.sleep(0.3)
            return sorted(hits, key=os.path.getmtime)[-1]
        time.sleep(0.2)
    return None


def snapshot():
    return {p: os.path.getmtime(p) for p in glob.glob(os.path.join(DL, "*"))}


def wait_new(pattern, before, timeout=15):
    """A file matching the pattern that is new, or rewritten since the snapshot (headless Chrome overwrites a same-named download)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in glob.glob(os.path.join(DL, pattern)):
            if not p.endswith(".crdownload") and (p not in before or os.path.getmtime(p) > before[p]):
                time.sleep(0.3)
                return p
        time.sleep(0.2)
    return None


def main():
    b = Browser(os.path.join(SCRATCH, f"profile_{STAMP}"))
    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId="Asia/Ulaanbaatar")
        b.downloads_to(DL)
        b.goto(TOOL)
        b.js("RTM.setNow('2026-10-27T13:00:00+08:00'); APP.noFSA = true; APP.render(); true")
        b.shot(os.path.join(SCREENS, "01_start.png"))

        # ---------- 1. core functions ----------
        check("sha256('abc') matches the FIPS test vector", b.js("RTM.sha256('abc')") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        s = "Ulaanbaatar Улаанбаатар — 試験 " * 50
        check("sha256 of Unicode text equals Python's hashlib", b.js(f"RTM.sha256({json.dumps(s)})") == sha(s))
        sub = b.js(f"crypto.subtle ? crypto.subtle.digest('SHA-256', new TextEncoder().encode({json.dumps(s)})).then(x => Array.from(new Uint8Array(x)).map(v => v.toString(16).padStart(2,'0')).join('')) : 'none'")
        check("sha256 equals the browser's own crypto", sub in (sha(s), "none"), sub)
        check("canonical JSON sorts keys and keeps nulls", b.js("RTM.canon({b:1,a:[2,{d:null,c:'x'}]})") == '{"a":[2,{"c":"x","d":null}],"b":1}')
        rt = b.js("(() => { const rows=[{a:'x,y',b:'say \"hi\"',c:'two\\nlines'},{a:'',b:'Ö',c:'3'}]; const t=RTM.toCSV(rows,['a','b','c']); return JSON.stringify(RTM.parseCSV(t))===JSON.stringify(rows); })()")
        check("CSV writes and reads back commas, quotes, newlines and Unicode", rt)
        check("09:00 in Ulaanbaatar is 01:00 UTC", b.js("RTM.zoned('2026-11-01', 9, 0, 'Asia/Ulaanbaatar').toISOString()") == "2026-11-01T01:00:00.000Z")
        check("weekdays: 26 Oct 2026 is a Monday, 1 Nov a Sunday", b.js("[RTM.weekdayOfKey('2026-10-26'), RTM.weekdayOfKey('2026-11-01')]") == [1, 7])

        # ---------- 2. open the assignment ----------
        b.set_files("#f-assign", [A07])
        b.wait("!!(window.APP && APP.S)")
        n = b.js("APP.S.assignment.households.length")
        a07 = json.load(open(A07))
        check("assignment opens with all its households", n == len(a07["households"]), n)
        check("the Python-made fingerprint verifies in the browser", b.js("RTM.fingerprint(APP.S.assignment) === APP.S.assignment.fingerprint"))
        check("the session starts with a 'started' event, fingerprint confirmed", b.js("APP.S.events[0].type === 'session' && APP.S.events[0].fingerprint_ok === 1"))
        due = b.js("RTM.queue(APP.C, RTM.now(), '2026-10-27').due.map(c => c.hhid)")
        check("today's list has households due (overdue first dials of 26 Oct and those due by 13:00)", len(due) > 0, len(due))
        b.shot(os.path.join(SCREENS, "02_today.png"), full=True)

        def open_hh(h):
            sel = f'[data-act="open"][data-hh="{h}"]'
            if not b.js(f"!!document.querySelector({json.dumps(sel)})"):
                b.click('[data-act="tab"][data-t="households"]')
                b.click('[data-act="filter"][data-f="all"]')
            b.click(sel)
            b.wait(f"APP.sel === {json.dumps(h)}")

        vis = []

        def call(h, slot, start, mins, status, appt=None, note=None, action=None, shot=None):
            b.js(f"RTM.setNow('{start}'); true")
            open_hh(h)
            b.click(f'[data-act="call"][data-slot="{slot}"]')
            b.wait("APP.call && !APP.call.end")
            b.js(f"RTM.setNow(new Date(Date.parse('{start}') + {mins} * 60000).toISOString()); true")
            b.click('[data-act="endcall"]')
            b.wait("!!document.querySelector('#callform')")
            vis.append(b.js("(() => { const r = document.querySelector('.callbox').getBoundingClientRect(); return r.top >= 0 && r.top < window.innerHeight - 120; })()"))
            b.js(f"document.querySelector('input[name=status][value={status}]').checked = true; true")
            if appt:
                b.js(f"document.querySelector('#callform [name=appointment]').value = '{appt}'; true")
            if note:
                b.js(f"document.querySelector('#callform [name=note]').value = {json.dumps(note)}; true")
            if action:
                b.js(f"document.querySelector('#callform [name=action]').value = '{action}'; true")
            if shot:
                b.shot(os.path.join(SCREENS, shot))
            before = b.js("APP.S.events.length")
            b.click('[data-act="savecall"]')
            b.wait(f"APP.S.events.length === {before + 1}")
            return b.js("APP.S.events[APP.S.events.length - 1]")

        # ---------- 3. a complete ----------
        h1 = due[0]
        e = call(h1, 1, "2026-10-27T13:00:00+08:00", 6, "COMPLETE", shot="03_call_result.png")
        check("a complete is logged with start, end, status and who logged it (the clock keeps running, so allow a few seconds)",
              e["status"] == "COMPLETE" and "2026-10-27T13:00:00+08:00" <= e["ts"] <= "2026-10-27T13:00:05+08:00"
              and "2026-10-27T13:06:00+08:00" <= e["end_ts"] <= "2026-10-27T13:06:05+08:00" and e["logged_by"] == "E07" and e["operator"] == "E07", e)
        check("the household is now complete", b.js(f"APP.C.map.get('{h1}').state") == "complete")
        check("after ending a call, the result form is on screen without scrolling", vis == [True], vis)
        keep_h = b.js("APP.C.list.find(c => (c.h.assignment || {}).reason === 'keep').hhid")
        open_hh(keep_h)
        b.click(".drawer details.why summary"); time.sleep(0.1)
        check("a household kept with its enumerator cites the handbook's default rule (Section 3.5.3), one click away under 'Why is this household with me?'",
              "stated default is to keep the same enumerator" in b.js("document.querySelector('.drawer').innerText") and "Section 3.5.3" in b.js("document.querySelector('.drawer').innerText"))
        new_h = b.js("APP.C.list.find(c => (c.h.assignment || {}).reason === 'new').hhid")
        open_hh(new_h)
        check("a new household's planned time is not described as coming from a last interview",
              "from the last interview" not in b.js("document.querySelector('.drawer').innerText") and "planned by your leader" in b.js("document.querySelector('.drawer').innerText"))

        # ---------- 4. a callback ----------
        h2 = due[1]
        call(h2, 1, "2026-10-27T13:10:00+08:00", 2, "APPOINTMENT", appt="2026-10-27T18:30", note="call after work")
        nx = b.js(f"(() => {{ const c = APP.C.map.get('{h2}'); return [c.next.kind, c.next.at.toISOString()]; }})()")
        check("a booked callback is suggested at the agreed time", nx == ["callback", "2026-10-27T10:30:00.000Z"], nx)

        # ---------- 5. redials ----------
        h3 = due[2]
        call(h3, 1, "2026-10-27T13:15:00+08:00", 1, "NO_ANSWER")
        nx = b.js(f"(() => {{ const c = APP.C.map.get('{h3}'); return [c.next.kind, RTM.localISO(c.next.at)]; }})()")
        check("after no answer, a same-day redial at least two hours later", nx[0] == "redial" and nx[1] >= "2026-10-27T15:16", nx)
        call(h3, 1, "2026-10-27T20:30:00+08:00", 1, "NO_ANSWER")
        nx = b.js(f"(() => {{ const c = APP.C.map.get('{h3}'); return [c.next.kind, RTM.localISO(c.next.at)]; }})()")
        check("after an evening dial, the next working day", nx[0] == "next_day" and nx[1].startswith("2026-10-28"), nx)
        b.js("RTM.setNow('2026-10-27T13:30:00+08:00'); APP.render(); true")

        # ---------- 6. the scheduler's rules (section D) ----------
        def sug(last_end, target=18, n=1, cal_extra=""):
            return b.js(f"""(() => {{ const A = JSON.parse(JSON.stringify(APP.S.assignment)); {cal_extra}
              const cal = RTM.calendarOf(A);
              const c = {{ open: true, n: {n}, flags: {{}}, appointment: null, h: {{ plan: {{ target_hour: {target}, first_dial_date: '2026-11-12' }} }},
                           last: {{ ts: '{last_end}', end_ts: '{last_end}' }} }};
              const s = RTM.suggest(c, cal, new Date(Date.parse('2026-10-27T13:30:00+08:00')));
              return [s.kind, s.at ? RTM.localISO(s.at) : null]; }})()""")
        r = sug("2026-11-07T20:50:00+08:00")
        check("a Saturday-evening dial moves to Monday (Sunday is not a working day)", r == ["next_day", "2026-11-09T18:00:00+08:00"], r)
        r = sug("2026-11-09T20:50:00+08:00")
        check("a dial on the eve of the 10 November holiday moves to 11 November", r == ["next_day", "2026-11-11T18:00:00+08:00"], r)
        r = sug("2026-11-02T10:00:00+08:00", n=8)
        check("at the dial cap (8), the suggestion is to release", r[0] == "cap", r)
        r = sug("2026-11-20T20:30:00+08:00")
        check("past the window's last day, the suggestion is to release", r[0] == "window_end", r)
        r = b.js("""(() => { const A = JSON.parse(JSON.stringify(APP.S.assignment)); A.calendar.ramadan = { dates: ['2026-11-12'], break_fast_hour: 18 };
              const cal = RTM.calendarOf(A); const c = { open: true, n: 0, flags: {}, appointment: null, h: { plan: { target_hour: 18, first_dial_date: '2026-11-12' } } };
              const s = RTM.suggest(c, cal, new Date(Date.parse('2026-10-27T13:30:00+08:00'))); return [s.kind, RTM.localISO(s.at)]; })()""")
        check("during Ramadan, a dial planned at the hour the fast is broken moves an hour later", r == ["first", "2026-11-12T19:00:00+08:00"], r)
        r = b.js("""(() => { const A = JSON.parse(JSON.stringify(APP.S.assignment)); const cal = RTM.calendarOf(A);
              const c = { open: true, n: 0, flags: {}, appointment: null, h: { plan: { target_hour: 7, first_dial_date: '2026-11-03' } } };
              const s = RTM.suggest(c, cal, new Date(Date.parse('2026-10-27T13:30:00+08:00'))); return RTM.localISO(s.at); })()""")
        check("a target hour before the call hours moves to the opening hour", r == "2026-11-03T09:00:00+08:00", r)

        # ---------- 7. a dead number, then a replacement ----------
        hd = b.js("APP.C.list.filter(c => c.open && c.n === 0 && c.slots.length === 1 && c.replacements.length).map(c => c.hhid)[0]")
        call(hd, 1, "2026-10-27T13:40:00+08:00", 0.3, "DEAD_NUMBER")
        st = b.js(f"(() => {{ const c = APP.C.map.get('{hd}'); return [c.flags.all_dead, c.next.kind]; }})()")
        check("a household whose only number is dead needs a decision", st == [True, "dead"], st)
        check("the remove request is enabled once no number works", b.js("!document.querySelector('[data-act=remove]').disabled"))
        rep = b.js(f"APP.C.map.get('{hd}').replacements[0].hhid")
        b.click('[data-act="replace"]')
        b.wait("APP.modal && APP.modal.kind === 'confirm'")
        b.shot(os.path.join(SCREENS, "04_replacement_modal.png"))
        b.js("document.querySelector('#modal-input').value = 'only number not in service'; true")
        b.click('[data-act="modalok"]')
        b.wait(f"APP.C.map.has('{rep}')")
        st = b.js(f"[APP.C.map.get('{hd}').state, APP.C.map.get('{rep}').kind, APP.C.map.get('{rep}').h.replaces, APP.C.map.get('{rep}').open]")
        check("activating a replacement closes the household and opens its first replacement", st == ["replaced", "replacement", hd, True], st)

        # ---------- 8. release, and undo ----------
        open_hh(h3)
        b.click('[data-act="release"]')
        b.wait("APP.modal && APP.modal.kind === 'confirm'")
        b.click('[data-act="modalok"]')
        b.wait(f"APP.C.map.get('{h3}').state === 'released'")
        check("release closes the household for the round", True)
        ev = b.js(f"APP.C.map.get('{h3}').actions.find(a => a.action === 'RELEASE').event_id")
        b.click(f'[data-act="correct"][data-ev="{ev}"]')
        b.wait("!!document.querySelector('#corrform')")
        b.js("document.querySelector('#corrform [name=reason]').value = 'released by mistake'; true")
        b.click('[data-act="savecorr"]')
        b.wait(f"APP.C.map.get('{h3}').state === 'in_progress'")
        check("undoing the release reopens it; both entries stay in the log", b.js("APP.S.events.filter(e => e.type === 'correction').length") == 1)

        # ---------- 9. corrections and voids ----------
        dev = b.js(f"APP.C.map.get('{h1}').dials[0].event_id")
        open_hh(h1)
        b.click(f'[data-act="correct"][data-ev="{dev}"]')
        b.wait("!!document.querySelector('#corrform')")
        b.js("document.querySelector('#corrform [name=minutes]').value = '2'; document.querySelector('#corrform [name=reason]').value = 'timer left running'; true")
        b.click('[data-act="savecorr"]')
        b.wait(f"APP.C.map.get('{h1}').flags.complete_short === true")
        st_short = b.js(f"(() => {{ const c = APP.C.map.get('{h1}'); return [c.state, c.open, document.querySelector('.drawer').innerText.includes('counts it as an appointment contact')]; }})()")
        check("a corrected complete under 3 minutes is flagged, and the household stays open to call again, as Box 3.0 and the leader's counts have it",
              st_short == ["in_progress", True, True], st_short)
        h4 = due[3]
        call(h4, 1, "2026-10-27T14:00:00+08:00", 0.2, "BUSY")
        vev = b.js(f"APP.C.map.get('{h4}').dials[0].event_id")
        b.click(f'[data-act="correct"][data-ev="{vev}"]')
        b.wait("!!document.querySelector('#corrform')")
        b.js("document.querySelector('#corrform [name=void]').checked = true; document.querySelector('#corrform [name=reason]').value = 'wrong household'; true")
        b.click('[data-act="savecorr"]')
        b.wait(f"APP.C.map.get('{h4}').n === 0")
        check("a voided call leaves the effective log but stays in the event log", b.js(f"APP.S.events.some(e => e.event_id === '{vev}')"))

        cev = b.js(f"APP.C.map.get('{h2}').dials[0].event_id")
        open_hh(h2)
        b.click(f'[data-act="correct"][data-ev="{cev}"]')
        b.wait("!!document.querySelector('#corrform')")
        nev = b.js("APP.S.events.length")
        b.js("document.querySelector('#corrform [name=note]').value = 'call after 18:00'; document.querySelector('#corrform [name=reason]').value = 'clearer note'; true")
        b.click('[data-act="savecorr"]')
        b.wait(f"APP.S.events.length === {nev + 1}")
        ch = b.js("APP.S.events[APP.S.events.length - 1].changes")
        check("a correction changes only the field the enumerator edited (times shown to the minute stay exact)", ch == {"note": "call after 18:00"}, ch)

        # ---------- 10. a call logged afterwards ----------
        h5 = b.js(f"APP.C.list.filter(c => c.open && c.n === 0 && c.kind !== 'replacement' && !{json.dumps(due[:4])}.includes(c.hhid)).map(c => c.hhid)[0]")
        open_hh(h5)
        b.click('[data-act="manual"]')
        b.wait("!!document.querySelector('#callform [name=start]')")
        b.js("""(() => { const f = document.querySelector('#callform'); f.querySelector('[name=start]').value = '2026-10-27T10:15'; f.querySelector('[name=minutes]').value = '3';
                f.querySelector('input[name=status][value=NOT_AVAILABLE]').checked = true; return true; })()""")
        b.click('[data-act="savemanual"]')
        b.wait(f"APP.C.map.get('{h5}').n === 1")
        e = b.js("APP.S.events[APP.S.events.length - 1]")
        check("a call logged afterwards keeps its own time and records when it was entered",
              e["ts"] == "2026-10-27T10:15:00+08:00" and e["logged_at"] > e["ts"] and e.get("entered") == "after the call", e)

        # ---------- 11. a new phone number ----------
        open_hh(h2)
        b.click('[data-act="contact"]')
        b.wait("!!document.querySelector('#contactform')")
        b.js("""(() => { const f = document.querySelector('#contactform'); f.querySelector('[name=slot]').value = 'new'; f.querySelector('[name=number]').value = '+000 5555 1234';
                f.querySelector('[name=label]').value = 'spouse'; return true; })()""")
        b.click('[data-act="savecontact"]')
        b.wait(f"APP.C.map.get('{h2}').slots.length >= 2")
        e = b.js("APP.S.events[APP.S.events.length - 1]")
        check("a new number is logged with its digest, the number kept apart", e["type"] == "contact_update" and e["private"]["number"] == "+000 5555 1234" and e["private_digest"] == sha(canon({"number": "+000 5555 1234"})), e)
        b.shot(os.path.join(SCREENS, "05_household.png"), full=True)
        check("the event log passes its integrity check", b.js("RTM.verifyChain(APP.S.events, APP.S.genesis).ok"))

        # ---------- 12. export ----------
        b.click('[data-act="export"]')
        b.wait("APP.modal && APP.modal.kind === 'export'")
        b.shot(os.path.join(SCREENS, "06_export.png"))
        for w in ("csv", "json", "contacts"):
            b.click(f'[data-act="dl"][data-what="{w}"]')
        fcsv, fjson, fcon = wait_file("E07_2026-10-27.csv"), wait_file("E07_2026-10-27.json"), wait_file("E07_2026-10-27_contacts.json")
        check("the export is named {enumerator_id}_{date}", all([fcsv, fjson, fcon]), [fcsv, fjson, fcon])
        J = json.load(open(fjson, encoding="utf-8"))
        csv_text = open(fcsv, encoding="utf-8").read()
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        ok, at = verify_chain_py(J["events"], J["chain_genesis"])
        check("the exported hash chain verifies in Python", ok and J["last_hash"] == J["events"][-1]["hash"], at)
        check("the export's genesis is the assignment's fingerprint", J["chain_genesis"] == a07["fingerprint"])
        check("the CSV has the documented columns, without a byte-order mark", csv_text.split("\n")[0] == ",".join(COLS))
        check("the CSV rows equal the JSON's dial rows", [{k: r[k] for k in COLS} for r in rows] == [{k: ("" if v is None else str(v)) for k, v in d.items()} for d in J["dials"]])
        check("the CSV holds one row per effective dial (voided call excluded)", len(rows) == b.js("RTM.effective(APP.S).dials.length"))
        check("no phone number appears in the CSV or the JSON", "+000" not in csv_text and "+000" not in json.dumps(J, ensure_ascii=False))
        check("the JSON lists corrections and contact updates (without numbers), as the proposal's section A.4 says",
              len(J["corrections"]) == sum(1 for e in J["events"] if e["type"] == "correction") and len(J["contact_updates"]) == 1 and "number" not in J["contact_updates"][0])
        CJ = json.load(open(fcon, encoding="utf-8"))
        check("the contacts file holds the new number and matches its digest", CJ["updates"][0]["number"] == "+000 5555 1234" and CJ["updates"][0]["private_digest"] == sha(canon({"number": "+000 5555 1234"})))
        check("the corrected complete shows as corrected, 2 minutes", any(r["hhid"] == h1 and r["corrected"] == "1" and r["dur_min"] == "2.00" for r in rows))
        b.click('[data-act="closemodal"]')

        # ---------- 13. round trip: the exported files read back as written ----------
        back_csv = b.js(f"RTM.readExport({json.dumps(csv_text)}, 'x.csv').rows")
        back_json = b.js(f"RTM.readExport({json.dumps(open(fjson, encoding='utf-8').read())}, 'x.json').rows")
        check("export, reload: the CSV reads back identical", back_csv == [{k: r[k] for k in COLS} for r in rows])
        check("export, reload: the JSON reads back identical to the CSV", back_json == back_csv)

        # ---------- 14. save, close, reopen: nothing lost ----------
        snap = b.js("JSON.stringify({ ev: APP.S.events, st: APP.C.list.map(c => [c.hhid, c.state, c.n, c.next.kind, c.next.at ? c.next.at.toISOString() : null]) })")
        b.click('[data-act="save"]')
        fp = wait_file("E07_project_R05_*.json")
        check("the session saves to E07_project_R05_<date>_<time>.json when the browser cannot overwrite a file", fp is not None, fp)
        P = json.load(open(fp, encoding="utf-8"))
        chk = P.pop("checksum")
        check("the saved session's checksum verifies in Python", sha(canon(P)) == chk)
        check("the saved session's hash chain verifies in Python", verify_chain_py(P["events"], P["chain_genesis"])[0])
        check("saving clears the unsaved count", b.js("APP.unsaved") == 0)
        b.click('[data-act="close"]')
        b.wait("APP.modal && APP.modal.kind === 'confirm'")
        b.click('[data-act="modalok"]')
        b.wait("APP.S === null")
        b.set_files("#f-project", [fp])
        b.wait("!!APP.S")
        snap2 = b.js("JSON.stringify({ ev: APP.S.events, st: APP.C.list.map(c => [c.hhid, c.state, c.n, c.next.kind, c.next.at ? c.next.at.toISOString() : null]) })")
        check("save and reload mid-session: every event and every household's state is restored", snap == snap2)
        X2 = b.js("RTM.buildExport(APP.S, RTM.now()).csv")
        check("save and reload: a new export gives the same CSV", X2 == csv_text)

        # ---------- 15. the Python-made sample session, and earlier logs ----------
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-project", [P07])
        b.wait("!!APP.S")
        check("the Python-made saved session opens: checksum and chain verified across languages", b.js("APP.S.events.length") == len(json.load(open(P07))["events"]) and not b.js("APP.loadErrors.length"))
        past_rows = list(csv.DictReader(open(PAST, encoding="utf-8")))
        sep = [r for r in past_rows if r["ts"].startswith("2026-09")]
        exp_sep = (len(sep), sum(1 for r in sep if r["status"] == "COMPLETE" and float(r["dur_min"]) >= 3))
        got = b.js("(() => { const tz = APP.C.cal.tz; const all = APP.C.eff.dials.map(RTM.dialRow).concat(APP.S.past.dials); const p = RTM.perf(all.filter(r => RTM.monthKey(r, tz) === '2026-09'), tz); return [p.dials, p.completes]; })()")
        check("performance: last month's dials and completes equal a count from the CSV", got == list(exp_sep), [got, exp_sep])
        b.set_files("#f-past", [PAST])
        b.wait("APP.toasts.some(t => /no new dials/.test(t.text))")
        check("loading an earlier log twice adds nothing (rows matched by event ID)", b.js("APP.S.past.dials.length") == len(past_rows))
        b.click('[data-act="tab"][data-t="performance"]')
        b.shot(os.path.join(SCREENS, "07_performance.png"), full=True)
        b.click('[data-act="tab"][data-t="calendar"]')
        b.shot(os.path.join(SCREENS, "08_calendar.png"), full=True)
        check("the calendar shows the 10 November holiday", "Genghis Khan" in b.js("document.querySelector('.months').innerText"))
        b.click('[data-act="tab"][data-t="households"]')
        b.shot(os.path.join(SCREENS, "09_households.png"), full=True)
        b.click('[data-act="tab"][data-t="log"]')
        check("the log tab reports the integrity check", "Integrity check passed" in b.js("document.querySelector('.panel').innerText"))
        b.shot(os.path.join(SCREENS, "10_log.png"))

        # ---------- 16. wrong files are refused with a clear message ----------
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-assign", [P07])
        b.wait("APP.loadErrors.length > 0")
        check("a saved session opened as an assignment is refused, saying which button to use", "saved session" in b.js("APP.loadErrors[0]"))
        b.set_files("#f-project", [A07])
        b.wait("APP.loadErrors.length > 0 && /assignment file/.test(APP.loadErrors[0])")
        check("an assignment opened as a saved session is refused", True)
        bad = os.path.join(SCRATCH, f"tampered_{STAMP}.json")
        T = json.load(open(P07, encoding="utf-8"))
        next(e for e in T["events"] if e["type"] == "dial")["status"] = "COMPLETE"
        json.dump(T, open(bad, "w", encoding="utf-8"))
        b.set_files("#f-project", [bad])
        b.wait("APP.loadErrors.length > 0 && /checksum/.test(APP.loadErrors.join(' '))")
        check("a saved session edited outside the tool is refused (checksum)", True)
        badA = os.path.join(SCRATCH, f"tampered_assign_{STAMP}.json")
        TA = json.load(open(A07, encoding="utf-8"))
        TA["households"][0]["contact"]["name"] = "edited by hand"
        json.dump(TA, open(badA, "w", encoding="utf-8"))
        b.set_files("#f-assign", [badA])
        b.wait("!!APP.S")
        check("an assignment changed after it was generated opens with a warning, recorded in the log",
              any("fingerprint" in w for w in b.js("APP.loadWarnings")) and b.js("APP.S.events[0].fingerprint_ok") == 0)
        b.shot(os.path.join(SCREENS, "11_warning.png"))
        b.set_files("#f-past", [PAST])
        b.wait(f"APP.S.past.dials.length === {len(past_rows)}")
        check("an earlier log loads into a fresh session: every dial added once", b.js("APP.S.past.files.length") == 1)
        other = os.path.join(SCRATCH, f"E02_2026-10-21_{STAMP}.csv")
        open(other, "w", encoding="utf-8").write(open(PAST, encoding="utf-8").read().replace(",E07,", ",E02,"))
        b.set_files("#f-past", [other])
        b.wait("APP.toasts.some(t => /E02's log, not yours/.test(t.text))")
        check("another enumerator's earlier log is refused: the performance view uses only the enumerator's own logs",
              b.js("APP.S.past.dials.length") == len(past_rows))
        b.click('[data-act="tab"][data-t="households"]')
        check("the Households tab cites the handbook's default rule", "Section 3.5.3" in b.js("document.querySelector('.panel').innerText"))

        # ---------- 17. an updated assignment from the leader ----------
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.js("RTM.setNow('2026-10-27T15:00:00+08:00'); true")
        b.set_files("#f-assign", [A07]); b.wait("!!APP.S")
        due17 = b.js("RTM.queue(APP.C, RTM.now(), '2026-10-27').due.map(c => c.hhid)")
        first, second = due17[0], due17[1]
        call(first, 1, "2026-10-27T15:00:00+08:00", 1, "NO_ANSWER")
        call(second, 1, "2026-10-27T15:05:00+08:00", 1, "NO_ANSWER")
        U = json.load(open(A07, encoding="utf-8"))
        gone = next(h for h in U["households"] if h["hhid"] not in (first, second))["hhid"]
        U["households"] = [h for h in U["households"] if h["hhid"] not in (gone, second)]
        extra = json.loads(json.dumps(U["households"][-1])); extra["hhid"] = "0112-099"; extra["assignment"] = {"reason": "manual"}; extra["replacements"] = []
        U["households"].append(extra); U["generated_at"] = "2026-10-27T14:30:00+08:00"; U["fingerprint"] = py_fingerprint(U)
        upd = os.path.join(SCRATCH, f"E07_assignment_R05_update_{STAMP}.json"); json.dump(U, open(upd, "w", encoding="utf-8"), ensure_ascii=False)
        b.set_files("#f-update", [upd])
        b.wait("APP.S.events.some(e => e.what === 'assignment_updated')")
        e = b.js("APP.S.events.find(e => e.what === 'assignment_updated')")
        check("an updated assignment is logged: households added and removed, by ID, its fingerprint confirmed",
              e["households_added"] == 1 and e["households_removed"] == 2 and sorted(e["removed_hhids"]) == sorted([gone, second]) and e["fingerprint_ok"] == 1 and e["logged_by"] == "E07", e)
        check("after the update, the new household is listed and the calls already logged are kept",
              b.js("APP.C.map.has('0112-099')") and b.js(f"APP.C.map.get('{first}').n") == 1)
        st = b.js(f"['{gone}', '{second}'].map(h => {{ const c = APP.C.map.get(h); return c ? [c.kind, c.state, c.open, c.n] : null; }})")
        check("households taken out by the update stay visible, read-only, with their logged calls (proposal, section B)",
              st == [["removed", "reassigned", False, 0], ["removed", "reassigned", False, 1]], st)
        check("a removed household's call is still in the export, and the summary counts it apart",
              any(r["hhid"] == second for r in b.js("RTM.buildExport(APP.S, RTM.now()).rows")) and "2 no longer assigned to you" in b.js("document.querySelector('.legend').innerText"))
        b.set_files("#f-update", [upd])
        b.wait("APP.toasts.some(t => /already in your session/.test(t.text))")
        check("opening the same update twice changes nothing", b.js("APP.S.events.filter(e => e.what === 'assignment_updated').length") == 1)
        nev = b.js("APP.S.events.length")
        b.set_files("#f-update", [os.path.join(ROOT, "samples", "round05", "E02_assignment_R05.json")])
        b.wait("APP.toasts.some(t => /not E07/.test(t.text))")
        check("another enumerator's assignment is refused as an update, and nothing is logged", b.js("APP.S.events.length") == nev)
        before = snapshot()
        b.click('[data-act="save"]')
        newest = wait_new("E07_project_R05_*.json", before)
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-project", [newest]); b.wait("!!APP.S || APP.loadErrors.length")
        check("a session saved after an update reopens cleanly (chain still starts at the first assignment)",
              b.js("!!APP.S && APP.loadErrors.length === 0 && APP.C.map.has('0112-099')"), b.js("APP.loadErrors"))

        # ---------- 18. a protected assignment (D11) ----------
        PROT = os.path.join(ROOT, "samples", "round05", "E07_assignment_R05_protected.json")
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-assign", [PROT])
        b.wait("APP.modal && APP.modal.kind === 'passphrase'")
        b.shot(os.path.join(SCREENS, "13_passphrase.png"))
        b.js("document.querySelector('#modal-input').value = 'not-the-passphrase'; true")
        b.click('[data-act="unseal"]')
        b.wait("APP.modal && !!APP.modal.error", timeout=30)
        check("a wrong passphrase is refused with a clear message", "does not open this file" in b.js("APP.modal.error") and b.js("APP.S") is None)
        b.js("document.querySelector('#modal-input').value = 'synthetic-E07'; true")
        b.click('[data-act="unseal"]')
        b.wait("!!APP.S", timeout=30)
        check("the right passphrase opens the Python-protected assignment: all households, fingerprint confirmed, logged as protected",
              b.js("APP.S.assignment.households.length") == len(a07["households"]) and b.js("APP.S.events[0].fingerprint_ok") == 1 and b.js("APP.S.events[0].protected") == 1)
        check("the passphrase is not kept: not in the page, not in the log; the key cannot be extracted",
              "synthetic-E07" not in b.js("JSON.stringify(APP.S.events) + document.documentElement.outerHTML") and b.js("APP.S.seal.key.extractable") is False)
        hp = b.js("APP.C.list[0].hhid")
        open_hh(hp)
        b.click('[data-act="contact"]'); b.wait("!!document.querySelector('#contactform')")
        b.js("""(() => { const f = document.querySelector('#contactform'); f.querySelector('[name=slot]').value = 'new'; f.querySelector('[name=number]').value = '+000 4444 9999'; return true; })()""")
        b.click('[data-act="savecontact"]'); b.wait("APP.S.events.some(e => e.type === 'contact_update')")
        before = snapshot()
        b.click('[data-act="export"]'); b.wait("APP.modal && APP.modal.kind === 'export'")
        b.click('[data-act="dl"][data-what="contacts"]')
        fc = wait_new("E07_*_contacts*.json", before)
        CE = json.load(open(fc, encoding="utf-8"))
        check("with a protected assignment, the contacts file is protected too, and Python opens it",
              CE["schema"] == "rtm-sealed-1.0" and CE["contains"] == "rtm-contacts-1.0" and "+000" not in open(fc, encoding="utf-8").read()
              and py_unseal(CE, "synthetic-E07")["updates"][0]["number"] == "+000 4444 9999")
        b.click('[data-act="closemodal"]')
        before = snapshot()
        b.click('[data-act="save"]')
        fp2 = wait_new("E07_project_R05_*.json", before)
        PE = json.load(open(fp2, encoding="utf-8"))
        inner = py_unseal(PE, "synthetic-E07")
        chk = inner.pop("checksum")
        check("the saved session is protected as well; Python opens it and its checksum verifies",
              PE["contains"] == "rtm-project-1.0" and "+000" not in open(fp2, encoding="utf-8").read() and sha(canon(inner)) == chk)
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-project", [fp2]); b.wait("APP.modal && APP.modal.kind === 'passphrase'")
        b.js("document.querySelector('#modal-input').value = 'synthetic-E07'; true")
        b.click('[data-act="unseal"]'); b.wait("!!APP.S", timeout=30)
        check("the protected saved session reopens with the passphrase, nothing lost", b.js("APP.S.events.length") == len(inner["events"]) and b.js("!!APP.S.seal"))
        T = json.loads(json.dumps(PE)); T["enumerator_id"] = "E02"
        badp = os.path.join(SCRATCH, f"relabelled_{STAMP}.json"); json.dump(T, open(badp, "w"))
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-project", [badp]); b.wait("APP.modal && APP.modal.kind === 'passphrase'")
        b.js("document.querySelector('#modal-input').value = 'synthetic-E07'; true")
        b.click('[data-act="unseal"]'); b.wait("APP.modal && !!APP.modal.error", timeout=30)
        check("a protected file whose label was changed is refused, even with the right passphrase", b.js("APP.S") is None)
        b.click('[data-act="closemodal"]')
        b.set_files("#f-assign", [A07]); b.wait("!!APP.S")
        # closing with unsaved changes offers to save first (usability pass, round 4)
        before = snapshot()
        b.click('[data-act="close"]'); b.wait("APP.modal")
        labels = b.js("[...document.querySelectorAll('.modal button')].map(x => x.textContent)")
        b.click('[data-act="modalok"]'); b.wait("APP.S === null")
        fp3 = wait_new("E07_project_R05_*.json", before)
        check("closing with unsaved changes offers 'Save, then close' first, and it saves the session before closing",
              labels[:2] == ["Save, then close", "Close without saving"] and fp3 is not None, [labels, fp3])
        b.set_files("#f-assign", [A07]); b.wait("!!APP.S")

        # ---------- 19. no network ----------
        r = b.js("fetch('https://example.com/x').then(() => 'loaded').catch(() => 'blocked')")
        check("the page cannot fetch anything (content-security policy)", r == "blocked", r)
        r = b.js("""new Promise(res => { document.addEventListener('securitypolicyviolation', e => res('blocked ' + e.violatedDirective), { once: true });
                    const i = new Image(); i.src = 'https://example.com/p.png'; setTimeout(() => res('no violation'), 3000); })""")
        check("the page cannot load an image from outside either", r.startswith("blocked"), r)

        # ---------- 20. phone width ----------
        b.ws.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        b.js("APP.tab = 'today'; APP.render(); true")
        b.shot(os.path.join(SCREENS, "12_phone_today.png"))
        wide = b.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
        check("at phone width (390 px) the page has no sideways scroll", wide, b.js("[document.documentElement.scrollWidth, window.innerWidth]"))
        b.ws.call("Emulation.clearDeviceMetricsOverride")

        # ---------- 20b. the day list, and a household moved during the round (the author's requests of 28 October 2026) ----------
        if b.js("!!APP.S"):
            b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.js("RTM.setNow('2026-10-27T13:00:00+08:00'); true")
        b.set_files("#f-assign", [A07]); b.wait("!!APP.S")
        q = b.js("(() => { const q = RTM.queue(APP.C, RTM.now(), '2026-10-27'); return { dl: q.dayList, due: q.due.length, later: q.later.length, ahead: q.ahead.map(c => [c.hhid, c.next.kind, RTM.partsIn(c.next.at, APP.C.cal.tz).key]) }; })()")
        check("the assignment carries the leader's day list; today's list is filled up to it with households ahead of plan, none due today and no callbacks",
              q["dl"] == json.load(open(A07))["calendar"]["day_list"] and len(q["ahead"]) == max(0, q["dl"] - q["due"] - q["later"])
              and all(k > "2026-10-27" and kind != "callback" for _, kind, k in q["ahead"]) and [k for _, _, k in q["ahead"]] == sorted(k for _, _, k in q["ahead"]), q)
        check("the Today tab has an 'Ahead of plan' column and explains the day list", "Ahead of plan" in b.js("document.querySelector('.panel').innerText") and f"day list of {q['dl']} households" in b.js("document.querySelector('.panel').innerText"))
        unitq = b.js("""(() => { const A = JSON.parse(JSON.stringify(APP.S.assignment)); A.households = A.households.slice(0, 6);
            const days = ['2026-10-27', '2026-10-27', '2026-10-30', '2026-10-28', '2026-11-02', '2026-10-29'];
            A.households.forEach((h, i) => { h.plan = { first_dial_date: days[i], target_hour: 10 }; }); A.calendar.day_list = 5; delete A.fingerprint;
            const q = RTM.queue(RTM.cases(RTM.newSession(A), RTM.now()), RTM.now(), '2026-10-27');
            A.calendar.day_list = 2; const q2 = RTM.queue(RTM.cases(RTM.newSession(A), RTM.now()), RTM.now(), '2026-10-27');
            delete A.calendar.day_list; const q3 = RTM.queue(RTM.cases(RTM.newSession(A), RTM.now()), RTM.now(), '2026-10-27');
            return { ahead: q.ahead.map(c => c.h.plan.first_dial_date), due: q.due.length, ahead2: q2.ahead.length, dl3: q3.dayList, ahead3: q3.ahead.length }; })()""")
        check("the day list pulls households forward from later days, soonest first, only up to the list length; a file without a day list shows none",
              unitq == {"ahead": ["2026-10-28", "2026-10-29", "2026-10-30"], "due": 2, "ahead2": 0, "dl3": None, "ahead3": 0}, unitq)
        unith = b.js("""(() => { const A = JSON.parse(JSON.stringify(APP.S.assignment)); const h = A.households[0];
            h.handover = { from: 'E02', moved_at: '2026-10-27T09:00:00+08:00', dials: 7, last_status: 'NO_ANSWER', last_ts: '2026-10-26T18:00:00+08:00' }; delete A.fingerprint;
            const c = RTM.cases(RTM.newSession(A), RTM.now()).map.get(h.hhid);
            h.handover.dials = 8; const c8 = RTM.cases(RTM.newSession(A), RTM.now()).map.get(h.hhid);
            return { nAll: c.nAll, cap: c.flags.cap_reached, kind: c.next.kind, prior: c.prior.from, kind8: c8.next.kind, text8: c8.next.text }; })()""")
        check("a household moved mid-round brings the previous enumerator's dials: 7 of a cap of 8 leave one; 8 reach the cap, and the suggestion says whose dials they were",
              unith["nAll"] == 7 and unith["cap"] is False and unith["kind"] in ("first", "overdue") and unith["prior"] == "E02" and unith["kind8"] == "cap" and "8 of the dials by E02" in unith["text8"], unith)
        # a revised file that omits the plans of households already held: they are carried beside it, and survive a save
        U = json.load(open(A07, encoding="utf-8"))
        U["generated_at"] = "2026-10-27T12:00:00+08:00"; U["revision"] = 2; U["supersedes"] = U["fingerprint"]
        for h in U["households"]:
            h.pop("plan", None); h.pop("history", None)
        U["fingerprint"] = py_fingerprint(U)
        upd2 = os.path.join(SCRATCH, f"E07_assignment_R05_rev2_{STAMP}.json"); json.dump(U, open(upd2, "w", encoding="utf-8"), ensure_ascii=False)
        h0 = U["households"][0]["hhid"]
        plan0 = b.js(f"JSON.stringify(APP.C.map.get('{h0}').h.plan)")
        b.set_files("#f-update", [upd2]); b.wait("APP.S.events.some(e => e.what === 'assignment_updated')")
        check("a revised file without plans keeps every household's plan and history from the earlier file, and the file's own fingerprint still verifies",
              b.js(f"JSON.stringify(APP.C.map.get('{h0}').h.plan)") == plan0 and b.js("APP.S.events.find(e => e.what === 'assignment_updated').fingerprint_ok") == 1 and b.js("RTM.fingerprint(APP.S.assignment) === APP.S.fingerprint"))
        before = snapshot()
        b.click('[data-act="save"]')
        newest = wait_new("E07_project_R05*.json", before)
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-project", [newest]); b.wait("!!APP.S || APP.loadErrors.length")
        check("the carried plans survive a save and reopen", b.js(f"!!APP.S && APP.loadErrors.length === 0 && JSON.stringify(APP.C.map.get('{h0}').h.plan)") == plan0, b.js("APP.loadErrors"))
        nev = b.js("APP.S.events.length")
        b.set_files("#f-update", [A07])
        b.wait("APP.toasts.some(t => /older than the assignment in your session/.test(t.text))")
        check("the earlier file, opened again by mistake, is refused as older and nothing is logged", b.js("APP.S.events.length") == nev)

        # ---------- 21. every file the browser wrote passes the format checker ----------
        sys.path.insert(0, os.path.join(ROOT, "formats"))
        import check_formats as cf
        from contextlib import redirect_stdout
        os.environ["RTM_PASSPHRASE"] = "synthetic-E07"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cf.main([DL])
        os.environ.pop("RTM_PASSPHRASE", None)
        check("every file the browser wrote passes the format checker: schema, integrity, privacy (protected ones opened)",
              code == 0 and "warning" not in buf.getvalue(), buf.getvalue())
    finally:
        b.close()
    passed = sum(ok for _, ok, _ in results)
    lines = [f"Enumerator view tests, {time.strftime('%d %b %Y %H:%M')}: {passed} of {len(results)} passed"] + [("PASS " if ok else "FAIL ") + n + (f"  [{d}]" if d and not ok else "") for n, ok, d in results]
    open(os.path.join(HERE, "results_enumerator.txt"), "w").write("\n".join(lines) + "\n")
    print(lines[0])
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
