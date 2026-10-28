"""An independent, plain-Python implementation of the handbook's call-log rules, used to check the leader view's analytics.

Written from the handbook's scripts as documented (10_build_attempts.py finish_cases; 11_s33_attempts.py; 12_s31_enumerators.py;
15_s35_scheduling.py; 20d_s36_benchmarks.py), not from the tool's JavaScript. It reads the merged calls files the leader view exports.
"""
import csv
import datetime as dt
import io
import math
import statistics


def jsround(x, scale):
    return int(math.floor(x * scale + 0.5))


def read_calls(paths):
    rows = []
    for p in paths:
        if not p.endswith("_calls.csv"):
            continue
        rows += list(csv.DictReader(open(p, encoding="utf-8")))
    return rows


def interviewed_per_round_strict(paths):
    """Box 3.0 as the text states it: a household is interviewed in a round when a complete-coded dial lasted 3 minutes or more
    (or has no recorded length). This is what the tool uses for a household's last interview."""
    out = {}
    for r in read_calls(paths):
        if r["status"] == "COMPLETE" and (r["dur_min"] == "" or float(r["dur_min"]) >= 3):
            out.setdefault(int(r["round"]), set()).add(r["hhid"])
    return [[k, len(v)] for k, v in sorted(out.items())]


def completes_by_enumerator(calls_text, manifest):
    """Households of the round with a qualifying complete, by the enumerator who holds them (activated replacements: who dialled)."""
    rows = list(csv.DictReader(io.StringIO(calls_text)))
    holder = {h["hhid"]: h["enumerator_id"] for h in manifest["households"]}
    for r in rows:
        if r["replaces"] and r["hhid"] not in holder:
            holder[r["hhid"]] = r["operator"]
    done = {}
    for r in sorted(rows, key=lambda r: (r["hhid"], r["ts"])):
        if r["status"] == "COMPLETE" and (r["dur_min"] == "" or float(r["dur_min"]) >= 3) and r["hhid"] in holder:
            done.setdefault(r["hhid"], holder[r["hhid"]])
    out = {e["enumerator_id"]: 0 for e in manifest["enumerators"]}
    for h, e in done.items():
        out[e] = out.get(e, 0) + 1
    return out


def build(rows):
    """finish_cases: drop incomplete rows, de-duplicate, order, clock errors, the 3-minute flag with its fallback, delete dials after the complete."""
    d = []
    seen = set()
    for i, r in enumerate(rows):
        if not r["hhid"] or not r["round"] or not r["ts"]:
            continue
        key = (r["hhid"], int(r["round"]), r["ts"], r["status"])
        if key in seen:
            continue
        seen.add(key)
        dur = float(r["dur_min"]) if r["dur_min"] != "" else None
        d.append({"hhid": r["hhid"], "round": int(r["round"]), "ts": r["ts"], "status": r["status"], "cmp_code": r["status"] == "COMPLETE",
                  "dur": dur, "op": r["operator"], "seq": i, "date": dt.date.fromisoformat(r["ts"][:10]), "hour": int(r["ts"][11:13]), "minute": int(r["ts"][14:16])})
    d.sort(key=lambda x: (x["hhid"], x["round"], x["ts"], x["seq"]))
    med = {}
    for rnd in {x["round"] for x in d}:
        ords = [x["date"].toordinal() for x in d if x["round"] == rnd]
        med[rnd] = statistics.median(ords)
    d = [x for x in d if math.floor(abs(x["date"].toordinal() - med[x["round"]])) <= 90]
    for x in d:
        x["is_cmp"] = x["cmp_code"] and x["dur"] is not None and x["dur"] >= 3.0
    cases = {}
    for x in d:
        cases.setdefault((x["hhid"], x["round"]), []).append(x)
    kept, table = [], {}
    fallbacks = 0
    for key, ds in cases.items():
        prev, day = None, 0
        for i, x in enumerate(ds):
            x["attempt"] = i + 1
            if x["date"] != prev:
                day += 1
            x["day_idx"] = day
            prev = x["date"]
        q = next((x["attempt"] for x in ds if x["is_cmp"]), None)
        f = next((x["attempt"] for x in ds if x["cmp_code"]), None)
        k = q if q is not None else f
        if q is None and f is not None:
            fallbacks += 1
        if k is not None:
            ds = ds[:k]
        for x in ds:
            x["ok"] = x["attempt"] == k
            kept.append(x)
        table[key] = {"hhid": key[0], "round": key[1], "n_att": len(ds), "k": k, "n_days": ds[-1]["day_idx"], "dials": ds}
    return kept, table, fallbacks


