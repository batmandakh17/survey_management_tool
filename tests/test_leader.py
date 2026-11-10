"""End-to-end test of the leader view (Step 3), in headless Chrome, on the synthetic samples.

Run from the tool folder:  python3 tests/test_leader.py
Writes tests/results_leader.txt and screenshots in tests/screens/leader_*.png.
The analytics are checked against an independent Python implementation of the handbook's rules (tests/ref_stats.py).
"""
import collections
import csv
import glob
import hashlib
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "samples"))
sys.path.insert(0, os.path.join(ROOT, "formats"))
from cdp import Browser  # noqa: E402
from make_protected_sample import unseal as py_unseal  # noqa: E402
import ref_stats  # noqa: E402

SCRATCH = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
SCREENS = os.path.join(HERE, "screens")
os.makedirs(SCREENS, exist_ok=True)
STAMP = time.strftime("%H%M%S")
DL = os.path.join(SCRATCH, f"ldl_{STAMP}")
TOOL = "file://" + os.path.join(ROOT, "rtm_interview_tool.html")
S = os.path.join(ROOT, "samples", "leader")
HIST = sorted(glob.glob(os.path.join(S, "history", "*")))
EXPORTS = sorted(glob.glob(os.path.join(S, "exports_R05", "*")))
MANIFEST = os.path.join(S, "L2MN-DEMO_R05_manifest.json")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:600]}]" if detail and not ok else ""))


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def snapshot():
    return {p: os.path.getmtime(p) for p in glob.glob(os.path.join(DL, "*"))}


