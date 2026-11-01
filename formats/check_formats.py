"""Check interview-tool files against their formats: schema, integrity and privacy.

Usage, from anywhere:
    python3 formats/check_formats.py FILE_OR_FOLDER [...] [--ask-passphrase]

Each JSON file is recognised by its "schema" field, each CSV by its header. For every file it checks:
  - the JSON Schema in this folder (rtm-assign-1.0, rtm-calllog-1.0, rtm-contacts-1.0, rtm-project-1.0, rtm-sealed-1.0);
  - integrity: an assignment's fingerprint, a saved session's checksum, a call log's hash chain and last hash,
    a contacts file's digests, and that a CSV's rows equal the dial rows of the JSON beside it;
  - privacy: a call log (CSV or JSON) holds no name, phone number or private part.
A protected file (rtm-sealed-1.0) is checked as an envelope; with --ask-passphrase, or the passphrase in the
environment variable RTM_PASSPHRASE, it is opened (needs the Python package cryptography) and its content checked too.
Exit status 0 when no file has an error (warnings allowed), 1 otherwise. Needs the Python package jsonschema.
"""
import base64
import csv
import getpass
import glob
import hashlib
import io
import json
import os
import re
import sys
import unicodedata

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMAS = {}
for p in sorted(glob.glob(os.path.join(HERE, "rtm-*.schema.json"))):
    s = json.load(open(p, encoding="utf-8"))
    SCHEMAS[os.path.basename(p)[: -len(".schema.json")]] = s
REGISTRY = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in SCHEMAS.values()])
COLS = SCHEMAS["rtm-calllog-1.0"]["$defs"]["dial_row"]["required"]
INT_COLS = {"round", "attempt", "is_cmp_code", "phone_slot", "corrected"}
FORBIDDEN_IN_LOG = {"number", "phones", "name", "contact", "private"}
ACOLS = ["program", "round", "hhid", "action", "target_hhid", "reason", "note", "via", "logged_by", "logged_at", "event_id"]
REPORT_COLS = ["type", "severity", "status", "enumerator", "hhid", "file", "detail", "decision", "resolved_by", "resolved_at", "note", "key"]
CONTACT_COLS = ["hhid", "slot", "change", "number", "label", "enumerator_id", "logged_by", "logged_at", "event_id", "digest_ok", "file"]


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_errors(obj, sid):
    v = Draft202012Validator(SCHEMAS[sid], registry=REGISTRY)
    out = []
    for e in sorted(v.iter_errors(obj), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(x) for x in e.absolute_path) or "(top)"
        out.append(f"schema: at {where}: {e.message[:200]}")
    return out


def verify_chain(events, genesis):
    prev = genesis
    for i, e in enumerate(events):
        if e.get("prev_hash") != prev:
            return f"event {i + 1} does not follow the one before it (prev_hash)"
        pub = {k: v for k, v in e.items() if k not in ("hash", "private")}
        if sha(canon(pub)) != e.get("hash"):
            return f"event {i + 1} was changed after it was logged (hash)"
        prev = e["hash"]
    return None


