"""Synthetic sample files for the interview tool: one imaginary program, rounds 1 to 5. Nothing here is real.

The program "L2MN-DEMO" runs monthly rounds on Mongolia's calendar with four enumerators (E01, E02, E03, E07).
Rounds 1-4 are simulated in full; round 5 (26 Oct - 20 Nov 2026) is in progress, with E03 away. Every file
is written as the tool itself writes it: the same canonical JSON, SHA-256 hash chain and column order as
src/core.js and src/leader_core.js, so the browser's checks on these files also test the two implementations.

Writes:
  leader/household_list.csv                 the round-5 household list (proposal A.1), mains, replacements, refreshment
  leader/selection.csv                      the round-1 phone-sample draw, as rtmtools exports it (A.2)
  leader/history/L2MN-DEMO_R0k_*            rounds 1-4 as the leader view exports them: calls, actions, manifest
  leader/L2MN-DEMO_R05_manifest.json        the round-5 roster (A.6)
  leader/exports_R05/                       each enumerator's round-5 export of Friday 6 November (A.4)
  leader/merge_cases/                       damaged, duplicate, early, wrong-round and conflicting files (F)
  round05/E0k_assignment_R05.json           the round-5 assignment files (A.3)
  round05/E07_project_R05.json              E07's saved session on 27 October at 12:30 (A.5)
  past/E07_2026-10-21.csv and .json         E07's round-4 export, for the enumerator's performance view
Phone numbers use the invalid country code +000, so none can be dialed by mistake.
Run:  python3 samples/make_samples.py
"""
import copy
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import shutil
import tempfile
import uuid
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSION = "0.3.0"
PROGRAM, COUNTRY, TZNAME = "L2MN-DEMO", "MN", "Asia/Ulaanbaatar"
TZ = dt.timezone(dt.timedelta(hours=8))
OFF = "+08:00"
rng = random.Random(20261027)
WORK = [1, 2, 3, 4, 5, 6]                      # Monday to Saturday
CALL_HOURS = {"start": 9, "end": 21}
CAP = 8
WINDOWS = {1: ("2026-06-29", "2026-07-22"), 2: ("2026-07-27", "2026-08-19"), 3: ("2026-08-31", "2026-09-23"),
           4: ("2026-09-28", "2026-10-21"), 5: ("2026-10-26", "2026-11-20")}
TEAM = ["E01", "E02", "E03", "E07"]
AWAY = {3: ["E02"], 5: ["E03"]}                 # E02 away in round 3, E03 in round 5
ROTATION = 0.10
SEED = 20261027
NOW5 = dt.datetime(2026, 11, 6, 18, 0, tzinfo=TZ)        # the round-5 exports
EARLY7 = dt.datetime(2026, 10, 30, 18, 0, tzinfo=TZ)     # E07's earlier round-5 export
PROJECT_AT = dt.datetime(2026, 10, 27, 12, 30, tzinfo=TZ)  # E07's saved session
COLS = ["program", "round", "hhid", "attempt", "ts", "end_ts", "utc_offset", "dur_min", "status", "is_cmp_code", "operator", "phone_slot",
        "appointment_ts", "action", "replaces", "note", "corrected", "logged_by", "logged_at", "event_id", "prev_hash"]
ACOLS = ["program", "round", "hhid", "action", "target_hhid", "reason", "note", "via", "logged_by", "logged_at", "event_id"]
INT_COLS = ("round", "attempt", "is_cmp_code", "phone_slot", "corrected")


# ---- canonical JSON and hashing, as in src/core.js ----
def clean(d):
    return {k: v for k, v in d.items() if v is not None and v != ""}


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fingerprint(a):
    return sha(canon({k: v for k, v in a.items() if k != "fingerprint"}))


def uid():
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S") + OFF


def parse(s):
    return dt.datetime.fromisoformat(s)


def day(s):
    return dt.date.fromisoformat(s)


class Log:
    """An append-only event log with the hash chain of RTM.append."""
    def __init__(self, rnd, enum, genesis):
        self.round, self.enum, self.events, self.genesis = rnd, enum, [], genesis

    def append(self, typ, fields, logged_at, private=None, event_id=None):
        prev = self.events[-1]["hash"] if self.events else self.genesis
        e = {"event_id": event_id or uid(), "type": typ, "program": PROGRAM, "round": self.round}
        e.update(fields)
        e.update({"logged_by": self.enum, "logged_at": iso(logged_at) if isinstance(logged_at, dt.datetime) else logged_at, "prev_hash": prev})
        e = clean(e)
        if private:
            e["private_digest"] = sha(canon(clean(private)))
        e["hash"] = sha(canon({k: v for k, v in e.items() if k not in ("hash", "private")}))
        if private:
            e["private"] = clean(private)
        self.events.append(e)
        return e


# ---- the effective log and export rows, as RTM.effective and RTM.dialRow ----
def effective(events):
    by_id, dials, actions, contacts = {}, [], [], []
    for e in events:
        if e["type"] == "dial":
            d = dict(e, corrected=0); by_id[e["event_id"]] = d; dials.append(d)
        elif e["type"] == "action":
            a = dict(e, corrected=0); by_id[e["event_id"]] = a; actions.append(a)
        elif e["type"] == "contact_update":
            contacts.append(e)
    for e in events:
        if e["type"] != "correction" or e["target"] not in by_id:
            continue
        t = by_id[e["target"]]
        if e.get("void"):
            t["void"] = True
        else:
            t.update(e.get("changes", {}))
        t["corrected"] = 1
    live = sorted([d for d in dials if not d.get("void")], key=lambda d: (d["hhid"], parse(d["ts"]), d["logged_at"]))
    n = {}
    for d in live:
        n[d["hhid"]] = n.get(d["hhid"], 0) + 1
        d["attempt"] = n[d["hhid"]]
        d["dur_min"] = max(0.0, (parse(d["end_ts"]) - parse(d["ts"])).total_seconds() / 60) if d.get("end_ts") else None
    standalone = [a for a in actions if not a.get("void")]
    via = [{"event_id": d["event_id"], "type": "action", "hhid": d["hhid"], "action": d["action"], "logged_by": d["logged_by"],
            "logged_at": d["logged_at"], "via": "dial", "round": d["round"], "program": d["program"]} for d in live if d.get("action")]
    return live, standalone, via, contacts


def wall(s):
    return s[:19].replace("T", " ") if s else ""


def dial_row(d, attempt=None):
    return {"program": d["program"], "round": d["round"], "hhid": d["hhid"], "attempt": attempt or d["attempt"],
            "ts": wall(d["ts"]), "end_ts": wall(d.get("end_ts")), "utc_offset": d["ts"][19:] if len(d["ts"]) > 19 else "",
            "dur_min": "" if d.get("dur_min") is None else f"{d['dur_min']:.2f}", "status": d["status"],
            "is_cmp_code": 1 if d["status"] == "COMPLETE" else 0, "operator": d.get("operator") or d["logged_by"],
            "phone_slot": d["phone_slot"], "appointment_ts": wall(d.get("appointment_ts")), "action": d.get("action", ""),
            "replaces": d.get("replaces", ""), "note": d.get("note", ""), "corrected": 1 if d.get("corrected") else 0,
            "logged_by": d["logged_by"], "logged_at": d["logged_at"], "event_id": d["event_id"], "prev_hash": d["prev_hash"]}


def write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})


def write_json(path, o, indent=1):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=indent)


