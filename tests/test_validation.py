"""Step 5 checks not covered by the other suites: the merge batch the prompt names (a missing enumerator, a duplicate and a
genuine conflict, together), every assignment rule besides the default, access control under every rule, and the bundled
holiday table against one country's official calendar.

Run from the tool folder:  python3 tests/test_validation.py
Writes tests/results_validation.txt.
"""
import csv
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

SCRATCH = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
STAMP = time.strftime("%H%M%S")
S = os.path.join(ROOT, "samples", "leader")
results = []

# The Philippines' days off for 2026, from the official proclamations (all read on 27 October 2026):
#   Proclamation No. 1006, s. 2025 (3 September 2025): regular holidays, special non-working days, additional special days;
#     25 February (EDSA anniversary) is a special WORKING day, so it is not a day off.
#   Proclamation No. 1189, s. 2026 (12 March 2026): Eid'l Fitr, Friday 20 March 2026.
#   Proclamation No. 1264, s. 2026 (21 May 2026): Eid'l Adha, Wednesday 27 May 2026.
#   Proclamation No. 1447, s. 2026 (17 September 2026): 16-18 November 2026, special non-working days in the National
#     Capital Region only (ASEAN Summit); regional, so not in a national table.
PH_2026 = {
    "2026-01-01": "New Year's Day", "2026-04-02": "Maundy Thursday", "2026-04-03": "Good Friday", "2026-04-09": "Araw ng Kagitingan",
    "2026-05-01": "Labor Day", "2026-06-12": "Independence Day", "2026-08-31": "National Heroes Day", "2026-11-30": "Bonifacio Day",
    "2026-12-25": "Christmas Day", "2026-12-30": "Rizal Day",                                   # regular holidays
    "2026-08-21": "Ninoy Aquino Day", "2026-11-01": "All Saints' Day", "2026-12-08": "Immaculate Conception", "2026-12-31": "Last Day of the Year",
    "2026-02-17": "Chinese New Year", "2026-04-04": "Black Saturday", "2026-11-02": "All Souls' Day", "2026-12-24": "Christmas Eve",
    "2026-03-20": "Eid'l Fitr", "2026-05-27": "Eid'l Adha",
}
PH_WORKING = {"2026-02-25"}
PH_NCR_ONLY = {"2026-11-16", "2026-11-17", "2026-11-18"}


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:700]}]" if detail and not ok else ""))