def keys_in(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from keys_in(v)
    elif isinstance(o, list):
        for v in o:
            yield from keys_in(v)


def check_assign(A, errs, warns):
    seen, rseen = set(), set()
    for h in A.get("households", []):
        if h["hhid"] in seen:
            errs.append(f"household {h['hhid']} appears twice")
        seen.add(h["hhid"])
        for r in h.get("replacements", []) or []:
            if r["hhid"] in rseen:
                errs.append(f"replacement {r['hhid']} is listed for two households")
            rseen.add(r["hhid"])
    for r in rseen & seen:
        errs.append(f"replacement {r} is also a main household")
    cal = A.get("calendar", {})
    if cal.get("window_end", "") < cal.get("window_start", ""):
        errs.append("the window ends before it starts")
    if A.get("fingerprint"):
        if sha(canon({k: v for k, v in A.items() if k != "fingerprint"})) != A["fingerprint"]:
            warns.append("the fingerprint does not match: the file was changed after it was generated")
    else:
        warns.append("no fingerprint")


def check_calllog(J, errs, warns):
    bad = verify_chain(J.get("events", []), J.get("chain_genesis"))
    if bad:
        errs.append("hash chain: " + bad)
    ev = J.get("events", [])
    if (ev[-1]["hash"] if ev else J.get("chain_genesis")) != J.get("last_hash"):
        errs.append("last_hash is not the hash of the last event")
    if J.get("event_count") != len(ev):
        errs.append(f"event_count is {J.get('event_count')}, but {len(ev)} events are listed")
    dial_ids = {e["event_id"] for e in ev if e.get("type") == "dial"}
    missing = [d["event_id"] for d in J.get("dials", []) if d.get("event_id") not in dial_ids]
    if missing:
        errs.append(f"{len(missing)} dial rows point to no dial event")
    leaks = sorted(set(keys_in(J)) & FORBIDDEN_IN_LOG)
    if leaks:
        errs.append("privacy: the call log holds contact fields: " + ", ".join(leaks))


def check_contacts(C, errs, warns):
    for u in C.get("updates", []):
        if "number" in u and u.get("private_digest") != sha(canon({"number": u["number"]})):
            errs.append(f"the number for {u.get('hhid')} slot {u.get('slot')} does not match its digest")


def check_project(P, errs, warns):
    body = {k: v for k, v in P.items() if k != "checksum"}
    if sha(canon(body)) != P.get("checksum"):
        errs.append("the checksum does not match: the file was changed or damaged after it was saved")
    A = P.get("assignment") or {}
    if sha(canon({k: v for k, v in A.items() if k != "fingerprint"})) != P.get("assignment_fingerprint"):
        errs.append("the embedded assignment does not match assignment_fingerprint")
    bad = verify_chain(P.get("events", []), P.get("chain_genesis"))
    if bad:
        errs.append("hash chain: " + bad)
    a_errs, a_warns = [], []
    check_assign(A, a_errs, a_warns)
    errs.extend("embedded assignment: " + e for e in a_errs)


def check_manifest(M, errs, warns):
    if sha(canon({k: v for k, v in M.items() if k != "fingerprint"})) != M.get("fingerprint"):
        warns.append("the fingerprint does not match: the manifest was changed after it was written")
    ids = [h["hhid"] for h in M.get("households", [])]
    if len(ids) != len(set(ids)):
        errs.append("a household is listed twice")
    roster = {e["enumerator_id"] for e in M.get("enumerators", [])}
    stray = sorted({h["enumerator_id"] for h in M.get("households", [])} - roster)
    if stray:
        errs.append("households assigned to enumerators not in the roster: " + ", ".join(stray))
    for e in M.get("enumerators", []):
        n = sum(1 for h in M.get("households", []) if h["enumerator_id"] == e["enumerator_id"])
        if n != e["households"]:
            errs.append(f"{e['enumerator_id']}: the roster says {e['households']} households, the list has {n}")
    leaks = sorted(set(keys_in(M)) & {"number", "phones", "contact", "private"})
    if leaks:
        errs.append("privacy: the manifest holds contact fields: " + ", ".join(leaks))


def check_leader(P, errs, warns):
    body = {k: v for k, v in P.items() if k != "checksum"}
    if sha(canon(body)) != P.get("checksum"):
        errs.append("the checksum does not match: the file was changed or damaged after it was saved")
    bad = verify_chain(P.get("events", []), P.get("chain_genesis"))
    if bad:
        errs.append("the leader's log: " + bad)
    warns.append("holds contact information (the household list): keep it in the leader's own folder")


def other_csv(header, rows, errs, warns):
    """The leader's other tables, recognised by their columns. Returns a label, or None when the file is not one of them."""
    h = [c.strip().lower() for c in header]
    # the files of KoBoToolbox, Survey Solutions and a calling service (proposal K); a KoBo export is semicolon-separated, so its header arrives as one field
    joined = ";".join(header) if len(header) == 1 and ";" in header[0] else None
    if joined is not None:
        hk = [c.strip() for c in header[0].split(";")]
        if "_uuid" in hk and "hhid" in hk and "result" in hk:
            warns.append("a KoBoToolbox export of the call-record form: holds the numbers the form pulled in; for the leader's Import tab, never for the common folder")
            return "KoBoToolbox call-record export"
        if "_uuid" in hk and "hhid" in hk and "int_id" in hk and "X15" in hk:
            warns.append("a KoBoToolbox export in the L2PHL layout (one submission per call attempt): for the leader's Import tab, never for the common folder")
            return "KoBoToolbox export, L2PHL layout"
        if "_uuid" in hk and "hhid" in hk and "ocode" in hk and "agreement" in hk:
            warns.append("a KoBoToolbox export of an interview form (L2Taj layout): for the leader's Import tab, never for the common folder")
            return "KoBoToolbox interview export, L2Taj layout"
        if {"operator_id", "hh_id", "dialing_phone", "status", "start_time"} <= set(hk):
            warns.append("a call-center system's call log (L2Taj layout): holds phone numbers; for the leader's Import tab only, never re-exported")
            return "call-center system log, L2Taj layout"
        if {"callid", "hhid", "operator", "dialing_phone", "status", "start_time"} <= set(hk):
            warns.append("a call-center system's call log (L2CU layout): holds phone numbers; for the leader's Import tab only, never re-exported")
            return "call-center system log, L2CU layout"
        if hk[:3] == ["hhid", "operator", "enumerator_id"] and "date_nextcall" in hk and "replacement_for" in hk:
            warns.append("the call-center system's assignment table: holds phone numbers; it goes to the system only")
            return "call-center assignment table"
    if h[:4] == ["list_name", "name", "label", "filter_int_id"]:
        bad = [r for r in rows if r.get("list_name") != "SN"]
        if bad:
            errs.append(f"{len(bad)} row(s) whose list_name is not SN")
        ids = [r["name"] for r in rows]
        if len(ids) != len(set(ids)):
            errs.append("a household appears twice in the choices list")
        return f"KoBo choices list of households, {len(rows)} rows"
    if h[:3] == ["name", "label", "hhid"] and "enumerator_id" in h and "kind" in h:
        bad = [r for r in rows if r.get("kind") not in ("main", "replacement")]
        if bad:
            errs.append(f"{len(bad)} row(s) with a kind other than main or replacement")
        ids = [r["hhid"] for r in rows]
        if len(ids) != len(set(ids)):
            errs.append("a household appears twice in the household file")
        warns.append("the KoBo form's household file: holds phone numbers; it goes to the KoBoToolbox project's media only")
        return f"KoBo household file, {len(rows)} rows"
    hn = [c.replace(" ", "").replace("_", "") for c in h]
    if ("sid" in hn or "callsid" in hn) and "to" in hn and "status" in hn and ("starttime" in hn or "datecreated" in hn):
        warns.append("a calling service's call log: holds phone numbers; for the leader's Import tab only, never re-exported")
        return f"calling service log, {len(rows)} calls"
    if "_uuid" in h and "hhid" in h and "result" in h:
        warns.append("a KoBoToolbox export of the call-record form: holds the numbers the form pulled in; for the leader's Import tab, never for the common folder")
        return f"KoBoToolbox call-record export, {len(rows)} records"
    if header == ACOLS:
        bad = [r for r in rows if r["action"] not in ("RELEASE", "SWITCH_REQUEST", "REMOVE_REQUEST", "ACTIVATE_REPLACEMENT")]
        if bad:
            errs.append(f"{len(bad)} row(s) with an unknown action")
        return f"actions, {len(rows)} rows"
    if header == REPORT_COLS:
        return f"merge report, {len(rows)} rows"
    if h[:5] == ["model", "round", "hhid", "enumerator_id", "tier"]:
        if any(r["tier"] not in ("high", "medium", "low") for r in rows):
            errs.append("a tier other than high, medium or low")
        warns.append("a risk list: for the leader only, never for enumerators (D7)")
        return f"risk list, {len(rows)} households"
    if header == CONTACT_COLS:
        warns.append("holds phone numbers: give it to the leader directly, never through the common folder")
        return f"contact updates, {len(rows)} rows"
    if h == ["enumerator_id", "file", "passphrase"]:
        warns.append("holds passphrases: keep it private and give each enumerator only theirs")
        return "passphrase list"
    if h == ["round", "start", "end"]:
        if any(not (len(r["start"]) == 10 and len(r["end"]) == 10) for r in rows):
            errs.append("start and end must be YYYY-MM-DD")
        return "calendar.csv"
    if h[:2] == ["code", "meaning"]:
        return f"outcome codes, {len(rows)}"
    if h == ["hhid", "interview_date", "outcome", "enumerator"]:
        ids = [r["hhid"] for r in rows]
        if len(ids) != len(set(ids)):
            errs.append("a household appears twice (the round template needs one row per household)")
        if any(r["interview_date"] and not (len(r["interview_date"]) == 10 and r["interview_date"][4] == "-") for r in rows):
            errs.append("interview_date must be YYYY-MM-DD")
        return f"interviews.csv, {len(rows)} households"
    if {"unit_id", "stratum", "selected", "reserve"} <= set(h):
        sci = [r for r in rows if "e+" in str(r.get("unit_id", "")).lower()]
        if sci:
            errs.append(f"{len(sci)} IDs in scientific notation (as rtmtools wrote them before its fix of 27 October 2026): they cannot be matched")
        return f"rtmtools selection, {len(rows)} frame rows"
    if {"stratum", "n_units", "n_selected", "n_reserve"} <= set(h):
        warns.append("the sampling tool's draw summary (rtmtools): not read by this tool")
        return f"rtmtools draw summary, {len(rows)} strata"
    if {"hhid", "psu", "stratum"} <= set(h):
        ids = [r["hhid"] for r in rows]
        if len(ids) != len(set(ids)):
            errs.append("a household appears twice")
        st = {(r.get("status") or "active").strip().lower() for r in rows}
        if st - {"active", "removed", "reserve"}:
            errs.append("status must be active, removed or reserve")
        warns.append("holds contact information: never in the common folder")
        return f"household list, {len(rows)} households"
    return None


def unseal(env, passphrase):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kd, ci = env["kdf"], env["cipher"]
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(kd["salt"]), iterations=kd["iterations"]).derive(
        unicodedata.normalize("NFC", passphrase).encode("utf-8"))
    head = {k: env[k] for k in ("schema", "contains", "program", "round", "enumerator_id") if env.get(k) not in (None, "")}
    pt = AESGCM(key).decrypt(base64.b64decode(ci["iv"]), base64.b64decode(env["data"]), canon(head).encode("utf-8"))
    return json.loads(pt.decode("utf-8"))


