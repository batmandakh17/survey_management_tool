"""Write VALIDATION.md from the test results (tests/results_*.txt) and the risk backtests (models/risk_models.json).
Every count and figure in the report is read from those files. Run after the test suites:
    python3 tests/make_validation_report.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUITES = [("enumerator", "Enumerator view, in headless Chrome", "tests/test_enumerator.py"),
          ("leader", "Leader view, in headless Chrome", "tests/test_leader.py"),
          ("risk", "Risk models in the browser, against the training code", "tests/test_risk.py"),
          ("validation", "Merge batch, every rule, access control, holidays", "tests/test_validation.py"),
          ("formats", "Format checker, on good and damaged files", "tests/test_formats.py"),
          ("rtmtools", "A real rtmtools replacement list, through both views", "tests/test_rtmtools_import.py")]


def results(name):
    lines = open(os.path.join(HERE, f"results_{name}.txt")).read().strip().split("\n")
    head = lines[0]
    m = re.search(r"(\d+) of (\d+) passed", head)
    when = re.search(r", (\d+ \w+ \d{4} \d\d:\d\d):", head)
    checks = [(l[5:], l.startswith("PASS")) for l in lines[1:]]
    return int(m.group(1)), int(m.group(2)), when.group(1) if when else "", checks


def pick(checks, *needles):
    out = []
    for n, ok in checks:
        if any(x.lower() in n.lower() for x in needles):
            out.append(f"- {'Passed' if ok else '**Failed**'}: {n}.")
    return "\n".join(out)


def main():
    R = {k: results(k) for k, _, _ in SUITES}
    M = json.load(open(os.path.join(ROOT, "models", "risk_models.json")))
    S = M["validation_summary"]
    pct = lambda x: f"{100 * x:.0f}%"
    lo = S["dropout_leave_one_program_out"]
    ro = S["dropout_rolling_origin"]
    rt = S["return_other_program"]
    rr = S["return_rolling_origin"]
    total = sum(r[0] for r in R.values()), sum(r[1] for r in R.values())
    better_cal = [p for p, x in ro.items() if x["brier_pooled_recalibrated"] < x["brier_pooled_as_is"]]
    lost = [p for p, x in lo.items() if not (x["auc"] > x["auc_tenure_only"] and x["auc"] > x["auc_dials_rule"])]
    beat = "The model beat both in every program." if not lost else f"The model did not beat both in {', '.join(lost)}."
    worse_cal = [p for p, x in ro.items() if x["brier_pooled_recalibrated"] >= x["brier_pooled_as_is"]]
    w = []
    a = w.append
    a("# Validation report\n")
    a(f"Step 5 of the build prompt. Written by `tests/make_validation_report.py` from the test results and the risk backtests, "
      f"so every count and figure below comes from those files. Checks passed: **{total[0]} of {total[1]}**.\n")
    a("| Suite | What it checks | Passed | Run |")
    a("|---|---|---|---|")
    for k, label, path in SUITES:
        p, n, when, _ = R[k]
        a(f"| `{path}` | {label} | {p} of {n} | {when} |")
    a("\nAll test and sample data are synthetic: the imaginary program L2MN-DEMO, with phone numbers under the invalid code +000. "
      "Real data were used only to train and backtest the risk models, locally, with only aggregates written. The tests drive the "
      "page in headless Chrome through the DevTools protocol (`tests/cdp.py`); Edge, Firefox and Safari were not tested.\n")

    a("## 1. Round trip\n")
    a("The prompt: export a log, reload it and confirm it is identical; save and reload a project file mid-session and confirm "
      "nothing is lost.\n")
    a(pick(R["enumerator"][3], "export, reload", "save and reload", "reads back", "Python-made", "hash chain verifies", "checksum verifies"))
    a("\nThe saved session written by the Python sample generator also opens in the browser, so the canonical JSON and SHA-256 "
      "chain agree across the two implementations.\n")

    a("## 2. Merge\n")
    a("The prompt: import a batch including a missing enumerator, a duplicate and a genuine conflict, and confirm each is handled "
      "as the proposal described (section F), not silently.\n")
    a(pick(R["validation"][3], "merge batch"))
    a("\nThe other situations of section F, one at a time (`tests/test_leader.py`):\n")
    a(pick(R["leader"][3], "uploaded twice", "two exports from one enumerator", "another round", "assigned to someone else", "two completes",
           "edited after export", "verified version", "merge report", "byte for byte", "share a name", "clean batch", "JSON did not arrive", "lacking a dial", "CSV only is compared", "counts once", "same-day name", "copy is an earlier export", "logged before its own time"))

    a("\n## 3. Access control\n")
    a("The prompt: an enumerator's assignment file must contain no other enumerator's contact information.\n")
    a(pick(R["leader"][3], "access control", "exactly one file", "IDs only", "passphrase"))
    a(pick(R["validation"][3], "access control"))

    a("\n## 4. Assignment rules\n")
    a("The default rule, keep the same enumerator, with its rotation and hard-to-reach switch (`tests/test_leader.py`):\n")
    a(pick(R["leader"][3], "absent enumerator", "kept households", "hard-to-reach", "rotation moves", "new to the panel", "same inputs and seed",
           "another seed", "load check", "balancing", "first dials fall", "hour of its last interview", "no default", "setting changed"))
    a("\nThe other rules (`tests/test_validation.py`):\n")
    a(pick(R["validation"][3], "random:", "equal split", "share of total", "manual:", "reason code", "can be chosen and applied", "under the random rule", "moved by the rule"))

    a("\n## 5. Risk models\n")
    a("Trained and backtested locally on the handbook's six programs with dial logs (`models/train_risk.py`); the full tables are in "
      "`models/MODEL_CARD.md`. No figure was reported before the backtests ran.\n")
    a(f"- **A new program** (each program left out in turn): the dropout model's AUC ranged from {min(x['auc'] for x in lo.values()):.2f} "
      f"to {max(x['auc'] for x in lo.values()):.2f}. The tenure-only baseline ranged from {min(x['auc_tenure_only'] for x in lo.values()):.2f} "
      f"to {max(x['auc_tenure_only'] for x in lo.values()):.2f}, the dials rule from {min(x['auc_dials_rule'] for x in lo.values()):.2f} to "
      f"{max(x['auc_dials_rule'] for x in lo.values()):.2f}. " + beat + " The boosted-tree check reached "
      f"{min(x['auc_trees'] for x in lo.values()):.2f} to {max(x['auc_trees'] for x in lo.values()):.2f}, never clearly above the logistic model.")
    a(f"- **Workload:** the high tier, 15% of a round's households, held {pct(min(x['capture_high'] for x in lo.values()))} to "
      f"{pct(max(x['capture_high'] for x in lo.values()))} of the next round's losses.")
    a(f"- **Calibration:** applied as it is to an unseen program, the Brier score was worse than no model in "
      f"{sum(1 for x in lo.values() if x['brier'] > x['brier_null'])} of the six programs. Recalibrated on the program's own past rounds, "
      f"it improved on the model as is in {len(better_cal)} of {len(ro)} programs{(' (not in ' + ', '.join(worse_cal) + ')') if worse_cal else ''}. "
      "The tool therefore shows chances only after recalibration.")
    a(f"- **With the program's own rounds** (rolling origin), the recalibrated dropout model's AUC ranged from "
      f"{min(x['auc_pooled_recalibrated'] for x in ro.values()):.2f} to {max(x['auc_pooled_recalibrated'] for x in ro.values()):.2f}, and its high "
      f"tier held {pct(min(x['capture_high_recalibrated'] for x in ro.values()))} to {pct(max(x['capture_high_recalibrated'] for x in ro.values()))} of losses.")
    a(f"- **The return model is weak:** AUC {min(x['auc'] for x in rt.values()):.2f} to {max(x['auc'] for x in rt.values()):.2f} when trained on the "
      f"other program, and {min(x['auc_other_recalibrated'] for x in rr.values()):.2f} to {max(x['auc_other_recalibrated'] for x in rr.values()):.2f} "
      "recalibrated on a program's own rounds. It beats the tenure-only baseline, so it is kept, only to order redials.")
    names = {"UZB": "L2CU", "TAJ": "L2T", "KGZ": "L2KGZ", "KAZ": "L2Kaz", "PHL": "L2PHL", "IND": "L2Indo"}
    tparts = []
    for kind in ("dropout", "return"):
        ov = M["tiers"].get("overlaps", {}).get(kind, [])
        if not ov:
            tparts.append(f"the {kind} model keeps three tiers: no two adjacent tiers' 95% intervals overlapped in any held-out test of the model as trained or recalibrated")
        else:
            o = ov[0]; prog = next((names[x] for x in o["table"].split("/") if x in names), "")
            tparts.append(f"the {kind} model's {o['tiers'][0]} and {o['tiers'][1]} tiers overlapped in {prog}'s rolling-origin test of the recalibrated model "
                          f"({100 * o['rates'][0]:.1f}% and {100 * o['rates'][1]:.1f}%), so, as proposal E.5 sets out, they were merged and that model uses "
                          f"{' and '.join(M['tiers'][kind])} tiers")
    a("- **Tiers:** " + "; ".join(tparts) + ". The program-only refit is backtested on the program's own rounds before the tool offers it.")
    a("- **Spot checks by hand:** a few held-out households were read against their explanation, in the session only. They showed "
      "that an explanation built feature by feature can name a category the household is not in. For example, \"in the panel 13 rounds "
      "or more\" appeared as raising the risk for a household two rounds in. Explanations now add up related features and describe the "
      "household's own values, such as \"rounds since joining: 2\".")
    a("\nThe browser computes the same model as the training code (`tests/test_risk.py`):\n")
    a(pick(R["risk"][3], "features:", "scores:", "recalibration on", "refit on", "tiers for this round", "aggregates only", "read out in words"))

    a("\n## 6. Holiday calendar\n")
    a("The prompt: test against at least one real country's calendar. The bundled table (Python package `holidays` 0.105) was "
      "compared with the Philippines' official proclamations for 2026, read on 27 October 2026:\n")
    a("- [Proclamation No. 1006, s. 2025](https://lawphil.net/executive/proc/proc2025/proc_1006_2025.html): regular holidays, "
      "special non-working days and additional special days for 2026.")
    a("- [Proclamation No. 1189, s. 2026](https://lawphil.net/executive/proc/proc2026/proc_1189_2026.html): Eid'l Fitr, Friday 20 March.")
    a("- [Proclamation No. 1264, s. 2026](https://lawphil.net/executive/proc/proc2026/proc_1264_2026.html): Eid'l Adha, Wednesday 27 May.")
    a("- [Proclamation No. 1447, s. 2026](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/7/102893): 16 to 18 November, "
      "non-working days in the National Capital Region only.")
    a("")
    a(pick(R["validation"][3], "Philippines 2026"))
    a("\nRegional or decreed closures like the ASEAN Summit days are what the leader view's \"Add a day off\" is for. Mongolia, the "
      "worked example, could not be checked the same way: no official government list of its 2026 lunar holidays was found, and "
      "secondary sources disagree on Tsagaan Sar (17 to 19 or 18 to 20 February). The tool uses the package's dates and labels "
      "estimated ones, and the leader can correct them.\n")

    a("## 7. The sampling tool's replacement list\n")
    a("Step 7 of the prompt: if the appendix sampling tool's export does not match what this tool expects, adapt this tool's import. "
      "`samples/rtmtools_export/` holds a real run of `rtmsample draw` with `reserve(3)`, made in Stata 18 with the installed rtmtools "
      "on a synthetic frame of 12 PSUs of 15 households with 9-digit numeric IDs (`draw_replacements.do`). The export matched the "
      "import as it stood; the only change it needed was in rtmtools itself, the full-width ID export of 27 October (D9).\n")
    a(pick(R["rtmtools"][3], ""))
    a("\n## 8. Further checks\n")
    a(pick(R["leader"][3], "analytics '"))
    a(pick(R["enumerator"][3], "content-security", "cannot load an image", "phone width", "Save, then close", "stays open"))
    a(pick(R["leader"][3], "phone width", "Excel workbook", "interview records only"))
    open(os.path.join(ROOT, "VALIDATION.md"), "w").write("\n".join(w) + "\n")
    print(f"written VALIDATION.md: {total[0]} of {total[1]} checks passed")


if __name__ == "__main__":
    main()
