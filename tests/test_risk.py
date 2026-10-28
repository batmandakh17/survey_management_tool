"""Step 4: the risk models in the leader view, checked against the training script's own code (tests/ref_risk.py).

Run from the tool folder:  python3 tests/test_risk.py
Writes tests/results_risk.txt and screenshots tests/screens/risk_*.png.
"""
import csv
import glob
import json
import math
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from cdp import Browser  # noqa: E402
import ref_risk  # noqa: E402

SCRATCH = os.environ.get("RTM_SCRATCH", os.path.join(HERE, "_work"))
SCREENS = os.path.join(HERE, "screens")
STAMP = time.strftime("%H%M%S")
DL = os.path.join(SCRATCH, f"rdl_{STAMP}")
S = os.path.join(ROOT, "samples", "leader")
HIST = sorted(glob.glob(os.path.join(S, "history", "*")))
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:700]}]" if detail and not ok else ""))


def close(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    model = ref_risk.MODEL
    D, Rr = ref_risk.features(HIST)
    dk = [f["key"] for f in model["dropout"]["features"]]
    rk = [f["key"] for f in model["return"]["features"]]
    py_d, py_r = ref_risk.rows_of(D, dk), ref_risk.rows_of(Rr, rk)
    check("the reference has rows to compare: every interviewed household-round, and every miss after an interview", len(py_d) > 300 and len(py_r) > 30, [len(py_d), len(py_r)])
    for p in ("risk_models.json", "validation.json"):
        txt = open(os.path.join(ROOT, "models", p)).read()
        check(f"models/{p} holds aggregates only: no household ID field", '"hhid"' not in txt and "hhid" not in json.loads(txt).keys())
    b = Browser(os.path.join(SCRATCH, f"rprofile_{STAMP}"), port=9346)
    try:
        b.downloads_to(DL)
        b.goto("file://" + os.path.join(ROOT, "rtm_interview_tool.html"))
        b.js("RTM.setNow('2026-10-23T15:00:00+08:00'); APP.noFSA = true; true")
        b.click('[data-act="view"][data-v="leader"]'); b.wait("!!document.querySelector('#lstart')")
        b.js("""(() => { const f = document.querySelector('#lstart'); f.querySelector('[name=leader]').value = 'L01'; f.querySelector('[name=program]').value = 'L2MN-DEMO';
               f.querySelector('[name=country]').value = 'MN'; f.querySelector('[name=round]').value = '5'; return true; })()""")
        b.click('[data-lact="start"]'); b.wait("!!LEAD.state()")
        b.set_files("#lf-hh", [os.path.join(S, "household_list.csv")]); b.wait("!!LEAD.state().inputs.households")
        b.set_files("#lf-hist", HIST); b.wait(f"LEAD.state().inputs.history.length === {len(HIST)}")
        js = json.loads(b.js("""(() => {
            const m = LRISK.model(), L = LCORE;
            const H = L.buildHistory(LEAD.state().inputs.history.map(f => L.readHistoryFile(f.name, f.text)), {tz: 'Asia/Ulaanbaatar'});
            const input = []; for (const [r, ds] of H.dials) ds.forEach(x => input.push({hhid: x.hhid, round: r, wall: x.wall, status: x.status, cmp_code: x.cmp, dur: x.dur, operator: x.operator}));
            const X = LRISK.facts(LSTATS.build(input), m);
            const drop = {}, ret = {};
            for (const f of X.F.values()) {
              if (!f.completed) continue;
              const d = LRISK.dropoutRow(m, X, f.hhid, f.round); if (d) drop[f.hhid + '|' + f.round] = Object.assign({}, d, { _lp: LRISK.score(m.dropout, [d], {kind: 'pooled'})[0].lp });
              const r = LRISK.returnRow(m, X, f.hhid, f.round); if (r) ret[f.hhid + '|' + f.round] = Object.assign({}, r, { _lp: LRISK.score(m.return, [r], {kind: 'pooled'})[0].lp });
            }
            const cal = LRISK.fitVersion(m, X, 'dropout', 'recalibrated'), own = LRISK.ownPairs(m, X, 'dropout');
            const rf = LRISK.refit(m.dropout, own, 1.0);
            return JSON.stringify({ drop, ret, cal, rf: { intercept: rf.intercept, coef: rf.coef }, own: own.length });
        })()"""))
        # features
        bad = []
        for key, row in py_d.items():
            j = js["drop"].get(key)
            if j is None:
                bad.append((key, "missing")); continue
            for k in dk:
                if not close(row[k], j.get(k), 1e-9):
                    bad.append((key, k, row[k], j.get(k)))
        check("dropout features: every value the browser computes equals the training script's, for every household-round", not bad and len(js["drop"]) == len(py_d), bad[:5] + [len(js["drop"]), len(py_d)])
        bad = []
        for key, row in py_r.items():
            j = js["ret"].get(key)
            if j is None:
                bad.append((key, "missing")); continue
            for k in rk:
                if not close(row[k], j.get(k), 1e-9):
                    bad.append((key, k, row[k], j.get(k)))
        check("return features: every value equals the training script's", not bad and len(js["ret"]) == len(py_r), bad[:5] + [len(js["ret"]), len(py_r)])
        lp_bad = [k for k, row in py_d.items() if not close(ref_risk.lp(model["dropout"], row), js["drop"][k]["_lp"], 1e-9)]
        lp_bad += [k for k, row in py_r.items() if not close(ref_risk.lp(model["return"], row), js["ret"][k]["_lp"], 1e-9)]
        check("scores: the browser's linear predictor equals the bundled model applied in Python", not lp_bad, lp_bad[:5])
        a, bb, n = ref_risk.recalibration(model["dropout"], py_d)
        check("recalibration on the program's own rounds: intercept and slope equal the training script's function",
              close(a, js["cal"]["a"], 1e-6) and close(bb, js["cal"]["b"], 1e-6) and js["own"] == n, [a, bb, js["cal"], n, js["own"]])
        icpt, coef = ref_risk.refit(model["dropout"], py_d)
        check("refit on the program's own rounds: coefficients equal the training script's ridge fit",
              close(icpt, js["rf"]["intercept"], 1e-5) and all(close(x, y, 1e-5) for x, y in zip(coef, js["rf"]["coef"])), [icpt, js["rf"]["intercept"], coef[:3], js["rf"]["coef"][:3]])

        # the Risk tab
        b.click('[data-lact="tab"][data-t="risk"]')
        b.shot(os.path.join(SCREENS, "risk_01_lists.png"), full=True)
        txt = b.js("document.querySelector('.panel').innerText")
        check("the Risk tab says it is for the leader only, that a tier is never a prediction about one household, and never a reason to drop one",
              "for the leader only" in txt and "never a prediction about one household" in txt and "never a reason to drop one" in txt)
        hl = {r["hhid"]: r for r in csv.DictReader(open(os.path.join(S, "household_list.csv"), encoding="utf-8"))}
        mains = {h for h, r in hl.items() if r["status"] == "active"}
        cand = sorted([(ref_risk.lp(model["dropout"], row), k.split("|")[0]) for k, row in py_d.items() if k.endswith("|4") and k.split("|")[0] in mains], key=lambda x: (-x[0], x[1]))
        n = len(cand)
        py_tiers = {h: ("high" if (i + 1) / n <= 0.15 else "medium" if (i + 1) / n <= 0.5 else "low") for i, (_, h) in enumerate(cand)}
        js_tiers = {h: t for h, t in b.js("LEAD.riskData().dropout.map(s => [s.row._.hhid, s.tier])")}
        shown = b.js("[...document.querySelectorAll('.tier')].length")
        check("tiers for this round: the top 15% of last round's respondents high, the next 35% medium, as the training's tier rule",
              js_tiers == py_tiers and shown >= sum(1 for t in py_tiers.values() if t == "high"), [len(js_tiers), len(py_tiers), [h for h in py_tiers if js_tiers.get(h) != py_tiers[h]][:5]])
        expl = b.js("[...document.querySelectorAll('.lcard')].filter(c => /Dropout risk:/.test(c.innerText)).map(c => c.innerText).join(' ')")
        check("explanations describe the household's own values (no 'in the panel 13 rounds or more' for a newer household)",
              "Rounds since joining:" in expl and "In the panel 13 rounds or more" not in expl and ("raises the risk" in expl or "lowers the risk" in expl))
        check("before recalibration, each household is shown against the round's average, not as a chance", "times" in expl and "similar households were not interviewed" not in expl)
        check("tiers by stratum are shown, so that a concentration in one area is visible", "Tiers by stratum" in expl)
        # own data: backtest, then switch to the recalibrated model
        b.click('[data-lact="backtest"][data-k="dropout"]'); b.wait("!!LEAD.ui.bt_dropout")
        bt = b.js("LEAD.ui.bt_dropout")
        check("the own-round backtest runs before any switch, round by round, on outcomes known at the time", bt["steps"] >= 1 and bt["pooled"] and bt["recalibrated"], bt)
        # the verdict under the backtest: its AUC interval equals the Hanley-McNeil interval computed here
        P = bt["pooled"]; A, n1, n0 = P["auc"], P["events"], P["n"] - P["events"]
        q1, q2 = A / (2 - A), 2 * A * A / (1 + A)
        se = ((A * (1 - A) + (n1 - 1) * (q1 - A * A) + (n0 - 1) * (q2 - A * A)) / (n1 * n0)) ** 0.5
        lo, hi = max(0.0, A - 1.96 * se), min(1.0, A + 1.96 * se)
        vtxt = b.js("[...document.querySelectorAll('.lcard')].filter(c => /This program's own data/.test(c.innerText)).map(c => c.innerText).join(' ')")
        want = f"95% interval {lo:.2f} to {hi:.2f}, on {P['n']} household-rounds with {n1} losses"
        verdict_ok = (want in vtxt and (("worse than chance" in vtxt) if hi < 0.5 else ("cannot be told from chance" in vtxt) if lo <= 0.5 else ("better than chance" in vtxt)))
        check("the backtest is read out in words, with the AUC's 95% interval (Hanley-McNeil, recomputed here) deciding what the leader is told", verdict_ok, [want, vtxt[:600]])
        b.click('[data-lact="usever"][data-k="dropout"][data-v="recalibrated"]'); b.wait("LEAD.state().risk.dropout.kind === 'recalibrated'")
        b.shot(os.path.join(SCREENS, "risk_02_recalibrated.png"), full=True)
        txt = b.js("document.querySelector('.panel').innerText")
        ev = b.js("LEAD.state().events.filter(e => e.what === 'risk_model_switched')")
        check("switching to the recalibrated model is logged with who and when, and the chance is then shown as a frequency",
              ev and ev[-1]["logged_by"] == "L01" and "similar households were not interviewed the next round" in txt)
        check("a refit is not offered before about 300 own losses", "refit needs about 300" in txt and not b.js("!!(LEAD.ui.bt_dropout.refit)"))
        before = {p: os.path.getmtime(p) for p in glob.glob(os.path.join(DL, "*"))}
        b.click('[data-lact="riskcsv"][data-k="dropout"]')
        t0 = time.time(); f = None
        while time.time() - t0 < 15 and not f:
            f = next((p for p in glob.glob(os.path.join(DL, "*_risk_dropout*.csv")) if p not in before), None); time.sleep(0.2)
        rows = list(csv.DictReader(open(f, encoding="utf-8"))) if f else []
        check("the risk list downloads for the leader: tier, chance once calibrated, drivers; no name or phone number",
              rows and set(rows[0]) >= {"hhid", "tier", "chance", "driver_1"} and "+000" not in open(f).read() and "Contact" not in open(f).read() and all(r["chance"] for r in rows))
        check("the model card is shown beside the lists", "Where the models do poorly" in b.js("document.querySelector('.panel').innerText"))
        # planning: the high dropout tier gets an early first dial; tiers never reach an assignment file
        b.click('[data-lact="tab"][data-t="prepare"]')
        def setv(sel, v):
            b.js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); el.value = {json.dumps(v)}; el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()")
        setv('[data-lset="cal.window_start"]', "2026-10-26"); setv('[data-lset="cal.window_end"]', "2026-11-20")
        b.js("(() => { const el = document.querySelector('[data-lteam=\"2\"][data-f=\"available\"]'); el.checked = false; el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()")
        setv('[data-lset="rule.rotation_share"]', "10"); setv('[data-lset="rule.seed"]', "20261027")
        b.click('[data-lact="apply"]'); b.wait("!!LEAD.state().plan")
        plan = json.loads(b.js("""JSON.stringify((() => { const st = LEAD.state(), r = LRISK; const high = new Set();
             const rd = st.plan; return { out: [...rd.out], plans: [...rd.plans], sums: [...rd.sums].map(([h, s]) => [h, s.joined_round]) }; })())"""))
        high = {h for h, t in py_tiers.items() if t == "high"}
        out, plans, joined = dict(plan["out"]), dict(plan["plans"]), dict(plan["sums"])
        phones = {h: sum(1 for k in ("phone_1", "phone_2", "phone_3") if hl[h].get(k)) for h in hl}
        ok = True
        for e in {x["enumerator_id"] for x in out.values()}:
            mine = [h for h, x in out.items() if x["enumerator_id"] == e]
            prio = [h for h in mine if joined[h] is None or out[h]["reason"] == "switch_hard_to_reach" or h in high]
            rest = [h for h in mine if h not in prio]
            if prio and rest and max(plans[h]["first_dial_date"] for h in prio) > min(plans[h]["first_dial_date"] for h in rest):
                ok = False
        check("high dropout-tier households get the earliest first dials, with new and switched households (Section 3.4 box)", ok and high)
        b.click('[data-lact="write"]'); b.wait("!!LEAD.ui.ready", timeout=30)
        files = b.js("LEAD.ui.ready.map(f => f.text)")
        check("no assignment file carries a tier, a score or a risk field (D7: leader only)", all('"tier"' not in t and "risk" not in t.lower() for t in files))
        # the chosen version survives saving and reopening
        before = {p: os.path.getmtime(p) for p in glob.glob(os.path.join(DL, "*"))}
        b.click('[data-lact="save"]'); b.wait("APP.modal"); b.click('[data-act="modalok"]')
        t0 = time.time(); fp = None
        while time.time() - t0 < 15 and not fp:
            fp = next((p for p in glob.glob(os.path.join(DL, "leader_*.json")) if p not in before), None); time.sleep(0.2)
        b.click('[data-lact="close"]'); b.wait("APP.modal"); b.js("(document.querySelector('[data-act=\"modalalt\"]') || document.querySelector('[data-act=\"modalok\"]')).click(); true"); b.wait("!LEAD.state()")
        b.set_files("#lf-project", [fp]); b.wait("!!LEAD.state()")
        check("the model version in use is saved with the leader session and restored", b.js("LEAD.state().risk.dropout.kind") == "recalibrated" and close(b.js("LEAD.state().risk.dropout.a"), js["cal"]["a"], 1e-9))
    finally:
        b.close()
    passed = sum(ok for _, ok in results)
    lines = [f"Risk model tests, {time.strftime('%d %b %Y %H:%M')}: {passed} of {len(results)} passed"] + [("PASS " if ok else "FAIL ") + n for n, ok in results]
    open(os.path.join(HERE, "results_risk.txt"), "w").write("\n".join(lines) + "\n")
    print(lines[0])
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