def check_json(obj, passphrase, errs, warns):
    sid = obj.get("schema") if isinstance(obj, dict) else None
    if sid == "rtm-export-1.0":
        warns.append("a run manifest of the sampling tool (rtmtools), kept beside its selection: not an interview-tool file, not checked here")
        return sid
    if sid not in SCHEMAS:
        errs.append(f"not an interview-tool file (schema {sid!r})")
        return sid
    errs.extend(schema_errors(obj, sid))
    if errs:
        return sid
    if sid == "rtm-assign-1.0":
        check_assign(obj, errs, warns)
    elif sid == "rtm-calllog-1.0":
        check_calllog(obj, errs, warns)
    elif sid == "rtm-contacts-1.0":
        check_contacts(obj, errs, warns)
    elif sid == "rtm-project-1.0":
        check_project(obj, errs, warns)
    elif sid == "rtm-roundmanifest-1.0":
        check_manifest(obj, errs, warns)
    elif sid == "rtm-leader-1.0":
        check_leader(obj, errs, warns)
    elif sid == "rtm-sealed-1.0":
        if not passphrase:
            warns.append(f"protected ({obj['contains']}): envelope checked; give a passphrase to check the content")
        else:
            try:
                inner = unseal(obj, passphrase)
            except Exception:
                errs.append("the passphrase does not open it, or the file was changed after it was protected")
                return sid
            if inner.get("schema") != obj["contains"]:
                errs.append("the protected content is not what its label says")
            else:
                ie, iw = [], []
                check_json(inner, None, ie, iw)
                errs.extend("content: " + e for e in ie)
                warns.extend("content: " + w for w in iw)
    return sid