# ---- calendar ----
def bundled_holidays():
    s = open(os.path.join(ROOT, "src", "holidays_data.js"), encoding="utf-8").read()
    return json.loads(s[s.index("{"): s.rindex("}") + 1])["table"][COUNTRY]


HOLS = bundled_holidays()


DAY_LIST = {}      # round -> the day list the leader view would write: 1.5 x the busiest enumerator's first dials per day (set by plan_round)


def calendar(r):
    a, b = WINDOWS[r]
    hol = [{"date": d, "name": n, "estimated": bool(e), "working": False} for d, n, e in HOLS if a <= d <= b]
    c = {"window_start": a, "window_end": b, "working_weekdays": WORK, "call_hours": CALL_HOURS, "time_zone": TZNAME,
         "holidays": hol, "dial_cap": CAP}
    if r in DAY_LIST:
        c["day_list"] = DAY_LIST[r]
    return c


def working_days(r):
    a, b = WINDOWS[r]
    hol = {d for d, _, _ in HOLS}
    d, out = day(a), []
    while d <= day(b):
        if d.isoweekday() in WORK and d.isoformat() not in hol:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ---- households ----
LABELS = ["respondent", "spouse", "son or daughter"]


def phone(p, s, slot):
    return f"+000 {p:02d}{s:03d} {slot}{rng.randint(100, 999)}"


def make_households():
    H = {}
    for p in range(1, 13):
        psu, stratum = f"01{p:02d}", "1" if p <= 6 else "2"
        for s in range(1, 10):
            hid = f"{psu}-{s:03d}"
            nph = rng.choices([1, 2, 3], weights=[6, 3, 1] if s <= 3 else [3, 5, 2])[0]
            H[hid] = {"hhid": hid, "psu": psu, "stratum": stratum, "kind": "main", "rank": s, "joined": 1, "status": "active",
                      "name": f"Contact {hid} (synthetic)", "phones": [{"slot": k, "number": phone(p, s, k), "label": LABELS[k - 1]} for k in range(1, nph + 1)]}
        for r in (1, 2, 3):
            hid = f"{psu}-{100 + r:03d}"
            H[hid] = {"hhid": hid, "psu": psu, "stratum": stratum, "kind": "reserve", "reserve": r, "joined": None, "status": "reserve",
                      "name": f"Reserve {hid} (synthetic)", "phones": [{"slot": 1, "number": phone(p, 100 + r, 1), "label": "respondent"}]}
    for s in range(1, 7):                     # a refreshment sample that joins in round 5
        hid = f"0113-{s:03d}"
        H[hid] = {"hhid": hid, "psu": "0113", "stratum": "2", "kind": "refresh", "joined": 5, "status": "active",
                  "name": f"Contact {hid} (synthetic)", "phones": [{"slot": 1, "number": phone(13, s, 1), "label": "respondent"}]}
    for h in H.values():                      # latent traits that drive the simulated dials
        h["p"] = rng.choice([0.16, 0.24, 0.32, 0.45])
        h["h_pref"] = rng.choices(range(9, 21), weights=[2, 3, 4, 4, 5, 5, 6, 7, 9, 11, 10, 6])[0]
        h["drop_round"] = rng.choices([None, 2, 3, 4, 5, 6], weights=[70, 9, 6, 5, 5, 5])[0]
        h["drop_type"] = rng.choice(["gone", "gone", "refuse"])
        h["miss"] = {r for r in range(1, 6) if rng.random() < 0.08}
        h["death"] = {ph["slot"]: (rng.choice([2, 3, 4, 5]) if rng.random() < 0.07 else None) for ph in h["phones"]}
        h["repl"], h["used_repl"] = [], []
    # D6: each PSU's ordered reserve dealt round-robin to its main households in selection order
    for p in range(1, 13):
        psu = f"01{p:02d}"
        mains = sorted([h for h in H.values() if h["psu"] == psu and h["kind"] == "main"], key=lambda h: h["rank"])
        for res in sorted([h for h in H.values() if h["psu"] == psu and h["kind"] == "reserve"], key=lambda h: h["reserve"]):
            mains[(res["reserve"] - 1) % len(mains)]["repl"].append(res["hhid"])
    return H


# ---- history, as the leader view computes it from earlier rounds ----
class History:
    def __init__(self):
        self.dials = {}       # round -> list of merged effective dials
        self.actions = {}     # round -> list of actions
        self.roster = {}      # round -> {hhid: enumerator}
        self._cmp = {}

    def completes(self, r):
        if r in self._cmp:
            return self._cmp[r]
        out = {}
        for d in sorted(self.dials.get(r, []), key=lambda d: (parse(d["ts"]), d["logged_at"])):
            if d["status"] == "COMPLETE" and (d["dur_min"] is None or d["dur_min"] >= 3) and d["hhid"] not in out:
                out[d["hhid"]] = d
        if r in self.dials:
            self._cmp[r] = out
        return out

    def summary(self, hid, t, joined):
        last = None
        for r in range(t - 1, 0, -1):
            c = self.completes(r).get(hid)
            if c:
                ts = parse(c["ts"])
                last = {"round": r, "date": ts.date().isoformat(), "hour": ts.hour, "enum": c["operator"]}
                break
        last3 = None
        if joined and joined < t:
            last3 = [(hid in self.completes(r)) if r >= joined else None for r in (t - 3, t - 2, t - 1)]
        prev = self.roster.get(t - 1, {}).get(hid)
        dials_last = sum(1 for d in self.dials.get(t - 1, []) if d["hhid"] == hid)
        switch = any(a["hhid"] == hid and a["action"] == "SWITCH_REQUEST" for a in self.actions.get(t - 1, []))
        slot_last = {}
        for d in sorted([d for d in self.dials.get(t - 1, []) if d["hhid"] == hid], key=lambda d: parse(d["ts"])):
            slot_last[d["phone_slot"]] = d["status"]
        return {"last": last, "last3": last3, "prev": prev, "dials_last": dials_last, "switch": switch, "slot_last": slot_last,
                "interviewed_last": hid in self.completes(t - 1)}


# ---- assignment (proposal C), a plain version of the rule the leader view applies ----
def deal(hids, enums, R, exclude=None):
    """Sort by stratum and a seeded key, then deal by largest deficit, skipping each household's excluded enumerator."""
    exclude = exclude or {}
    keyed = sorted(hids, key=lambda h: (H[h]["stratum"], R.random()))
    target = {e: len(keyed) / len(enums) for e in enums}
    got = {e: 0 for e in enums}
    out = {}
    for i, h in enumerate(keyed, 1):
        allowed = [e for e in enums if e != exclude.get(h)] or enums
        e = max(allowed, key=lambda e: (target[e] * i / len(keyed) - got[e], -enums.index(e)))
        out[h] = e
        got[e] += 1
    return out


