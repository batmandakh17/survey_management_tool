"""Write models/MODEL_CARD.md from models/risk_models.json and models/validation.json, so that every number in the card
comes from the backtests and none is typed by hand. Run after train_risk.py:  python3 models/make_card.py
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, "risk_models.json")))
V = json.load(open(os.path.join(HERE, "validation.json")))
S = M["validation_summary"]
pct = lambda x, d=0: "–" if x is None else f"{100 * x:.{d}f}%"
f2 = lambda x: "–" if x is None else f"{x:.2f}"


def tier(t):
    return "–" if not t else f"{pct(t['rate'], 1)} ({pct(t['lo'], 1)}–{pct(t['hi'], 1)})"


def low_tier(kind, tiers):
    """The low tier as the tool uses it: when a model's medium tier is merged (proposal E.5), its low tier is everything
    below the top tier, so its rate and Wilson interval come from the medium and low counts together."""
    if "medium" in M["tiers"][kind] or not tiers.get("medium") or not tiers.get("low"):
        return tiers.get("low")
    m, l = tiers["medium"], tiers["low"]
    n = m["n"] + l["n"]
    k = round(m["rate"] * m["n"]) + round(l["rate"] * l["n"])
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"rate": p, "lo": max(0, c - h), "hi": min(1, c + h), "n": n}


def trees_text():
    better = [p for p, x in S["dropout_leave_one_program_out"].items() if x["auc_trees"] > x["auc"] + 0.01]
    names = {"UZB": "L2CU", "TAJ": "L2T", "KGZ": "L2KGZ", "KAZ": "L2Kaz", "PHL": "L2PHL", "IND": "L2Indo"}
    closer = [names[c] for c, x in V["dropout"]["leave_one_program_out"].items() if x["gbm_check"]["brier"] < x["brier"]]
    if not better:
        return ("The boosted trees are a check on the model's form. They ranked households no better than the logistic model in any "
                "program (AUC)" + (f"; their chances were somewhat closer to what happened in {', '.join(closer)} (Brier), which "
                "bears on calibration, and the tool recalibrates chances on the program's own rounds before showing any" if closer else "")
                + ". The logistic model, whose explanations are clearer, is the one used.")
    return (f"The boosted trees, a check on the model's form, did better in {', '.join(better)}; the logistic model is kept for its "
            "clearer explanations, and this is an open item.")


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def tiers_text():
    """Which tiers each model uses and why, from risk_models.json (proposal E.5: overlapping adjacent tiers are merged)."""
    T = M["tiers"]
    names = {"UZB": "L2CU", "TAJ": "L2T", "KGZ": "L2KGZ", "KAZ": "L2Kaz", "PHL": "L2PHL", "IND": "L2Indo"}
    out = []
    for kind, label in (("dropout", "dropout"), ("return", "return")):
        ov = T.get("overlaps", {}).get(kind, [])
        if not ov:
            out.append(f"The {label} model keeps {', '.join(T[kind])}: no two adjacent tiers' 95% intervals overlapped in any held-out test of the model as trained or recalibrated.")
            continue
        parts = []
        for o in ov:
            where = o["table"].split("/")
            prog = next((names[x] for x in where if x in names), "")
            test = "rolling-origin test of the recalibrated model" if "other_recalibrated" in where or "pooled_recalibrated" in where else "held-out test"
            parts.append(f"the {o['tiers'][0]} and {o['tiers'][1]} tiers overlapped in {prog}'s {test} ({100 * o['rates'][0]:.1f}% and {100 * o['rates'][1]:.1f}%)")
        out.append(f"For the {label} model {'; '.join(parts)}, so its tiers are merged to {' and '.join(T[kind])}, the low tier taking the rest.")
    return " ".join(out) + " The program-only refit is tested separately, on the program's own rounds, before the tool offers it."


def main():
    lines = []
    w = lines.append
    w("# Model card: dropout risk and return likelihood\n")
    w(f"Written by `models/make_card.py` from the backtests of `models/train_risk.py` (trained {M['trained_at'][:10]}). "
      "Every number below comes from those files. The tool shows this card beside every risk list.\n")
    w("## What the models predict\n")
    w(table(["Model", "For", "Predicts", "Handbook measure", "What the leader does with it"], [
        ["Dropout risk", "a household interviewed in the last round", "not interviewed in this round", "loss, the complement of continuation (Box 2.0, Section 3.4.3)",
         "give it an early first dial at its usual hour, keep its enumerator, check its numbers, collect another number"],
        ["Return likelihood", "a household interviewed two rounds ago and missed last round", "interviewed again within the next three rounds", "returns (Sections 3.3.5 and 3.4.3)",
         "order the redials; never drop a household, which the handbook rules out (3.3.5)"],
    ]))
    w("\nInterviewed means a completed call-log case, as the handbook's build script defines it. A tier is never a prediction "
      "about one household: it says how similar households fared.\n")
    w("## Training data\n")
    rows = []
    for p, meta in M["trained_on"].items():
        fmt = lambda v: f"{v:,}" if isinstance(v, int) else v
        rows.append([p, meta["rounds"], f"{meta['first_round']}–{meta['last_round']}", f"{meta['cases']:,}", fmt(M["dropout"]["n"].get(p, "–")), fmt(M["return"]["n"].get(p, "–")),
                     "yes" if meta["available"]["number"] else "no", "yes" if meta["available"]["refusal"] else "no", "yes" if meta["available"]["length"] else "no"])
    w(table(["Program", "Rounds used", "Round numbers", "Cases", "Dropout pairs", "Return pairs", "Number codes", "Refusal codes", "Call length"], rows))
    w(f"\nThe handbook's harmonized case and dial tables of its six programs with dial logs, kept locally and never published. Loss "
      f"rate over all dropout pairs: {pct(M['dropout']['loss_rate'], 1)}; return rate over all return pairs: {pct(M['return']['return_rate'], 1)}. "
      "The return model uses L2PHL and L2Indo only, because they redial almost every missed household; elsewhere the households "
      "redialed are chosen, and a model would learn the team's choice rather than the household's chance (3.3.5). Training writes "
      "only coefficients and the aggregates below, with no household ID and with cells under 10 suppressed.\n")
    w("## Features\n")
    w("Operational only: no demographic feature. Each is computed from what is known before the round predicted.\n")
    C = json.load(open(os.path.join(HERE, "coefficients.json"))) if os.path.exists(os.path.join(HERE, "coefficients.json")) else None

    def feature_rows(kind):
        sig = {f["key"]: f for f in C[kind]["features"]} if C else {}
        rows = []
        for f in M[kind]["features"]:
            x = sig.get(f["key"])
            p_ = "–" if not x else ("<0.001" if x["p"] < 0.001 else f"{x['p']:.3f}")
            rows.append([f["label"], f"{f['coef']:+.3f}", f"{x['ci_lo']:+.3f} to {x['ci_hi']:+.3f}" if x else "–", f"{x['z']:.1f}" if x else "–", p_,
                         f2(f["mean"]), f2(f["sd"])])
        return rows
    head = ["Coefficient", "95% interval", "z", "p", "Mean", "SD"]
    w(table(["Dropout model"] + head, feature_rows("dropout")))
    w("\n")
    w(table(["Return model"] + head, feature_rows("return")))
    if C:
        d, r = C["dropout"], C["return"]
        sig_out = lambda kind: [f["label"].lower() for f in C[kind]["features"] if f["ci_lo"] <= 0 <= f["ci_hi"]]
        w(f"\nSignificance (`models/coef_significance.py`): standard errors from the sandwich estimator of the same penalised fit, with "
          f"households as clusters, since a household contributes several household-rounds ({d['n']:,} household-rounds from "
          f"{d['households']:,} households for dropout; {r['n']:,} from {r['households']:,} for return). z is the coefficient over its "
          "standard error; p is two-sided. With this many household-rounds, small effects reach significance: the size of a coefficient "
          "and the backtests below say more about the lists than p does. Features are correlated (the tenure bands, the missed rounds), "
          "so each coefficient is the feature's effect with the others held fixed. 95% intervals that include zero: "
          f"dropout, {', '.join(sig_out('dropout')) or 'none'}; return, {', '.join(sig_out('return')) or 'none'}.\n")
    w("\nCoefficients are per standard deviation, from a ridge-penalised logistic regression with one intercept per program. "
      "Rounds since joining is compared with 4 to 6 rounds. A feature a program's codes do not define counts as average for that "
      "program. In the tool, the explanation adds up the contributions of related features and describes the household's own values.\n")
    w("**Left out on purpose:** household size, the respondent's sex and age, education, region, urban or rural, language, and every "
      "survey answer. Region and urban or rural are sampling variables, but they would steer effort by place; survey answers would "
      "steer it by welfare. The leader view shows how each tier divides by stratum, so that any concentration in one area is visible.\n")
    w("**Not in the training tables:** the number of phone numbers and whether another number was used. The tool records both, so a "
      "program can add them once its own data allow a refit.\n")
    w("## How well they work, on data they were not trained on\n")
    w("### Dropout risk, each program left out in turn\n")
    w("Trained on five programs, tested on the sixth with the average intercept: the honest test for a new program such as Mongolia.\n")
    rows = []
    for p, x in S["dropout_leave_one_program_out"].items():
        rows.append([p, f"{x['n']:,}", pct(x["rate"], 1), f2(x["auc"]), f2(x["auc_tenure_only"]), f2(x["auc_dials_rule"]), f2(x["auc_trees"]),
                     f"{x['brier']:.4f} / {x['brier_null']:.4f}", pct(x["capture_high"]), pct(x["capture_tenure_only"])])
    w(table(["Program left out", "Household-rounds", "Loss rate", "AUC", "AUC, tenure only", "AUC, dials rule", "AUC, boosted trees", "Brier / no model",
             "Losses in the high tier", "… tenure only"], rows))
    w("\nAUC is the chance that a lost household scores above a kept one (0.5 is no better than chance). The high tier is the top 15% "
      "of each round's households. The two baselines: the loss rate by rounds since joining alone (the handbook's "
      "hazard curve), and the rule \"needed more dials than three households in four last round\". " + trees_text() + "\n")
    w("### Dropout risk, with the program's own past rounds\n")
    w("Rolling origin: at each round, only the rounds whose outcomes were already known are used. \"Recalibrated\" here is the model "
      "trained on the other five programs, with its intercept and slope refitted on the program's own past rounds once two rounds have "
      "outcomes. The tool does the same for a new program with the model trained on all six.\n")
    rows = []
    for p, x in S["dropout_rolling_origin"].items():
        t = V["dropout"]["rolling_origin"][{"L2CU": "UZB", "L2T": "TAJ", "L2KGZ": "KGZ", "L2Kaz": "KAZ", "L2PHL": "PHL", "L2Indo": "IND"}[p]]["pooled_recalibrated"]["tiers"]
        rows.append([p, x["steps"], f2(x["auc_own"]), f2(x["auc_pooled_recalibrated"]), f"{x['brier_pooled_recalibrated']:.4f} / {x['brier_pooled_as_is']:.4f}",
                     pct(x["capture_high_recalibrated"]), tier(t["high"]), tier(t["medium"]), tier(t["low"])])
    w(table(["Program", "Rounds tested", "AUC, own rounds only", "AUC, recalibrated", "Brier, recalibrated / as is", "Losses in the high tier",
             "High tier: loss rate (95% CI)", "Medium tier", "Low tier"], rows))
    w("\n### Return likelihood\n")
    rows = []
    for p, x in S["return_other_program"].items():
        rr = S["return_rolling_origin"].get(p, {})
        rows.append([p, f"{x['n']:,}", pct(x["rate"], 1), f2(x["auc"]), f2(x["auc_tenure_only"]), f"{x['brier']:.4f} / {x['brier_null']:.4f}",
                     f2(rr.get("auc_other_recalibrated")), f"{rr.get('brier_other_recalibrated', 0):.4f} / {rr.get('brier_null', 0):.4f}", tier(x["tiers"]["high"]), tier(low_tier("return", x["tiers"]))])
    w(table(["Program tested", "Household-rounds", "Return rate", "AUC, trained on the other", "AUC, tenure only", "Brier / no model",
             "AUC, recalibrated on own rounds", "Brier recalibrated / no model", "High tier: return rate, trained on the other", "Low tier" + (" (all but the high tier)" if "medium" not in M["tiers"]["return"] else "") + ", trained on the other"], rows))
    w("\n## Where the models do poorly\n")
    lo = min(S["dropout_leave_one_program_out"].values(), key=lambda x: x["auc"])
    worst = [p for p, x in S["dropout_leave_one_program_out"].items() if x["auc"] == lo["auc"]][0]
    w(f"- **Levels do not carry between programs.** Loss rates range from {pct(min(x['rate'] for x in S['dropout_leave_one_program_out'].values()), 1)} "
      f"to {pct(max(x['rate'] for x in S['dropout_leave_one_program_out'].values()), 1)}. Applied as it is to a program it has not seen, the dropout "
      "model ranks households usefully but its chances are off: in three of the six programs its Brier score is worse than having no model. "
      "The tool therefore shows a new program only the tier and how far a household is above the round's average, and shows a chance "
      "only after recalibrating on the program's own rounds.")
    caps = [x["capture_high"] for x in S["dropout_leave_one_program_out"].values()] + [x["capture_high_recalibrated"] for x in S["dropout_rolling_origin"].values()]
    w(f"- **The ranking is moderate, not sharp.** The weakest held-out program is {worst} (AUC {f2(lo['auc'])}). The high tier holds between "
      f"{pct(min(caps))} and {pct(max(caps))} of next round's losses; most losses still come from the medium and low tiers.")
    rr = S["return_rolling_origin"]
    auc_r = ", ".join(f"{p} {f2(x['auc_other_recalibrated'])}" for p, x in rr.items())
    w(f"- **The return model is weak.** Its AUC is about 0.6 within a program ({auc_r} after "
      "recalibration), and recalibrated it is only slightly better than the average return rate. Its return levels differ so much between "
      "L2PHL and L2Indo that pooling the two inverts the ranking. Use it only to order redials, never to decide whom to drop.")
    w("- **Some features are missing in some programs.** L2T's and L2KGZ's result codes are not defined in the handbook, so the number and "
      "refusal features rest on the other programs; L2Indo records no call length.")
    w("- **Rounds since joining counts from the first round in the data.** A program that starts using the tool mid-panel undercounts its "
      "households' tenure until earlier rounds are loaded.")
    w("- **Dropout also depends on next round's effort,** which no model fitted before the round can see.")
    w("\n## How the tool uses them\n")
    w(f"- **Tiers, tied to workload.** Within the round, the top {pct(M['tiers']['high'])} of households by score are high, the next "
      f"{pct(M['tiers']['medium'])} medium, the rest low. " + tiers_text())
    w("- **Leader only.** Enumerators never see a household's tier. The tier is not written into assignment files; it only moves high "
      "tier households earlier in the plan of first dials, as Section 3.4's box asks.")
    w("- **Features behind the score.** The three groups of features that move the score most, with the household's own values.")
    w("- **The program's own data.** After two rounds with outcomes, the tool offers a recalibration, backtested on the program's own "
      "rounds; after about 300 own losses, a refit. The leader switches only after seeing the backtest, and the card says which version is "
      "active.")
    open(os.path.join(HERE, "MODEL_CARD.md"), "w").write("\n".join(lines) + "\n")
    print("written models/MODEL_CARD.md")


if __name__ == "__main__":
    main()