def typed_row(r):
    return {k: (int(v) if k in INT_COLS and v != "" else v) for k, v in r.items()}


def check_csv(path, errs, warns):
    text = open(path, encoding="utf-8").read()
    if text.startswith("﻿"):
        errs.append("the CSV starts with a byte-order mark")
        text = text[1:]
    header = text.split("\n", 1)[0].strip("\r").split(",")
    if header != COLS:
        label = other_csv(header, list(csv.DictReader(io.StringIO(text))), errs, warns)
        if label is None:
            errs.append("not one of the tool's tables: the header is not a call log, actions, report, calendar, interviews, household list or selection")
        return label
    rows = list(csv.DictReader(io.StringIO(text)))
    # the row schema's $refs point inside the call-log schema, so it is reached through the registry
    v = Draft202012Validator({"$ref": "urn:rtm:schema:rtm-calllog-1.0#/$defs/dial_row"}, registry=REGISTRY)
    for i, r in enumerate(rows):
        try:
            tr = typed_row(r)
        except ValueError:
            errs.append(f"row {i + 2}: a whole-number column holds text")
            continue
        for e in v.iter_errors(tr):
            errs.append(f"row {i + 2}: {'/'.join(str(x) for x in e.absolute_path)}: {e.message[:150]}")
            break
    companion = path[:-4] + ".json"
    if os.path.exists(companion):
        J = json.load(open(companion, encoding="utf-8"))
        if J.get("schema") == "rtm-calllog-1.0":
            want = [{k: ("" if d.get(k) is None else str(d.get(k))) for k in COLS} for d in J.get("dials", [])]
            if want != [{k: r[k] for k in COLS} for r in rows]:
                errs.append(f"the rows differ from the dial rows of {os.path.basename(companion)}")
    elif re.search(r"_R\d+_calls\.csv$", os.path.basename(path)) or os.path.basename(path).startswith("expected_"):
        pass   # a merged call log: each export's chain was checked when it was merged
    else:
        warns.append("unverified: no JSON export beside it, so its hash chain cannot be checked")
    return len(rows)