def reference(paths):
    rows = read_calls(paths)
    kept, cases, fallbacks = build(rows)
    rounds = sorted({c["round"] for c in cases.values()})
    out = {"cases": len(cases), "dials": len(kept), "fallbacks": fallbacks}
    done = [c for c in cases.values() if c["k"] is not None]
    out["dpc"] = sum(c["n_att"] for c in cases.values()) / len(done)
    out["byRound"] = [[r, sum(1 for c in cases.values() if c["round"] == r), sum(1 for c in done if c["round"] == r),
                       sum(c["n_att"] for c in cases.values() if c["round"] == r)] for r in rounds]
    out["hazard"] = [[k, sum(1 for c in cases.values() if c["n_att"] >= k), sum(1 for c in done if (c["k"] == k if k < 20 else c["k"] >= 20))] for k in range(1, 9)]
    # continuation: interviewed = a completed case (the scripts' rule)
    sets = {r: {c["hhid"] for c in done if c["round"] == r} for r in rounds}
    out["cont"] = [[a, b, len(sets[a]), jsround(len(sets[a] & sets[b]) / len(sets[a]), 1e6)] for a, b in zip(rounds, rounds[1:]) if b == a + 1]
    # 3.3.5: completed in r-1, dialled and not completed in r, r+1 in the data; redialled in r+1
    dset = {(c["hhid"], c["round"]) for c in cases.values()}
    cset = {(c["hhid"], c["round"]) for c in done}
    lost = [c for c in cases.values() if (c["hhid"], c["round"] - 1) in cset and c["k"] is None and (c["round"] + 1) in rounds]
    out["missed"] = [len(lost), sum(1 for c in lost if (c["hhid"], c["round"] + 1) in dset)]
    # 3.1: enumerator-days, durations below 0 or above 120 replaced by the median of the same kind of dial, missing = 0
    d31 = [dict(x) for x in kept if x["op"].strip() not in ("", "nan", "None")]
    bad = lambda x: x["dur"] is not None and (x["dur"] < 0 or x["dur"] > 120)
    med = {kind: statistics.median([x["dur"] for x in d31 if x["ok"] == kind and x["dur"] is not None and not bad(x)] or [0]) for kind in (True, False)}
    for x in d31:
        x["min"] = 0 if x["dur"] is None else (med[x["ok"]] if bad(x) else x["dur"])
    od = {}
    for x in d31:
        k = (x["round"], x["op"].strip(), x["date"])
        o = od.setdefault(k, {"cmp": 0, "talk": 0.0})
        o["cmp"] += 1 if x["ok"] else 0
        o["talk"] += x["min"]
    out["od"] = len(od)
    out["cpd"] = jsround(sum(o["cmp"] for o in od.values()) / len(od), 1e6)
    att = []
    for r in rounds:
        days = [k for k in od if k[0] == r]
        ops = {k[1] for k in days}
        fw = {x["date"] for x in d31 if x["round"] == r}
        att.append(len(days) / (len(ops) * len(fw)))
    out["att"] = jsround(statistics.median(att), 1e6)
    out["mpc"] = jsround(sum(o["talk"] for o in od.values()) / sum(o["cmp"] for o in od.values()), 1e4)
    # 3.5.1: hours with at least 50 dials
    hours = {}
    for x in kept:
        h = hours.setdefault(x["hour"], [0, 0])
        h[0] += 1
        h[1] += 1 if x["ok"] else 0
    out["hours"] = [[h, v[0], v[1] if v[0] >= 50 else None] for h, v in sorted(hours.items())]
    # 3.5.2 and 3.5.3: first dial of round r against the start of round r-1's completing dial
    comp = {(c["hhid"], c["round"] + 1): c["dials"][c["k"] - 1] for c in done}
    same, n_cont, bins = 0, 0, [0, 0, 0]
    for c in cases.values():
        prev = comp.get((c["hhid"], c["round"]))
        if not prev:
            continue
        f = c["dials"][0]
        diff = abs((f["hour"] + f["minute"] / 60) - (prev["hour"] + prev["minute"] / 60))
        gap = min(diff, 24 - diff)
        bins[0 if gap <= 1 else 1 if gap <= 3 else 2] += 1
        norm = lambda s: s.strip().replace("_", "").upper()
        if f["op"].strip() and prev["op"].strip():
            n_cont += 1
            same += 1 if norm(f["op"]) == norm(prev["op"]) else 0
    out["same"] = bins
    out["cont35"] = [n_cont, jsround(same / n_cont, 1e6)]
    return out
