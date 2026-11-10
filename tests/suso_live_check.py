"""Read a real Survey Solutions export with the tool and compare it with the layout the tool assumes.

usage: python3 tests/suso_live_check.py EXPORT.zip [--manifest FILE] [--households FILE] [--tz ZONE] [--now ISO]
                                        [--move HHID:FROM:TO:AT ...] [--shot FILE]

Part 1 reads the zip in Python: the files it holds, their columns against the layout of formats/suso/README.md, and the
codes and formats of the values (statuses, action codes, timestamps, missing values). Part 2 opens the tool in headless
Chrome, starts a leader session on the manifest and household list (the synthetic round 5 by default, whose logins CATI01,
CATI02 and CATI07 match samples/suso/assignments.tab), adds the zip on the Survey Solutions tab and prints what the tool
makes of it: the files kept, the split by interviewer, dials and completes per enumerator, the step-3 summary, the merge
questions and, for each --move (the household, the enumerator IDs before and after, the time), the step-4 line: in
Headquarters done, pending or not in the export.

Lines starting with DIFF mark a departure from the assumed layout; the exit code is their number. Run it on the sample zip
(samples/suso/rtm_call_record_1_Tabular_All.zip) to see the layout it expects. It prints logins, codes and counts only,
never an answer: no name, no phone number.
"""
import argparse
import collections
import csv
import io
import json
import os
import re
import sys
import time
import zipfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "samples"))
from cdp import Browser  # noqa: E402
import make_samples as MS  # noqa: E402  (its column lists are the layout the tool was built on)

TOOL = "file://" + os.path.join(ROOT, "rtm_interview_tool.html")
S = os.path.join(ROOT, "samples", "leader")

# docs.mysurvey.solutions, "System-generated export file anatomy" (opened 6 November 2026, release 26.11)
INTERVIEW_ACTIONS = {0: "SupervisorAssigned", 1: "InterviewerAssigned", 2: "FirstAnswerSet", 3: "Completed", 4: "Restarted",
                     5: "ApprovedBySupervisor", 6: "ApprovedByHeadquarter", 7: "RejectedBySupervisor", 8: "RejectedByHeadquarter",
                     9: "Deleted", 10: "Restored", 11: "UnapprovedByHeadquarter", 12: "Created", 13: "InterviewReceivedByTablet",
                     14: "Resumed", 15: "Paused", 16: "TranslationSwitched", 17: "OpenedBySupervisor", 18: "ClosedBySupervisor",
                     19: "InterviewSwitchedToCawiMode", 20: "InterviewSwitchedToCapiMode"}
ASSIGNMENT_ACTIONS = {1: "Created", 2: "Archived", 3: "Deleted", 4: "ReceivedByTablet", 5: "Unarchived", 6: "AudioRecordingChanged",
                      7: "Reassigned", 8: "QuantityChanged", 9: "WebModeChanged", 11: "Completed"}
STATUSES = {-1: "Deleted", 0: "Restored", 20: "Created", 40: "SupervisorAssigned", 60: "InterviewerAssigned", 65: "RejectedBySupervisor",
            80: "ReadyForInterview", 85: "SentToCapi", 95: "Restarted", 100: "Completed", 120: "ApprovedBySupervisor",
            125: "RejectedByHeadquarters", 130: "ApprovedByHeadquarters"}
ROLES = {0: "none", 1: "Interviewer", 2: "Supervisor", 3: "Headquarter", 4: "Administrator", 5: "ApiUser"}
SERVICE = {"interview__actions": MS.SUSO_ACT_COLS, "interview__diagnostics": MS.SUSO_DIAG_COLS, "assignment__actions": MS.SUSO_ASSIGN_ACT_COLS}
SKIPPED = {"interview__errors", "interview__comments", "paradata", "export__readme"}
MISSING = {"##N/A##", "-999999999"}
RX_DATE, RX_TIME = re.compile(r"^\d{4}-\d\d-\d\d$"), re.compile(r"^\d\d:\d\d:\d\d$")
RX_STAMP, RX_DUR = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$"), re.compile(r"^\d\d\.\d\d:\d\d:\d\d$")
RX_APPT = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d$")  # the mask ####-##-## ##:## of the tool's questionnaire

diffs = []


def say(line=""):
    print(line)


def diff(line):
    diffs.append(line)
    print("DIFF " + line)


def codes_seen(rows, col, table, label):
    c = collections.Counter(r.get(col, "") for r in rows)
    out = []
    for k, n in sorted(c.items(), key=lambda x: (not x[0].lstrip("-").isdigit(), int(x[0]) if x[0].lstrip("-").isdigit() else 0)):
        name = table.get(int(k)) if k.lstrip("-").isdigit() else None
        out.append(f"{k} {name or '?'}: {n}")
        if name is None:
            diff(f"{label}: code {k!r} is not in the documentation's table")
    say(f"  {label}: " + "; ".join(out))