def assign_round(t, roster_ids, hist):
    enums = [e for e in TEAM if e not in AWAY.get(t, [])]
    R = random.Random(SEED * 10 + t)
    out = {}
    if t == 1:
        for h, e in deal(roster_ids, enums, R).items():
            out[h] = (e, "new", None)
        return out
    pending_new, pending_away, pending_switch = [], [], []
    for h in roster_ids:
        s = hist.summary(h, t, H[h]["joined"])
        start = (s["last"] or {}).get("enum") or s["prev"]
        if start is None:
            pending_new.append(h)
        elif start not in enums:
            pending_away.append((h, start))
        elif (not s["interviewed_last"] and s["dials_last"] >= CAP) or s["switch"]:
            pending_switch.append((h, start))
        else:
            out[h] = (start, "keep", None)
    for h, e in deal(pending_new, enums, R).items():
        out[h] = (e, "new", None)
    for h, e in deal([h for h, _ in pending_away], enums, R).items():
        out[h] = (e, "enumerator_unavailable", dict(pending_away)[h])
    prev = dict(pending_switch)
    for h, e in deal(list(prev), enums, R, exclude=prev).items():
        out[h] = (e, "switch_hard_to_reach", prev[h])
    rot = {}
    for e in enums:
        kept = sorted(h for h, (x, reason, _) in out.items() if x == e and reason == "keep")
        for h in R.sample(kept, round(ROTATION * len(kept))):
            rot[h] = e
    for h, e in deal(list(rot), enums, R, exclude=rot).items():
        out[h] = (e, "rotation", rot[h])
    return out