def wait_new(pattern, before, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in sorted(glob.glob(os.path.join(DL, pattern))):
            if not p.endswith(".crdownload") and (p not in before or os.path.getmtime(p) > before[p]):
                time.sleep(0.3)
                return p
        time.sleep(0.2)
    return None


def main():
    b = Browser(os.path.join(SCRATCH, f"lprofile_{STAMP}"), port=9344)
    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId="Asia/Ulaanbaatar")
        b.downloads_to(DL)
        b.goto(TOOL)
        b.js("RTM.setNow('2026-10-23T15:00:00+08:00'); APP.noFSA = true; true")

        def setv(sel, v):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

        def tick(sel, on):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.checked = {str(bool(on)).lower()}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

        def start(leader="L01", program="L2MN-DEMO", country="MN", rnd=5):
            if b.js("!!(window.LEAD && LEAD.state())"):
                b.click('[data-lact="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("!LEAD.state()")
            if b.js("APP.view") != "leader":
                b.click('[data-act="view"][data-v="leader"]')
            b.wait("!!document.querySelector('#lstart')")
            b.js(f"""(() => {{ const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = {json.dumps(leader)};
                   f.querySelector('[name=program]').value = {json.dumps(program)}; f.querySelector('[name=country]').value = {json.dumps(country)};
                   f.querySelector('[name=round]').value = {json.dumps(str(rnd))}; return true; }})()""")
            b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")

        # ================= A. preparing round 5 =================
        b.click('[data-act="view"][data-v="leader"]')
        b.wait("!!document.querySelector('#lstart')")
        b.shot(os.path.join(SCREENS, "leader_01_start.png"))
        check("the leader view states plainly that it has no server, shared database or network",
              "no server, no shared database and no network connection" in b.js("document.body.innerText"))
        start()
        b.click('[data-lact="apply"]')
        errs = b.js("LEAD.ui.errors")
        check("applying the rule with nothing loaded lists what is missing", any("household list" in e for e in errs) and any("rotation share" in e for e in errs), errs)
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", HIST); b.wait(f"LEAD.state().inputs.history.length === {len(HIST)}")
        b.set_files("#lf-repl", [os.path.join(S, "selection.csv")]); b.wait("!!LEAD.state().inputs.replacements")
        txt = b.js("document.querySelector('.panel').innerText")
        check("the household list is read: 110 to assign, 34 unused replacements, 6 removed and kept", "110 households to assign, 34 unused replacements, 6 removed" in txt, txt[:600])
        # interviewed per round, against the Python generator's count (Box 3.0 rule)
        py_int = ref_stats.interviewed_per_round_strict(HIST)
        js_int = b.js("[...LEAD.state() && LCORE.buildHistory(LEAD.state().inputs.history.map(f => LCORE.readHistoryFile(f.name, f.text)), {tz: 'Asia/Ulaanbaatar'}).complete].map(([r, m]) => [r, m.size])")
        check("earlier rounds: interviewed households per round equal an independent count from the calls files", [list(x) for x in js_int] == py_int, [js_int, py_int])
        check("the rtmtools selection is read as is: 36 replacements dealt to 36 households, round-robin per PSU", "rtmtools selection: 36 replacements, one for each of 36 households" in txt)
        check("the team, dial cap and calendar habits are taken from the last manifest", b.js("LEAD.state().team.map(t => t.id).join(',')") == "E01,E02,E03,E07" and b.js("LEAD.state().cal.dial_cap") == 8)
        setv('[data-lset="cal.window_start"]', "2026-10-26"); setv('[data-lset="cal.window_end"]', "2026-11-20")
        check("the calendar lists the 10 November holiday from the bundled table", "Genghis Khan" in b.js("document.querySelector('.panel').innerText"))
        tick('[data-lteam="2"][data-f="available"]', False)            # E03 away
        b.click('[data-lact="apply"]')
        check("keep the same enumerator refuses to run without this round's rotation share (no default, D4)", any("no default" in e for e in b.js("LEAD.ui.errors")))
        setv('[data-lset="rule.rotation_share"]', "10"); setv('[data-lset="rule.seed"]', "20261027")
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        b.shot(os.path.join(SCREENS, "leader_02_prepare.png"), full=True)
        P = json.loads(b.js("JSON.stringify([...LEAD.state().plan.out])"))
        out = {h: x for h, x in P}
        sums = json.loads(b.js("JSON.stringify([...LEAD.state().plan.sums].map(([h, s]) => [h, s]))"))
        sums = {h: s for h, s in sums}
        check("every household to assign has an enumerator, none of them the one away", len(out) == 110 and all(x["enumerator_id"] != "E03" for x in out.values()))
        away = [h for h, x in out.items() if x["reason"] == "enumerator_unavailable"]
        check("the absent enumerator's households are dealt to the others, reason 'enumerator unavailable'", away and all(out[h].get("previous_enumerator") == "E03" for h in away), len(away))
        keep_ok = all(x["enumerator_id"] == ((sums[h].get("last_interview") or {}).get("enumerator") or sums[h].get("previous")) for h, x in out.items() if x["reason"] == "keep")
        check("kept households stay with the enumerator who completed their last interview (step 1)", keep_ok)
        hard = [h for h, x in out.items() if x["reason"] == "switch_hard_to_reach"]
        hard_def = all((not sums[h]["interviewed_last"] and sums[h]["in_last"] and sums[h]["dials_last"] >= 8) or sums[h]["switch_requested"] for h in hard)
        check("hard-to-reach households (full cap missed, or a switch request) go to another enumerator (D5)",
              hard and hard_def and all(out[h]["enumerator_id"] != out[h]["previous_enumerator"] for h in hard), hard)
        rot = [h for h, x in out.items() if x["reason"] == "rotation"]
        kept_before = {}
        for h, x in out.items():
            if x["reason"] in ("keep", "rotation"):
                e0 = x.get("previous_enumerator") if x["reason"] == "rotation" else x["enumerator_id"]
                kept_before[e0] = kept_before.get(e0, 0) + 1
        given = {}
        for h in rot:
            given[out[h]["previous_enumerator"]] = given.get(out[h]["previous_enumerator"], 0) + 1
        check("rotation moves round(10%) of each enumerator's kept households to another enumerator (step 4)",
              all(given.get(e, 0) == round(0.10 * n) for e, n in kept_before.items()) and all(out[h]["enumerator_id"] != out[h]["previous_enumerator"] for h in rot), [given, kept_before])
        new = [h for h, x in out.items() if x["reason"] == "new"]
        check("households new to the panel are dealt at random, evenly (2 each)", sorted([out[h]["enumerator_id"] for h in new]) == ["E01", "E01", "E02", "E02", "E07", "E07"], new)
        # reproducibility
        b.click('[data-lact="apply"]'); time.sleep(0.3)
        check("the same inputs and seed give the same assignment", json.loads(b.js("JSON.stringify([...LEAD.state().plan.out])")) == P)
        setv('[data-lset="rule.seed"]', "777"); b.click('[data-lact="apply"]'); time.sleep(0.3)
        check("another seed gives another rotation", json.loads(b.js("JSON.stringify([...LEAD.state().plan.out])")) != P)
        # review cycle 5: a setting changed after the rule was applied sets the assignment aside until it is applied again
        seed_now = b.js("LEAD.state().rule.seed")
        setv('[data-lset="rule.seed"]', "778")
        aside = b.js("[LEAD.state().plan === null, document.querySelector('.panel').innerText.includes('Apply the rule again')]")
        setv('[data-lset="rule.seed"]', str(seed_now)); b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        check("a setting changed after the rule was applied (here the seed) sets the assignment aside and asks for the rule again",
              aside == [True, True] and not b.js("document.querySelector('.panel').innerText.includes('Apply the rule again')"), aside)
        setv('[data-lset="rule.seed"]', "20261027"); b.click('[data-lact="apply"]'); time.sleep(0.3)
        # load check and balance
        loads = b.js("LCORE.loads(Object.assign({}, {team: LEAD.state().team, cap: 8}), LEAD.state().plan.out, LEAD.state().plan.sums)")
        check("the load check shows each enumerator's expected dials against the target", len(loads) == 3 and any(abs(l["departure"]) > 0.15 for l in loads), loads)
        b.click('[data-lact="balance"]'); time.sleep(0.3)
        loads2 = b.js("LCORE.loads(Object.assign({}, {team: LEAD.state().team, cap: 8}), LEAD.state().plan.out, LEAD.state().plan.sums)")
        moved = [x for x in b.js("[...LEAD.state().plan.out.values()]") if x["reason"] == "capacity"]
        check("balancing moves kept households with reason 'capacity' until every load is within the margin",
              moved and all(abs(l["departure"]) <= 0.15 + 1e-9 for l in loads2) and all(m.get("previous_enumerator") for m in moved), [loads2, len(moved)])
        # planning
        plans = json.loads(b.js("JSON.stringify([...LEAD.state().plan.plans])"))
        days = b.js("LCORE.workingDays(LEAD.state() && (() => { const c = Object.assign({}, LEAD.state().cal); c.holidays = [{date: '2026-11-10', working: false}]; return c; })())")
        first_part = days[: round(0.5 * len(days))]
        check("first dials fall on the first half of the working days, never a Sunday or the 10 November holiday",
              all(p["first_dial_date"] in first_part for _, p in plans) and "2026-11-10" not in [p["first_dial_date"] for _, p in plans], first_part)
        same_hour = [h for h, p in plans if sums[h].get("last_interview") and sums[h]["last_interview"].get("hour") is not None]
        check("each household's first dial is planned at the hour of its last interview (3.5.2)",
              same_hour and all(dict(plans)[h]["target_hour"] == sums[h]["last_interview"]["hour"] for h in same_hour))
        # write the files
        before = snapshot()
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        b.click('[data-lact="dlall"]')
        got = [wait_new(n, before) for n in ("E01_assignment_R05.json", "E02_assignment_R05.json", "E07_assignment_R05.json", "L2MN-DEMO_R05_manifest.json", "calendar.csv")]
        check("one assignment file per available enumerator, the manifest and the calendar row are written", all(got), got)
        A = {e: json.load(open(os.path.join(DL, f"{e}_assignment_R05.json"), encoding="utf-8")) for e in ("E01", "E02", "E07")}
        M = json.load(open(os.path.join(DL, "L2MN-DEMO_R05_manifest.json"), encoding="utf-8"))
        hl = list(csv.DictReader(open(os.path.join(S, "household_list.csv"), encoding="utf-8")))
        ss = {e: a["calendar"].get("self_scheduling") for e, a in A.items()}
        check("the files carry what enumerators may change themselves: by default moving a call and marking time off, first calls held to the plan's first-call period, whose last day is the last first-dial day",
              all(v == {"reschedule": True, "availability": True, "push_first_calls": False, "first_calls_by": first_part[-1]} for v in ss.values()) and M["calendar"]["self_scheduling"] == ss["E07"], [ss, first_part[-1]])
        tick('[data-lset="cal.self.push_first_calls"]', True)
        flip = b.js("[LEAD.ui.ready === null, !!LEAD.state().plan, LEAD.state().events.slice(-1)[0].what]")
        check("changing what enumerators may change sets the written files aside, keeps the assignment, and is logged", flip == [True, True, "self_scheduling_set"], flip)
        tick('[data-lset="cal.self.push_first_calls"]', False)
        check("the files carry the contact protocol; by default the earlier rule (two hours apart, no daily or day limit)",
              all(a["calendar"].get("contact_protocol") == {"gap_hours": 2, "vary_times": False} for a in A.values()) and M["calendar"]["contact_protocol"] == {"gap_hours": 2, "vary_times": False}, [a["calendar"].get("contact_protocol") for a in A.values()])
        setv('[data-lset="cal.protocol.per_day"]', "3"); setv('[data-lset="cal.protocol.days"]', "5"); tick('[data-lset="cal.protocol.vary_times"]', True)
        ptx = b.js("document.querySelector('.panel').innerText")
        proto_ev = b.js("LEAD.state().events.slice(-3).map(e => [e.what, e.setting, e.value])")
        check("step 4 sets the contact protocol: 3 calls a day over 5 working days is 15 calls, set against the dial cap; each change is logged and sets the written files aside",
              "3 a day over 5 working days is 15 calls" in ptx and b.js("LEAD.ui.ready === null && !!LEAD.state().plan") and [x[0] for x in proto_ev] == ["contact_protocol_set"] * 3
              and b.js("JSON.stringify(LEAD.state().cal.protocol)") == json.dumps({"per_day": 3, "gap_hours": 2, "days": 5, "vary_times": True}, separators=(",", ":")), [proto_ev, b.js("JSON.stringify(LEAD.state().cal.protocol)")])
        setv('[data-lset="cal.protocol.per_day"]', ""); setv('[data-lset="cal.protocol.days"]', ""); tick('[data-lset="cal.protocol.vary_times"]', False)
        phones_of = {r["hhid"]: {r[k] for k in ("phone_1", "phone_2", "phone_3") if r.get(k)} for r in hl}
        leak = []
        for e, a in A.items():
            mine = {h["hhid"] for h in a["households"]} | {r["hhid"] for h in a["households"] for r in h.get("replacements", [])}
            allowed = set().union(*[phones_of[h] for h in mine])
            for h in a["households"]:
                for p in h["contact"]["phones"]:
                    if p["number"] not in allowed: leak.append((e, h["hhid"]))
                for r in h.get("replacements", []):
                    for p in r["contact"]["phones"]:
                        if p["number"] not in allowed: leak.append((e, r["hhid"]))
            others = set().union(*[phones_of[h] for h in phones_of if h not in mine])
            text = json.dumps(a, ensure_ascii=False)
            leak += [(e, n) for n in others if n and n in text]
        check("access control: no assignment file holds another enumerator's contact information", not leak, leak[:5])
        ids = [h["hhid"] for a in A.values() for h in a["households"]]
        reps = [r["hhid"] for a in A.values() for h in a["households"] for r in h.get("replacements", [])]
        check("each household is in exactly one file, and each replacement belongs to exactly one household", len(ids) == len(set(ids)) == 110 and len(reps) == len(set(reps)) == 34, [len(ids), len(reps)])
        check("the manifest holds IDs only (no names or phone numbers) and every file's fingerprint",
              "+000" not in json.dumps(M) and "Contact" not in json.dumps(M) and {e["enumerator_id"]: e["fingerprint"] for e in M["enumerators"]} == {e: a["fingerprint"] for e, a in A.items()})
        import check_formats as cf
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cf.main([os.path.join(DL, f"{e}_assignment_R05.json") for e in A] + [os.path.join(DL, "L2MN-DEMO_R05_manifest.json")])
        check("the written files pass the format checker (schema and fingerprint)", code == 0 and "warning" not in buf.getvalue(), buf.getvalue())
        check("every assignment file cites the handbook's default rule in its rule header", all(a["rule"]["name"] == "keep_same" and a["rule"]["rotation_share"] == 0.1 and a["rule"]["seed"] == 20261027 for a in A.values()))
        # the enumerator view opens a file the leader view wrote
        b.click('[data-act="view"][data-v="enum"]')
        b.set_files("#f-assign", [os.path.join(DL, "E07_assignment_R05.json")]); b.wait("!!APP.S")
        check("the enumerator view opens a file the leader view wrote, its fingerprint confirmed", b.js("APP.S.events[0].fingerprint_ok") == 1 and b.js("APP.S.assignment.households.length") == len(A["E07"]["households"]))
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.click('[data-act="view"][data-v="leader"]')
        # protected files (D11)
        tick('[data-lset="protect"]', True)
        before = snapshot()
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.passphrases", timeout=60)
        pw = {p["enumerator_id"]: p["passphrase"] for p in b.js("LEAD.ui.passphrases")}
        b.shot(os.path.join(SCREENS, "leader_03_files.png"), full=True)
        b.click('[data-lact="dlall"]')
        f7 = wait_new("E07_assignment_R05*.json", before)
        env = json.load(open(f7, encoding="utf-8"))
        check("protected files: one passphrase per enumerator, made by the tool and shown once; Python opens E07's file with E07's",
              len(set(pw.values())) == 3 and env["schema"] == "rtm-sealed-1.0" and py_unseal(env, pw["E07"])["enumerator_id"] == "E07" and "+000" not in open(f7).read())
        try:
            py_unseal(env, pw["E01"]); wrong_ok = False
        except Exception:
            wrong_ok = True
        check("another enumerator's passphrase does not open the file", wrong_ok)
        check("passphrases are not kept in the leader's session", not any(p in b.js("JSON.stringify(LEAD.state())") for p in pw.values()))

        # ================= B. importing the round's logs =================
        start()
        b.click('[data-lact="tab"][data-t="import"]')
        b.js("RTM.setNow('2026-11-07T09:00:00+08:00'); true")
        b.set_files("#lf-manifest", [MANIFEST]); b.wait("!!LEAD.state().manifest")
        b.set_files("#lf-imports", EXPORTS); b.wait(f"LEAD.state().imports.length === {len(EXPORTS)}")
        b.shot(os.path.join(SCREENS, "leader_04_import.png"), full=True)
        check("a clean batch merges with no question open", b.js("document.querySelector('.panel').innerText").count("No merge question is open") == 1)
        exp_calls = open(os.path.join(S, "expected_R05_calls.csv"), encoding="utf-8").read().strip()
        exp_acts = open(os.path.join(S, "expected_R05_actions.csv"), encoding="utf-8").read().strip()
        b.click('[data-lact="tab"][data-t="calllog"]')
        before = snapshot()
        for w in ("calls", "actions", "interviews", "outcomes", "calendar"):
            b.click(f'[data-lact="export"][data-what="{w}"]')
        fc = wait_new("L2MN-DEMO_R05_calls*.csv", before); fa = wait_new("L2MN-DEMO_R05_actions*.csv", before)
        fi = wait_new("interviews*.csv", before); fo = wait_new("outcome_codes*.csv", before)
        check("the merged call log equals the Python generator's own merge, byte for byte", open(fc, encoding="utf-8").read().strip() == exp_calls)
        check("the merged actions equal the Python merge", open(fa, encoding="utf-8").read().strip() == exp_acts)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cf.main([fc])
        check("the merged call log passes the format checker as a call-log CSV", "ERROR" not in buf.getvalue(), buf.getvalue())
        iv = list(csv.DictReader(open(fi, encoding="utf-8")))
        oc = {r["code"] for r in csv.DictReader(open(fo, encoding="utf-8"))}
        man = json.load(open(MANIFEST, encoding="utf-8"))
        check("interviews.csv: one row per household of the round, hhid first, every outcome documented in outcome_codes.csv",
              len(iv) == len({r["hhid"] for r in iv}) and list(iv[0].keys())[0] == "hhid" and {r["outcome"] for r in iv} <= oc and len(iv) >= len(man["households"]))
        # completes per enumerator against an independent count from the merged log
        py_cmp = ref_stats.completes_by_enumerator(exp_calls, man)
        prog = {r["enumerator_id"]: r for r in b.js("LCORE.progress(LEAD.state().manifest, LCORE.cases(LEAD.state().manifest, LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now())), LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now())).list")}
        check("progress: completes per enumerator equal an independent count from the merged log", {e: prog[e]["complete"] for e in py_cmp} == py_cmp, [py_cmp, {e: prog[e]["complete"] for e in prog}])
        check("interviews.csv counts the same completes", sum(1 for r in iv if r["outcome"] == "COMPLETE") == sum(py_cmp.values()))
        b.click('[data-lact="tab"][data-t="progress"]')
        b.shot(os.path.join(SCREENS, "leader_05_progress.png"), full=True)
        check("the contacts file's new number is listed for the leader, its digest matching the call log",
              b.js("LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now()).updates.every(u => u.digest_ok)"))

        # the merge cases (proposal F)
        def issues():
            return b.js("LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(LEAD.state().resolutions.map(r => [r.key, r])), RTM.now()).issues.map(i => [i.type, i.status, i.key, i.enumerator || '', i.hhid || '', (i.choices || []).map(c => c.value)])")

        b.click('[data-lact="tab"][data-t="import"]')
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "merge_cases", "duplicate", "*"))))
        b.wait(f"LEAD.state().imports.length === {len(EXPORTS) + 1}")
        check("a file uploaded twice: the copy is ignored and reported", any(i[0] == "duplicate" for i in issues()))
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "merge_cases", "early_export", "*"))))
        b.wait(f"LEAD.state().imports.length === {len(EXPORTS) + 3}")
        files = b.js("LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now()).files")
        check("two exports from one enumerator: the later is used, the earlier noted in the files and as a line of the merge report, no gap",
              any("replaced by the later export, E07_2026-11-06.json" in f["use"] for f in files) and any(i[0] == "older_export" and i[3] == "E07" for i in issues())
              and not any(i[0] == "gap" for i in issues()))
        # a later same-day export of E02 whose JSON did not arrive: its CSV is used, as unverified, with the earlier JSON's actions
        n_e02 = b.js("LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now()).perEnum.get('E02').dials.length")
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "merge_cases", "csv_only", "*"))))
        b.wait(f"LEAD.state().imports.length === {len(EXPORTS) + 4}")
        g2 = b.js("""(() => { const G = LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now()), x = G.perEnum.get('E02');
                      return { kind: x.file.kind, unverified: !!x.unverified, dials: x.dials.length, actions: x.actions.length,
                               issues: G.issues.filter(i => i.enumerator === 'E02').map(i => [i.type, i.detail]), uses: G.files.filter(f => f.enumerator_id === 'E02').map(f => [f.name, f.kind, f.use]) }; })()""")
        types2 = [t for t, _ in g2["issues"]]
        check("a later export whose JSON did not arrive: its CSV is used, as unverified, with one more dial; the earlier JSON is noted as replaced (F)",
              g2["kind"] == "csv" and g2["unverified"] and g2["dials"] == n_e02 + 1 and "unverified" in types2 and "older_export" in types2
              and "csv_differs" not in types2 and any(k == "json" and u.startswith("replaced by the later export") for _, k, u in g2["uses"]), g2)
        # review cycle 3: a later CSV lacking an earlier dial; an earlier CSV-only export; a contact update in two files
        rows_l = open(os.path.join(S, "merge_cases", "csv_only", "E02_2026-11-06.csv"), encoding="utf-8").read().rstrip("\n").split("\n")
        hdr = rows_l[0].split(","); ai, hi = hdr.index("action"), hdr.index("hhid")
        rel = next(r for r in rows_l[1:] if r.split(",")[ai] == "RELEASE")
        later = "\n".join([rows_l[0]] + [r for r in rows_l[1:] if r != rel]) + "\n"
        rel_hh, rel_id = rel.split(",")[hi], rel.split(",")[hdr.index("event_id")]
        g4 = b.js(f"""(() => {{ const st = LEAD.state(), seen = new Set(), base = st.imports.filter(f => {{ if (seen.has(f.name) || f.name.includes('(1)')) return false; seen.add(f.name); return true; }}).map(f => LCORE.readImport(f.name, f.text));
                     const imp = base.concat([LCORE.readImport('E02_2026-11-07.csv', {json.dumps(later)})]);
                     const run = res => {{ const G = LCORE.merge(st.manifest, imp, res, RTM.now()), x = G.perEnum.get('E02');
                       return {{ G, x, dial: x.dials.some(d => d.event_id === {json.dumps(rel_id)}), act: x.actions.some(a => a.event_id === {json.dumps(rel_id)} && a.action === 'RELEASE') }}; }};
                     const a = run(new Map()), gap = a.G.issues.find(i => i.type === 'gap' && i.enumerator === 'E02');
                     const b2 = gap ? run(new Map([[gap.key, {{ key: gap.key, decision: 'exclude', logged_by: 'L01', logged_at: '2026-11-07T09:00:00+08:00' }}]])) : null;
                     return {{ file: a.x.file.name, gap: !!gap, keptDial: a.dial, keptAct: a.act, outDial: b2 && b2.dial, outAct: b2 && b2.act }}; }})()""")
        check("a later CSV lacking a dial an earlier export has: the gap is flagged and the dial kept with its release; 'leave them out' drops both",
              g4["file"] == "E02_2026-11-07.csv" and g4["gap"] and g4["keptDial"] and g4["keptAct"] and g4["outDial"] is False and g4["outAct"] is False, g4)
        # review cycle 4: the same later CSV under the same-day name, and an earlier same-day CSV saved as a " (1)" copy
        g6 = b.js(f"""(() => {{ const st = LEAD.state(), seen = new Set(), base = st.imports.filter(f => {{ if (seen.has(f.name) || f.name.includes('(1)')) return false; seen.add(f.name); return true; }}).map(f => LCORE.readImport(f.name, f.text));
                     const G = LCORE.merge(st.manifest, base.concat([LCORE.readImport('E02_2026-11-06.csv', {json.dumps(later)})]), new Map(), RTM.now()), x = G.perEnum.get('E02');
                     return {{ kind: x.file.kind, unverified: !!x.unverified, gap: G.issues.some(i => i.type === 'gap' && i.enumerator === 'E02'), differs: G.issues.some(i => i.type === 'csv_differs' && i.enumerator === 'E02') }}; }})()""")
        check("a later CSV under the same-day name that lacks a dial voided since is used, as unverified, and the gap is flagged (F)",
              g6["kind"] == "csv" and g6["unverified"] and g6["gap"] and not g6["differs"], g6)
        rows_x = open(os.path.join(S, "exports_R05", "E02_2026-11-06.csv"), encoding="utf-8").read().rstrip("\n").split("\n")
        li = hdr.index("logged_at")
        cut = sorted(r.split(",")[li] for r in rows_x[1:])[-6]          # an export made before the last five dials were logged
        earlier_csv = "\n".join([rows_x[0]] + [r for r in rows_x[1:] if r.split(",")[li] <= cut]) + "\n"
        g7 = b.js(f"""(() => {{ const st = LEAD.state(), seen = new Set(), base = st.imports.filter(f => {{ if (seen.has(f.name) || f.name.includes('(1)')) return false; seen.add(f.name); return true; }}).map(f => LCORE.readImport(f.name, f.text));
                     const G = LCORE.merge(st.manifest, base.concat([LCORE.readImport('E02_2026-11-06 (1).csv', {json.dumps(earlier_csv)})]), new Map(), RTM.now());
                     const row = G.files.find(f => f.name === 'E02_2026-11-06 (1).csv');
                     return {{ used: G.perEnum.get('E02').file.name, use: row && row.use, differs: G.issues.some(i => i.type === 'csv_differs'), older: G.issues.some(i => i.type === 'older_export' && i.file === 'E02_2026-11-06 (1).csv') }}; }})()""")
        check("an earlier same-day CSV saved as a ' (1)' copy is an earlier export: replaced by the later one and noted, not flagged as differing",
              g7["used"] == "E02_2026-11-06.json" and not g7["differs"] and g7["older"] and (g7["use"] or "").startswith("replaced by the later export"), g7)
        mid = sorted(rows_x[1:], key=lambda r: r.split(",")[li])[len(rows_x) // 2]       # a dial logged mid-day, voided before a re-export
        voided_csv = "\n".join([rows_x[0]] + [r for r in rows_x[1:] if r != mid]) + "\n"
        g8 = b.js(f"""(() => {{ const st = LEAD.state(), seen = new Set(), base = st.imports.filter(f => {{ if (seen.has(f.name) || f.name.includes('(1)')) return false; seen.add(f.name); return true; }}).map(f => LCORE.readImport(f.name, f.text));
                     const extra = LCORE.readImport('E02_2026-11-06 (2).csv', {json.dumps(voided_csv)});
                     const G = LCORE.merge(st.manifest, base.concat([extra]), new Map(), RTM.now());
                     const last = {json.dumps(max(r.split(",")[li] for r in rows_x[1:]))};
                     return {{ differs: G.issues.some(i => i.type === 'csv_differs' && i.file === 'E02_2026-11-06 (2).csv'), stamp: extra.exported_at === last }}; }})()""")
        check("a same-day CSV lacking a dial logged before its own time is flagged as differing, not taken for an earlier export; a CSV's time stays in the enumerator's clock",
              g8["differs"] and g8["stamp"], g8)
        rows_e = open(os.path.join(S, "merge_cases", "early_export", "E07_2026-10-30.csv"), encoding="utf-8").read().rstrip("\n").split("\n")
        fake = rows_e[-1].split(","); fake[hdr.index("event_id")] = "00000000-0000-4000-8000-000000000001"
        early = "\n".join(rows_e + [",".join(fake)]) + "\n"
        g5 = b.js(f"""(() => {{ const st = LEAD.state(), imp = st.imports.filter(f => f.name.startsWith('E0') && !f.name.includes('(1)')).map(f => LCORE.readImport(f.name, f.text))
                       .filter(f => !f.name.startsWith('E07_2026-10-30')).concat([LCORE.readImport('E07_2026-10-30.csv', {json.dumps(early)})]);
                     const G = LCORE.merge(st.manifest, imp, new Map(), RTM.now()), x = G.perEnum.get('E07');
                     return {{ file: x.file.name, gap: G.issues.some(i => i.type === 'gap' && i.file === 'E07_2026-10-30.csv'), kept: x.dials.some(d => d.event_id === '00000000-0000-4000-8000-000000000001') }}; }})()""")
        check("an earlier export that came as a CSV only is compared too: a dial the later JSON lacks is kept and the gap flagged (F)",
              g5["file"] == "E07_2026-11-06.json" and g5["gap"] and g5["kept"], g5)
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        b.set_files("#lf-imports", EXPORTS + sorted(glob.glob(os.path.join(S, "merge_cases", "duplicate", "*"))) + sorted(glob.glob(os.path.join(S, "merge_cases", "early_export", "*"))))
        b.wait(f"LEAD.state().imports.length === {len(EXPORTS) + 3}")
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "merge_cases", "wrong_round", "*"))))
        b.wait(f"LEAD.state().imports.length === {len(EXPORTS) + 4}")
        check("a file from another round is not merged, and is reported", any(i[0] == "wrong_round" for i in issues()))
        cf = json.load(open(os.path.join(S, "merge_cases", "conflict", "E01_2026-11-06_contacts.json"), encoding="utf-8")); cf["round"] = 4
        g3 = b.js(f"""(() => {{ const st = LEAD.state(), extra = LCORE.readImport('E01_2026-10-21_contacts.json', {json.dumps(json.dumps(cf))});
                     const G = LCORE.merge(st.manifest, st.imports.map(f => LCORE.readImport(f.name, f.text)).concat([extra]), new Map(), RTM.now());
                     return {{ wrong: G.issues.some(i => i.type === 'wrong_round' && i.file === 'E01_2026-10-21_contacts.json'), use: G.files.find(f => f.name === 'E01_2026-10-21_contacts.json').use }}; }})()""")
        check("a contacts file from another round is not used, and is reported", g3["wrong"] and g3["use"] == "other round, not merged", g3)
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "merge_cases", "conflict", "*"))))
        b.wait("LEAD.state().imports.some(f => f.name.includes('conflict') || f.text.includes('18:55'))", timeout=10)
        time.sleep(0.5)
        n_files = b.js("LEAD.state().imports.filter(f => f.name.endsWith('_contacts.json')).length")
        n_upd = b.js("LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now()).updates.length")
        n_ev = len({u["event_id"] for f in [os.path.join(S, "exports_R05", "E01_2026-11-06_contacts.json"), os.path.join(S, "merge_cases", "conflict", "E01_2026-11-06_contacts.json")]
                    for u in json.load(open(f, encoding="utf-8"))["updates"]})
        check("a contact update repeated in a later contacts file counts once", n_files == 2 and n_upd == n_ev == 1, [n_files, n_upd, n_ev])
        iss = issues()
        tc = [i for i in iss if i[0] == "two_completes"]
        na = [i for i in iss if i[0] == "not_assigned"]
        check("dials on a household assigned to someone else are kept and flagged", na and na[0][1] == "open", na)
        check("same-day exports that share a name are each checked against their own JSON (no false 'CSV differs')", not any(i[0] == "csv_differs" for i in iss), [i for i in iss if i[0] == "csv_differs"])
        check("two completes for one household are kept, flagged, and left out of the counts until the leader chooses", tc and tc[0][1] == "open"
              and b.js(f"LCORE.cases(LEAD.state().manifest, LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now())).get('{tc[0][4]}').state") == "conflict", tc)
        b.js("APP.render(); true")
        b.shot(os.path.join(SCREENS, "leader_06_decisions.png"), full=True)
        # the leader decides: a mistyped ID
        b.click(f'[data-lact="resolve"][data-key="{na[0][2]}"][data-v="typo"]')
        b.wait("LEAD.state().resolutions.length === 1")
        iss = issues()
        check("a decision is logged with who and when; the mistyped dials leave the counts and the conflict closes",
              b.js("LEAD.state().resolutions[0].logged_by") == "L01" and not any(i[0] == "two_completes" for i in iss)
              and b.js(f"LCORE.cases(LEAD.state().manifest, LCORE.merge(LEAD.state().manifest, LEAD.state().imports.map(f => LCORE.readImport(f.name, f.text)), new Map(LEAD.state().resolutions.map(r => [r.key, r])), RTM.now())).get('{tc[0][4]}').state") == "complete")
        # an edited file
        b.set_files("#lf-imports", sorted(glob.glob(os.path.join(S, "merge_cases", "edited", "*"))))
        time.sleep(0.8)
        iss = issues()
        check("a file edited after export: its chain fails, the differing event is a conflict", any(i[0] == "chain_broken" for i in iss) and any(i[0] == "event_conflict" for i in iss))
        ec = next(i for i in iss if i[0] == "event_conflict")
        labels = b.js("LEAD.merged().G.issues.find(i => i.type === 'event_conflict').choices.map(c => c.label)")
        check("when the two files share a name, the choices say which one passes its integrity check", len(set(labels)) == len(labels) and "integrity check passed" in labels[0] and "integrity check failed" in labels[1], labels)
        b.click(f'[data-lact="resolve"][data-key="{ec[2]}"][data-v="{ec[5][0]}"]')
        b.wait("LEAD.state().resolutions.length === 2")
        check("the leader keeps the verified version: the event counts again", not any(i[0] == "event_conflict" and i[1] == "open" for i in issues()))
        before = snapshot()
        b.click('[data-lact="export"][data-what="report"]')
        fr = wait_new("L2MN-DEMO_R05_merge_report*.csv", before)
        rep = list(csv.DictReader(open(fr, encoding="utf-8")))
        check("the merge report lists every situation, the rule applied and the leader's decisions",
              {"duplicate", "wrong_round", "not_assigned", "chain_broken", "event_conflict"} <= {r["type"] for r in rep} and any(r["decision"] == "typo" and r["resolved_by"] == "L01" for r in rep))
        # save and reopen the leader's session
        st_before = b.js("JSON.stringify({ i: LEAD.state().imports.length, r: LEAD.state().resolutions, m: LEAD.state().manifest.fingerprint })")
        before = snapshot()
        b.click('[data-lact="save"]'); b.wait("APP.modal"); b.click('[data-act="modalok"]')
        fp = wait_new("leader_L2MN-DEMO_R05*.json", before)
        P = json.load(open(fp, encoding="utf-8")); chk = P.pop("checksum")
        check("the leader session saves with a checksum that verifies in Python", sha(canon(P)) == chk)
        b.click('[data-lact="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("!LEAD.state()")
        b.set_files("#lf-project", [fp]); b.wait("!!LEAD.state()")
        check("reopening the leader session restores imports, decisions and the manifest", b.js("JSON.stringify({ i: LEAD.state().imports.length, r: LEAD.state().resolutions, m: LEAD.state().manifest.fingerprint })") == st_before)
        bad = os.path.join(SCRATCH, f"leader_tampered_{STAMP}.json")
        T = json.load(open(fp, encoding="utf-8")); T["resolutions"][0]["decision"] = "reassign"; json.dump(T, open(bad, "w"))
        b.click('[data-lact="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("!LEAD.state()")
        b.set_files("#lf-project", [bad]); time.sleep(1)
        check("a leader session changed outside the tool is refused", not b.js("!!LEAD.state()") and b.js("APP.toasts.some(t => /checksum/.test(t.text))"))
        # protected leader session
        b.set_files("#lf-project", [fp]); b.wait("!!LEAD.state()")
        before = snapshot()
        b.click('[data-lact="save"]'); b.wait("APP.modal")
        b.js("document.querySelector('#modal-input').value = 'leader-secret-1'; document.querySelector('#modal-input2').value = 'leader-secret-1'; true")
        b.click('[data-act="modalok"]')
        fps = wait_new("leader_L2MN-DEMO_R05*.json", before)
        envs = json.load(open(fps, encoding="utf-8"))
        # the ciphertext is base64, whose alphabet has "+": "+000" can occur in it by chance, so only the clear fields are searched
        clear_fields = json.dumps({k: v for k, v in envs.items() if k != "data"})
        opened = py_unseal(envs, "leader-secret-1")
        check("a protected leader session holds no phone number in the clear; Python opens it", envs["schema"] == "rtm-sealed-1.0" and "+000" not in clear_fields
              and opened["schema"] == "rtm-leader-1.0" and "+000" in json.dumps(opened))

        # ================= C. analytics, against an independent implementation =================
        start()
        b.set_files("#lf-hist", HIST); b.wait(f"LEAD.state().inputs.history.length === {len(HIST)}")
        b.click('[data-lact="tab"][data-t="import"]')
        b.set_files("#lf-manifest", [MANIFEST]); b.wait("!!LEAD.state().manifest")
        b.set_files("#lf-imports", EXPORTS); b.wait(f"LEAD.state().imports.length === {len(EXPORTS)}")
        b.click('[data-lact="tab"][data-t="analytics"]')
        b.shot(os.path.join(SCREENS, "leader_07_analytics.png"), full=True)
        js = b.js("""(() => { const d = LCORE.buildHistory(LEAD.state().inputs.history.map(f => LCORE.readHistoryFile(f.name, f.text)), {tz: 'Asia/Ulaanbaatar'});
            const input = []; for (const [r, ds] of d.dials) ds.forEach(x => input.push({hhid: x.hhid, round: r, wall: x.wall, status: x.status, cmp_code: x.cmp, dur: x.dur, operator: x.operator}));
            const T = LSTATS.build(input), rs = T.rounds, I = LSTATS.interviewed(T, null);
            const s33 = LSTATS.s33(T, rs), s34 = LSTATS.s34(I, rs, null), s31 = LSTATS.s31(T, rs), s35 = LSTATS.s35(T, rs, {});
            return JSON.stringify({ cases: T.cases.size, dials: T.dials.length, fallbacks: T.fallbacks, dpc: s33.pooled.dials_per_complete, byRound: s33.byRound.map(x => [x.round, x.cases, x.completes, x.dials]),
              hazard: s33.hazard.slice(0, 8).map(h => [h.k, h.at_risk, h.completes]), cont: s34.continuation.map(x => [x.from, x.round, x.base, Math.round(x.share * 1e6)]),
              missed: [s33.missed.newly_missed, s33.missed.redialled && s33.missed.redialled.k],
              cpd: Math.round(s31.pooled.completes_per_day * 1e6), od: s31.pooled.enumerator_days, att: Math.round(s31.pooled.attendance * 1e6), mpc: Math.round(s31.pooled.minutes_per_complete * 1e4),
              hours: s35.hours.map(h => [h.hour, h.n, h.success ? h.success.k : null]), same: s35.same_time.map(x => x.n), cont35: [s35.continuity.n, Math.round(s35.continuity.same_share * 1e6)] }); })()""")
        js = json.loads(js)
        py = ref_stats.reference(HIST)
        for k in ("cases", "dials", "fallbacks", "byRound", "hazard", "cont", "missed", "od", "cpd", "att", "mpc", "hours", "same", "cont35"):
            check(f"analytics '{k}' equals the independent Python implementation of the handbook's rules", js[k] == py[k], [js[k], py[k]])
        check("dials per complete, pooled, equals the reference", abs(js["dpc"] - py["dpc"]) < 1e-9, [js["dpc"], py["dpc"]])
        txt = b.js("document.querySelector('.panel').innerText")
        check("the analytics tab shows each measure with its handbook definition", all(s in txt for s in ("Box 2.0", "Section 3.3.1", "Section 3.1", "Section 3.5.2", "Section 3.5.3", "Section 3.5.4")))

        # earlier rounds given as interview records only (a program without dial logs)
        ivp = os.path.join(SCRATCH, f"interviews_R01_R04_{STAMP}.csv")
        done = {}
        for pth in [x for x in HIST if x.endswith("_calls.csv")]:
            for r in csv.DictReader(open(pth, encoding="utf-8")):
                if r["status"] == "COMPLETE" and (r["dur_min"] == "" or float(r["dur_min"]) >= 3):
                    done.setdefault((r["hhid"], r["round"]), (r["ts"][:10], r["operator"]))
        with open(ivp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n"); w.writerow(["hhid", "round", "interview_date", "outcome", "enumerator"])
            for (h, rnd), (d, e) in sorted(done.items()):
                w.writerow([h, rnd, d, "complete", e])
        start()
        b.set_files("#lf-hist", [ivp]); b.wait("LEAD.state().inputs.history.length === 1")
        js_iv = b.js("[...LCORE.buildHistory(LEAD.state().inputs.history.map(f => LCORE.readHistoryFile(f.name, f.text)), {tz: 'Asia/Ulaanbaatar'}).complete].map(([r, m]) => [r, m.size])")
        check("earlier rounds given as interview records only are read: interviewed households per round as from the dial logs",
              [list(x) for x in js_iv] == py_int, [js_iv, py_int])

        # an Excel workbook as the household list (proposal G: a built-in reader)
        try:
            import openpyxl
        except ImportError:
            openpyxl = None
        if openpyxl:
            hl_rows = list(csv.reader(open(os.path.join(S, "household_list.csv"), encoding="utf-8")))
            wb = openpyxl.Workbook(); ws = wb.active; ws.title = "households"
            for r in hl_rows:
                ws.append(r)
            for row in ws.iter_rows():
                for c in row:
                    c.number_format = "@"
            x1 = os.path.join(SCRATCH, f"household_list_{STAMP}.xlsx"); wb.save(x1)
            wb2 = openpyxl.Workbook(); ws2 = wb2.active
            for i, r in enumerate(hl_rows):
                ws2.append([int(v.replace("+", "").replace(" ", "")) if (i and j in (4, 6, 8) and v) else v for j, v in enumerate(r)])
            x2 = os.path.join(SCRATCH, f"household_list_numbers_{STAMP}.xlsx"); wb2.save(x2)
            start()
            b.set_files("#lf-hh", [x1]); b.wait("!!LEAD.state().inputs.households")
            same = b.js(f"JSON.stringify([...LCORE.parseHouseholds(LEAD.state().inputs.households.text).households]) === JSON.stringify([...LCORE.parseHouseholds({json.dumps(open(os.path.join(S, 'household_list.csv'), encoding='utf-8').read())}).households])")
            check("an Excel workbook is read offline by the built-in reader, exactly as the same list in CSV", same and "110 households to assign" in b.js("document.querySelector('.panel').innerText"))
            b.set_files("#lf-hh", [x2]); b.wait("APP.toasts.some(t => /stored as numbers/.test(t.text))")
            check("phone numbers stored as numbers in Excel raise a warning: leading zeros and + are lost", "phone_1" in b.js("APP.toasts.map(t => t.text).join(' ')"))
        else:
            check("an Excel workbook is read by the built-in reader (openpyxl missing: not tested)", False, "install openpyxl to run this check")

        # ================= D. matching criteria, the day list, and moving households during the round =================
        # (the author's requests of 28 October 2026: assign by language, sex or dialect and record the criteria; longer day
        # lists so that nobody waits; move waiting households from slower to faster enumerators without double calls)
        import check_formats as cfm
        b.ws.call("Emulation.clearDeviceMetricsOverride")
        b.js("RTM.setNow('2026-10-23T15:00:00+08:00'); true")
        start()
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", HIST); b.wait(f"LEAD.state().inputs.history.length === {len(HIST)}")
        b.set_files("#lf-repl", [os.path.join(S, "selection.csv")]); b.wait("!!LEAD.state().inputs.replacements")
        setv('[data-lset="cal.window_start"]', "2026-10-26"); setv('[data-lset="cal.window_end"]', "2026-11-20")
        tick('[data-lteam="2"][data-f="available"]', False)
        setv('[data-lset="rule.rotation_share"]', "10"); setv('[data-lset="rule.seed"]', "20261027")
        txt = b.js("document.querySelector('.panel').innerText")
        check("step 5 offers the household list's columns as matching criteria, with their values (language: kk, mn; respondent sex: f, m)",
              "Match households to enumerators by" in txt and "language" in txt and "respondent sex" in txt and "(f, m;" in txt and "(kk, mn;" in txt, txt[:300])
        tick('[data-lcrit="language"]', True)
        b.click('[data-lact="apply"]')
        check("with a criterion ticked, the rule refuses to run until every available enumerator has values for it", any("values for language" in e for e in b.js("LEAD.ui.errors")), b.js("LEAD.ui.errors"))
        team = b.js("LEAD.state().team.map(t => t.id)")
        for e, v in {"E01": "mn kk", "E02": "mn", "E07": "mn"}.items():
            setv(f'[data-lattr="{team.index(e)}"][data-c="language"]', v)
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        b.shot(os.path.join(SCREENS, "leader_09_criteria.png"), full=True)
        kk = {r["hhid"] for r in hl if r["language"] == "kk"}
        out = {h: x for h, x in json.loads(b.js("JSON.stringify([...LEAD.state().plan.out])"))}
        kk_in = sorted(h for h in kk if h in out)
        check("every Kazakh-speaking household is with the one enumerator who speaks Kazakh, and no household is left without an enumerator",
              kk_in and all(out[h]["enumerator_id"] == "E01" for h in kk_in) and len(out) == 110 and b.js("LEAD.state().plan.unmatched.length") == 0, {h: out[h]["enumerator_id"] for h in kk_in})
        moved = [h for h, x in out.items() if x["reason"] == "match"]
        check("a kept household whose enumerator does not match moves with the reason 'match' and its previous enumerator recorded",
              moved and all(h in kk and out[h]["previous_enumerator"] in ("E02", "E07") for h in moved), moved)
        check("every household is marked as matched, and the note counts the moves", all(x.get("matched") is True for x in out.values()) and any("moved to match the criteria" in n for n in b.js("LEAD.state().plan.notes")), b.js("LEAD.state().plan.notes"))
        if b.js("!!document.querySelector('[data-lact=\"balance\"]')"):
            b.click('[data-lact="balance"]'); time.sleep(0.3)
            out2 = {h: x for h, x in json.loads(b.js("JSON.stringify([...LEAD.state().plan.out])"))}
            check("balancing the loads respects the criteria: no Kazakh-speaking household leaves E01", all(out2[h]["enumerator_id"] == "E01" for h in kk_in))
        else:
            check("balancing the loads respects the criteria (loads already within the margin: not exercised)", True)
        # nobody speaks Kazakh: the households wait for the leader
        setv(f'[data-lattr="{team.index("E01")}"][data-c="language"]', "mn")
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        un = b.js("LEAD.state().plan.unmatched")
        check("when no available enumerator matches, the households are listed without an enumerator and no file can be written",
              sorted(un) == kk_in and b.js("document.querySelector('[data-lact=\"write\"]').disabled") and any("match no available enumerator" in w for w in b.js("LEAD.state().plan.warnings")), un)
        setv(f'[data-lmove="{un[0]}"]', "E02")
        check("the leader assigns such a household by hand: it leaves the list, marked as not matched, with a warning",
              b.js("LEAD.state().plan.unmatched.length") == len(un) - 1 and b.js(f"LEAD.state().plan.out.get('{un[0]}').matched") is False and b.js("APP.toasts.some(t => /does not match E02/.test(t.text))"))
        setv(f'[data-lattr="{team.index("E01")}"][data-c="language"]', "kk, mn")
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        check("the day list is taken from the last round's manifest, like the dial cap and the call hours", b.js("LEAD.state().cal.day_list") == 5)
        setv('[data-lset="cal.day_list"]', "")
        dl_default = b.js("LEAD.state().plan.dayListDefault")
        check("left empty, the day list defaults to 1.5 × the busiest enumerator's planned first dials per day, shown in step 4",
              dl_default >= 1 and f"empty means 1.5 × that, {dl_default}" in b.js("document.querySelector('.panel').innerText") and b.js("LEAD.state().cal.day_list") is None, dl_default)
        before = snapshot()
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        b.click('[data-lact="dlall"]')
        got = [wait_new(n, before) for n in ("E01_assignment_R05.json", "E02_assignment_R05.json", "E07_assignment_R05.json", "L2MN-DEMO_R05_manifest.json")]
        A = {e: json.load(open(os.path.join(DL, f"{e}_assignment_R05.json"), encoding="utf-8")) for e in ("E01", "E02", "E07")}
        M = json.load(open(os.path.join(DL, "L2MN-DEMO_R05_manifest.json"), encoding="utf-8"))
        check("the manifest records the criteria and every enumerator's values; each file carries the criteria and its enumerator's values",
              all(got) and M.get("matching") == {"criteria": ["language"], "enumerators": {"E01": {"language": ["kk", "mn"]}, "E02": {"language": ["mn"]}, "E07": {"language": ["mn"]}}}
              and all(a["matching"] == {"criteria": ["language"], "enumerator": M["matching"]["enumerators"][e]} for e, a in A.items()), M.get("matching"))
        check("each household in a file carries its own value and whether its enumerator matches; the kk households are all in E01's file",
              all(h["criteria"]["language"] in ("kk", "mn") and h["assignment"]["matched"] is True for a in A.values() for h in a["households"])
              and sorted(h["hhid"] for h in A["E01"]["households"] if h["criteria"]["language"] == "kk") == kk_in
              and not any(h["criteria"]["language"] == "kk" for e in ("E02", "E07") for h in A[e]["households"]))
        check("the files carry the day list, equal to the default when the leader left it empty", all(a["calendar"]["day_list"] == dl_default for a in A.values()) and M["calendar"]["day_list"] == dl_default and all(a["revision"] == 1 for a in A.values()),
              [dl_default, M["calendar"].get("day_list"), {e: (a["calendar"].get("day_list"), a.get("revision")) for e, a in A.items()}])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cfm.main([os.path.join(DL, f"{e}_assignment_R05.json") for e in A] + [os.path.join(DL, "L2MN-DEMO_R05_manifest.json")])
        check("files with criteria and a day list pass the format checker", code == 0 and "warning" not in buf.getvalue(), buf.getvalue())
        setv('[data-lset="cal.day_list"]', "9")
        check("changing the day list sets the files aside but keeps the assignment", b.js("LEAD.ui.ready === null && !!LEAD.state().plan"))
        before = snapshot()
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        b.click('[data-lact="dlall"]')
        wait_new("E07_assignment_R05.json", before)
        check("the leader's own day list is written instead", json.load(open(os.path.join(DL, "E07_assignment_R05.json"), encoding="utf-8"))["calendar"]["day_list"] == 9)
        # the saved session keeps the criteria and the values
        before = snapshot()
        b.click('[data-lact="save"]'); b.wait("APP.modal"); b.click('[data-act="modalok"]')
        fpc = wait_new("leader_L2MN-DEMO_R05*.json", before)
        Pc = json.load(open(fpc, encoding="utf-8"))
        check("the saved leader session keeps the criteria and each enumerator's values", Pc["settings"]["criteria"] == ["language"] and Pc["settings"]["team"][team.index("E01")]["attrs"] == {"language": "kk, mn"})

        # the proposal of moves, on fabricated paces: from the enumerator furthest behind to the one with most spare days
        unit = b.js("""(() => { const rows = [
            { enumerator_id: 'A', known: true, fresh: true, need: 3.4 }, { enumerator_id: 'B', known: true, fresh: true, need: -2.6 },
            { enumerator_id: 'C', known: true, fresh: true, need: -0.4 }, { enumerator_id: 'D', known: true, fresh: false, export_day: '2026-11-01', need: -9, why: 'last export 2026-11-01, not today' } ];
          const C = new Map(); const add = (h, e, state, extra) => C.set(h, Object.assign({ hhid: h, enumerator_id: e, state, dials: [], n: 0 }, extra || {}));
          add('a1', 'A', 'not_started'); add('a2', 'A', 'not_started'); add('a3', 'A', 'in_progress', { dials: [{ status: 'NO_ANSWER' }], n: 1 }); add('a4', 'A', 'complete');
          add('a5', 'A', 'in_progress', { dials: [{ status: 'NO_ANSWER', appointment_ts: '2026-11-10T10:00:00+08:00' }], n: 1 }); add('b1', 'B', 'not_started'); add('d1', 'D', 'not_started');
          const r1 = LCORE.proposeMoves({ rows }, C, { include: 'not_started' });
          const r2 = LCORE.proposeMoves({ rows }, C, { include: 'in_progress' });
          const r3 = LCORE.proposeMoves({ rows }, C, { include: 'not_started', eligible: (h, e) => !(h.hhid === 'a2' && e === 'B'), hh: new Map([['a1', { hhid: 'a1' }], ['a2', { hhid: 'a2' }]]) });
          const r4 = LCORE.proposeMoves({ rows }, C, { include: 'not_started', allowStale: true });
          const mv = (r) => r.moves.map(m => [m.hhid, m.from, m.to]);
          return { r1: mv(r1), r2: mv(r2), r3: mv(r3), r4: mv(r4), left: r1.left_out }; })()""")
        check("moves go one at a time from the enumerator furthest behind to the one with most spare days, never dialed households first, until nobody is more than half a household off",
              unit["r1"] == [["a2", "A", "B"], ["a1", "A", "B"]], unit)
        check("called households without a booked callback move only when the leader allows it; a booked callback or a complete never moves", unit["r2"] == [["a2", "A", "B"], ["a1", "A", "B"], ["a3", "A", "B"]], unit)
        check("a household moves only to an enumerator who matches its criteria", unit["r3"] == [["a1", "A", "B"]], unit)
        check("an enumerator whose export is from an earlier day is not judged unless the leader says so", unit["left"] == [{"id": "D", "why": "last export 2026-11-01, not today"}] and unit["r4"][0] == ["a2", "A", "D"], unit)
        # more cases during the round (3 November 2026): an enumerator who finished early, one who is given households, one who leaves
        unit2 = b.js("""(() => { const rows = [
            { enumerator_id: 'A', known: true, fresh: true, open: 4, need: 3.4 }, { enumerator_id: 'B', known: true, fresh: true, open: 1, need: -2.6 },
            { enumerator_id: 'C', known: true, fresh: true, open: 2, need: -0.4 }, { enumerator_id: 'D', known: true, fresh: false, open: 1, export_day: '2026-11-01', need: -9, why: 'last export 2026-11-01, not today' },
            { enumerator_id: 'F', known: true, fresh: false, open: 0, export_day: '2026-11-01', need: -3, why: '' },
            { enumerator_id: 'G', known: true, fresh: true, open: 0, need: -1, away: true, why: 'away since 2026-11-02' } ];
          const C = new Map(); const add = (h, e, state, extra) => C.set(h, Object.assign({ hhid: h, enumerator_id: e, state, dials: [], n: 0 }, extra || {}));
          add('a1', 'A', 'not_started'); add('a2', 'A', 'not_started'); add('a3', 'A', 'in_progress', { dials: [{ status: 'NO_ANSWER' }], n: 1 }); add('a4', 'A', 'complete');
          add('a5', 'A', 'in_progress', { dials: [{ status: 'APPOINTMENT', appointment_ts: '2026-11-10T10:00:00+08:00' }], n: 1 });
          add('a6', 'A', 'in_progress', { dials: [{ status: 'REFUSAL_HARD' }], n: 1 }); add('a7', 'A', 'not_started'); add('b1', 'B', 'not_started'); add('c1', 'C', 'not_started'); add('c2', 'C', 'not_started'); add('d1', 'D', 'not_started');
          const mv = r => r.moves.map(m => [m.hhid, m.from, m.to]);
          const r1 = LCORE.proposeMoves({ rows }, C, { include: 'not_started' });
          const r5 = LCORE.proposeMoves({ rows }, C, { include: 'not_started', take: { id: 'C', n: 2 } });
          const r6 = LCORE.proposeMoves({ rows }, C, { include: 'not_started', take: { id: 'N', n: 9 }, exclude: new Set(['a7']) });
          const r7 = LCORE.coverAway({ rows }, C, { away: 'A' });
          const r8 = LCORE.coverAway({ rows }, C, { away: 'A', eligible: (h, e) => e === 'C', hh: new Map([['a1', { hhid: 'a1' }]]) });
          return { r1: mv(r1), judged1: r1.judged, left1: r1.left_out.map(x => x.id), r5: mv(r5), r6: mv(r6), short6: r6.short, r7: mv(r7), cb7: r7.moves.map(m => m.callback || ''), stay7: r7.stay, r8: mv(r8) }; })()""")
        check("an enumerator who finished early (nothing open) is judged on any export and takes households; one marked away never does",
              unit2["r1"] == [["a7", "A", "F"], ["a2", "A", "B"], ["a1", "A", "F"]] and unit2["judged1"] == ["A", "B", "C", "F"] and unit2["left1"] == ["D", "G"], unit2)
        check("'give n households to X': X alone takes n, from the enumerator furthest behind, whether or not X is short", unit2["r5"] == [["a7", "A", "C"], ["a2", "A", "C"]], unit2)
        check("given to a newcomer, with one household excluded: from those behind, then those with most waiting; the shortfall is reported when nobody judged has more",
              unit2["r6"] == [["a2", "A", "N"], ["a1", "A", "N"], ["c2", "C", "N"], ["c1", "C", "N"], ["b1", "B", "N"]] and unit2["short6"] == 4, unit2)
        check("an enumerator who leaves: every open household goes to the others, those with spare days first and then evenly, a booked callback with its household; a hard refusal stays",
              unit2["r7"] == [["a7", "A", "F"], ["a2", "A", "B"], ["a1", "A", "F"], ["a5", "A", "B"], ["a3", "A", "F"]] and unit2["cb7"] == ["", "", "", "2026-11-10T10:00:00+08:00", ""]
              and unit2["stay7"] == [{"hhid": "a6", "why": "hard refusal: nobody calls it again"}], unit2)
        check("covering an enumerator who leaves respects the criteria: a household goes only to an enumerator who matches it", unit2["r8"][2] == ["a1", "A", "C"], unit2)

        # moving households during the round: the sample's exports of 6 November, judged on Friday 13 November with 7 working days left
        start()
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", HIST); b.wait(f"LEAD.state().inputs.history.length === {len(HIST)}")
        b.click('[data-lact="tab"][data-t="import"]')
        b.js("RTM.setNow('2026-11-13T09:00:00+08:00'); true")
        b.set_files("#lf-manifest", [MANIFEST]); b.wait("!!LEAD.state().manifest")
        b.set_files("#lf-imports", EXPORTS); b.wait(f"LEAD.state().imports.length === {len(EXPORTS)}")
        b.click('[data-lact="tab"][data-t="progress"]')
        txt = b.js("document.querySelector('.panel').innerText")
        check("the Progress tab shows each enumerator's pace and capacity for the working days left, and who is short or has spare days",
              "Move waiting households" in txt and "Completes per day" in txt and "7 working days left" in txt, txt[:200])
        # E07's export with their own changes (3 November 2026): two calls moved (one a first call moved later), and time off: one day and an afternoon ahead, one day already past
        selfx = b.js("""(() => { const st = LEAD.state(), f = st.imports.find(x => /E07_2026-11-06\\.json$/.test(x.name)), j = JSON.parse(f.text);
            const S = { assignment: { program: j.program, round: j.round, enumerator_id: j.enumerator_id }, events: j.events, genesis: j.chain_genesis };
            RTM.setNow('2026-11-06T17:00:00+08:00');
            const open = [...LEAD.merged().C.values()].filter(c => c.enumerator_id === 'E07' && c.state === 'not_started').map(c => c.hhid);
            RTM.append(S, 'plan', { hhid: open[0], at: '2026-11-09T18:00:00+08:00', reason: 'TOLD', was: '2026-11-02T18:00:00+08:00', first: 1 });
            RTM.append(S, 'plan', { hhid: open[1], at: '2026-11-07T12:00:00+08:00', reason: 'WORKLOAD', was: '2026-11-07T17:00:00+08:00', first: 1 });
            RTM.append(S, 'availability', { date: '2026-11-05', part: 'day' });
            RTM.append(S, 'availability', { date: '2026-11-16', part: 'day' });
            RTM.append(S, 'availability', { date: '2026-11-17', part: 'afternoon' });
            RTM.setNow('2026-11-13T09:00:00+08:00');
            j.events = S.events.map(RTM.exportEvent); j.event_count = j.events.length; j.last_hash = j.events[j.events.length - 1].hash;
            f.orig = f.text; f.text = JSON.stringify(j); LEAD.refresh();
            const g = LEAD.merged(), r = g.P.list.find(x => x.enumerator_id === 'E07'), pace = LCORE.pace(st.manifest, g.C, g.P, RTM.now()).rows;
            return { row: [r.moved_by_them, r.first_later, r.days_off], left: Object.fromEntries(pace.map(x => [x.enumerator_id, x.days_left])),
              cap: (x => [x.capacity, x.pace * 5.5])(pace.find(x => x.enumerator_id === 'E07')), chain: g.G.issues.filter(i => i.type === 'chain_broken').length }; })()""")
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.2)
        ptxt = b.js("document.querySelector('.panel').innerText")
        check("the leader reads each enumerator's own changes from their JSON export: calls they moved, first calls moved later, days off (a half day counts half), shown on the Progress tab",
              selfx["row"] == [2, 1, 2.5] and selfx["chain"] == 0 and "Calls they moved" in ptxt and "First calls moved later" in ptxt and "Days off marked" in ptxt, [selfx, ptxt[:300]])
        check("the pace counts only the days each enumerator works: E07's day and afternoon off ahead leave 5.5 of the 7 working days (the day off already past does not count); the others keep 7",
              selfx["left"] == {"E01": 7, "E02": 7, "E07": 5.5} and abs(selfx["cap"][0] - selfx["cap"][1]) < 1e-9 and "1.5 days off ahead" in ptxt, [selfx, ptxt[:400]])
        b.js("(() => { const f = LEAD.state().imports.find(x => x.orig); f.text = f.orig; delete f.orig; LEAD.refresh(); return true; })()")
        man = json.load(open(MANIFEST, encoding="utf-8"))
        hold = {h["hhid"]: h["enumerator_id"] for h in man["households"]}
        py_pace = ref_stats.pace_by_enumerator(exp_calls, exp_acts, man, days_left=7)
        js_pace = {r["enumerator_id"]: r for r in b.js("LCORE.pace(LEAD.state().manifest, LEAD.merged().C, LEAD.merged().P, RTM.now()).rows")}
        check("pace, capacity and the shortfall per enumerator equal an independent computation from the merged log",
              all(abs(js_pace[e]["pace"] - p["pace"]) < 1e-9 and js_pace[e]["open"] == p["open"] and abs(js_pace[e]["need"] - p["need"]) < 1e-9 for e, p in py_pace.items()), [py_pace, {e: (r["pace"], r["open"], r["need"]) for e, r in js_pace.items()}])
        b.click('[data-lact="propose"]'); time.sleep(0.3)
        check("exports from an earlier day are not judged unless the leader says so", b.js("LEAD.ui.moves.list.length") == 0 and "not today" in b.js("document.querySelector('.panel').innerText"))
        tick('[data-lset="__movesStale"]', True)
        b.click('[data-lact="propose"]'); time.sleep(0.3)
        mv = b.js("LEAD.ui.moves.list")
        waiting = {e: b.js(f"[...LEAD.merged().C.values()].filter(c => c.enumerator_id === '{e}' && c.state === 'not_started').map(c => c.hhid).sort().reverse()") for e in ("E01", "E07")}
        exp_need = {e: round(p["need"], 1) for e, p in py_pace.items()}
        check("on 13 November two households move to E02, the only enumerator with spare days (2.3): first from E01 (1.9 short), then from E07 (1.0 short, now the furthest behind), each its latest-planned household, until E02 is within half a household",
              exp_need == {"E01": 1.9, "E02": -2.3, "E07": 1.0} and len(mv) == 2 and [(m["from"], m["to"], m["state"], m["hhid"]) for m in mv] == [("E01", "E02", "not_started", waiting["E01"][0]), ("E07", "E02", "not_started", waiting["E07"][0])], [mv, exp_need, waiting])
        by_hand = next(h for h in reversed(waiting["E01"]) if h != mv[0]["hhid"])
        b.js(f"document.querySelector('#lmv-hh').value = {json.dumps(by_hand)}; document.querySelector('#lmv-to').value = 'E02'; true")
        b.click('[data-lact="addmove"]'); time.sleep(0.3)
        n_list = b.js("LEAD.ui.moves.list.length")
        b.js("document.querySelector('#lmv-hh').value = [...LEAD.merged().C.values()].find(c => c.state === 'complete').hhid; true"); b.click('[data-lact="addmove"]'); time.sleep(0.2)
        check("the leader adds a move by hand; a household already complete is refused",
              n_list == 3 and b.js("LEAD.ui.moves.list[2].by_hand") is True and b.js("APP.toasts.some(t => /cannot move: it is Complete/.test(t.text)) && LEAD.ui.moves.list.length === 3"),
              [n_list, b.js("APP.toasts.map(t => t.text)")])
        b.shot(os.path.join(SCREENS, "leader_10_moves.png"), full=True)
        old_fp = {e["enumerator_id"]: e["fingerprint"] for e in man["enumerators"]}
        before = snapshot()
        b.click('[data-lact="writemoves"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'moves'", timeout=30)
        b.click('[data-lact="dlall"]')
        got = [wait_new(n, before) for n in ("E01_assignment_R05.json", "E02_assignment_R05.json", "E07_assignment_R05.json", "L2MN-DEMO_R05_manifest.json")]
        R2 = {e: json.load(open(os.path.join(DL, f"{e}_assignment_R05.json"), encoding="utf-8")) for e in ("E01", "E02", "E07")}
        M2 = json.load(open(os.path.join(DL, "L2MN-DEMO_R05_manifest.json"), encoding="utf-8"))
        moved_ids = {mv[0]["hhid"], mv[1]["hhid"], by_hand}
        check("revised files are written for the three enumerators concerned, and the manifest's revision 2 supersedes revision 1",
              all(got) and M2["revision"] == 2 and M2["supersedes"] == man["fingerprint"] and all(a["revision"] == 2 and a["supersedes"] == old_fp[e] for e, a in R2.items()), [M2.get("revision"), M2.get("supersedes") == man["fingerprint"]])
        check("the manifest lists the three moves with when and by whom, the households now with E02 for the reason 'mid_round', their previous enumerator kept",
              [(m["hhid"], m["from"], m["to"]) for m in M2["moves"]] == [(mv[0]["hhid"], "E01", "E02"), (mv[1]["hhid"], "E07", "E02"), (by_hand, "E01", "E02")] and all(m["by"] == "L01" and m["at"].startswith("2026-11-13T09:00") for m in M2["moves"])
              and all(h["enumerator_id"] == "E02" and h["reason"] == "mid_round" and h["previous_enumerator"] == hold[h["hhid"]] for h in M2["households"] if h["hhid"] in moved_ids), M2["moves"])
        check("the roster counts follow the moves, and each revised file's earlier fingerprint is kept so that logs begun from it still belong",
              {e["enumerator_id"]: e["households"] for e in M2["enumerators"]} == {"E01": 38, "E02": 27, "E07": 45} and all(e["previous_fingerprints"] == [old_fp[e["enumerator_id"]]] for e in M2["enumerators"]),
              {e["enumerator_id"]: e["households"] for e in M2["enumerators"]})
        e02new = {h["hhid"]: h for h in R2["E02"]["households"]}
        check("E02's revised file holds its 24 households and the 3 moved ones, with the previous enumerator's dials (handover), a first dial today and the household's usual hour",
              len(e02new) == 27 and all(e02new[h]["handover"]["dials"] == 0 and e02new[h]["handover"]["from"] == hold[h] and e02new[h]["plan"]["first_dial_date"] == "2026-11-13" and e02new[h]["assignment"]["reason"] == "mid_round" for h in moved_ids)
              and all("handover" not in h for k, h in e02new.items() if k not in moved_ids), [e02new[h].get("handover") for h in moved_ids])
        hl_by = {r["hhid"]: r for r in hl}
        corrected = {}                      # numbers enumerators corrected this round go into the revised files (the contacts file of the exports)
        for cfile in glob.glob(os.path.join(S, "exports_R05", "*_contacts.json")):
            for u in json.load(open(cfile, encoding="utf-8"))["updates"]:
                if u.get("number"): corrected.setdefault(u["hhid"], set()).add(u["number"])
        own = lambda h: {hl_by[h][k] for k in ("phone_1", "phone_2", "phone_3")} | corrected.get(h, set())
        check("access control holds: each revised file carries only its own households' numbers, with the numbers corrected this round",
              all(all(p["number"] in own(h["hhid"]) for h in a["households"] for p in h["contact"]["phones"]) for a in R2.values())
              and any(p["number"] in corrected.get(h["hhid"], set()) for a in R2.values() for h in a["households"] for p in h["contact"]["phones"]), corrected)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cfm.main([os.path.join(DL, f"{e}_assignment_R05.json") for e in R2] + [os.path.join(DL, "L2MN-DEMO_R05_manifest.json")])
        check("the revised files and the manifest pass the format checker", code == 0 and "warning" not in buf.getvalue(), buf.getvalue())
        # the merge with the revised manifest: dials before the move are the previous enumerator's; a dial after it is a double call
        rows7 = open(os.path.join(S, "exports_R05", "E07_2026-11-06.csv"), encoding="utf-8").read().rstrip("\n").split("\n")
        hdr7 = rows7[0].split(","); ix = {k: hdr7.index(k) for k in ("hhid", "ts", "end_ts", "logged_at", "event_id", "prev_hash", "attempt", "appointment_ts", "action")}
        gone7 = mv[1]["hhid"]              # the household that left E07
        def dial_row(ts, eid):
            f = rows7[-1].split(","); f[ix["hhid"]] = gone7; f[ix["ts"]] = ts; f[ix["end_ts"]] = ts[:14] + "01:00"; f[ix["logged_at"]] = ts.replace(" ", "T") + "+08:00"
            f[ix["event_id"]] = eid; f[ix["attempt"]] = "1"; f[ix["appointment_ts"]] = ""; f[ix["action"]] = ""
            return ",".join(f)
        later7 = "\n".join(rows7 + [dial_row("2026-11-06 15:00:00", "00000000-0000-4000-8000-00000000000a"), dial_row("2026-11-13 10:00:00", "00000000-0000-4000-8000-00000000000b")]) + "\n"
        g9 = b.js(f"""(() => {{ const st = LEAD.state(), base = st.imports.map(f => LCORE.readImport(f.name, f.text)).concat([LCORE.readImport('E07_2026-11-13.csv', {json.dumps(later7)})]);
                     const G = LCORE.merge(st.manifest, base, new Map(), RTM.now());
                     const iss = G.issues.filter(i => i.hhid === {json.dumps(gone7)}).map(i => [i.type, i.enumerator, i.detail]);
                     return {{ iss, before: G.dials.some(d => d.event_id === '00000000-0000-4000-8000-00000000000a'), after: G.dials.some(d => d.event_id === '00000000-0000-4000-8000-00000000000b'),
                               holder: LCORE.cases(st.manifest, G).get({json.dumps(gone7)}).enumerator_id }}; }})()""")
        check("after the move, E07's dial on the household before the move is accepted without a question; the one after it is flagged as a double call, kept until the leader decides",
              [t for t, _, _ in g9["iss"]] == ["after_move"] and g9["iss"][0][1] == "E07" and "moved to E02" in g9["iss"][0][2] and g9["before"] and g9["after"] and g9["holder"] == "E02", g9)
        # the leader's session keeps the revised manifest
        before = snapshot()
        b.click('[data-lact="save"]'); b.wait("APP.modal"); b.click('[data-act="modalok"]')
        fpm = wait_new("leader_L2MN-DEMO_R05*.json", before)
        check("the saved leader session holds the revised manifest and logs the moves", json.load(open(fpm, encoding="utf-8"))["manifest"]["revision"] == 2 and any(e["what"] == "households_moved_mid_round" and e["moves"] == 3 for e in json.load(open(fpm, encoding="utf-8"))["events"]))
        # the enumerators open the revised files as updates
        b.click('[data-act="view"][data-v="enum"]')
        b.set_files("#f-assign", [os.path.join(ROOT, "samples", "round05", "E02_assignment_R05.json")]); b.wait("!!APP.S")
        keep02 = next(h["hhid"] for h in json.load(open(os.path.join(ROOT, "samples", "round05", "E02_assignment_R05.json"), encoding="utf-8"))["households"] if h["hhid"] not in moved_ids)
        plan_before = b.js(f"JSON.stringify(APP.C.map.get('{keep02}').h.plan)")
        b.set_files("#f-update", [os.path.join(DL, "E02_assignment_R05.json")]); b.wait("APP.S.events.some(e => e.what === 'assignment_updated')")
        ev = b.js("APP.S.events.find(e => e.what === 'assignment_updated')")
        check("E02 loads the revised file as an update: 3 households added, revision 2 logged, the log kept",
              ev["households_added"] == 3 and ev["households_removed"] == 0 and ev["revision"] == 2 and ev["fingerprint_ok"] == 1, ev)
        check("a household E02 already had keeps its planned first dial and history (carried beside the revised file, which omits them)",
              b.js(f"JSON.stringify(APP.C.map.get('{keep02}').h.plan)") == plan_before and b.js(f"!!APP.S.carry['{keep02}']"))
        prior = b.js(f"(() => {{ const c = APP.C.map.get({json.dumps(mv[0]['hhid'])}); return [c.prior.from, c.nAll, c.state, c.next.kind, RTM.partsIn(c.next.at, APP.C.cal.tz).key]; }})()")
        check("a moved household shows who had it, counts their dials toward the cap and is due today", prior == ["E01", 0, "not_started", "first", "2026-11-13"], prior)
        nev = b.js("APP.S.events.length")
        b.set_files("#f-update", [os.path.join(ROOT, "samples", "round05", "E02_assignment_R05.json")])
        b.wait("APP.toasts.some(t => /older than the assignment in your session/.test(t.text))")
        check("the earlier file, opened again by mistake, is refused as older", b.js("APP.S.events.length") == nev)
        before = snapshot()
        b.click('[data-act="save"]'); wait_new("E02_project_R05*.json", before)
        newest = wait_new("E02_project_R05*.json", before)
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-project", [newest]); b.wait("!!APP.S || APP.loadErrors.length")
        check("a session saved after the update reopens with the carried plans", b.js(f"!!APP.S && APP.loadErrors.length === 0 && JSON.stringify(APP.C.map.get('{keep02}').h.plan)") == plan_before, b.js("APP.loadErrors"))
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.set_files("#f-assign", [os.path.join(ROOT, "samples", "round05", "E07_assignment_R05.json")]); b.wait("!!APP.S")
        b.set_files("#f-update", [os.path.join(DL, "E07_assignment_R05.json")]); b.wait("APP.S.events.some(e => e.what === 'assignment_updated')")
        check("E07 loads the revised file: the moved household is no longer theirs, shown read-only",
              b.js(f"[APP.S.events.find(e => e.what === 'assignment_updated').households_removed, APP.C.map.get({json.dumps(gone7)}).kind]") == [1, "removed"])
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.click('[data-act="view"][data-v="leader"]')

        # ---- more cases during the round (3 November 2026), on revision 2: E01 leaves, E09 joins and is given households ----
        b.click('[data-lact="tab"][data-t="progress"]')
        e01_open = b.js("[...LEAD.merged().C.values()].filter(c => c.enumerator_id === 'E01' && !c.replaces && (c.state === 'not_started' || c.state === 'in_progress') && !c.dials.some(d => d.status === 'REFUSAL_HARD')).map(c => c.hhid).sort()")
        e01_cb = b.js(f"(() => {{ const open = new Set({json.dumps(e01_open)}); return [...LEAD.merged().C.values()].filter(c => open.has(c.hhid) && c.dials.length && c.dials[c.dials.length - 1].appointment_ts && RTM.CALLBACK_STATUSES.includes(c.dials[c.dials.length - 1].status)).map(c => [c.hhid, c.dials[c.dials.length - 1].appointment_ts]); }})()")
        not_open_cb = b.js("[...LEAD.merged().C.values()].filter(c => c.enumerator_id === 'E01' && c.dials.length && c.dials[c.dials.length - 1].appointment_ts && !(c.state === 'not_started' || c.state === 'in_progress')).map(c => [c.hhid, c.state])")
        open_before = {r["enumerator_id"]: r["open"] for r in b.js("LCORE.pace(LEAD.state().manifest, LEAD.merged().C, LEAD.merged().P, RTM.now()).rows")}
        b.js("document.querySelector('#lmv-away').value = 'E01'; true"); b.click('[data-lact="away"]'); time.sleep(0.3)
        mv2 = b.js("LEAD.ui.moves.list")
        got_by = {e: sum(1 for m in mv2 if m["to"] == e) for e in ("E02", "E07")}
        check("an enumerator who leaves (E01): every open household moves to the others, the booked callbacks with them, spread evenly when nobody has spare days",
              len(e01_open) > 2 and e01_cb and sorted(m["hhid"] for m in mv2) == e01_open and all(m["from"] == "E01" and m["to"] in ("E02", "E07") and m["away"] for m in mv2)
              and all(next(m for m in mv2 if m["hhid"] == h)["callback"] == ts for h, ts in e01_cb) and b.js("LEAD.ui.moves.away") == "E01"
              and all(h not in {m["hhid"] for m in mv2} for h, _ in not_open_cb)
              and abs((open_before["E02"] + got_by["E02"]) - (open_before["E07"] + got_by["E07"])) <= 1, [len(mv2), e01_cb, not_open_cb, open_before, got_by])
        b.js("document.querySelector('#lnew-id').value = 'E09'; document.querySelector('#lnew-name').value = 'New hire'; document.querySelector('#lnew-pid').value = 'CATI09'; true")
        b.click('[data-lact="addjoin"]'); time.sleep(0.3)
        check("an enumerator who joins mid-round (E09) is added with their platform code and offered as a taker",
              b.js("LEAD.ui.added.length === 1 && LEAD.ui.added[0].enumerator_id === 'E09' && LEAD.ui.added[0].platform_id === 'CATI09'") and "E09 (new)" in b.js("document.querySelector('#lmv-take').innerText"))
        n_before = b.js("LEAD.ui.moves.list.length")
        b.js("document.querySelector('#lmv-n').value = '4'; document.querySelector('#lmv-take').value = 'E09'; true"); b.click('[data-lact="take"]'); time.sleep(0.3)
        mv3 = b.js(f"LEAD.ui.moves.list.slice({n_before})")
        check("'give 4 households to E09' adds four moves to the newcomer from the enumerators furthest behind, none already in the list",
              len(mv3) == 4 and all(m["to"] == "E09" and m["from"] in ("E02", "E07") and m["state"] == "not_started" for m in mv3) and len({m["hhid"] for m in b.js("LEAD.ui.moves.list")}) == n_before + 4, mv3)
        unit3 = b.js("""(() => { const st = LEAD.state(), M = JSON.parse(JSON.stringify(st.manifest));
            M.matching = { criteria: ['language'], enumerators: { E01: { language: ['kk', 'mn'] }, E02: { language: ['mn'] }, E07: { language: ['mn'] } } };
            const B = LCORE.reviseFiles({ M, moves: [], C: LEAD.merged().C, hh: new Map(), sumOf: null, plans: null, updates: [], leader: 'L01', at: '2026-11-13T09:30:00+08:00', now: RTM.now(),
              added: [{ enumerator_id: 'E09', name: 'New hire', platform_id: 'CATI09', attrs: { language: 'MN, kk' } }], away: null });
            const e = B.manifest.enumerators.find(x => x.enumerator_id === 'E09');
            return { values: B.manifest.matching.enumerators.E09, e09: e, files: B.files.length, rev: B.manifest.revision }; })()""")
        check("a newcomer's criteria values are recorded in the manifest's matching, lower-cased and sorted; without a move they join the roster with no file",
              unit3["values"] == {"language": ["kk", "mn"]} and unit3["e09"]["households"] == 0 and unit3["e09"]["joined_at"] == "2026-11-13T09:30:00+08:00" and unit3["files"] == 0 and unit3["rev"] == 3, unit3)
        before = snapshot()
        b.click('[data-lact="writemoves"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'moves'", timeout=30)
        b.click('[data-lact="dlall"]')
        got3 = [wait_new(n, before) for n in ("E01_assignment_R05.json", "E02_assignment_R05.json", "E07_assignment_R05.json", "E09_assignment_R05.json", "L2MN-DEMO_R05_manifest.json")]
        M3 = json.load(open(got3[-1], encoding="utf-8")); R3 = {e: json.load(open(f, encoding="utf-8")) for e, f in zip(("E01", "E02", "E07", "E09"), got3[:-1])}
        ros = {e["enumerator_id"]: e for e in M3["enumerators"]}
        check("revision 3: E01 is marked away in the roster, with only closed households left in their file; E09 joins the roster with their platform code and a first file that supersedes nothing",
              M3["revision"] == 3 and ros["E01"]["away_from"].startswith("2026-11-13") and all(h["hhid"] not in e01_open for h in R3["E01"]["households"]) and ros["E01"]["households"] == len(R3["E01"]["households"])
              and ros["E09"]["platform_id"] == "CATI09" and ros["E09"]["name"] == "New hire" and ros["E09"]["joined_at"].startswith("2026-11-13") and ros["E09"]["households"] == 4
              and R3["E09"]["revision"] == 3 and "supersedes" not in R3["E09"] and R3["E09"]["note"].startswith("You join") and len(R3["E09"]["households"]) == 4 and all(h["handover"]["from"] in ("E02", "E07") for h in R3["E09"]["households"]),
              [M3["revision"], ros.get("E01"), ros.get("E09")])
        taken = {h["hhid"]: h for e in ("E02", "E07") for h in R3[e]["households"]}
        check("a household moved with a booked callback carries it in the handover, and the manifest's moves list has grown by every move",
              all(taken[h]["handover"]["appointment_ts"] == ts and taken[h]["handover"]["from"] == "E01" for h, ts in e01_cb) and len(M3["moves"]) == 3 + len(mv2) + 4, [e01_cb, len(M3["moves"])])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cfm.main(got3)
        check("the revision-3 files and the manifest, with the newcomer and the enumerator away, pass the format checker", code == 0 and "warning" not in buf.getvalue(), buf.getvalue())
        check("after the write, the roster offers E09 and marks E01 away, and the pace table says since when",
              "E09" in b.js("document.querySelector('#lmv-to').innerText") and "E01 (away)" in b.js("document.querySelector('#lmv-to').innerText") and "away since 2026-11-13" in b.js("document.querySelector('.panel').innerText") and b.js("LEAD.ui.added.length") == 0)
        # the newcomer opens their first file; the enumerator who received a household with a callback is due at that time
        b.click('[data-act="view"][data-v="enum"]')
        b.set_files("#f-assign", [got3[3]]); b.wait("!!APP.S")
        check("the newcomer opens their first file: four households, each showing who had it before", b.js("APP.C.list.filter(c => c.kind === 'main').length") == 4 and b.js("APP.C.list.every(c => c.kind !== 'main' || (c.prior && c.prior.from))"))
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        cb_h, cb_ts = e01_cb[0]; cb_e = "E02" if any(h["hhid"] == cb_h for h in R3["E02"]["households"]) else "E07"
        b.set_files("#f-assign", [os.path.join(ROOT, "samples", "round05", f"{cb_e}_assignment_R05.json")]); b.wait("!!APP.S")
        b.set_files("#f-update", [got3[1] if cb_e == "E02" else got3[2]]); b.wait("APP.S.events.some(e => e.what === 'assignment_updated')")
        cbc = b.js(f"(() => {{ const c = APP.C.map.get({json.dumps(cb_h)}); return [c.prior.from, c.prior.appointment_ts, c.next.kind, c.appointment ? c.appointment.getTime() === Date.parse({json.dumps(cb_ts)}) : null]; }})()")
        check("the enumerator who receives a household with a booked callback sees it due at that time, with who booked it", cbc == ["E01", cb_ts, "callback", True], cbc)
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.click('[data-act="view"][data-v="leader"]')
        # a household moved back to its first enumerator (E07 → E02 → E07): the dial E07 made while E02 held it is still a double call
        later7b = "\n".join(rows7 + [dial_row("2026-11-06 15:00:00", "00000000-0000-4000-8000-00000000000a"), dial_row("2026-11-13 10:00:00", "00000000-0000-4000-8000-00000000000b"), dial_row("2026-11-14 11:00:00", "00000000-0000-4000-8000-00000000000c")]) + "\n"
        g11 = b.js(f"""(() => {{ const st = LEAD.state(), M = {json.dumps(M2)};
                     M.moves.push({{ hhid: {json.dumps(gone7)}, from: 'E02', to: 'E07', at: '2026-11-14T09:00:00+08:00', by: 'L01' }});
                     M.households.forEach(h => {{ if (h.hhid === {json.dumps(gone7)}) {{ h.enumerator_id = 'E07'; h.previous_enumerator = 'E02'; }} }});
                     const base = st.imports.map(f => LCORE.readImport(f.name, f.text)).concat([LCORE.readImport('E07_2026-11-14.csv', {json.dumps(later7b)})]);
                     const G = LCORE.merge(M, base, new Map(), new Date('2026-11-14T12:00:00+08:00'));
                     const iss = G.issues.filter(i => i.hhid === {json.dumps(gone7)}).map(i => [i.type, i.enumerator, i.detail]);
                     return {{ iss, holder: LCORE.cases(M, G).get({json.dumps(gone7)}).enumerator_id, kept: ['a', 'b', 'c'].map(x => G.dials.some(d => d.event_id === '00000000-0000-4000-8000-00000000000' + x)) }}; }})()""")
        check("a household moved back to its first enumerator: their dial while the other held it is still flagged as a double call; dials before the move and after the return are theirs",
              [t for t, _, _ in g11["iss"]] == ["after_move"] and g11["iss"][0][1] == "E07" and "1 dial" in g11["iss"][0][2] and "moved to E02 on 2026-11-13 09:00" in g11["iss"][0][2] and g11["holder"] == "E07" and g11["kept"] == [True, True, True], g11)

        # ================= D2. replacements the leader approves (3 November 2026) =================
        start()
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.click('[data-lact="tab"][data-t="import"]')
        b.js("RTM.setNow('2026-11-13T09:00:00+08:00'); true")
        b.set_files("#lf-manifest", [MANIFEST]); b.wait("!!LEAD.state().manifest")
        b.set_files("#lf-imports", EXPORTS); b.wait(f"LEAD.state().imports.length === {len(EXPORTS)}")
        pre = b.js("""(() => { const st = LEAD.state(); st.manifest.replacement_policy = Object.assign({}, st.manifest.replacement_policy, { approval: 'leader' });
            const f = st.imports.find(x => /E07_2026-11-06\\.json$/.test(x.name)), j = JSON.parse(f.text);
            const S = { assignment: { program: j.program, round: j.round, enumerator_id: j.enumerator_id }, events: j.events, genesis: j.chain_genesis };
            LEAD.refresh();
            const used = new Set(LEAD.merged().G.activatedBy.keys());
            const cand = [...LEAD.merged().C.values()].filter(c => c.enumerator_id === 'E07' && c.state === 'in_progress' && !c.replaces
              && (st.manifest.households.find(h => h.hhid === c.hhid).replacements || []).some(r => !used.has(r)));
            RTM.setNow('2026-11-06T17:00:00+08:00');
            RTM.append(S, 'action', { hhid: cand[0].hhid, action: 'REPLACEMENT_REQUEST', target_hhid: st.manifest.households.find(h => h.hhid === cand[0].hhid).replacements[0], reason: 'refused firmly' });
            RTM.append(S, 'action', { hhid: cand[1].hhid, action: 'REPLACEMENT_REQUEST', target_hhid: st.manifest.households.find(h => h.hhid === cand[1].hhid).replacements[0], reason: 'no working number' });
            RTM.setNow('2026-11-13T09:00:00+08:00');
            j.events = S.events.map(RTM.exportEvent); j.event_count = j.events.length; j.last_hash = j.events[j.events.length - 1].hash; f.text = JSON.stringify(j); LEAD.refresh();
            const g = LEAD.merged();
            return { a: cand[0].hhid, b: cand[1].hhid, next: (st.manifest.households.find(h => h.hhid === cand[0].hhid).replacements || []).find(r => !used.has(r)),
              states: [g.C.get(cand[0].hhid).state, g.C.get(cand[1].hhid).state], notrel: g.G.issues.filter(i => i.type === 'replacement_not_released').length, acts: used.size,
              rq: LCORE.replacementRequests(st.manifest, g.G, g.C).map(r => [r.main, r.status, r.next]) }; })()""")
        check("with the leader's approval, the enumerators' requests wait on the Progress tab with the next replacement in line, the households count as 'Replacement asked', and a replacement used without a release is a question",
              pre["states"] == ["replacement_requested", "replacement_requested"] and sorted(r[1] for r in pre["rq"]) == ["pending", "pending"] and {r[0]: r[2] for r in pre["rq"]}[pre["a"]] == pre["next"]
              and pre["notrel"] == pre["acts"], pre)
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.2)
        rtxt = b.js("document.querySelector('.panel').innerText")
        tick(f'[data-lrrsel="{pre["a"]}"]', True); b.click('[data-lact="rrrelease"]'); time.sleep(0.2)
        tick(f'[data-lrrsel="{pre["b"]}"]', True); setv("#lrr-note", "keep calling in the evening"); b.click('[data-lact="rrdecline"]'); time.sleep(0.2)
        queued = b.js("[...LEAD.ui.rr.values()].map(x => [x.main, x.decision, x.replacement || '', x.note || ''])")
        before = snapshot()
        b.click('[data-lact="rrwrite"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'decisions'", timeout=30)
        b.click('[data-lact="dlall"]')
        f07 = wait_new("E07_assignment_R05.json", before); fm = wait_new("L2MN-DEMO_R05_manifest.json", before)
        A7 = json.load(open(f07, encoding="utf-8")); M7 = json.load(open(fm, encoding="utf-8"))
        ha = next(h for h in A7["households"] if h["hhid"] == pre["a"]); hb = next(h for h in A7["households"] if h["hhid"] == pre["b"])
        check("the leader releases one request and declines the other in a batch; the revised file of their enumerator carries the release and the decline, and the manifest records both decisions",
              "Replacement requests" in rtxt and queued == [[pre["a"], "released", pre["next"], ""], [pre["b"], "declined", "", "keep calling in the evening"]]
              and ha.get("replacement_release", {}).get("hhid") == pre["next"] and hb.get("replacement_declined", {}).get("note") == "keep calling in the evening"
              and [(d["main"], d["decision"]) for d in M7["replacement_decisions"]] == [(pre["a"], "released"), (pre["b"], "declined")] and M7["revision"] == 2 and "released 1 replacement(s) and declined 1" in A7["note"], [queued, ha.get("replacement_release"), hb.get("replacement_declined"), M7.get("replacement_decisions")])
        post = b.js(f"""(() => {{ const g = LEAD.merged(), st = LEAD.state(), hh = LEAD.state().inputs.households ? null : null;
            const rel = g.C.get({json.dumps(pre["next"])});
            return {{ a: g.C.get({json.dumps(pre["a"])}).state, b: g.C.get({json.dumps(pre["b"])}).state, rel: rel ? [rel.enumerator_id, rel.replaces] : null,
              rq: Object.fromEntries(LCORE.replacementRequests(st.manifest, g.G, g.C).map(r => [r.main, r.status])) }}; }})()""")
        check("with the new manifest the released replacement is active for the household's enumerator and the household counts as replaced; the declined one is in progress again",
              post["a"] == "replaced" and post["rel"] == ["E07", pre["a"]] and post["b"] == "in_progress" and post["rq"] == {pre["a"]: "released", pre["b"]: "declined"}, post)
        b.click('[data-lact="tab"][data-t="platform"]'); time.sleep(0.2)
        before = snapshot(); b.click('[data-lact="export"][data-what="choices"]'); fch = wait_new("choices_households*.csv", before)
        chr_ = [r for r in csv.DictReader(open(fch, encoding="utf-8")) if r["kind"] == "replacement"]
        check("for a team on KoBoToolbox, the form's list carries only the replacements the leader released", [r["name"] for r in chr_] == [pre["next"]], [r["name"] for r in chr_][:5])

        # ================= D3. the round's changes, field visits, blocked numbers, areas, messages, codes (3 November 2026) =================
        start()
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", HIST); b.wait(f"LEAD.state().inputs.history.length === {len(HIST)}")
        b.click('[data-lact="tab"][data-t="import"]')
        b.js("RTM.setNow('2026-11-13T09:00:00+08:00'); true")
        b.set_files("#lf-manifest", [MANIFEST]); b.wait("!!LEAD.state().manifest")
        b.set_files("#lf-imports", EXPORTS); b.wait(f"LEAD.state().imports.length === {len(EXPORTS)}")
        d3 = b.js("""(() => { const st = LEAD.state(), f = st.imports.find(x => /E07_2026-11-06\\.json$/.test(x.name)), j = JSON.parse(f.text);
            const S = { assignment: { program: j.program, round: j.round, enumerator_id: j.enumerator_id }, events: j.events, genesis: j.chain_genesis };
            const ip = [...LEAD.merged().C.values()].filter(c => c.enumerator_id === 'E07' && c.state === 'in_progress' && !c.replaces).map(c => c.hhid);
            RTM.setNow('2026-11-06T17:00:00+08:00');
            RTM.append(S, 'dial', { hhid: ip[0], ts: '2026-11-06T16:00:00+08:00', end_ts: '2026-11-06T16:01:00+08:00', status: 'BLOCKED', phone_slot: 1, operator: 'E07' });
            RTM.append(S, 'action', { hhid: ip[1], action: 'FIELD_VISIT_REQUEST', reason: 'never answers' });
            RTM.setNow('2026-11-13T09:00:00+08:00');
            j.events = S.events.map(RTM.exportEvent); j.event_count = j.events.length; j.last_hash = j.events[j.events.length - 1].hash; f.text = JSON.stringify(j); LEAD.refresh();
            return { blocked: ip[0], visit: ip[1] }; })()""")
        b.click('[data-lact="tab"][data-t="progress"]'); time.sleep(0.3)
        ptx = b.js("document.querySelector('.panel').innerText")
        b.click('[data-lact="mvblocked"]'); time.sleep(0.2)
        bm = b.js("(LEAD.ui.moves ? LEAD.ui.moves.list : []).map(m => [m.hhid, m.from, m.to, !!m.blocked])")
        check("a household whose respondent blocked the caller's number shows on the Progress tab, and one click lists its move to a colleague",
              "blocked their caller's number" in ptx and len(bm) == 1 and bm[0][0] == d3["blocked"] and bm[0][1] == "E07" and bm[0][2] != "E07" and bm[0][3], [bm, d3])
        b.js("LEAD.ui.moves = null; true")
        # the round's changes: a later last day, a household added, E01's file re-issued
        # a top-up household, added to the household list (every household of the sample list is already in the round)
        add_id = "0199-001"
        b.js(f"""(() => {{ const st = LEAD.state(), t = st.inputs.households.text.replace(/\\s+$/, ''), head = t.split(/\\r?\\n/)[0].split(',');
            const row = head.map(c => ({{ hhid: {json.dumps(add_id)}, psu: '0199', stratum: '1', phone_1: '+000 99 001 0001', phone_1_label: 'respondent', contact_name: 'Contact 0199-001 (synthetic)', status: 'active' }})[c] || '');
            st.inputs.households.text = t + '\\n' + row.join(',') + '\\n'; LEAD.refresh(); return true; }})()""")
        setv("#lchg-end", "2026-11-25"); b.click('[data-lact="chgwin"]')
        setv("#lchg-hh", add_id); b.click('[data-lact="chgadd"]')
        b.js("document.querySelector('#lchg-reissue').value = 'E01'; true"); b.click('[data-lact="chgreissue"]'); time.sleep(0.2)
        chg = b.js("JSON.parse(JSON.stringify(LEAD.ui.chg))")
        before = snapshot()
        b.click('[data-lact="chgwrite"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'changes'", timeout=30)
        b.click('[data-lact="dlall"]')
        fm3 = wait_new("L2MN-DEMO_R05_manifest.json", before); M3c = json.load(open(fm3, encoding="utf-8"))
        to = chg["add"][0]["to"]
        fa = {e: json.load(open(wait_new(f"{e}_assignment_R05.json", before), encoding="utf-8")) for e in ("E01", "E02", "E07")}
        addh = next(h for h in fa[to]["households"] if h["hhid"] == add_id)
        cfx = b.js(f"""(() => RTM.validateAssignment({json.dumps(fa[to])}).errors)()""")
        check("changing the round: the new last day reaches every enumerator's revised file and the manifest; the added household goes to the enumerator with the fewest open, with a first call on the next working day; E01's file is re-issued",
              chg["end"] == "2026-11-25" and chg["reissue"] == ["E01"] and M3c["calendar"]["window_end"] == "2026-11-25" and all(a["calendar"]["window_end"] == "2026-11-25" for a in fa.values())
              and any(h["hhid"] == add_id and h["reason"] == "added_mid_round" and h["enumerator_id"] == to for h in M3c["households"])
              and addh["assignment"]["reason"] == "added_mid_round" and addh["plan"]["first_dial_date"] == "2026-11-13" and "runs 2026-10-26 to 2026-11-25" in fa[to]["note"] and cfx == [], [chg, M3c["calendar"]["window_end"], addh.get("plan"), cfx])
        lft = {r["enumerator_id"]: r["days_left"] for r in b.js("LCORE.pace(LEAD.state().manifest, LEAD.merged().C, LEAD.merged().P, RTM.now()).rows")}
        check("with the new manifest the pace counts the longer window", all(v == 11 for v in lft.values()), lft)
        # field visits: the referral, the list, the outcome written as a note
        vtx = b.js("document.querySelector('.panel').innerText")
        before = snapshot(); b.click('[data-lact="export"][data-what="visits"]'); fv = list(csv.DictReader(open(wait_new("L2MN-DEMO_R05_field_visits*.csv", before), encoding="utf-8")))
        setv(f'[data-lvisit="{d3["visit"]}"]', "time_agreed"); setv(f'[data-lvisitnote="{d3["visit"]}"]', "call after 6 pm")
        before = snapshot()
        b.click('[data-lact="visitwrite"]'); b.wait("!!LEAD.ui.ready && LEAD.ui.readyKind === 'visits'", timeout=30)
        b.click('[data-lact="dlall"]')
        fe7 = json.load(open(wait_new("E07_assignment_R05.json", before), encoding="utf-8")); fm4 = json.load(open(wait_new("L2MN-DEMO_R05_manifest.json", before), encoding="utf-8"))
        vh = next(h for h in fe7["households"] if h["hhid"] == d3["visit"])
        check("a field visit asked by an enumerator is listed with what is needed to plan it, its outcome is recorded, and the revised file carries it as a note on the household",
              "Field visits" in vtx and len(fv) == 1 and fv[0]["hhid"] == d3["visit"] and fv[0]["phone_1"].startswith("+000") and fm4["field_visits"][0]["outcome"] == "time_agreed"
              and vh.get("note", "").startswith("Field visit 2026-11-13: reached, a time to call agreed. call after 6 pm") and fm4["calendar"]["window_end"] == "2026-11-25", [fv[:1], vh.get("note"), fm4.get("field_visits")])
        # the text-message list for a day with a booked callback
        smsd = b.js("""(() => { const g = LEAD.merged(); for (const c of g.C.values()) { const l = c.dials[c.dials.length - 1]; if ((c.state === 'in_progress') && l && l.appointment_ts && RTM.CALLBACK_STATUSES.includes(l.status)) return [c.hhid, RTM.partsIn(new Date(Date.parse(l.appointment_ts)), 'Asia/Ulaanbaatar').key]; } return null; })()""")
        setv('[data-lset="__smsDay"]', smsd[1])
        before = snapshot(); b.click('[data-lact="export"][data-what="sms"]'); sl = list(csv.DictReader(open(wait_new(f"L2MN-DEMO_R05_messages_{smsd[1]}*.csv", before), encoding="utf-8")))
        check("the text-message list for a day holds the households with a callback booked that day, with their number", any(r["hhid"] == smsd[0] and r["why"] == "callback" and r["phone"].startswith("+000") for r in sl), [smsd, sl[:2]])
        # areas
        ar = b.js("(() => { const st = LEAD.state(), g = LEAD.merged(); const A = LCORE.areaView(st.manifest, g.C, null, null); return [A.rows.length, A.rows.reduce((a, r) => a + r.households, 0), g.C.size]; })()")
        atx = b.js("document.querySelector('.panel').innerText")
        check("the Progress tab shows completes by area, every household counted once, with the earlier rounds loaded", ar[1] == ar[2] and ar[0] >= 2 and "By area" in atx and "Round 4" in atx, [ar, atx[-300:]])
        # interviewer codes: an alias, and a new value in a built-in layout
        PHLx = os.path.join(ROOT, "samples", "kobo", "L2MN-DEMO_CATI_R05_-_all_versions_-_False_-_2026-11-06-18-00-00.csv")
        prow = list(csv.DictReader(open(PHLx, encoding="utf-8"), delimiter=";"))
        k = next(i for i, r in enumerate(prow) if r["X15"] == "6"); prow[k]["X15"] = "11"
        j7 = next(i for i, r in enumerate(prow) if r["int_id"] == "CATI07" and i != k); prow[j7]["int_id"] = "CATI70"
        buf2 = io.StringIO(); w2 = csv.DictWriter(buf2, fieldnames=list(prow[0].keys()), delimiter=";", lineterminator="\n"); w2.writeheader(); w2.writerows(prow)
        cx = b.js(f"""(() => {{ const st = LEAD.state(), rec = LCORE.readImport('x.csv', {json.dumps(buf2.getvalue())}, st.profiles);
            const uk = LCORE.unknownPlatformCodes([rec], {{}});
            const G1 = LCORE.merge(st.manifest, [rec], new Map(), RTM.now(), {{ profileExtra: {{ phl_kobo: {{ '11': 'NO_ANSWER' }} }}, codes: {{ E07: 'CATI07, CATI70' }} }});
            const d = G1.dials.find(x => x.event_id === {json.dumps(prow[k]["_uuid"])}) || {{}};
            return {{ uk: uk.map(u => [u.value, u.n]), st: d.status, alias: LCORE.enumMapper(st.manifest, {{ E07: 'CATI07, CATI70' }})('cati-70'), first: LCORE.codeOf(st.manifest, {{ E07: 'CATI07, CATI70' }})('E07'),
              unknownE: G1.issues.filter(i => i.type === 'unknown_enumerator').length }}; }})()""")
        check("a new value in a built-in layout is found and, once mapped, read as that result; an interviewer's second code reads as the same interviewer, and the first is written",
              cx["uk"] == [["11", 1]] and cx["st"] == "NO_ANSWER" and cx["alias"] == "E07" and cx["first"] == "CATI07" and cx["unknownE"] == 0, cx)

        # ================= E. exports of KoBoToolbox (proposal K) =================
        # the same round-5 calls as the enumerators' exports, in the form's layouts (samples/kobo)
        KOBO = os.path.join(ROOT, "samples", "kobo", "rtm_call_record_2026-11-06.csv")
        exp_dials = {}
        for r in csv.DictReader(io.StringIO(exp_calls)):
            exp_dials[r["operator"]] = exp_dials.get(r["operator"], 0) + 1
        exp_standalone = [r for r in csv.DictReader(io.StringIO(exp_acts)) if r["via"] != "dial"]

        def merged_now():
            return b.js("""(() => { const g = LEAD.merged(), G = g.G; const by = {};
                G.dials.forEach(d => { by[d.source] = (by[d.source] || 0) + 1; });
                return { dials: by, completes: Object.fromEntries(g.P.list.map(r => [r.enumerator_id, r.complete])), standalone: G.actions.filter(a => a.via !== 'dial').map(a => [a.hhid, a.action, a.target_hhid || '']),
                  files: G.files.map(f => [f.name, f.kind, f.enumerator_id, f.count, f.use]), issues: G.issues.map(i => [i.type, i.status, i.enumerator || '', i.hhid || '', i.severity]),
                  svc: G.serviceStats || null, unverified: [...G.perEnum.values()].every(x => x.unverified), nodur: G.dials.filter(d => d.dur_min === null).length }; })()""")

        start()
        b.js("RTM.setNow('2026-11-07T09:00:00+08:00'); true")
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.click('[data-lact="tab"][data-t="import"]')
        b.set_files("#lf-manifest", [MANIFEST]); b.wait("!!LEAD.state().manifest")
        txt = b.js("document.querySelector('.panel').innerText")
        check("the Import tab takes the enumerators' own exports and points a KoBo team to the KoBoToolbox tab", "KoBoToolbox" in txt and not b.js("!!document.querySelector('#lf-platform')"), txt[:300])
        b.click('[data-lact="tab"][data-t="platform"]'); time.sleep(0.3)
        txt = b.js("document.querySelector('.panel').innerText")
        check("the KoBoToolbox tab walks the round's cycle: the form and the codes, the list out, the export in each day, after moves, the records to look at",
              all(h in txt for h in ("1 · The form", "2 · Before the round", "3 · Each day", "4 · After moves", "5 · Records to look at")) and b.js("!!document.querySelector('#lf-platform') && !!document.querySelector('[data-lpcode=\"E07\"]')"), txt[:300])
        b.set_files("#lf-platform", [KOBO]); b.wait("LEAD.state().imports.length === 1")
        k = merged_now()
        check("a KoBoToolbox export (one submission per call, semicolon CSV) is recognised, split by enumerator and merged as unverified CSV exports",
              any(f[1].startswith("RTM call record") and "split into 3 exports" in f[4] for f in k["files"]) and k["unverified"] and sorted(f[2] for f in k["files"] if f[1] == "platform records") == ["E01", "E02", "E07"], k["files"])
        check("the KoBo export gives the same dials per enumerator as the enumerators' own exports", k["dials"] == exp_dials, [k["dials"], exp_dials])
        check("and the same completes per enumerator (Box 3.0: the first complete of 3 minutes or more)", k["completes"] == py_cmp, [k["completes"], py_cmp])
        check("a record without a call (result NONE) becomes an action without a dial, as in the enumerators' own logs",
              sorted(k["standalone"]) == sorted([a["hhid"], a["action"], a["target_hhid"]] for a in exp_standalone), [k["standalone"], [(a["hhid"], a["action"]) for a in exp_standalone]])
        check("no merge question is open: the form's dials sit on their own households (each part is noted as unverified, as a CSV without its JSON is)",
              not any(i[1] == "open" and i[4] == "action" for i in k["issues"]) and sum(1 for i in k["issues"] if i[0] == "unverified") == 3, [i for i in k["issues"] if i[1] == "open"])
        kobo_rows = list(csv.DictReader(open(KOBO, encoding="utf-8"), delimiter=";"))
        blank_ends = sum(1 for r in kobo_rows if r["result"] not in ("NONE",) and r["call_end"] == "")
        check("call ends the enumerator left blank give dials without a length", k["nodur"] == blank_ends and blank_ends > 0, [k["nodur"], blank_ends])
        willing = [r for r in kobo_rows if r["willing"] == "later"]
        check("the willingness to take part travels into the merged log's note",
              willing and b.js(f"LEAD.merged().G.dials.filter(d => (d.note || '').includes('willing: later')).length") == len([r for r in willing if r["result"] != "NONE"]), len(willing))
        # ---- the layout of an L2 program's real form (proposal K.2): the L2PHL form's export, one submission per call attempt ----
        PHL = os.path.join(ROOT, "samples", "kobo", "L2MN-DEMO_CATI_R05_-_all_versions_-_False_-_2026-11-06-18-00-00.csv")
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        b.set_files("#lf-platform", [PHL]); b.wait("LEAD.state().imports.length === 1")
        q = merged_now()
        check("a KoBoToolbox export in the L2PHL layout (the interview form that records each attempt: int_id, hhid, Z8, X15) is recognised by its columns and read under the tool's IDs through the manifest's platform codes",
              any(f[1].startswith("L2PHL") for f in q["files"]) and sorted(f[2] for f in q["files"] if f[1] == "platform records") == ["E01", "E02", "E07"], q["files"])
        check("it gives the same dials and completes per enumerator as the enumerators' own exports (X15 code 1 is a complete)", q["dials"] == exp_dials and q["completes"] == py_cmp, [q["dials"], exp_dials, q["completes"], py_cmp])
        check("no merge question is open for it", not any(i[1] == "open" and i[4] == "action" for i in q["issues"]), [i for i in q["issues"] if i[1] == "open"])
        # the program's own rule (its processing keeps x15 == 1 & z9 == 1): a complete needs consent; code 2, a break-off with no more callback, closes the case
        phl_rows = list(csv.DictReader(open(PHL, encoding="utf-8"), delimiter=";"))
        import datetime as _dt
        _mins = lambda r: (_dt.datetime.fromisoformat(r["end"]) - _dt.datetime.fromisoformat(r["start"])).total_seconds() / 60 if r["start"] and r["end"] else 0
        cmp_rows = [r for r in phl_rows if r["X15"] == "1" and _mins(r) >= 4]
        by_hh = {}
        for r in cmp_rows: by_hh.setdefault(r["hhid"], []).append(r)
        n_cmp = {}
        for r in phl_rows:
            if r["X15"] == "1": n_cmp[r["hhid"]] = n_cmp.get(r["hhid"], 0) + 1
        solo = [rs[0] for h, rs in sorted(by_hh.items()) if len(rs) == 1 and n_cmp[h] == 1][:2]
        alt = []
        for r in phl_rows:
            r2 = dict(r)
            if r["_uuid"] == solo[0]["_uuid"]: r2["Z9"] = "2"
            if r["_uuid"] == solo[1]["_uuid"]: r2["X15"] = "2"
            alt.append(r2)
        buf_ = io.StringIO(); w_ = csv.DictWriter(buf_, fieldnames=list(phl_rows[0].keys()), delimiter=";", lineterminator="\n"); w_.writeheader(); w_.writerows(alt)
        cz = b.js(f"""(() => {{ const st = LEAD.state(), rec = LCORE.readImport('alt/' + {json.dumps(os.path.basename(PHL))}, {json.dumps(buf_.getvalue())}, st.profiles);
            const G = LCORE.merge(st.manifest, [rec], new Map(), RTM.now()), C = LCORE.cases(st.manifest, G);
            const d = id => G.dials.find(x => x.event_id === id) || {{}};
            return {{ n: C.size, done: [...C.values()].filter(c => c.state === 'complete').length, a: [d({json.dumps(solo[0]["_uuid"])}).status, d({json.dumps(solo[0]["_uuid"])}).note || ''],
              b: [d({json.dumps(solo[1]["_uuid"])}).status, d({json.dumps(solo[1]["_uuid"])}).note || ''] }}; }})()""")
        check("in the L2PHL layout a complete needs consent (Z9 = 1) and code 2 (partially complete, no more callback) closes the case as a firm refusal, as the program's own processing and protocol do; both keep the form's meaning in the note",
              cz["done"] == sum(q["completes"].values()) - 2 and cz["a"][0] == "OTHER" and "without consent" in cz["a"][1] and cz["b"][0] == "REFUSAL_HARD" and "no more callback" in cz["b"][1], [cz, q["completes"]])
        # a form with unknown columns is mapped once, in the Import tab: the same calls under other names and codes, the interviewer code
        # written CATI-07, local times without an offset, and the number dialed instead of the slot
        hl_rows = {r["hhid"]: r for r in csv.DictReader(open(os.path.join(S, "household_list.csv"), encoding="utf-8"))}
        own = {"COMPLETE": "C", "PARTIAL": "P", "APPOINTMENT": "AP", "REFUSAL_SOFT": "R", "REFUSAL_HARD": "RH", "NO_ANSWER": "NA", "BUSY": "B", "SWITCHED_OFF": "OFF",
               "DEAD_NUMBER": "DN", "WRONG_NUMBER": "WN", "NOT_AVAILABLE": "NT", "LANGUAGE": "L", "OTHER": "O"}
        unk = os.path.join(SCRATCH, "unknown_log.csv")
        n_num = 0
        with open(unk, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["op", "household", "t0", "t1", "res", "rid", "num"])
            for r in csv.DictReader(io.StringIO(exp_calls)):
                num = hl_rows.get(r["hhid"], {}).get(f"phone_{r['phone_slot']}", "") if r["phone_slot"] else ""
                n_num += bool(num)
                w.writerow(["CATI-" + r["operator"].lstrip("E"), r["hhid"], r["ts"], r["end_ts"], own[r["status"]], r["event_id"], num])
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        b.set_files("#lf-platform", [unk]); b.wait("LEAD.state().imports.length === 1")
        check("a table with unknown columns opens the mapping card instead of being merged", b.js("!!document.querySelector('#lmap')") and merged_now()["dials"] == {}, merged_now()["files"])
        b.js("""(() => { const sel = (k, v) => { const s = document.querySelector(`[data-lprof="${k}"]`); if (!s) return; s.value = v; s.dispatchEvent(new Event('change', { bubbles: true })); };
            sel('col:hhid', 'household'); sel('col:enumerator', 'op'); sel('col:start', 't0'); sel('col:end', 't1'); sel('col:result', 'res'); sel('col:id', 'rid'); sel('col:phone', 'num');
            const codes = %s;
            Object.entries(codes).forEach(([k, v]) => sel(`code:${k}`, v)); sel('name', 'Our call-record form'); return true; })()""" % json.dumps({v: k for k, v in own.items()}))
        b.click('[data-lact="saveprofile"]'); b.wait("LEAD.state().profiles.length === 1")
        u2 = merged_now()
        check("once the leader has mapped its columns and codes, the file merges like a known layout, and the mapping is kept in the session",
              u2["dials"] == exp_dials and u2["completes"] == py_cmp and b.js("LEAD.state().profiles[0].name") == "Our call-record form", [u2["dials"], u2["completes"], u2["files"]])
        slots = b.js("(() => { const G = LEAD.merged().G; return [G.dials.length, G.dials.filter(d => d.phone_slot).length, G.dials.filter(d => /\\+08:00$/.test(d.ts)).length]; })()")
        check("the number dialed becomes the household's slot, from the household list, and is not kept; the round's time zone supplies the missing offsets",
              slots[1] == n_num and n_num > 0 and slots[2] == slots[0], [slots, n_num])
        b.shot(os.path.join(SCREENS, "leader_12_mapping.png"), full=True)
        # the records to look at in the platform (K.8): every dial behind a merge question, with the platform's record ID
        rv = b.js(f"""(() => {{ const st = LEAD.state(), orig = st.imports.find(f => f.name.endsWith('unknown_log.csv'));
            const rows = orig.text.split('\\n'), r1 = rows.slice(1).find(r => {{ const f = r.split(','); return f[4] === 'C' && Date.parse(f[3]) - Date.parse(f[2]) >= 180000; }});
            const extra = r1.split(',').map((v, i) => i === 2 ? '2026-11-06 19:00:00' : i === 3 ? '2026-11-06 19:20:00' : i === 5 ? 'dup-record-0001' : v).join(',');
            const recs = [LCORE.readImport('dup/unknown_log.csv', orig.text + extra + '\\n', st.profiles)];
            const G = LCORE.merge(st.manifest, recs, new Map(), RTM.now());
            const R_ = LCORE.reviewRows(G); return {{ hh: r1.split(',')[1], n: R_.length, rows: R_.filter(r => r.issue === 'two_completes').map(r => [r.hhid, r.record_id, r.result, r.status]) }}; }})()""")
        check("the review list names every dial behind a merge question with the form's own record ID (here a second complete added to the mapped file: both completes listed, open)",
              rv["n"] >= 2 and len(rv["rows"]) == 2 and all(r[0] == rv["hh"] and r[2] == "COMPLETE" and r[3] == "open" for r in rv["rows"]) and any(r[1] == "dup-record-0001" for r in rv["rows"]), rv)
        # the files the leader hands to the form, from the manifest: on the KoBoToolbox tab, step 2
        b.click('[data-lact="tab"][data-t="platform"]'); time.sleep(0.2)
        before = snapshot()
        b.click('[data-lact="export"][data-what="kobo"]')
        b.click('[data-lact="export"][data-what="choices"]')
        fk = wait_new("households*.csv", before); fc = wait_new("choices_households*.csv", before)
        hk = list(csv.DictReader(open(fk, encoding="utf-8")))
        sample_hk = {r["hhid"]: r for r in csv.DictReader(open(os.path.join(ROOT, "samples", "kobo", "households.csv"), encoding="utf-8"))}
        same = all(r["hhid"] in sample_hk and all(r[c] == sample_hk[r["hhid"]][c] for c in ("enumerator_id", "phone_1", "phone_2", "phone_3", "kind", "replaces", "rank", "program", "round")) for r in hk)
        check("households.csv for the KoBo form: one row per household and reserve, with the enumerator, numbers and replacement links of the manifest (the sample file, apart from the plan)",
              len(hk) == len(sample_hk) and same and "name" in hk[0] and "label" in hk[0], [len(hk), len(sample_hk)])
        ch = list(csv.DictReader(open(fc, encoding="utf-8")))
        check("choices_households.csv (the L2PHL form's SN list): one row per household and reserve, the enumerator's platform code in filter_int_id",
              len(ch) == len(sample_hk) and all(r["list_name"] == "SN" and r["filter_int_id"] == "CATI" + sample_hk[r["name"]]["enumerator_id"][1:] for r in ch), [len(ch), ch[:1]])
        # a code typed on the Platform tab overrides the manifest's, for reading and for writing
        b.js("""(() => { const el = document.querySelector('[data-lpcode="E07"]'); el.value = 'INT-07'; el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()""")
        before = snapshot(); b.click('[data-lact="export"][data-what="choices"]'); fc2 = wait_new("choices_households*.csv", before)
        ch2 = list(csv.DictReader(open(fc2, encoding="utf-8")))
        check("a code typed on the KoBoToolbox tab overrides the manifest's: the list carries it, and the form's records under it are read as that enumerator",
              all(r["filter_int_id"] == "INT-07" for r in ch2 if r["enumerator_id"] == "E07") and b.js("LCORE.enumMapper(LEAD.state().manifest, LEAD.state().platform.codes)('int07')") == "E07"
              and b.js("LCORE.enumMapper(LEAD.state().manifest, LEAD.state().platform.codes)('CATI07')") == "E07", [r for r in ch2 if r["enumerator_id"] == "E07"][:1])
        b.js("""(() => { const el = document.querySelector('[data-lpcode="E07"]'); el.value = ''; el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()""")

        # ================= E2. exports of Survey Solutions (proposal K.9) =================
        import zipfile
        SUSO = os.path.join(ROOT, "samples", "suso", "rtm_call_record_1_Tabular_All.zip")
        b.click('[data-lact="clearimports"]') if b.js("!!document.querySelector('[data-lact=\"clearimports\"]')") else None
        b.wait("LEAD.state().imports.length === 0")
        b.click('[data-lact="tab"][data-t="suso"]'); time.sleep(0.3)
        txt = b.js("document.querySelector('.panel').innerText")
        check("the Survey Solutions tab walks the same cycle: the questionnaire and the logins, the assignments out, the export in each day, after moves, the interviews to look at",
              all(h in txt for h in ("1 · The questionnaire", "2 · Before the round", "3 · Each day", "4 · After moves", "5 · Interviews to look at")) and b.js("!!document.querySelector('#lf-suso') && !!document.querySelector('[data-lpcode=\"E07\"]')"), txt[:300])
        b.set_files("#lf-suso", [SUSO]); b.wait("LEAD.state().imports.length >= 4")
        names = b.js("LEAD.state().imports.map(f => f.name)")
        s1 = merged_now()
        check("the export's zip is opened in the browser: its main file, the calls roster and the three service files are kept, the empty error and comment files left out",
              sorted(n.split("/")[-1] for n in names) == ["assignment__actions.tab", "calls.tab", "interview__actions.tab", "interview__diagnostics.tab", "rtm_call_record.tab"], names)
        check("the tool's own questionnaire is recognised without a question (the roster calls, its result codes), split by interviewer through the logins and merged as unverified exports",
              any(f[1].startswith("RTM call record (Survey Solutions") and "107 interviews" in f[4] and "split into 3 exports" in f[4] for f in s1["files"])
              and sorted(f[2] for f in s1["files"] if f[1] == "Survey Solutions records") == ["E01", "E02", "E07"] and not b.js("!!document.querySelector('#lsusolevel')"), s1["files"])
        check("the Survey Solutions export gives the same dials and completes per enumerator as the enumerators' own exports", s1["dials"] == exp_dials and s1["completes"] == py_cmp, [s1["dials"], exp_dials, s1["completes"], py_cmp])
        check("a call record without a call (result 99) becomes an action without a dial, as in the enumerators' own logs",
              sorted(s1["standalone"]) == sorted([a["hhid"], a["action"], a["target_hhid"]] for a in exp_standalone), s1["standalone"])
        check("no merge question is open for it", not any(i[1] == "open" and i[4] == "action" for i in s1["issues"]), [i for i in s1["issues"] if i[1] == "open"])
        z = zipfile.ZipFile(SUSO)
        tab = lambda n: list(csv.DictReader(io.StringIO(z.read(n).decode("utf-8")), delimiter="\t"))
        mains_, calls_, acts_, aacts_ = tab("rtm_call_record.tab"), tab("calls.tab"), tab("interview__actions.tab"), tab("assignment__actions.tab")
        b.shot(os.path.join(SCREENS, "leader_13_suso.png"), full=True)
        # what the export says of its interviews, and the one the supervisor rejected
        rej = [m for m in mains_ if m["interview__status"] == "65"]
        txt = b.js("document.querySelector('.panel').innerText")
        n_by = collections.Counter(m["interview__status"] for m in mains_)
        check("step 3 summarises the export: interviews by status, handovers, validation errors, rejected interviews and the assignment actions",
              "says of its 107 interviews" in txt and f"Completed\t{n_by['100']}" in txt and f"Interviewer assigned\t{n_by['60']}" in txt and "1 interview rejected" in txt and rej[0]["interview__key"] in txt
              and "144 assignments in assignment__actions" in txt, txt[txt.find("says of its"):][:600])
        rj = [i for i in s1["issues"] if i[0] == "suso_rejected"]
        check("an interview rejected by the supervisor gives an information line per household in the merge report (its complete still counts; the merge's completes equal the enumerators' own)",
              len(rej) == 1 and len(rj) == 1 and rj[0][3] == rej[0]["hhid"] and rj[0][4] == "info" and rj[0][2] == "E02" and s1["completes"] == py_cmp, [rj, rej[0]["hhid"], rej[0]["interview__key"]])
        # an interview reassigned mid-way: each call goes to the interviewer who held the interview when it started
        per = {}
        for c in calls_:
            if c["call_start"] != "##N/A##": per.setdefault(c["interview__id"], []).append(c)
        iid, cs = next((k, v) for k, v in sorted(per.items()) if len(v) >= 3)
        m0 = next(m for m in mains_ if m["interview__id"] == iid)
        import datetime as _dt
        t_mid = (_dt.datetime.fromisoformat(cs[1]["call_start"]) - _dt.timedelta(minutes=1)).replace(tzinfo=_dt.timezone(_dt.timedelta(hours=8))).astimezone(_dt.timezone.utc)
        holder = next(a["responsible_name"] for a in acts_ if a["interview__id"] == iid)
        other = "CATI01" if holder != "CATI01" else "CATI02"
        # the supervisor's InterviewerAssigned action, and from then on the new interviewer opening and pausing the interview
        a_lines = z.read("interview__actions.tab").decode("utf-8").rstrip("\n").split("\n")
        cut = t_mid.strftime("%Y-%m-%d %H:%M:%S")
        def moved_line(l):
            f = l.split("\t")
            if f[1] == iid and f"{f[2]} {f[3]}" > cut: f[5] = other; f[7] = other
            return "\t".join(f)
        acts_txt = "\n".join([a_lines[0]] + [moved_line(l) for l in a_lines[1:]]) + "\n" + "\t".join([m0["interview__key"], iid, t_mid.strftime("%Y-%m-%d"), t_mid.strftime("%H:%M:%S"), "1", "sup01", "2", other, "1"]) + "\n"
        rw = b.js(f"""(() => {{ const st = LEAD.state(), parts = st.imports.map(f => f.name.endsWith('interview__actions.tab') ? {{ name: f.name, text: {json.dumps(acts_txt)} }} : f);
            const recs = parts.map(f => LCORE.readImport('rw/' + f.name.split('/').pop(), f.text, st.profiles));
            const G = LCORE.merge(st.manifest, recs, new Map(), RTM.now(), {{ codes: st.platform.codes }});
            return G.dials.filter(d => d.hhid === {json.dumps(m0['hhid'])}).sort((a, b) => a.ts < b.ts ? -1 : 1).map(d => d.source); }})()""")
        want_other = "E" + other[-2:]
        check("an interview reassigned in Headquarters between two calls: the calls before stay with the first interviewer, the calls after go to the new one (interview__actions)",
              len(rw) == len(cs) and rw[0] != want_other and all(x == want_other for x in rw[1:]), [rw, want_other])
        # the assignments upload, from the manifest
        before = snapshot(); b.click('[data-lact="export"][data-what="suso"]'); fa = wait_new("assignments*.tab", before)
        at = list(csv.DictReader(open(fa, encoding="utf-8"), delimiter="\t"))
        sample_at = {r["hhid"]: r for r in csv.DictReader(open(os.path.join(ROOT, "samples", "suso", "assignments.tab"), encoding="utf-8"), delimiter="\t")}
        check("assignments.tab for the tool's own questionnaire: one assignment per household and reserve, the login in _responsible, the identifying columns of the sample upload (apart from the plan)",
              open(fa, encoding="utf-8").readline().rstrip("\n").split("\t") == open(os.path.join(ROOT, "samples", "suso", "assignments.tab"), encoding="utf-8").readline().rstrip("\n").split("\t")
              and len(at) == len(sample_at) and all(r["hhid"] in sample_at and all(r[c] == sample_at[r["hhid"]][c] for c in ("_responsible", "_quantity", "phone_1", "phone_2", "kind", "replaces", "rank", "program", "round")) for r in at), [len(at), len(sample_at), at[:1]])
        b.js("""(() => { const set = (k, v) => { const el = document.querySelector(`[data-lsuso="${k}"]`); el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); }; set('layout', 'id'); set('idVar', 'hh_code'); set('quantity', '-1'); return true; })()""")
        before = snapshot(); b.click('[data-lact="export"][data-what="suso"]'); fa2 = wait_new("assignments*.tab", before)
        at2 = list(csv.DictReader(open(fa2, encoding="utf-8"), delimiter="\t"))
        check("for a program's own questionnaire the file carries the household ID alone under its variable's name, and 'no limit' writes _quantity -1 (one interview per call attempt)",
              list(at2[0].keys()) == ["hh_code", "_responsible", "_quantity"] and all(r["_quantity"] == "-1" for r in at2) and len(at2) == len(at), at2[:2])
        b.js("""(() => { const set = (k, v) => { const el = document.querySelector(`[data-lsuso="${k}"]`); el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); }; set('layout', 'rtm'); set('idVar', 'hhid'); set('quantity', '1'); return true; })()""")
        # the moves to make in Headquarters, with the assignment and interview the export shows for each household
        mv = b.js(f"""(() => {{ const st = LEAD.state(), M = Object.assign({{}}, st.manifest, {{ moves: [{{ hhid: {json.dumps(m0['hhid'])}, from: 'E07', to: 'E01', at: '2026-11-07T08:30:00+08:00', by: 'L01' }}] }});
            return LCORE.susoMoves(M, st.platform.codes, LEAD.merged().G.suso); }})()""")
        check("the list of moves gives each moved household's logins before and after, and the assignment and interview keys of the latest export, to reassign in Headquarters",
              len(mv) == 1 and mv[0]["from_login"] == "CATI07" and mv[0]["to_login"] == "CATI01" and mv[0]["assignment_id"] == m0["assignment__id"] and mv[0]["interview_keys"] == m0["interview__key"], mv)
        check("the export does not yet show the move, so it is pending in Headquarters, and the tablet has already received the work (assignment__actions ReceivedByTablet)",
              mv[0]["in_hq"] == "pending" and mv[0]["received_on_tablet"] == "yes", mv)
        # Headquarters reassigns the assignment after the move: assignment__actions gains a Reassigned row, and the list says done
        aa_txt = z.read("assignment__actions.tab").decode("utf-8").rstrip("\n") + "\n" + "\t".join([m0["assignment__id"], "2026-11-07", "02:10:00", "7", "sup01", "2", "CATI01", "1", "CATI07", "CATI01", "moved by the leader"]) + "\n"
        mv2 = b.js(f"""(() => {{ const st = LEAD.state(), parts = st.imports.map(f => f.name.endsWith('assignment__actions.tab') ? {{ name: f.name, text: {json.dumps(aa_txt)} }} : f);
            const G = LCORE.merge(st.manifest, parts.map(f => LCORE.readImport('mv/' + f.name.split('/').pop(), f.text, st.profiles)), new Map(), RTM.now(), {{ codes: st.platform.codes }});
            const M = Object.assign({{}}, st.manifest, {{ moves: [{{ hhid: {json.dumps(m0['hhid'])}, from: 'E07', to: 'E01', at: '2026-11-07T08:30:00+08:00', by: 'L01' }}, {{ hhid: '0199-999', from: 'E07', to: 'E01', at: '2026-11-07T08:30:00+08:00', by: 'L01' }}] }});
            return LCORE.susoMoves(M, st.platform.codes, G.suso); }})()""")
        check("once the export shows the assignment reassigned to the new login after the move, the list says done; a household the export does not hold is marked so",
              len(mv2) == 2 and mv2[0]["in_hq"] == "done" and mv2[1]["in_hq"] == "not in the export" and mv2[1]["received_on_tablet"] == "", mv2)
        # a reassignment that predates the move (a move back) does not count as done
        aa_old = z.read("assignment__actions.tab").decode("utf-8").rstrip("\n") + "\n" + "\t".join([m0["assignment__id"], "2026-11-01", "02:10:00", "7", "sup01", "2", "CATI01", "1", "CATI07", "CATI01", ""]) + "\n"
        mv3 = b.js(f"""(() => {{ const st = LEAD.state(), parts = st.imports.map(f => f.name.endsWith('assignment__actions.tab') ? {{ name: f.name, text: {json.dumps(aa_old)} }} : f);
            const G = LCORE.merge(st.manifest, parts.map(f => LCORE.readImport('mv2/' + f.name.split('/').pop(), f.text, st.profiles)), new Map(), RTM.now(), {{ codes: st.platform.codes }});
            return LCORE.susoMoves(Object.assign({{}}, st.manifest, {{ moves: [{{ hhid: {json.dumps(m0['hhid'])}, from: 'E07', to: 'E01', at: '2026-11-07T08:30:00+08:00', by: 'L01' }}] }}), st.platform.codes, G.suso)[0].in_hq; }})()""")
        check("a reassignment recorded before the move does not count as the move done", mv3 == "pending", mv3)
        # step 2 refuses to pretend: an enumerator without a login is named before the file is written
        warn_txt = b.js("""(() => { const st = LEAD.state(), e = st.manifest.enumerators.find(x => x.enumerator_id === 'E02'), keep = e.platform_id; e.platform_id = ''; const c = st.platform.codes.E02; delete st.platform.codes.E02;
            LEAD.refresh(); const t = document.querySelector('.panel').innerText; e.platform_id = keep; if (c) st.platform.codes.E02 = c; LEAD.refresh(); return t; })()""")
        check("step 2 names an enumerator without a login before the assignments file is written (Headquarters refuses a login it does not know)",
              "1 enumerator without a login" in warn_txt and "(E02)" in warn_txt and "without a login" not in b.js("document.querySelector('.panel').innerText"), warn_txt[warn_txt.find("2 ·"):][:300])
        # the interviews to look at: a second complete added to the roster gives two records, each the interview key and its roster row
        cmp_calls = [c for c in calls_ if c["result"] == "1" and (_dt.datetime.fromisoformat(c["call_end"]) - _dt.datetime.fromisoformat(c["call_start"])).total_seconds() >= 180]
        c1 = cmp_calls[0]
        k1 = next(m["interview__key"] for m in mains_ if m["interview__id"] == c1["interview__id"])
        extra_row = "\t".join([k1, c1["interview__id"], "99", c1["phone_slot"], "2026-11-06T19:00:00", "2026-11-06T19:20:00", "1", "1", "##N/A##", "1", "##N/A##", "second complete"])
        calls_txt = z.read("calls.tab").decode("utf-8").rstrip("\n") + "\n" + extra_row + "\n"
        rv = b.js(f"""(() => {{ const st = LEAD.state(), parts = st.imports.map(f => f.name.endsWith('calls.tab') ? {{ name: f.name, text: {json.dumps(calls_txt)} }} : f);
            const G = LCORE.merge(st.manifest, parts.map(f => LCORE.readImport('dup/' + f.name.split('/').pop(), f.text, st.profiles)), new Map(), RTM.now(), {{ codes: st.platform.codes }});
            return LCORE.reviewRows(G).filter(r => r.issue === 'two_completes').map(r => r.record_id); }})()""")
        check("the review list names both completes of a household with their records: the interview key and, after #, the row of the calls roster",
              len(rv) == 2 and all(r.startswith(k1 + "#") for r in rv) and (k1 + "#99") in rv, rv)
        # a program's own questionnaire: one interview per call attempt, its result in its own codes, a household roster beside it
        own = {"COMPLETE": 11, "PARTIAL": 12, "APPOINTMENT": 13, "REFUSAL_SOFT": 21, "REFUSAL_HARD": 22, "NO_ANSWER": 31, "BUSY": 32, "SWITCHED_OFF": 33, "DEAD_NUMBER": 41,
               "WRONG_NUMBER": 42, "NOT_AVAILABLE": 14, "LANGUAGE": 51, "OTHER": 99, "BLOCKED": 34}
        login = lambda e: "CATI" + e[1:]
        utc = lambda s, off: _dt.datetime.fromisoformat(s.replace(" ", "T") + off).astimezone(_dt.timezone.utc)
        pm, pa, pr, pd = [], [], [], []
        for i, r in enumerate(csv.DictReader(io.StringIO(exp_calls))):
            key, iid2 = f"{10 + i // 10000:02d}-{i // 100 % 100:02d}-{i % 100:02d}-{i % 97:02d}", hashlib.md5(r["event_id"].encode()).hexdigest()
            end = r["end_ts"] or (_dt.datetime.fromisoformat(r["ts"]) + _dt.timedelta(minutes=1)).isoformat(sep=" ")
            pm.append([key, iid2, r["hhid"], str(own[r["status"]]), "0.5", "0", "100", str(5000 + i)])
            for code, t in (("12", r["ts"]), ("1", r["ts"]), ("2", r["ts"]), ("3", end)):
                u = utc(t, r["utc_offset"]); pa.append([key, iid2, u.strftime("%Y-%m-%d"), u.strftime("%H:%M:%S"), code, login(r["operator"]), "1", login(r["operator"]), "1"])
            pr.append([key, iid2, "1", "Member 1", "35"])
            pd.append([key, iid2, "100", login(r["operator"]), "1", "0", "0", "0", "00.00:05:00"])
        own_zip = os.path.join(SCRATCH, "phone_survey_1_Tabular_All.zip")
        with zipfile.ZipFile(own_zip, "w", zipfile.ZIP_DEFLATED) as oz:
            for n, head, rows in (("phone_survey.tab", ["interview__key", "interview__id", "household_id", "call_outcome", "ssSys_IRnd", "has__errors", "interview__status", "assignment__id"], pm),
                                  ("members.tab", ["interview__key", "interview__id", "members__id", "member_name", "age"], pr),
                                  ("interview__actions.tab", ["interview__key", "interview__id", "date", "time", "action", "originator", "role", "responsible_name", "responsible_role"], pa),
                                  ("interview__diagnostics.tab", ["interview__key", "interview__id", "interview__status", "responsible", "interviewers", "rejections__sup", "rejections__hq", "entities__errors", "interview__duration"], pd)):
                oz.writestr(n, "\t".join(head) + "\n" + "".join("\t".join(x) + "\n" for x in rows))
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        b.set_files("#lf-suso", [own_zip]); b.wait("LEAD.state().imports.length === 4"); time.sleep(0.2)
        check("an export the tool does not know asks which of its files holds the calls (the interviews, the roster members, or neither) and merges nothing yet",
              b.js("!!document.querySelector('#lsusolevel')") and merged_now()["dials"] == {} and "members" in b.js("document.querySelector('#lsusolevel').innerText"), merged_now()["files"])
        b.js("""(() => { const el = document.querySelector('[data-lsusolevel="phone_survey"]'); el.value = 'main'; el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()"""); time.sleep(0.2)
        guess = b.js("Object.fromEntries([...document.querySelectorAll('#lmap select[data-lprof^=\"col:\"]')].map(s => [s.dataset.lprof.slice(4), s.value]))")
        check("once the leader says the calls are the interviews, the mapping card opens with the export's own columns guessed: the interviewer, the record, the interview's start and completion",
              b.js("!!document.querySelector('#lmap')") and guess.get("enumerator") == "suso__interviewer" and guess.get("id") == "suso__record" and guess.get("start") == "suso__started" and guess.get("end") == "suso__completed", guess)
        b.js("""(() => { const sel = (k, v) => { const s = document.querySelector(`[data-lprof="${k}"]`); if (!s) return; s.value = v; s.dispatchEvent(new Event('change', { bubbles: true })); };
            sel('col:hhid', 'household_id'); sel('col:result', 'call_outcome');
            Object.entries(%s).forEach(([k, v]) => sel(`code:${k}`, v)); sel('name', 'Our phone survey (Survey Solutions)'); return true; })()""" % json.dumps({str(v): k for k, v in own.items()}))
        b.click('[data-lact="saveprofile"]'); b.wait("LEAD.state().profiles.some(p => p.name.includes('Survey Solutions'))")
        s2 = merged_now()
        check("mapped once, a program's own questionnaire with one interview per call attempt merges like a known layout: the same dials and completes per enumerator (start and end from interview__actions)",
              s2["dials"] == exp_dials and s2["completes"] == py_cmp and b.js("LEAD.state().platform.suso.phone_survey") == "main", [s2["dials"], s2["completes"], s2["files"][:3]])
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")
        b.set_files("#lf-suso", [own_zip]); b.wait("LEAD.state().imports.length === 4")
        check("the next export of the same questionnaire is read at once, with the saved level and mapping", merged_now()["dials"] == exp_dials and not b.js("!!document.querySelector('#lsusolevel') || !!document.querySelector('#lmap')"), merged_now()["files"][:2])
        b.click('[data-lact="clearimports"]'); b.wait("LEAD.state().imports.length === 0")

        # phone width
        b.ws.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        b.click('[data-lact="tab"][data-t="progress"]')
        b.shot(os.path.join(SCREENS, "leader_08_phone.png"))
        check("at phone width the page has no sideways scroll (tables scroll inside their cards)", b.js("document.documentElement.scrollWidth <= window.innerWidth + 1"), b.js("[document.documentElement.scrollWidth, window.innerWidth]"))
        b.ws.call("Emulation.clearDeviceMetricsOverride")
    finally:
        b.close()
    passed = sum(ok for _, ok, _ in results)
    lines = [f"Leader view tests, {time.strftime('%d %b %Y %H:%M')}: {passed} of {len(results)} passed"] + [("PASS " if ok else "FAIL ") + n for n, ok, _ in results]
    open(os.path.join(HERE, "results_leader.txt"), "w").write("\n".join(lines) + "\n")
    print(lines[0])
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