def part1(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    say(f"== Part 1. The zip: {os.path.basename(path)} ({len(names)} files)")
    tabs = {}
    for n in names:
        base = os.path.basename(n)
        stem = re.sub(r"\.(tab|txt)$", "", base, flags=re.I)
        if base.lower().endswith(".tab"):
            text = z.read(n).decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
            header = text.split("\n", 1)[0].rstrip("\r").split("\t")
            tabs[stem] = (header, rows)
            say(f"  {base}: {len(rows)} rows, {len(header)} columns")
        else:
            say(f"  {base}: not a tab file" + (" (skipped by the tool)" if stem in SKIPPED else ""))
    # which file is the main file and which the rosters
    service = {k: v for k, v in tabs.items() if k in SERVICE or k in SKIPPED}
    data = {k: v for k, v in tabs.items() if k not in service}
    rosters = {k: v for k, v in data.items() if f"{k}__id" in v[0]}
    mains = {k: v for k, v in data.items() if k not in rosters}
    say(f"  main file: {', '.join(mains) or 'none'}; rosters: {', '.join(rosters) or 'none'}; service: {', '.join(service)}")
    if len(mains) != 1:
        diff(f"expected one main file (no <name>__id column), found {len(mains)}")
    for k in SERVICE:
        if k not in tabs:
            diff(f"{k}.tab is missing")
            continue
        header = tabs[k][0]
        if header != SERVICE[k]:
            miss, extra = [c for c in SERVICE[k] if c not in header], [c for c in header if c not in SERVICE[k]]
            diff(f"{k}.tab columns differ: missing {miss or 'none'}, extra {extra or 'none'}, order {'same' if [c for c in header if c in SERVICE[k]] == [c for c in SERVICE[k] if c in header] else 'different'}")
        else:
            say(f"  {k}.tab: columns as assumed")
    for k, (header, rows) in mains.items():
        want = MS.SUSO_MAIN_COLS
        miss, extra = [c for c in want if c not in header], [c for c in header if c not in want]
        if miss or extra:
            diff(f"main file {k}.tab columns: missing {miss or 'none'}, extra {extra or 'none'}")
        else:
            say(f"  {k}.tab: the main file's columns as assumed (identifying variables, n_calls, ssSys_IRnd, has__errors, interview__status, assignment__id)")
        for c in ("interview__key", "interview__id", "interview__status", "assignment__id", "has__errors"):
            if c not in header:
                diff(f"main file lacks {c}, which the tool needs")
        if "interview__status" in header:
            codes_seen(rows, "interview__status", STATUSES, "interview__status")
        if "has__errors" in header:
            say(f"  has__errors: {dict(collections.Counter(r['has__errors'] for r in rows))}")
        keys = [r.get("interview__key", "") for r in rows]
        if not all(re.fullmatch(r"\d\d-\d\d-\d\d-\d\d", k_) for k_ in keys):
            diff("interview__key is not always NN-NN-NN-NN")
    for k, (header, rows) in rosters.items():
        if k == "calls":
            want = MS.SUSO_CALL_COLS
            miss, extra = [c for c in want if c not in header], [c for c in header if c not in want]
            if miss or extra:
                diff(f"calls.tab columns: missing {miss or 'none'}, extra {extra or 'none'}")
            else:
                say("  calls.tab: the roster's columns as assumed")
            if "call_start" in header:
                fmt = collections.Counter("missing" if r["call_start"] in MISSING or r["call_start"] == "" else "YYYY-MM-DDTHH:MM:SS" if RX_STAMP.match(r["call_start"]) else "other" for r in rows)
                say(f"  call_start formats: {dict(fmt)}")
                if fmt.get("other"):
                    ex = next(r["call_start"] for r in rows if r["call_start"] not in MISSING and not RX_STAMP.match(r["call_start"]))
                    diff(f"call_start has another format, for example {ex!r} (an offset, a space, or seconds missing)")
            if "result" in header:
                say(f"  result codes seen: {dict(sorted(collections.Counter(r['result'] for r in rows).items()))}")
            if "appointment" in header:
                ap = [r["appointment"] for r in rows if r["appointment"] not in MISSING and r["appointment"]]
                fmt = collections.Counter("YYYY-MM-DD HH:MM" if RX_APPT.match(a) else "other" for a in ap)
                say(f"  appointment: {len(ap)} filled, formats {dict(fmt)}" + (f", for example {next(a for a in ap if not RX_APPT.match(a))!r}" if fmt.get("other") else ""))
        else:
            say(f"  roster {k}: {header[:6]}{'...' if len(header) > 6 else ''}")
        seen = collections.Counter(v for r in rows for v in r.values() if v in MISSING)
        say(f"  {k}.tab missing-value tokens: {dict(seen) or 'none'}")
    # the responsible columns: the documentation page writes responsible_name, a 26.11 server responsible__name
    def col(header, *names):
        return next((n for n in names if n in header), names[0])
    if "interview__actions" in tabs:
        header, rows = tabs["interview__actions"]
        rn, rr = col(header, "responsible_name", "responsible__name"), col(header, "responsible_role", "responsible__role")
        codes_seen(rows, "action", INTERVIEW_ACTIONS, "interview__actions action")
        codes_seen(rows, "role", ROLES, "interview__actions role")
        codes_seen(rows, rr, ROLES, f"interview__actions {rr}")
        say(f"  originators: {sorted(set(r['originator'] for r in rows))}; {rn}: {sorted(set(r.get(rn, '') for r in rows))}")
        bad = [r for r in rows if not (RX_DATE.match(r["date"]) and RX_TIME.match(r["time"]))]
        if bad:
            diff(f"interview__actions date/time not YYYY-MM-DD / HH:MM:SS in {len(bad)} rows, for example {bad[0]['date']!r} {bad[0]['time']!r}")
        else:
            say("  interview__actions date and time: YYYY-MM-DD and HH:MM:SS (UTC by the documentation; compare with the device clock)")
        first = [r for r in rows if r["action"] == "2"]
        say(f"  interviews with a first answer: {len(set(r['interview__id'] for r in first))}; received by tablet (13): {len(set(r['interview__id'] for r in rows if r['action'] == '13'))}")
    if "assignment__actions" in tabs:
        header, rows = tabs["assignment__actions"]
        rn = col(header, "responsible_name", "responsible__name")
        codes_seen(rows, "action", ASSIGNMENT_ACTIONS, "assignment__actions action")
        say(f"  assignments: {len(set(r['assignment__id'] for r in rows))}; {rn}: {sorted(set(r.get(rn, '') for r in rows))}")
        re7 = [r for r in rows if r["action"] == "7"]
        if re7:
            say(f"  reassigned: {len(re7)} rows, old__value/new__value for example {re7[0]['old__value']!r} -> {re7[0]['new__value']!r}")
        bad = [r for r in rows if not (RX_DATE.match(r["date"]) and RX_TIME.match(r["time"]))]
        if bad:
            diff(f"assignment__actions date/time not YYYY-MM-DD / HH:MM:SS in {len(bad)} rows")
    if "interview__diagnostics" in tabs:
        rows = tabs["interview__diagnostics"][1]
        dur = collections.Counter("DD.HH:MM:SS" if RX_DUR.match(r["interview__duration"]) else "missing" if r["interview__duration"] in MISSING or not r["interview__duration"] else "other" for r in rows)
        say(f"  interview__duration formats: {dict(dur)}; interviewers: {dict(collections.Counter(r['interviewers'] for r in rows))}; "
            f"rejections__sup: {dict(collections.Counter(r['rejections__sup'] for r in rows))}; rejections__hq: {dict(collections.Counter(r['rejections__hq'] for r in rows))}")
        if dur.get("other"):
            diff("interview__duration has a format other than DD.HH:MM:SS")
    return z


def part2(path, args):
    say(f"\n== Part 2. The tool reads it (manifest {os.path.basename(args.manifest)}, zone {args.tz})")
    scratch = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
    b = Browser(os.path.join(scratch, f"suso_live_{time.strftime('%H%M%S')}"), port=9347)
    try:
        b.ws.call("Emulation.setTimezoneOverride", timezoneId=args.tz)
        b.goto(TOOL)
        b.js(f"RTM.setNow({json.dumps(args.now)}); APP.noFSA = true; true" if args.now else "APP.noFSA = true; true")
        m = json.load(open(args.manifest, encoding="utf-8"))
        b.click('[data-act="view"][data-v="leader"]'); b.wait("!!document.querySelector('#lstart')")
        b.js(f"""(() => {{ const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01';
               f.querySelector('[name=program]').value = {json.dumps(m['program'])}; f.querySelector('[name=country]').value = {json.dumps(m.get('country', 'MN'))};
               f.querySelector('[name=round]').value = {json.dumps(str(m['round']))}; return true; }})()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        b.set_files("#lf-hh", [args.households]); b.wait("!!LEAD.state().inputs.households")
        b.click('[data-lact="tab"][data-t="import"]'); b.set_files("#lf-manifest", [args.manifest]); b.wait("!!LEAD.state().manifest")
        b.click('[data-lact="tab"][data-t="suso"]'); time.sleep(0.3)
        logins_js = "JSON.stringify(Object.assign(Object.fromEntries((LEAD.state().manifest.enumerators || []).map(e => [e.enumerator_id, e.platform_id || ''])), LEAD.state().platform.codes))"
        say(f"  logins known to the tool (manifest platform_id, plus the codes table): {b.js(logins_js)}")
        b.set_files("#lf-suso", [path]); b.wait("LEAD.state().imports.length >= 1", timeout=30); time.sleep(0.8)
        names = b.js("LEAD.state().imports.map(f => f.name)")
        say(f"  files kept from the zip: {[n.split('/')[-1] for n in names]}")
        if b.js("!!document.querySelector('#lsusolevel')"):
            diff("the tool did not recognise its own questionnaire: step 3 asks which file holds the calls (the main file or the calls roster lacks a column the built-in layout detects: interview__key, calls__id, hhid, result, call_start)")
            say("  level card: " + b.js("document.querySelector('#lsusolevel').innerText")[:400].replace("\n", " | "))
        if b.js("!!document.querySelector('#lmap')"):
            diff("the mapping card opened: the calls table is read as an unknown layout")
        g = b.js("""(() => { const g = LEAD.merged(), G = g.G; const by = {};
            G.dials.forEach(d => { by[d.source] = (by[d.source] || 0) + 1; });
            const metas = (G.suso || []).map(s => ({ label: s.label || s.group || '', summary: s.summary, deleted: s.deleted, assign: s.assign ? s.assign.size : null, received: s.received ? s.received.size : null, hh: s.byHH ? s.byHH.size : null, orphans: s.orphans ? s.orphans.length : null }));
            return { dials: by, completes: Object.fromEntries(g.P.list.map(r => [r.enumerator_id, r.complete])), files: G.files.map(f => [f.name.split('/').pop(), f.kind, f.enumerator_id, f.count, f.use]),
              issues: G.issues.map(i => [i.type, i.status, i.severity, i.enumerator || '', i.hhid || '', (i.detail || '').slice(0, 160)]), standalone: G.actions.filter(a => a.via !== 'dial').map(a => [a.hhid, a.action, a.target_hhid || '']),
              metas, review: LCORE.reviewRows(G).map(r => [r.issue, r.record_id]) }; })()""")
        say("  files:")
        for f in g["files"]:
            say(f"    {f[0]} | {f[1]} | {f[2] or '-'} | {f[3]} | {f[4]}")
        say(f"  dials per enumerator: {g['dials']}")
        say(f"  completes per enumerator (Box 3.0 rule): {g['completes']}")
        say(f"  actions without a dial: {g['standalone']}")
        for mt in g["metas"]:
            say(f"  export summary: {json.dumps(mt, ensure_ascii=False)}")
        txt = b.js("document.querySelector('.panel').innerText")
        i = txt.find("says of its")
        if i >= 0:
            j = txt.find("4 · After moves", i)
            say("  step 3 text:\n    " + txt[i - 20:j if j > 0 else i + 900].strip().replace("\n", "\n    "))
        else:
            diff("step 3 shows no export summary")
        say(f"  merge questions: {len(g['issues'])}")
        for it in g["issues"][:40]:
            say(f"    {it[0]} | {it[1]} | {it[2]} | {it[3]} | {it[4]} | {it[5]}")
        say(f"  review rows: {len(g['review'])} {g['review'][:10]}")
        if args.move:
            mv = []
            for spec in args.move:
                hh, fr, to, at = spec.split(":", 3)
                mv.append({"hhid": hh, "from": fr, "to": to, "at": at, "by": "L01"})
            rows = b.js(f"""(() => {{ const st = LEAD.state(); return LCORE.susoMoves(Object.assign({{}}, st.manifest, {{ moves: {json.dumps(mv)} }}), st.platform.codes, LEAD.merged().G.suso); }})()""")
            say("  step 4, the moves given:")
            for r in rows:
                say("    " + json.dumps(r, ensure_ascii=False))
        if args.shot:
            b.shot(args.shot, full=True)
            say(f"  screenshot: {args.shot}")
    finally:
        b.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip")
    ap.add_argument("--manifest", default=os.path.join(S, "L2MN-DEMO_R05_manifest.json"))
    ap.add_argument("--households", default=os.path.join(S, "household_list.csv"))
    ap.add_argument("--tz", default="Asia/Ulaanbaatar")
    ap.add_argument("--now", default="", help="the tool's clock, ISO with offset (default: the real time)")
    ap.add_argument("--move", action="append", default=[], help="HHID:FROM_ENUM:TO_ENUM:ISO_TIME, may repeat")
    ap.add_argument("--shot", default="", help="save a full screenshot of the Survey Solutions tab here")
    ap.add_argument("--no-tool", action="store_true", help="part 1 only")
    args = ap.parse_args()
    part1(args.zip)
    if not args.no_tool:
        part2(args.zip, args)
    say(f"\n{len(diffs)} departure(s) from the assumed layout" + ("" if not diffs else ":\n  " + "\n  ".join(diffs)))
    return len(diffs)


if __name__ == "__main__":
    sys.exit(main())
