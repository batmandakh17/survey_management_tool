"""The format checker accepts the samples and catches each kind of damage (no browser needed).

Run from the tool folder:  python3 tests/test_formats.py
Writes tests/results_formats.txt. Tampered copies go to a scratch folder (RTM_SCRATCH, default tests/_work).
"""
import glob
import io
import json
import os
import shutil
import sys
import time
from contextlib import redirect_stdout

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "formats"))
import check_formats as cf  # noqa: E402

SCRATCH = os.path.join(os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work")), "formats_" + time.strftime("%H%M%S"))
os.makedirs(SCRATCH)
S = os.path.join(ROOT, "samples")
results = []


def run(*paths, passphrase=None):
    old = os.environ.pop("RTM_PASSPHRASE", None)
    if passphrase:
        os.environ["RTM_PASSPHRASE"] = passphrase
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cf.main(list(paths))
    os.environ.pop("RTM_PASSPHRASE", None)
    if old:
        os.environ["RTM_PASSPHRASE"] = old
    return code, buf.getvalue()


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))


def copy(src, name):
    dst = os.path.join(SCRATCH, name)
    shutil.copy(src, dst)
    return dst


def edit_json(path, fn):
    o = json.load(open(path, encoding="utf-8"))
    fn(o)
    json.dump(o, open(path, "w", encoding="utf-8"), ensure_ascii=False)


clean = [os.path.join(S, d) for d in ("round05", "past", os.path.join("leader", "history"), os.path.join("leader", "exports_R05"))] + \
    sorted(glob.glob(os.path.join(S, "leader", "*.*")))
code, out = run(*clean)
check("all sample files pass, the leader's inputs and outputs included", code == 0, out)
code, out = run(os.path.join(S, "leader", "merge_cases"))
check("of the merge cases, only the deliberately edited file fails, at its broken chain",
      code == 1 and out.count("ERROR") == 1 and "edited" in out.split("ERROR")[1].split("\n")[0] and "hash chain" in out, out)
code, out = run(os.path.join(S, "round05", "E07_assignment_R05_protected.json"), passphrase="synthetic-E07")
check("the protected sample opens with its passphrase and its content passes", code == 0 and "warning" not in out, out)
code, out = run(os.path.join(S, "round05", "E07_assignment_R05_protected.json"), passphrase="wrong")
check("a wrong passphrase is an error", code == 1 and "does not open it" in out, out)

# a call log whose dial was edited after logging
j = copy(os.path.join(S, "past", "E07_2026-10-21.json"), "E07_2026-10-21.json")
c = copy(os.path.join(S, "past", "E07_2026-10-21.csv"), "E07_2026-10-21.csv")
edit_json(j, lambda o: next(e for e in o["events"] if e["type"] == "dial" and e["status"] != "COMPLETE").update(status="COMPLETE"))
code, out = run(j)
check("an event edited after logging breaks the hash chain", code == 1 and "hash chain" in out, out)

# an event removed from the middle
edit_json(j, lambda o: None)
shutil.copy(os.path.join(S, "past", "E07_2026-10-21.json"), j)
edit_json(j, lambda o: o["events"].pop(5))
code, out = run(j)
check("an event removed from the log breaks the chain", code == 1 and "does not follow" in out, out)

# a phone number slipped into a call log
shutil.copy(os.path.join(S, "past", "E07_2026-10-21.json"), j)
edit_json(j, lambda o: o["actions"].append({"event_id": "00000000-0000-4000-8000-000000000000", "hhid": "x", "action": "RELEASE", "logged_by": "E07",
                                             "logged_at": "2026-10-21T10:00:00+08:00", "number": "+000 1111 2222"}))
code, out = run(j)
check("a phone number inside a call log is a privacy error", code == 1 and "privacy" in out, out)

# a CSV row changed, the JSON beside it intact
shutil.copy(os.path.join(S, "past", "E07_2026-10-21.json"), j)
text = open(c, encoding="utf-8").read().replace(",NO_ANSWER,0,", ",COMPLETE,1,", 1)
open(c, "w", encoding="utf-8").write(text)
code, out = run(c)
check("a CSV row that differs from its JSON is an error", code == 1 and "differ from the dial rows" in out, out)

# a CSV with a byte-order mark, and one without its JSON
open(c, "w", encoding="utf-8").write("﻿" + open(os.path.join(S, "past", "E07_2026-10-21.csv"), encoding="utf-8").read())
code, out = run(c)
check("a byte-order mark in the CSV is an error", code == 1 and "byte-order mark" in out, out)
lone = copy(os.path.join(S, "past", "E07_2026-10-21.csv"), "E07_2026-10-22.csv")
code, out = run(lone)
check("a CSV without its JSON passes but is marked unverified", code == 0 and "unverified" in out, out)

# a saved session edited outside the tool
p = copy(os.path.join(S, "round05", "E07_project_R05.json"), "E07_project_R05.json")
edit_json(p, lambda o: o["ui"].update(tab="log"))
code, out = run(p)
check("a saved session edited outside the tool fails its checksum", code == 1 and "checksum" in out, out)

# an assignment edited after it was generated: a warning, as in the tool
a = copy(os.path.join(S, "round05", "E07_assignment_R05.json"), "E07_assignment_R05.json")
edit_json(a, lambda o: o["households"][0]["contact"].update(name="edited"))
code, out = run(a)
check("an assignment edited after it was generated passes with a fingerprint warning", code == 0 and "fingerprint does not match" in out, out)
edit_json(a, lambda o: o["households"].append(dict(o["households"][0])))
code, out = run(a)
check("a household listed twice is an error", code == 1 and "appears twice" in out, out)
edit_json(a, lambda o: o["calendar"].update(dial_cap=0))
code, out = run(a)
check("a dial cap of 0 is a schema error", code == 1 and "dial_cap" in out, out)

# a contacts file whose number no longer matches its digest
con = os.path.join(SCRATCH, "E07_2026-10-27_contacts.json")
num = "+000 5555 1234"
json.dump({"schema": "rtm-contacts-1.0", "program": "L2MN-DEMO", "round": 5, "enumerator_id": "E07", "exported_at": "2026-10-27T14:00:00+08:00",
           "contains_contact_information": True, "updates": [{"event_id": "00000000-0000-4000-8000-000000000001", "hhid": "0101-005", "slot": 4, "change": "add",
                                                               "number": num, "private_digest": cf.sha(cf.canon({"number": num})), "logged_by": "E07", "logged_at": "2026-10-27T13:00:00+08:00"}]},
          open(con, "w", encoding="utf-8"))
code, out = run(con)
check("a well-formed contacts file passes", code == 0, out)
edit_json(con, lambda o: o["updates"][0].update(number="+000 5555 9999"))
code, out = run(con)
check("a number changed after export no longer matches its digest", code == 1 and "does not match its digest" in out, out)

# a protected file relabelled for another enumerator
sealed = copy(os.path.join(S, "round05", "E07_assignment_R05_protected.json"), "relabelled.json")
edit_json(sealed, lambda o: o.update(enumerator_id="E02"))
code, out = run(sealed, passphrase="synthetic-E07")
check("a protected file relabelled for another enumerator does not open", code == 1, out)

passed = sum(ok for _, ok in results)
line = f"Format checker tests, {time.strftime('%d %b %Y %H:%M')}: {passed} of {len(results)} passed"
open(os.path.join(HERE, "results_formats.txt"), "w").write(line + "\n" + "\n".join(("PASS " if ok else "FAIL ") + n for n, ok in results) + "\n")
print(line)
sys.exit(0 if passed == len(results) else 1)
