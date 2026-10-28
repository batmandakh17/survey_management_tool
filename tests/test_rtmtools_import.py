"""Step 7: the replacement list exported by the appendix sampling tool (rtmtools), read by this tool.

samples/rtmtools_export/ holds a real rtmtools run: `rtmsample draw, n(8) strata(psu) reserve(3)` on a synthetic frame
of 12 PSUs x 15 households with 9-digit numeric IDs (draw_replacements.do; Stata 18, rtmtools 0.6.1 with the full-width
ID export). This test builds the leader's household list from that selection, opens both files in the leader view as a
leader would, writes the round's files, and opens one enumerator's file. Every expectation is computed here in Python
from the export itself.

Run from the tool folder:  python3 tests/test_rtmtools_import.py
Writes tests/results_rtmtools.txt.
"""
import csv
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from cdp import Browser  # noqa: E402

SCRATCH = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
STAMP = time.strftime("%H%M%S")
X = os.path.join(ROOT, "samples", "rtmtools_export")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:600]}]" if detail and not ok else ""))


def expected_lists(rows):
    """D6, from the export: in each stratum (the PSU), the reserve in rank order, dealt round-robin to the selected
    households in their selection order."""
    by = {}
    for r in rows:
        g = by.setdefault(r["stratum"], {"mains": [], "reserves": []})
        if r["selected"] == "1":
            g["mains"].append((float(r["rank"]), r["unit_id"]))
        elif float(r["reserve"] or 0) > 0:
            g["reserves"].append((float(r["reserve"]), r["unit_id"]))
    out = {}
    for g in by.values():
        mains = [u for _, u in sorted(g["mains"])]
        for j, (_, u) in enumerate(sorted(g["reserves"])):
            out.setdefault(mains[j % len(mains)], []).append(u)
    return out