def files_of(args):
    for a in args:
        if os.path.isdir(a):
            for p in sorted(glob.glob(os.path.join(a, "**", "*"), recursive=True)):
                if p.endswith((".json", ".csv")) and not p.endswith(".schema.json"):
                    yield p
        else:
            yield a


def main(argv):
    ask = "--ask-passphrase" in argv
    args = [a for a in argv if a != "--ask-passphrase"]
    if not args:
        print(__doc__)
        return 2
    passphrase = os.environ.get("RTM_PASSPHRASE") or (getpass.getpass("Passphrase for protected files: ") if ask else None)
    n_err = 0
    for p in files_of(args):
        errs, warns = [], []
        if p.endswith(".csv"):
            n = check_csv(p, errs, warns)
            kind = n if isinstance(n, str) else (f"call log CSV, {n} rows" if n is not None else "CSV")
        else:
            try:
                obj = json.load(open(p, encoding="utf-8"))
            except ValueError:
                errs.append("not readable JSON")
                obj, kind = None, "?"
            if obj is not None:
                kind = check_json(obj, passphrase, errs, warns)
        n_err += bool(errs)
        print(f"{'ERROR' if errs else 'OK   '} {p}  [{kind}]")
        for e in errs:
            print("      error:   " + e)
        for w in warns:
            print("      warning: " + w)
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