def plan_round(t, assigned, hist):
    """First dials spread over the first half of the working days; new, switched and single-number households first (D)."""
    days = working_days(t)
    first = days[: (len(days) + 1) // 2]
    plans = {}
    by_enum = {}
    for h, (e, reason, _) in assigned.items():
        by_enum.setdefault(e, []).append(h)
    DAY_LIST[t] = max(1, math.ceil(1.5 * max(len(hs) for hs in by_enum.values()) / len(first)))
    for e, hs in by_enum.items():
        def pri(h):
            s = hist.summary(h, t, H[h]["joined"])
            return (0 if (s["last"] is None or assigned[h][1] == "switch_hard_to_reach") else 1, 0 if len(H[h]["phones"]) == 1 else 1, h)
        hs = sorted(hs, key=pri)
        for i, h in enumerate(hs):
            s = hist.summary(h, t, H[h]["joined"])
            hour = (s["last"] or {}).get("hour")
            hour = hour if hour is not None else CALL_HOURS["start"] + (i % (CALL_HOURS["end"] - CALL_HOURS["start"]))
            plans[h] = {"first_dial_date": first[i * len(first) // len(hs)].isoformat(), "target_hour": hour}
    return plans


# ---- dials ----
HOUR_F = {9: .55, 10: .65, 11: .7, 12: .7, 13: .7, 14: .75, 15: .8, 16: .9, 17: 1.0, 18: 1.15, 19: 1.25, 20: 1.1}
OTHER = [("APPOINTMENT", 20), ("NOT_AVAILABLE", 14), ("NO_ANSWER", 34), ("BUSY", 8), ("SWITCHED_OFF", 15), ("REFUSAL_SOFT", 5), ("LANGUAGE", 1), ("OTHER", 3)]


def pick(pairs):
    return rng.choices([a for a, _ in pairs], weights=[w for _, w in pairs])[0]


def simulate_household(h, enum, t, plan, days, stop_at, out, replaces=None):
    """Appends (logged_at, type, fields, private) to out; returns 'complete', 'refused', 'dead', 'released' or 'open'."""
    fate = "gone" if (h["drop_round"] and h["drop_round"] <= t) else ("miss" if t in h["miss"] else "ok")
    if fate == "gone" and h["drop_type"] == "refuse":
        fate = "refuse"
    di = next((i for i, d in enumerate(days) if d.isoformat() >= plan["first_dial_date"]), len(days))
    hour, minute = plan["target_hour"], rng.randint(0, 45)
    dead, k, last_ev, result = set(), 0, None, "open"
    while k < CAP and di < len(days):
        hour = max(CALL_HOURS["start"], min(CALL_HOURS["end"] - 1, hour))
        t0 = dt.datetime.combine(days[di], dt.time(hour, minute, rng.randint(0, 59)), tzinfo=TZ)
        if stop_at and t0 >= stop_at:
            break
        alive = [p["slot"] for p in h["phones"] if p["slot"] not in dead]
        if not alive:
            break
        slot = alive[0]
        k += 1
        if h["death"].get(slot) and h["death"][slot] <= t:
            status = "DEAD_NUMBER"; dead.add(slot)
        elif fate == "gone":
            status = pick([("NO_ANSWER", 55), ("SWITCHED_OFF", 35), ("BUSY", 10)])
        elif fate == "refuse":
            status = "REFUSAL_HARD" if rng.random() < 0.6 else pick([("NO_ANSWER", 60), ("SWITCHED_OFF", 40)])
        elif fate == "miss":
            status = pick([("NO_ANSWER", 45), ("SWITCHED_OFF", 25), ("NOT_AVAILABLE", 15), ("APPOINTMENT", 10), ("BUSY", 5)])
        else:
            q = h["p"] * HOUR_F.get(hour, .7) * (1.5 if abs(hour - h["h_pref"]) <= 1 else 1.0)
            status = "COMPLETE" if rng.random() < q else pick(OTHER)
        if status == "COMPLETE":
            dur = rng.uniform(1.5, 2.9) if rng.random() < 0.02 else rng.uniform(9, 24)
        elif status in ("DEAD_NUMBER", "NO_ANSWER", "BUSY", "SWITCHED_OFF"):
            dur = rng.uniform(0.2, 0.8)
        else:
            dur = rng.uniform(0.5, 2.5)
        end = t0 + dt.timedelta(minutes=dur)
        appt = None
        if status == "APPOINTMENT":
            same = h["h_pref"] >= hour + 2 and h["h_pref"] < CALL_HOURS["end"]
            appt = dt.datetime.combine(days[di] if same or di + 1 >= len(days) else days[di + 1], dt.time(h["h_pref"], 0), tzinfo=TZ)
        fields = {"hhid": h["hhid"], "phone_slot": slot, "ts": iso(t0), "end_ts": iso(end), "status": status, "operator": enum,
                  "appointment_ts": iso(appt) if appt else None, "replaces": replaces,
                  "note": "said to call in the evening" if status == "APPOINTMENT" and rng.random() < .3 else ("someone else answered" if status == "OTHER" else None)}
        last_ev = (end + dt.timedelta(seconds=rng.randint(5, 40)), "dial", fields, None)
        out.append(last_ev)
        if status == "COMPLETE":
            result = "complete"
            if len(h["phones"]) < 3 and rng.random() < 0.06:
                slot_new = len(h["phones"]) + 1
                num = phone(int(h["psu"][2:]), int(h["hhid"][5:]), slot_new)
                out.append((last_ev[0] + dt.timedelta(minutes=1), "contact_update", {"hhid": h["hhid"], "slot": slot_new, "change": "add", "label": LABELS[slot_new - 1]}, {"number": num}))
                h["phones"].append({"slot": slot_new, "number": num, "label": LABELS[slot_new - 1]})
                h["death"][slot_new] = None
            break
        if status == "REFUSAL_HARD":
            result = "refused"
            break
        if fate in ("gone", "miss") and k >= 4 and rng.random() < 0.15:
            fields["action"] = "RELEASE"; result = "released"
            break
        if appt:
            di += 1 if appt.date() > t0.date() else 0
            hour, minute = appt.hour, rng.randint(0, 10)
        elif hour + 2 < CALL_HOURS["end"] - 1 and rng.random() < 0.45:
            hour, minute = hour + rng.choice([2, 3]), rng.randint(0, 45)
        else:
            di += rng.choice([1, 1, 2]); hour, minute = plan["target_hour"] + rng.choice([-1, 0, 0, 1]), rng.randint(0, 45)
    if result == "open":
        if not [p for p in h["phones"] if p["slot"] not in dead]:
            result = "dead"
        elif k >= CAP and last_ev and rng.random() < 0.7:
            last_ev[2]["action"] = "RELEASE"; result = "released"
    return result, k, (last_ev[0] if last_ev else None)


def simulate_round(t, assigned, plans, stop_at=None):
    """Returns {enum: [(logged_at, type, fields, private)]}; activates replacements and updates statuses."""
    days = working_days(t)
    ev = {e: [] for e in set(e for e, _, _ in assigned.values())}
    order = sorted(assigned, key=lambda h: (plans[h]["first_dial_date"], plans[h]["target_hour"], h))
    for hid in order:
        e = assigned[hid][0]
        h = H[hid]
        result, k, last_at = simulate_household(h, e, t, plans[hid], days, stop_at, ev[e], replaces=h.get("replaces") if h.get("joined") == t else None)
        if last_at is None:
            continue
        if result in ("refused", "dead"):
            spare = [r for r in h["repl"] if r not in h["used_repl"]]
            if spare:
                r = spare[0]
                h["used_repl"].append(r)
                ev[e].append((last_at + dt.timedelta(minutes=1), "action", {"hhid": hid, "action": "ACTIVATE_REPLACEMENT", "target_hhid": r,
                                                                             "reason": "hard refusal" if result == "refused" else "no working number"}, None))
                rh = H[r]
                rh.update({"joined": t, "status": "active", "kind": "activated", "replaces": hid})
                h["status_next"] = "removed"
                nxt = next((d for d in days if d > last_at.date()), None)
                if nxt:
                    plan = {"first_dial_date": nxt.isoformat(), "target_hour": rng.randint(10, 19)}
                    simulate_household(rh, e, t, plan, days, stop_at, ev[e], replaces=hid)
                    assigned[r] = (e, "replacement", None)
                    plans[r] = plan
            elif result == "dead":
                ev[e].append((last_at + dt.timedelta(minutes=1), "action", {"hhid": hid, "action": "REMOVE_REQUEST", "reason": "no number works"}, None))
                h["status_next"] = "removed"
        elif result != "complete" and t == 4 and k >= CAP - 2 and rng.random() < 0.5:
            ev[e].append((last_at + dt.timedelta(minutes=2), "action", {"hhid": hid, "action": "SWITCH_REQUEST", "reason": "never at home when I call"}, None))
    return ev


def build_log(t, e, genesis, file_name, specs, start_day, n_fix, n_void, cutoff, checkpoints=()):
    """The enumerator's log in logging order: dials, actions and a few later corrections, each event appended at its time.
    A checkpoint (time, function) runs when the log reaches that time, as an export does."""
    specs = [dict(at=at, typ=typ, fields=fields, private=private, id=uid()) for at, typ, fields, private in specs]
    dials = [x for x in specs if x["typ"] == "dial"]
    fixes = rng.sample(dials, min(n_fix, len(dials)))
    for x in fixes:
        specs.append(dict(at=x["at"] + dt.timedelta(hours=rng.randint(1, 6)), typ="correction", private=None, id=uid(),
                          fields={"target": x["id"], "changes": {"note": "corrected after checking the paper log"}, "reason": "note added later"}))
    voidable = [x for x in dials if x["fields"]["status"] != "COMPLETE" and x not in fixes and not x["fields"].get("action")]
    for x in rng.sample(voidable, min(n_void, len(voidable))):
        specs.append(dict(at=x["at"] + dt.timedelta(minutes=rng.randint(5, 50)), typ="correction", private=None, id=uid(),
                          fields={"target": x["id"], "void": 1, "reason": "logged on the wrong household"}))
    specs = [x for x in specs if x["at"] <= cutoff]
    log = Log(t, e, genesis)
    log.append("session", {"what": "started", "fingerprint": genesis, "fingerprint_ok": 1, "file": file_name},
               dt.datetime.combine(start_day, dt.time(8, rng.randint(40, 59)), tzinfo=TZ))
    cps = sorted(checkpoints, key=lambda c: c[0])
    for x in sorted(specs, key=lambda x: (x["at"], x["typ"] != "dial", x["id"])):
        while cps and cps[0][0] < x["at"]:
            cps.pop(0)[1](log)
        log.append(x["typ"], clean(x["fields"]), x["at"], x["private"], event_id=x["id"])
    for c in cps:
        c[1](log)
    return log


# ---- files, as the tool writes them ----
def assignment_file(t, e, assigned, plans, hist, generated_at):
    hs = []
    for hid in sorted(h for h, (x, reason, _) in assigned.items() if x == e and reason != "replacement"):
        h, (_, reason, prev) = H[hid], assigned[hid]
        s = hist.summary(hid, t, h["joined"])
        phones = [clean({"slot": p["slot"], "number": p["number"], "label": p["label"], "last_status": s["slot_last"].get(p["slot"])}) for p in h["phones"]]
        last = {k: v for k, v in (s["last"] or {}).items() if k != "enum"} or None
        reps = [{"hhid": r, "rank": i + 1, "contact": {"name": H[r]["name"], "phones": [clean(dict(p)) for p in H[r]["phones"]]}}
                for i, r in enumerate([r for r in h["repl"] if r not in h["used_repl"]])]
        hs.append(clean({
            "hhid": hid, "psu": h["psu"], "stratum": h["stratum"],
            "contact": {"name": h["name"], "phones": phones},
            "history": clean({"joined_round": h["joined"], "last_interview": last, "last3": s["last3"], "last_enumerator": (s["last"] or {}).get("enum")}),
            "assignment": clean({"reason": reason, "previous_enumerator": prev}),
            "plan": plans[hid], "replacements": reps or None,
        }))
    a = {"schema": "rtm-assign-1.0", "tool_version": VERSION, "program": PROGRAM, "country": COUNTRY, "round": t, "enumerator_id": e,
         "generated_by": "L01", "generated_at": generated_at,
         "rule": {"name": "keep_same" if t > 1 else "random", "rotation_share": ROTATION if t > 1 else None, "hard_to_reach": "missed_with_full_cap_or_request" if t > 1 else None,
                  "fallback": "random" if t > 1 else None, "seed": SEED},
         "replacement_policy": {"active": True, "triggers": ["REFUSAL_HARD", "ALL_NUMBERS_DEAD"]},
         "synthetic": True, "note": "SYNTHETIC sample for trying the tool. No real household, name or phone number.",
         "calendar": calendar(t), "households": hs}
    a["rule"] = clean(a["rule"])
    a["fingerprint"] = fingerprint(a)
    return a


def manifest(t, assigned, files, generated_at):
    enums = sorted(files)
    hh = [clean({"hhid": hid, "enumerator_id": e, "reason": reason, "previous_enumerator": prev, "psu": H[hid]["psu"], "stratum": H[hid]["stratum"],
                 "replacements": [r for r in H[hid]["repl"] if r not in H[hid]["used_repl_at"].get(t, [])] or None})
          for hid, (e, reason, prev) in sorted(assigned.items()) if reason != "replacement"]
    m = {"schema": "rtm-roundmanifest-1.0", "tool_version": VERSION, "program": PROGRAM, "country": COUNTRY, "round": t,
         "generated_by": "L01", "generated_at": generated_at, "synthetic": True,
         "rule": files[enums[0]]["rule"], "replacement_policy": files[enums[0]]["replacement_policy"], "calendar": calendar(t),
         "away": AWAY.get(t, []),
         "enumerators": [{"enumerator_id": e, "available": True, "share": round(1 / len(enums), 4), "households": len(files[e]["households"]),
                          "file": f"{e}_assignment_R{t:02d}.json", "fingerprint": files[e]["fingerprint"]} for e in enums],
         "households": hh}
    m["fingerprint"] = fingerprint(m)
    return m


def export_json(log, t, e, a_fp, at, contacts_name):
    live, standalone, via, contacts = effective(log.events)
    rows = [dial_row(d) for d in live]
    pub = [{k: v for k, v in x.items() if k != "private"} for x in log.events]
    return {"schema": "rtm-calllog-1.0", "tool_version": VERSION, "program": PROGRAM, "country": COUNTRY, "round": t, "enumerator_id": e,
            "assignment_fingerprint": a_fp, "chain_genesis": log.genesis, "exported_at": iso(at), "exported_by": e,
            "event_count": len(log.events), "last_hash": log.events[-1]["hash"] if log.events else log.genesis, "chain_verified": True,
            "contains_contact_information": False, "contacts_file": contacts_name if contacts else None,
            "events": pub, "dials": rows,
            "actions": [clean({k: a.get(k) for k in ("event_id", "hhid", "action", "target_hhid", "reason", "note", "logged_by", "logged_at")}) for a in standalone],
            "corrections": [x for x in pub if x["type"] == "correction"],
            "contact_updates": [clean({k: c.get(k) for k in ("event_id", "hhid", "slot", "change", "label", "private_digest", "logged_by", "logged_at")}) for c in contacts]}, rows, contacts


def write_export(folder, log, t, e, a_fp, at):
    base = f"{e}_{at.date().isoformat()}"
    j, rows, contacts = export_json(log, t, e, a_fp, at, base + "_contacts.json")
    write_json(os.path.join(folder, base + ".json"), j)
    write_csv(os.path.join(folder, base + ".csv"), rows, COLS)
    if contacts:
        write_json(os.path.join(folder, base + "_contacts.json"), {
            "schema": "rtm-contacts-1.0", "tool_version": VERSION, "program": PROGRAM, "round": t, "enumerator_id": e, "exported_at": iso(at),
            "contains_contact_information": True, "note": "Contains phone numbers. Give this file to your team leader directly; do not put it in the common folder.",
            "updates": [clean({"event_id": c["event_id"], "hhid": c["hhid"], "slot": c["slot"], "change": c["change"], "label": c.get("label"),
                               "number": c.get("private", {}).get("number"), "private_digest": c.get("private_digest"), "logged_by": c["logged_by"], "logged_at": c["logged_at"]}) for c in contacts]})
    log.append("export", clean({"file_base": base, "event_count": len(log.events), "last_hash": log.events[-1]["hash"], "contacts_file": 1 if contacts else None}), at)
    return base, j


def merged(logs):
    """The leader's merged round: every enumerator's effective dials, attempt counted per household across enumerators."""
    dials, acts = [], []
    for log in logs:
        live, standalone, via, _ = effective(log.events)
        dials += live
        acts += [dict(a, via="") for a in standalone] + via
    dials.sort(key=lambda d: (d["hhid"], parse(d["ts"]), d["logged_at"], d["event_id"]))
    n, rows = {}, []
    for d in dials:
        n[d["hhid"]] = n.get(d["hhid"], 0) + 1
        rows.append(dial_row(d, n[d["hhid"]]))
    acts.sort(key=lambda a: (a["logged_at"], a["event_id"]))
    arows = [{"program": PROGRAM, "round": a["round"], "hhid": a["hhid"], "action": a["action"], "target_hhid": a.get("target_hhid", ""),
              "reason": a.get("reason", ""), "note": a.get("note", ""), "via": a.get("via", ""), "logged_by": a["logged_by"],
              "logged_at": a["logged_at"], "event_id": a["event_id"]} for a in acts]
    return dials, rows, acts, arows


def copy_log(log):
    c = Log(log.round, log.enum, log.genesis)
    c.events = copy.deepcopy(log.events)
    return c


KAZAKH_PSUS = {"0105", "0111"}     # two PSUs where the interview language is Kazakh: the leader's matching criterion (language)

# ---- the same round-5 calls as a KoBoToolbox export, a Survey Solutions export and a calling service's log (proposal K) ----
HH_COLS = ["name", "label", "hhid", "enumerator_id", "program", "round", "contact_name", "phone_1", "phone_1_label", "phone_2", "phone_2_label", "phone_3", "phone_3_label",
           "planned_date", "planned_hour", "psu", "stratum", "kind", "replaces", "rank"]
KOBO_COLS = ["start", "end", "deviceid", "enumerator_id", "hhid", "program", "round", "contact_name", "phone_1", "phone_1_label", "phone_2", "phone_2_label", "phone_3", "phone_3_label",
             "planned_date", "planned_hour", "replaces", "psu", "stratum", "phone_slot", "call_start", "call_end", "result", "willing", "appointment", "action", "target_hhid", "note",
             "_id", "_uuid", "_submission_time", "_validation_status", "_notes", "_status", "_submitted_by", "__version__", "_tags", "_index"]
SUSO_ASSIGN_COLS = ["hhid", "enumerator_id", "program", "round", "contact_name", "phone_1", "phone_1_label", "phone_2", "phone_2_label", "phone_3", "phone_3_label", "planned_date", "planned_hour",
                    "psu", "stratum", "replacement_1", "replacement_1_name", "replacement_1_phone", "replacement_2", "replacement_2_name", "replacement_2_phone", "_responsible", "_quantity"]
SUSO_MAIN_COLS = ["interview__key", "interview__id", "hhid", "enumerator_id", "program", "round", "contact_name", "phone_1", "phone_1_label", "phone_2", "phone_2_label", "phone_3", "phone_3_label",
                  "planned_date", "planned_hour", "psu", "stratum", "interview__status", "has_errors", "ssSys_IRnd"]
SUSO_CALL_COLS = ["interview__key", "interview__id", "calls__id", "phone_slot", "call_start", "call_end", "result", "willing", "appointment", "action", "target_hhid", "replaces", "note"]
SVC_COLS = ["sid", "date_created", "start_time", "end_time", "duration", "from", "to", "status", "direction", "price", "price_unit"]
WILLING = {"COMPLETE": "yes", "APPOINTMENT": "later", "PARTIAL": "later", "NOT_AVAILABLE": "later", "REFUSAL_SOFT": "no", "REFUSAL_HARD": "no", "LANGUAGE": "not_asked", "OTHER": "not_asked"}
SVC_STATUS = {"COMPLETE": "completed", "APPOINTMENT": "completed", "PARTIAL": "completed", "NOT_AVAILABLE": "completed", "REFUSAL_SOFT": "completed", "REFUSAL_HARD": "completed",
              "LANGUAGE": "completed", "OTHER": "completed", "WRONG_NUMBER": "completed", "NO_ANSWER": "no-answer", "BUSY": "busy", "SWITCHED_OFF": "no-answer", "DEAD_NUMBER": "failed"}
CENTER_LINE = "+000 11 000 0100"


def kobo_dt(s):
    """A KoboToolbox datetime answer: 2026-11-06T17:15:30.000+08:00."""
    if not s:
        return ""
    t = parse(s)
    z = t.strftime("%z")
    return t.strftime("%Y-%m-%dT%H:%M:%S.000") + z[:3] + ":" + z[3:]


def utc_naive(s):
    return parse(s).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def rfc2822(s):
    return parse(s).astimezone(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def write_tsv(path, rows, cols):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join("" if r.get(c) is None else str(r.get(c)).replace("\t", " ") for c in cols) + "\n")


def write_platform_samples(out, logs, files):
    """households.csv and assignments.tab as the leader view writes them for round 5; the enumerators' round-5 calls up to the
    6 November export as a KoBoToolbox CSV export (one submission per call), a Survey Solutions export (one interview per
    household, the calls in a roster) and a Twilio-style call log of the calling service; all from the same simulated events."""
    r2 = random.Random(SEED + 5000)              # a stream of its own: every other sample stays as it was
    contact = {}                                 # hhid -> (name, {slot: (number, label)}), mains and replacements
    hh_rows, as_rows, by_e = [], [], {}
    for e, a in sorted(files.items()):
        for h in a["households"]:
            ph = {p["slot"]: (p["number"], p["label"]) for p in h["contact"]["phones"]}
            contact[h["hhid"]] = (h["contact"]["name"], ph)
            c = {f"phone_{s}": ph[s][0] for s in ph} | {f"phone_{s}_label": ph[s][1] for s in ph}
            base = {"hhid": h["hhid"], "enumerator_id": e, "program": PROGRAM, "round": 5, "contact_name": h["contact"]["name"], "planned_date": h["plan"]["first_dial_date"],
                    "planned_hour": h["plan"]["target_hour"], "psu": h["psu"], "stratum": h["stratum"]}
            by_e[h["hhid"]] = e
            hh_rows.append({"name": h["hhid"], "label": f"{h['hhid']} · {h['contact']['name']}", **base, **c, "kind": "main", "replaces": "", "rank": ""})
            reps = h.get("replacements", [])
            for i, r in enumerate(reps):
                rph = {p["slot"]: (p["number"], p.get("label", "")) for p in r["contact"]["phones"]}
                contact[r["hhid"]] = (r["contact"]["name"], rph)
                by_e[r["hhid"]] = e
                hh_rows.append({"name": r["hhid"], "label": f"{r['hhid']} · {r['contact']['name']} (replacement {i + 1} for {h['hhid']})", "hhid": r["hhid"], "enumerator_id": e,
                                "program": PROGRAM, "round": 5, "contact_name": r["contact"]["name"], "planned_date": "", "planned_hour": "", "psu": h["psu"], "stratum": h["stratum"],
                                **{f"phone_{s}": rph[s][0] for s in rph}, **{f"phone_{s}_label": rph[s][1] for s in rph}, "kind": "replacement", "replaces": h["hhid"], "rank": i + 1})
            row = {**base, **c, "_responsible": e, "_quantity": 1}
            for i, r in enumerate(reps[:2]):
                row[f"replacement_{i + 1}"] = r["hhid"]; row[f"replacement_{i + 1}_name"] = r["contact"]["name"]; row[f"replacement_{i + 1}_phone"] = r["contact"]["phones"][0]["number"]
            as_rows.append(row)
    write_csv(os.path.join(out["kobo"], "households.csv"), hh_rows, HH_COLS)
    write_tsv(os.path.join(out["suso"], "assignments.tab"), as_rows, SUSO_ASSIGN_COLS)
    # the calls, from each enumerator's effective log at the time of the 6 November export
    kobo, mains, calls, svc = [], [], [], []
    n_id = 1000
    for e, log in sorted(logs.items()):
        live, standalone, via, _ = effective(log.events)
        recs = [dict(d, _kind="dial") for d in live] + [dict(a, _kind="action") for a in standalone]
        recs.sort(key=lambda x: (x.get("ts") or x["logged_at"], x["event_id"]))
        per_hh = {}
        for x in recs:
            hid = x["hhid"]
            name, ph = contact.get(hid, (f"Contact {hid}", {}))
            c = {f"phone_{s}": ph[s][0] for s in ph} | {f"phone_{s}_label": ph[s][1] for s in ph}
            planned = next((h for h in files[e]["households"] if h["hhid"] == hid), None)
            common = {"enumerator_id": e, "hhid": hid, "program": PROGRAM, "round": 5, "contact_name": name, **c, "psu": H[hid]["psu"] if hid in H else "", "stratum": H[hid]["stratum"] if hid in H else "",
                      "planned_date": planned["plan"]["first_dial_date"] if planned else "", "planned_hour": planned["plan"]["target_hour"] if planned else ""}
            n_id += 1
            if x["_kind"] == "dial":
                blank_end = x["status"] != "COMPLETE" and x.get("end_ts") and r2.random() < 0.08      # a call end the enumerator forgot: the service's log fills it
                rec = {"phone_slot": x["phone_slot"], "call_start": x["ts"], "call_end": "" if blank_end else (x.get("end_ts") or ""), "result": x["status"], "willing": WILLING.get(x["status"], ""),
                       "appointment": x.get("appointment_ts", ""), "action": x.get("action") or "none", "target_hhid": "", "replaces": x.get("replaces", ""), "note": x.get("note", "")}
                if x.get("end_ts") and x["event_id"] not in {} and r2.random() < 0.95:             # the calling service saw this call
                    number = ph.get(x["phone_slot"], ("", ""))[0]
                    if number:
                        dur = int((parse(x["end_ts"]) - parse(x["ts"])).total_seconds())
                        svc.append({"sid": "CA" + "".join(r2.choice("0123456789abcdef") for _ in range(32)), "date_created": rfc2822(x["ts"]), "start_time": rfc2822(x["ts"]),
                                    "end_time": rfc2822(x["end_ts"]) if SVC_STATUS.get(x["status"]) == "completed" else "", "duration": dur if SVC_STATUS.get(x["status"]) == "completed" else "",
                                    "from": CENTER_LINE, "to": number, "status": SVC_STATUS.get(x["status"], "completed"), "direction": "outbound-api",
                                    "price": f"-{max(dur, 60) / 60 * 0.014:.4f}" if SVC_STATUS.get(x["status"]) == "completed" else "", "price_unit": "USD"})
            else:
                rec = {"phone_slot": "", "call_start": "", "call_end": "", "result": "NONE", "willing": "", "appointment": "", "action": x["action"], "target_hhid": x.get("target_hhid", ""),
                       "replaces": "", "note": x.get("note", "")}
            logged = x["logged_at"]
            kobo.append({**common, "start": kobo_dt(rec["call_start"] or logged), "end": kobo_dt(logged), "deviceid": f"collect:{e}dev", **{k: (kobo_dt(v) if k in ("call_start", "call_end", "appointment") else v) for k, v in rec.items()},
                         "_id": n_id, "_uuid": x["event_id"], "_submission_time": utc_naive(logged), "_validation_status": "", "_notes": "", "_status": "submitted_via_web",
                         "_submitted_by": e, "__version__": "vK3xRtmCallRecord2026110101", "_tags": "", "_index": len(kobo) + 1})
            per_hh.setdefault(hid, {"common": common, "calls": [], "complete": False})
            per_hh[hid]["calls"].append(rec)
            if x["_kind"] == "dial" and x["status"] == "COMPLETE":
                per_hh[hid]["complete"] = True
        for hid, p in sorted(per_hh.items()):
            key = "-".join(f"{r2.randint(0, 99):02d}" for _ in range(4))
            iid = "".join(r2.choice("0123456789abcdef") for _ in range(32))
            mains.append({**p["common"], "interview__key": key, "interview__id": iid, "interview__status": 100 if p["complete"] else 65, "has_errors": 0, "ssSys_IRnd": round(r2.random(), 6)})
            for i, rec in enumerate(p["calls"], start=1):
                calls.append({"interview__key": key, "interview__id": iid, "calls__id": i, **{k: (parse(v).strftime("%Y-%m-%dT%H:%M:%S") if k in ("call_start", "call_end", "appointment") and v else v) for k, v in rec.items()}})
    # three calls the service saw that nobody recorded, and two calls to numbers outside the list
    for hid in r2.sample(sorted(h for h in by_e if contact[h][1]), 3):
        at = dt.datetime(2026, 11, 5, r2.randint(10, 19), r2.randint(0, 59), r2.randint(0, 59), tzinfo=TZ)
        svc.append({"sid": "CA" + "".join(r2.choice("0123456789abcdef") for _ in range(32)), "date_created": rfc2822(iso(at)), "start_time": rfc2822(iso(at)), "end_time": "", "duration": "",
                    "from": CENTER_LINE, "to": contact[hid][1][1][0], "status": "no-answer", "direction": "outbound-api", "price": "", "price_unit": "USD"})
    for k in (1, 2):
        at = dt.datetime(2026, 11, 4, 11 + k, 5, 0, tzinfo=TZ)
        svc.append({"sid": "CA" + "".join(r2.choice("0123456789abcdef") for _ in range(32)), "date_created": rfc2822(iso(at)), "start_time": rfc2822(iso(at)), "end_time": rfc2822(iso(at + dt.timedelta(seconds=40))),
                    "duration": 40, "from": CENTER_LINE, "to": f"+000 99 999 990{k}", "status": "completed", "direction": "outbound-api", "price": "-0.0093", "price_unit": "USD"})
    svc.sort(key=lambda r: parse(dt.datetime.strptime(r["start_time"], "%a, %d %b %Y %H:%M:%S %z").isoformat()))
    kobo.sort(key=lambda r: r["_submission_time"])
    for i, r in enumerate(kobo, start=1):
        r["_index"] = i
    with open(os.path.join(out["kobo"], "rtm_call_record_2026-11-06.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KOBO_COLS, delimiter=";", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in kobo:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in KOBO_COLS})
    write_tsv(os.path.join(out["suso"], "rtm_call_record.tab"), mains, SUSO_MAIN_COLS)
    write_tsv(os.path.join(out["suso"], "calls.tab"), calls, SUSO_CALL_COLS)
    with zipfile.ZipFile(os.path.join(out["suso"], "rtm_call_record_export.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(out["suso"], "rtm_call_record.tab"), "rtm_call_record.tab")
        z.write(os.path.join(out["suso"], "calls.tab"), "calls.tab")
        z.writestr("export__readme.txt", "SYNTHETIC export of the questionnaire RTM call record (L2MN-DEMO round 5), in the layout of a Survey Solutions tabular export. No real household.\n")
    write_csv(os.path.join(out["calls"], "service_calls_2026-11-06.csv"), svc, SVC_COLS)
    print(f"kobo/households.csv: {len(hh_rows)} rows; kobo/rtm_call_record_2026-11-06.csv: {len(kobo)} submissions; suso: {len(mains)} interviews, {len(calls)} call records; "
          f"calls/service_calls_2026-11-06.csv: {len(svc)} calls")


def write_household_list(out):
    """The leader's household list (A.1) as it stands when round 5 is prepared. Two columns beyond the standard ones,
    language and respondent_sex, let the leader try the matching criteria; they come from a stream of their own, so every
    other sample stays as it was."""
    sex_rng = random.Random(SEED + 2026)
    hl = []
    for hid in sorted(H):
        h = H[hid]
        row = {"hhid": hid, "psu": h["psu"], "stratum": h["stratum"], "contact_name": h["name"], "language": "kk" if h["psu"] in KAZAKH_PSUS else "mn",
               "respondent_sex": sex_rng.choice(["f", "f", "m"]), "status": h["status"]}
        for p in h["phones"]:
            row[f"phone_{p['slot']}"] = p["number"]
            row[f"phone_{p['slot']}_label"] = p["label"]
        hl.append(row)
    write_csv(os.path.join(out["leader"], "household_list.csv"), hl,
              ["hhid", "psu", "stratum", "contact_name", "phone_1", "phone_1_label", "phone_2", "phone_2_label", "phone_3", "phone_3_label", "language", "respondent_sex", "status"])
    print(f"leader/household_list.csv: {len(hl)} households")


def main():
    global H
    H = make_households()
    for h in H.values():
        h["used_repl_at"] = {}
    out = {k: os.path.join(HERE, k) for k in ("leader", "round05", "past", "leader/history", "leader/exports_R05", "leader/merge_cases", "kobo", "suso", "calls")}
    for p in out.values():
        os.makedirs(p, exist_ok=True)
    for sub_ in ("leader/merge_cases", "leader/exports_R05", "leader/history"):
        shutil.rmtree(out[sub_])
        os.makedirs(out[sub_])
    hist = History()
    for t in range(1, 6):
        roster_ids = sorted(hid for hid, h in H.items() if h["status"] == "active" and h["joined"] is not None and h["joined"] <= t)
        assigned = assign_round(t, roster_ids, hist)
        plans = plan_round(t, assigned, hist)
        gen_at = dt.datetime.combine(day(WINDOWS[t][0]) - dt.timedelta(days=3), dt.time(16, 5), tzinfo=TZ)
        for h in H.values():
            h["used_repl_at"][t] = list(h["used_repl"])
        files = {e: assignment_file(t, e, assigned, plans, hist, iso(gen_at)) for e in sorted(set(x for x, _, _ in assigned.values()))}
        man = manifest(t, assigned, files, iso(gen_at))
        if t == 5:
            write_household_list(out)
        stop = NOW5 - dt.timedelta(minutes=40) if t == 5 else None
        events = simulate_round(t, assigned, plans, stop_at=stop)
        round_end = dt.datetime.combine(day(WINDOWS[t][1]), dt.time(21, 30), tzinfo=TZ)
        cutoff = NOW5 if t == 5 else round_end
        logs = {}
        early_dir = os.path.join(out["leader/merge_cases"], "early_export")
        for e in sorted(files):
            cps = []
            if t == 5 and e == "E07":
                os.makedirs(early_dir, exist_ok=True)
                cps = [(EARLY7, lambda log, f=files[e]: write_export(early_dir, log, 5, "E07", f["fingerprint"], EARLY7))]
            logs[e] = build_log(t, e, files[e]["fingerprint"], f"{e}_assignment_R{t:02d}.json", events.get(e, []), day(WINDOWS[t][0]),
                                2 if t < 5 else 1, 1, cutoff, cps)
        if t < 5:
            write_export(out["past"], logs["E07"], 4, "E07", files["E07"]["fingerprint"], round_end) if t == 4 else None
            dials, rows, acts, arows = merged(logs.values())
            hist.dials[t], hist.actions[t] = dials, acts
            hist.roster[t] = {hid: x for hid, (x, _, _) in assigned.items()}
            write_csv(os.path.join(out["leader/history"], f"{PROGRAM}_R{t:02d}_calls.csv"), rows, COLS)
            write_csv(os.path.join(out["leader/history"], f"{PROGRAM}_R{t:02d}_actions.csv"), arows, ACOLS)
            write_json(os.path.join(out["leader/history"], f"{PROGRAM}_R{t:02d}_manifest.json"), man)
            for h in H.values():
                if h.pop("status_next", None) == "removed":
                    h["status"] = "removed"
            print(f"round {t}: {len(roster_ids)} households, {len(rows)} dials, {len(hist.completes(t))} interviewed, "
                  f"{sum(a['action'] == 'ACTIVATE_REPLACEMENT' for a in acts)} replacements activated, away {AWAY.get(t, [])}")
            continue
        # ---- round 5: assignment files, the manifest, E07's saved session and everyone's export of 6 November ----
        for e, a in files.items():
            write_json(os.path.join(out["round05"], f"{e}_assignment_R05.json"), a)
            print(f"round05/{e}_assignment_R05.json: {len(a['households'])} households, {sum(len(h.get('replacements', [])) for h in a['households'])} replacements, "
                  f"reasons {sorted(set(h['assignment']['reason'] for h in a['households']))}")
        write_json(os.path.join(out["leader"], f"{PROGRAM}_R05_manifest.json"), man)
        e7 = logs["E07"]
        prefix = [x for x in e7.events if x["logged_at"] <= iso(PROJECT_AT)]
        past_rows = [{k: str(v) for k, v in r.items()} for r in json.load(open(os.path.join(out["past"], "E07_2026-10-21.json"), encoding="utf-8"))["dials"]]
        proj = {"schema": "rtm-project-1.0", "tool_version": VERSION, "saved_at": iso(PROJECT_AT), "saved_by": "E07",
                "assignment": files["E07"], "assignment_fingerprint": files["E07"]["fingerprint"], "chain_genesis": files["E07"]["fingerprint"],
                "events": prefix, "past": {"files": [{"name": "E07_2026-10-21.json", "round": 4, "rows": len(past_rows), "added": len(past_rows)}], "dials": past_rows},
                "ui": {}, "last_export": None}
        proj["checksum"] = sha(canon(proj))
        write_json(os.path.join(out["round05"], "E07_project_R05.json"), proj)
        print(f"round05/E07_project_R05.json: {len(prefix)} events saved 27 Oct 12:30")
        exports = {}
        for e, log in sorted(logs.items()):
            assert all(x["logged_at"] <= iso(NOW5) for x in log.events), e
            base, j = write_export(out["leader/exports_R05"], log, 5, e, files[e]["fingerprint"], NOW5)
            exports[e] = (base, j)
            print(f"leader/exports_R05/{base}: {len(j['dials'])} dials, {len(j['events'])} events")
        dials, rows, acts, arows = merged(logs.values())
        write_csv(os.path.join(out["leader"], "expected_R05_calls.csv"), rows, COLS)
        write_csv(os.path.join(out["leader"], "expected_R05_actions.csv"), arows, ACOLS)
        write_platform_samples(out, logs, files)
        # ---- the merge cases (proposal F) ----
        mc = out["leader/merge_cases"]
        for d in ("duplicate", "csv_only", "wrong_round", "edited", "conflict"):
            os.makedirs(os.path.join(mc, d))
        shutil.copy(os.path.join(out["leader/exports_R05"], exports["E02"][0] + ".json"), os.path.join(mc, "duplicate", exports["E02"][0] + " (1).json"))
        # a later export of E02 the same day, whose JSON did not reach the common folder: only its CSV (F: used, as unverified)
        saved = rng.getstate()                        # its IDs come from a stream of their own, so every other sample stays as it was
        rng.seed(20261106)
        c2 = copy_log(logs["E02"])
        done2 = {d["hhid"] for d in effective(c2.events)[0] if d["status"] == "COMPLETE"}
        h2 = next(h["hhid"] for h in files["E02"]["households"] if h["hhid"] not in done2)
        t2 = dt.datetime(2026, 11, 6, 18, 20, tzinfo=TZ)
        c2.append("dial", {"hhid": h2, "phone_slot": 1, "ts": iso(t2), "end_ts": iso(t2 + dt.timedelta(minutes=1)), "status": "NO_ANSWER", "operator": "E02"},
                  t2 + dt.timedelta(minutes=1))
        with tempfile.TemporaryDirectory() as tmp:
            base2, _ = write_export(tmp, c2, 5, "E02", files["E02"]["fingerprint"], dt.datetime(2026, 11, 6, 18, 40, tzinfo=TZ))
            shutil.copy(os.path.join(tmp, base2 + ".csv"), os.path.join(mc, "csv_only", base2 + ".csv"))
        rng.setstate(saved)
        shutil.copy(os.path.join(out["past"], "E07_2026-10-21.json"), os.path.join(mc, "wrong_round", "E07_2026-10-21.json"))
        j = copy.deepcopy(exports["E01"][1])          # one dial's status changed after export: the chain breaks
        ev = next(x for x in j["events"] if x["type"] == "dial" and x["status"] != "COMPLETE")
        ev["status"] = "COMPLETE"
        write_json(os.path.join(mc, "edited", exports["E01"][0] + ".json"), j)
        e2_done = sorted(d["hhid"] for d in effective(logs["E02"].events)[0] if d["status"] == "COMPLETE" and (d["dur_min"] or 0) >= 3)
        target = e2_done[0]                           # E01 logs a complete on a household E02 completed: a typed ID
        c1 = copy_log(logs["E01"])
        t0 = dt.datetime(2026, 11, 6, 18, 40, tzinfo=TZ)
        c1.append("dial", {"hhid": target, "phone_slot": 1, "ts": iso(t0), "end_ts": iso(t0 + dt.timedelta(minutes=14)), "status": "COMPLETE", "operator": "E01"},
                  t0 + dt.timedelta(minutes=15))
        write_export(os.path.join(mc, "conflict"), c1, 5, "E01", files["E01"]["fingerprint"], dt.datetime(2026, 11, 6, 19, 0, tzinfo=TZ))
        print(f"leader/merge_cases: duplicate, csv_only, wrong_round, edited, early_export, conflict (E01 logs {target}, which E02 completed)")
    sel, order = [], 0
    for p in range(1, 13):
        psu = f"01{p:02d}"
        frame = sorted([h for h in H.values() if h["psu"] == psu and h["kind"] in ("main", "reserve", "activated")], key=lambda h: h["hhid"])
        for x in frame + [{"hhid": f"{psu}-{300 + i:03d}"} for i in range(1, 6)]:   # five frame households neither selected nor reserved
            order += 1
            main_ = x.get("rank") is not None
            res = x.get("reserve")
            sel.append({"unit_id": x["hhid"], "stratum": psu, "size": 1, "order": order, "key": f"{rng.random():.6f}", "cum_size": order,
                        "selection_number": x["rank"] if main_ else "", "selected": 1 if main_ else 0, "reserve": res or 0,
                        "rank": x["rank"] if main_ else "", "prob": f"{9 / 17:.6f}", "weight": f"{17 / 9:.6f}", "x": "", "y": ""})
    write_csv(os.path.join(out["leader"], "selection.csv"), sel,
              ["unit_id", "stratum", "size", "order", "key", "cum_size", "selection_number", "selected", "reserve", "rank", "prob", "weight", "x", "y"])
    print(f"leader/selection.csv: {len(sel)} frame rows")


if __name__ == "__main__":
    main()