def main():
    rows = list(csv.DictReader(open(os.path.join(X, "selection.csv"), encoding="utf-8")))
    man = json.load(open(os.path.join(X, "manifest.json"), encoding="utf-8"))
    check("the sample is a real rtmtools run: schema rtm-export-1.0, rtmsample draw with reserve(3)",
          man["schema"] == "rtm-export-1.0" and man["step"] == "draw" and "reserve(3)" in man["command"], man["command"])
    check("the export writes the 9-digit IDs in full (no scientific notation)",
          all(re.fullmatch(r"\d{9}", r["unit_id"]) for r in rows), [r["unit_id"] for r in rows[:3]])
    want = expected_lists(rows)
    mains = [r for r in rows if r["selected"] == "1"]
    reserves = [r for r in rows if r["selected"] != "1" and float(r["reserve"] or 0) > 0]

    # the leader's household list for the round: the selected households active, the reserve kept as reserve
    hl = os.path.join(SCRATCH, f"rtm_household_list_{STAMP}.csv")
    with open(hl, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hhid", "psu", "stratum", "phone_1", "status"])
        for i, r in enumerate(mains + reserves):
            region = "1" if int(r["stratum"]) <= 1106 else "2"
            w.writerow([r["unit_id"], r["stratum"], region, f"+000 {r['unit_id'][:5]} {1000 + i}", "active" if r["selected"] == "1" else "reserve"])

    b = Browser(os.path.join(SCRATCH, f"rprofile_{STAMP}"), port=9345)
    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId="Asia/Ulaanbaatar")
        b.goto("file://" + os.path.join(ROOT, "rtm_interview_tool.html"))
        b.js("RTM.setNow('2026-10-28T12:00:00+08:00'); APP.noFSA = true; true")

        def setv(sel, v):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")

        b.click('[data-act="view"][data-v="leader"]'); b.wait("!!document.querySelector('#lstart')")
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '1'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        b.set_files("#lf-hh", [hl]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-repl", [os.path.join(X, "selection.csv")]); b.wait("!!LEAD.state().inputs.replacements")
        card = b.js("[...document.querySelectorAll('.lcard')].find(c => /Replacement list/.test(c.innerText)).innerText")
        check("the leader view recognises the file as an rtmtools selection and reads it without a warning",
              f"rtmtools selection: {len(reserves)} replacements, one for each of {len(want)} households. {len(reserves)} are still in reserve" in card
              and "scientific notation" not in card and "not in the household list" not in card, card[:700])
        got = b.js("""(() => { const st = LEAD.state(), HL = LCORE.parseHouseholds(st.inputs.households.text);
                        const RP = LCORE.parseReplacements(st.inputs.replacements.text, HL.households);
                        return { format: RP.format, errors: RP.errors, warnings: RP.warnings, lists: [...RP.lists].map(([m, l]) => [m, l.map(x => x.hhid)]) }; })()""")
        check("every replacement goes to the household the export's ranks give it (D6, recomputed here from the export)",
              got["format"] == "rtmtools" and not got["errors"] and not got["warnings"] and dict(got["lists"]) == want,
              [got["format"], got["errors"], got["warnings"], len(got["lists"]), len(want)])

        # the round: a window, three enumerators, the random rule of a first round
        setv('[data-lset="cal.window_start"]', "2026-11-02"); setv('[data-lset="cal.window_end"]', "2026-11-27")
        setv('[data-lset="cal.dial_cap"]', "8")   # a first round has no earlier manifest to take the cap from, and it has no default
        for e in ("E01", "E02", "E03"):
            setv("#lenum-id", e); b.click('[data-lact="addenum"]'); time.sleep(0.1)
        b.js("(() => { const el = document.querySelector('[data-lrule=\"random\"]'); el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()")
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        files = b.js("LEAD.ui.ready.map(f => ({ name: f.name, text: f.text }))")
        assign = {f["name"]: json.loads(f["text"]) for f in files if "_assignment_" in f["name"]}
        in_files = {h["hhid"]: [r["hhid"] for r in h.get("replacements", [])] for a in assign.values() for h in a["households"]}
        check("the round's assignment files carry each household's replacements, IDs unchanged, in rank order",
              len(in_files) == len(mains) and {k: v for k, v in in_files.items() if v} == want, [len(in_files), len(mains)])
        owners = {}
        for name, a in assign.items():
            for h in a["households"]:
                for r in h.get("replacements", []):
                    owners.setdefault(r["hhid"], set()).add(name)
        check("each replacement is in exactly one enumerator's file, with its own household",
              len(owners) == len(reserves) and all(len(v) == 1 for v in owners.values()), len(owners))
        manifest = json.loads(next(f["text"] for f in files if f["name"].endswith("_manifest.json")))
        mtext = json.dumps(manifest)
        check("the round manifest lists the replacements by ID only (no phone numbers)",
              all(r["unit_id"] in mtext for r in reserves) and "+000" not in mtext)

        # an enumerator opens their file: the household's replacements are shown with their full IDs
        e_name, a = next((n, a) for n, a in assign.items() if any(h.get("replacements") for h in a["households"]))
        path = os.path.join(SCRATCH, f"rtm_{STAMP}_{e_name}")
        open(path, "w", encoding="utf-8").write(json.dumps(a))
        b.click('[data-act="view"][data-v="enum"]'); b.wait("!!document.querySelector('#f-assign')")
        b.set_files("#f-assign", [path]); b.wait("!!APP.S")
        h = next(h for h in a["households"] if h.get("replacements"))
        b.js(f"APP.sel = {json.dumps(h['hhid'])}; APP.render(); true"); time.sleep(0.2)
        drawer = b.js("document.querySelector('.drawer').innerText")
        check("the enumerator sees the household's replacements in order, with their full IDs",
              all(r["hhid"] in drawer for r in h["replacements"]) and "Replacements, in order".upper() in drawer.upper(), drawer[-400:])
        b.js("(() => { const el = document.querySelector('.drawer ol.repl'); if (el) el.scrollIntoView({block: 'center'}); return true; })()"); time.sleep(0.2)
        b.shot(os.path.join(HERE, "screens", "rtmtools_import_enumerator.png"))
    finally:
        b.close()
    n_ok = sum(1 for _, ok, _ in results if ok)
    with open(os.path.join(HERE, "results_rtmtools.txt"), "w", encoding="utf-8") as f:
        f.write(f"rtmtools import tests, {time.strftime('%d %b %Y %H:%M')}: {n_ok} of {len(results)} passed\n")
        for name, ok, _ in results:
            f.write(("PASS " if ok else "FAIL ") + name + "\n")
    print(f"rtmtools import tests, {time.strftime('%d %b %Y %H:%M')}: {n_ok} of {len(results)} passed")


if __name__ == "__main__":
    main()