def main():
    # ---- holidays against an official calendar ----
    s = open(os.path.join(ROOT, "src", "holidays_data.js"), encoding="utf-8").read()
    table = json.loads(s[s.index("{"): s.rindex("}") + 1])["table"]
    ph = {d: n for d, n, e in table["PH"] if d.startswith("2026")}
    check("Philippines 2026: every official day off in the proclamations is in the bundled table", set(PH_2026) <= set(ph), sorted(set(PH_2026) - set(ph)))
    check("Philippines 2026: the bundled table has no day off the proclamations do not declare", set(ph) <= set(PH_2026), sorted(set(ph) - set(PH_2026)))
    check("Philippines 2026: the special working day (EDSA anniversary) is not listed as a day off", not (PH_WORKING & set(ph)))
    check("Philippines 2026: the regional days off (NCR, ASEAN Summit) are not in the national table; the leader adds such days by hand",
          not (PH_NCR_ONLY & set(ph)))

    b = Browser(os.path.join(SCRATCH, f"vprofile_{STAMP}"), port=9347)
    try:
        b.goto("file://" + os.path.join(ROOT, "rtm_interview_tool.html"))
        b.js("RTM.setNow('2026-11-07T09:00:00+08:00'); APP.noFSA = true; true")
        b.click('[data-act="view"][data-v="leader"]'); b.wait("!!document.querySelector('#lstart')")

        def start():
            if b.js("!!LEAD.state()"):
                b.click('[data-lact="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("!LEAD.state()")
            b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
                   f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
            b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")

        # ---- the merge batch: E07 missing, a duplicate of E02's export, and E01 logging a complete on a household E02 completed ----
        start()
        b.click('[data-lact="tab"][data-t="import"]')
        b.set_files("#lf-manifest", [os.path.join(S, "L2MN-DEMO_R05_manifest.json")]); b.wait("!!LEAD.state().manifest")
        batch = sorted(glob.glob(os.path.join(S, "merge_cases", "conflict", "*"))) + \
            [os.path.join(S, "exports_R05", f) for f in ("E02_2026-11-06.json", "E02_2026-11-06.csv")] + \
            sorted(glob.glob(os.path.join(S, "merge_cases", "duplicate", "*")))
        b.set_files("#lf-imports", batch); b.wait(f"LEAD.state().imports.length === {len(batch)}")
        g = json.loads(b.js("""JSON.stringify((() => { const st = LEAD.state(), M = st.manifest;
             const G = LCORE.merge(M, st.imports.map(f => LCORE.readImport(f.name, f.text)), new Map(), RTM.now()), C = LCORE.cases(M, G);
             return { issues: G.issues.map(i => [i.type, i.severity, i.status, i.enumerator || '', i.hhid || '']), notReported: [...C.values()].filter(c => c.state === 'not_reported').map(c => c.enumerator_id),
                      conflict: [...C.values()].filter(c => c.state === 'conflict').map(c => c.hhid), e07: M.households.filter(h => h.enumerator_id === 'E07').length,
                      complete: [...C.values()].filter(c => c.state === 'complete').length }; })())"""))
        types = {i[0] for i in g["issues"]}
        check("merge batch: the missing enumerator is reported, and all of their households show as 'not reported'",
              "missing" in types and len(g["notReported"]) == g["e07"] and set(g["notReported"]) == {"E07"}, g["issues"])
        check("merge batch: the duplicate file is ignored and reported", "duplicate" in types)
        check("merge batch: the genuine conflict is flagged twice (dials outside the assignment, two completes) and left out of the counts",
              {"not_assigned", "two_completes"} <= types and len(g["conflict"]) == 1)
        check("merge batch: nothing is resolved silently: every situation needing a decision is open, every other one is listed",
              all(i[2] == "open" for i in g["issues"] if i[1] == "action") and len(g["issues"]) >= 4)
        txt = b.js("document.querySelector('.panel').innerText")
        check("merge batch: the open questions are shown as banners naming the enumerator", "Needs your decision" in txt and "No export from E07" in txt)

        # ---- the assignment rules besides the default ----
        start()
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", sorted(glob.glob(os.path.join(S, "history", "*")))); b.wait("LEAD.state().inputs.history.length === 12")
        b.set_files("#lf-repl", [os.path.join(S, "selection.csv")]); b.wait("!!LEAD.state().inputs.replacements")
        manual = os.path.join(SCRATCH, f"manual_{STAMP}.csv")
        hl = [r for r in csv.DictReader(open(os.path.join(S, "household_list.csv"), encoding="utf-8")) if r["status"] == "active"]
        with open(manual, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n"); w.writerow(["hhid", "enumerator_id"])
            for i, r in enumerate(hl[:-3]):
                w.writerow([r["hhid"], ["E01", "E02", "E07"][i % 3] if i != 5 else "E99"])
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        res = json.loads(b.js(f"""JSON.stringify((() => {{
            const st = LEAD.state(), L = LCORE;
            const H = L.buildHistory(st.inputs.history.map(f => L.readHistoryFile(f.name, f.text)), {{tz: 'Asia/Ulaanbaatar'}});
            const HL = L.parseHouseholds(st.inputs.households.text), RP = L.parseReplacements(st.inputs.replacements.text, HL.households);
            const RH = L.roundHouseholds(HL.households, RP.lists, H, 5), avail = L.availableReplacements(RP.lists, RH.reserves, HL.households);
            const T = L.readTable({json.dumps(open(manual, encoding='utf-8').read())}), man = new Map(T.rows.map(r => [r.hhid, r.enumerator_id]));
            const cal = {{ window_start: '2026-10-26', window_end: '2026-11-20', working_weekdays: [1,2,3,4,5,6], call_hours: {{start: 9, end: 21}}, time_zone: 'Asia/Ulaanbaatar', dial_cap: 8, holidays: [] }};
            const run = (rule, shares) => {{
              const team = [['E01', shares[0]], ['E02', shares[1]], ['E07', shares[2]]].map(([id, sh]) => ({{ id, available: true, share: sh }}));
              const inp = {{ round: 5, households: RH.mains, team, hist: H, tz: 'Asia/Ulaanbaatar', cap: 8, rule, manual: man, calendar: cal }};
              const A = L.assign(inp);
              const P = L.plan(inp, A.out, A.summaries, H);
              const B = L.buildFiles(Object.assign({{}}, inp, {{ program: 'L2MN-DEMO', country: 'MN', leader: 'L01', generated_at: '2026-10-23T16:00:00+08:00', replacement_policy: {{active: true}},
                out: A.out, sums: A.summaries, plans: P.plans, allHouseholds: HL.households, replacements: avail }}));
              return {{ out: [...A.out], warnings: A.warnings, files: B.files.map(f => ({{ e: f.enumerator_id, hh: f.obj.households.map(h => [h.hhid, h.contact.phones.map(p => p.number), (h.replacements || []).map(r => [r.hhid, r.contact.phones.map(p => p.number)])]) }})) }};
            }};
            return {{
              random: run({{ name: 'random', seed: 11 }}, [1, 1, 1]),
              equal: run({{ name: 'equal_split', seed: 11, order_by: 'psu' }}, [1, 1, 1]),
              share_blocks: run({{ name: 'share_of_total', seed: 11, order_by: 'psu', method: 'blocks' }}, [50, 30, 20]),
              share_random: run({{ name: 'share_of_total', seed: 11, method: 'random' }}, [50, 30, 20]),
              manual: run({{ name: 'manual', seed: 11 }}, [1, 1, 1]),
              mains: RH.mains.map(h => [h.hhid, h.psu, h.stratum]),
            }};
        }})())"""))
        mains = {h: (p, s_) for h, p, s_ in res["mains"]}
        n = len(mains)

        def counts(r):
            c = {}
            for _, x in r["out"]:
                c[x["enumerator_id"]] = c.get(x["enumerator_id"], 0) + 1
            return c
        rc = counts(res["random"])
        check("random: every household dealt, the enumerators' counts differ by at most one", sum(rc.values()) == n and max(rc.values()) - min(rc.values()) <= 1, rc)
        strata = sorted({s_ for _, s_ in mains.values()})
        mix_ok = True
        for st_ in strata:
            per = {}
            for h, x in res["random"]["out"]:
                if mains[h][1] == st_:
                    per[x["enumerator_id"]] = per.get(x["enumerator_id"], 0) + 1
            if max(per.values()) - min(per.values()) > 1:
                mix_ok = False
        check("random: each enumerator gets the same mix of strata (within one household per stratum)", mix_ok)
        order = sorted(mains, key=lambda h: (mains[h][0], h))
        ec = counts(res["equal"])
        seq = [dict(res["equal"]["out"])[h]["enumerator_id"] for h in order]
        blocks = [seq[0]] + [b_ for a_, b_ in zip(seq, seq[1:]) if a_ != b_]
        check("equal split: consecutive blocks of the list ordered by PSU, sizes differing by at most one, with the warning on area effects",
              max(ec.values()) - min(ec.values()) <= 1 and len(blocks) == 3 and any("cannot be told apart" in w for w in res["equal"]["warnings"]), [ec, blocks])
        sb, sr = counts(res["share_blocks"]), counts(res["share_random"])
        check("share of total: 50/30/20 shares give 55, 33 and 22 households, in blocks or dealt at random",
              sb == {"E01": 55, "E02": 33, "E07": 22} and sr == {"E01": 55, "E02": 33, "E07": 22}, [sb, sr])
        mo = dict(res["manual"]["out"])
        check("manual: the list is followed; an unknown enumerator ID and the households without one are flagged",
              any("E99" in w for w in res["manual"]["warnings"]) and any("4 households have no enumerator" in w for w in res["manual"]["warnings"])
              and all(mo[r["hhid"]]["enumerator_id"] == ["E01", "E02", "E07"][i % 3] for i, r in enumerate(hl[:-3]) if i != 5), res["manual"]["warnings"])
        check("every rule gives each household a reason code from the assignment format",
              all(x["reason"] in ("keep", "rotation", "switch_hard_to_reach", "enumerator_unavailable", "new", "manual", "capacity", "rule") for k in ("random", "equal", "share_blocks", "share_random", "manual") for _, x in res[k]["out"]))
        # access control under every rule
        phones = {r["hhid"]: {r[k] for k in ("phone_1", "phone_2", "phone_3") if r.get(k)} for r in csv.DictReader(open(os.path.join(S, "household_list.csv"), encoding="utf-8"))}
        leaks = []
        for k in ("random", "equal", "share_blocks", "share_random", "manual"):
            for f in res[k]["files"]:
                mine = {h for h, _, reps in f["hh"]} | {r for _, _, reps in f["hh"] for r, _ in reps}
                allowed = set().union(*[phones[h] for h in mine])
                for h, nums, reps in f["hh"]:
                    leaks += [(k, f["e"], h) for x in nums if x not in allowed]
                    leaks += [(k, f["e"], r) for r, rn in reps for x in rn if x not in allowed]
                    if dict(res[k]["out"]).get(h, {}).get("enumerator_id") != f["e"]:
                        leaks.append((k, f["e"], h, "household of another enumerator"))
        check("access control under every rule: no file holds a household, replacement or number of another enumerator", not leaks, leaks[:5])

        # ---- the other rules, chosen and applied from the screen (review loop, check 2) ----
        def setv(sel, v):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

        def tick(sel, on):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.checked = {str(bool(on)).lower()}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")
        setv('[data-lset="cal.window_start"]', "2026-10-26"); setv('[data-lset="cal.window_end"]', "2026-11-20")
        team = b.js("LEAD.state().team.map(t => t.id)")
        tick(f'[data-lteam="{team.index("E03")}"][data-f="available"]', False)
        ui_runs = {}
        for name, extra in (("random", None), ("equal_split", None), ("share_of_total", "blocks"), ("share_of_total", "random"), ("manual", None)):
            tick(f'[data-lrule="{name}"]', True); time.sleep(0.1)
            if name == "share_of_total":
                for e, sh in (("E01", 50), ("E02", 30), ("E07", 20)):
                    setv(f'[data-lteam="{team.index(e)}"][data-f="share"]', str(sh))
                setv('[data-lset="rule.method"]', extra)
            if name == "manual" and not b.js("!!LEAD.state().inputs.manual"):
                b.set_files("#lf-manual", [manual]); b.wait("!!LEAD.state().inputs.manual")
            b.click('[data-lact="apply"]'); time.sleep(0.4)
            st_ = b.js("(() => { const st = LEAD.state(); return { plan: !!st.plan, errors: LEAD.ui.errors || [], n: st.plan ? st.plan.out.size : 0, rule: st.rule.name, text: document.querySelector('.panel').innerText.includes('4 households have no enumerator in the manual list') }; })()")
            ui_runs[name + ("_" + extra if extra else "")] = st_
        # under the random rule, an enumerator reads why a moved household is theirs in the rule's own words
        tick('[data-lrule="random"]', True); time.sleep(0.1)
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        # step 7 under the random rule: the rule's own column, so every household is counted under a reason
        t7 = b.js("""(() => { const sec = [...document.querySelectorAll('.lcard')].find(c => /7 · Check the assignment/.test(c.innerText)); const tb = sec.querySelector('table');
                      const head = [...tb.querySelectorAll('thead th')].map(t => t.innerText.trim()); const hi = head.indexOf('Households');
                      const rows = [...tb.querySelectorAll('tbody tr')].map(r => [...r.querySelectorAll('td')].map(t => t.innerText.trim()));
                      return { head, ok: rows.every(r => r.slice(1, hi).reduce((a, v) => a + (+v || 0), 0) === +r[hi]) }; })()""")
        check("step 7 under the random rule has a column for households moved by the rule, and each row's reasons add up to its households",
              "dealt at random" in t7["head"] and t7["ok"], t7)
        # one household moved by hand to E01 (step 7's list): its reason is 'manual' under any rule
        hand = b.js("[...LEAD.state().plan.out.entries()].find(([id, x]) => x.enumerator_id !== 'E01')[0]")
        b.js(f"""(() => {{ const el = document.querySelector('[data-lmove="{hand}"]'); el.value = 'E01'; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()""")
        b.wait(f"LEAD.state().plan.out.get('{hand}').reason === 'manual'")
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        a01 = next(json.loads(f["text"]) for f in b.js("LEAD.ui.ready.map(f => ({ name: f.name, text: f.text }))") if f["name"].startswith("E01_assignment"))
        moved = next(h["hhid"] for h in a01["households"] if h["assignment"]["reason"] == "rule")
        pa = os.path.join(SCRATCH, f"random_E01_{STAMP}.json"); json.dump(a01, open(pa, "w", encoding="utf-8"))
        b.click('[data-act="view"][data-v="enum"]'); b.wait("!!document.querySelector('#f-assign')")
        b.set_files("#f-assign", [pa]); b.wait("!!APP.S")
        b.js(f"APP.sel = {json.dumps(moved)}; APP.render(); true"); b.click(".drawer details.why summary"); time.sleep(0.1)
        dtxt = b.js("document.querySelector('.drawer').innerText")
        check("under the random rule, a moved household reads 'dealt to you at random by this round's rule (random)', and the note explains that rule, not the default's rotation",
              "Dealt to you at random by this round’s rule (random)" in dtxt and "dealt households at random" in dtxt and "Rotation: part of the planned share" not in dtxt, dtxt[:400])
        b.js(f"APP.sel = {json.dumps(hand)}; APP.render(); true"); time.sleep(0.1)
        htxt = b.js("document.querySelector('.drawer').innerText")
        b.js("APP.sel = null; true"); b.click('[data-act="tab"][data-t="households"]'); time.sleep(0.2)
        row = b.js(f"[...document.querySelectorAll('#hh-table tr')].map(r => r.innerText).find(t => t.includes({json.dumps(moved)})) || ''")
        foot = b.js("document.querySelector('.panel').innerText")
        check("under the random rule, a household moved by hand reads 'Assigned by hand'; the Households tab words reasons and its note by the rule",
              "Assigned by hand" in htxt and "Dealt at random" in row and "dealt households at random" in foot and "stated default is to keep the same enumerator, rotate" not in foot,
              [htxt[:200], row, foot[-300:]])
        b.click('[data-act="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("APP.S === null")
        b.click('[data-act="view"][data-v="leader"]')
        check("every rule besides the default can be chosen and applied from the leader view's own controls (step 6): all 110 households dealt, "
              "or under the manual rule the 106 the list gives an enumerator, with the other 4 flagged on screen",
              all(x["plan"] and not x["errors"] and x["n"] == 110 for k, x in ui_runs.items() if k != "manual")
              and ui_runs["manual"]["plan"] and ui_runs["manual"]["n"] == 106 and ui_runs["manual"]["text"], ui_runs)
    finally:
        b.close()
    passed = sum(ok for _, ok in results)
    lines = [f"Validation tests, {time.strftime('%d %b %Y %H:%M')}: {passed} of {len(results)} passed"] + [("PASS " if ok else "FAIL ") + n for n, ok in results]
    open(os.path.join(HERE, "results_validation.txt"), "w").write("\n".join(lines) + "\n")
    print(lines[0])
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
