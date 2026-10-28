# RTM interview tool

One HTML file, `rtm_interview_tool.html`, with two views. The enumerator view logs calls. The team leader
view prepares each round, writing one assignment file per enumerator, then merges the enumerators' exports
into the round's call log, progress and analytics.

The tool has no server, no shared database and no network connection. The page's content-security policy
tells the browser to refuse every request. It reads only files you open, and writes only files you save
or export. `formats/README.md` defines every file.

Status, 28 October 2026: every step of the build prompt is done. The enumerator view (Step 2) and the leader
view (Step 3) were built on 27 October. The same day brought the risk models (Step 4, `models/MODEL_CARD.md`)
and the validation (Step 5, `VALIDATION.md`). On 28 October came the usability pass (Step 6, `USABILITY.md`),
the note in the handbook's Chapter 5 (Appendix C.1) and the test with a real `rtmtools` export (Step 7). The
review loop followed. What is still open is in `OPEN_ITEMS.md`.

All sample files are synthetic: one imaginary program, "L2MN-DEMO", on Mongolia's calendar, with four rounds
of history and round 5 under way. No real household, name or phone number; phone numbers use the invalid
country code +000. Open the tool in Chrome, for example by dragging the file onto a Chrome window. The tests
and the usability pass ran in Chrome. Edge, Firefox and Safari should work but are untested. In Firefox and
Safari, each save downloads a new file instead of overwriting the last one.

## Try the leader view

Choose "Team leader" at the top. The sample files are in `samples/leader/`.

1. **Start a round.** Enter a leader ID (L01), the program `L2MN-DEMO`, Mongolia and round 5.
2. **Open the inputs.** Step 1: `household_list.csv`. Step 2: every file in `history/`, the merged files of
   rounds 1 to 4. Step 3: `selection.csv`, the sampling tool's draw with its replacements. The team, dial cap
   and call hours are taken from round 4.
3. **Set the round.** Step 4: the window, 26 October to 20 November 2026; the 10 November holiday appears.
   Step 5: untick E03, who is away this round. Step 6: keep the default rule and enter a rotation share,
   for example 10%; it has no default.
4. **Check before writing.** Step 7 shows each enumerator's households by reason and stratum, and their
   expected dials against the target. E02 falls short; try "Move kept households at random to balance".
5. **Write the files.** Step 8 writes one assignment file per enumerator, the manifest and the calendar row.
   Tick "Protect each assignment file" to see the passphrases the tool makes for each enumerator.
6. **Import the round's logs.** Start a new round as in step 1, open the Import tab, open
   `L2MN-DEMO_R05_manifest.json`, then add every file in `exports_R05/`: the three enumerators' exports of
   Friday 6 November. Nothing needs a decision. While your computer's date is before 6 November 2026, the
   merge report notes that the exports are dated after your computer's clock; for these samples that is
   expected.
7. **Follow progress and the log.** The Progress tab shows each enumerator's households by state and the
   completes over the window. The Call log tab exports the merged call log, `interviews.csv` for the round
   template, and the other round files.
8. **Try the merge questions.** Add the files in `merge_cases/`, one folder at a time: a duplicate, an
   earlier export, a file from another round, a file edited after export, a CSV without its JSON (E02's later
   export that evening, whose JSON did not arrive, used as unverified), and a conflict where E01 logs a
   complete on a household of E02. Each produces a line in the merge report, and those that need you appear
   under "Needs your decision".
9. **Read the analytics.** Open the history files (Prepare tab, step 2) in the same session, then the
   Analytics tab: continuation and retention, loss and returns, dials per complete and hazard by dial,
   completes per enumerator-day and attendance, success by hour, the last interview's time, continuity and
   holidays, each as the handbook defines it.
10. **Read the risk lists.** With the history open, the Risk lists tab ranks round 4's respondents by dropout
    risk and the households missed in round 4 by the chance of their return. These lists are for the leader
    only; tiers are tied to workload. Press "Backtest on this program's own rounds" to see how the models do
    on this program. On the synthetic sample the verdict is "too few outcomes to judge", with 64
    household-rounds and 9 losses tested. The model card follows the lists.
11. **Save the session.** "Save leader session" keeps the inputs, the imports and your decisions in one file,
    optionally protected with a passphrase. "Close" with unsaved changes offers to save first.

## Try the enumerator view

1. **Open an assignment.** Choose "Open my assignment file" and pick `samples/round05/E07_assignment_R05.json`.
   The round runs from 26 October to 20 November 2026, so the Today tab lists calls due now.
2. **Log a call.** Open a household, press "Start call" by a number, then "End call", choose the result and
   save. Try a booked callback, a number not in service and then "Activate the next replacement", a release
   and its undo, and "Correct or void" on a logged call.
3. **Save and continue.** Press "Save session", then "Close session", then "Continue a saved session" and pick
   the saved file. Everything comes back.
4. **Export.** Press "Export log". The CSV and JSON go to the common folder. A contacts file appears only after
   "Add or correct a number", and goes to the leader directly.
5. **See your performance.** Open "My performance", press "Load earlier logs" and pick
   `samples/past/E07_2026-10-21.json`, the same enumerator's round-4 log.
6. **See the calendar.** It marks Sundays, which the sample's call center does not work, and the 10 November
   holiday.

| Other samples | What it is |
|---|---|
| `samples/round05/E07_project_R05.json` | E07's saved session on 27 October at 12:30, to open with "Continue a saved session" |
| `samples/round05/E07_assignment_R05_protected.json` | The E07 assignment protected with the passphrase `synthetic-E07` |
| `samples/round05/E01_…`, `E02_assignment_R05.json` | The other enumerators' assignments; opening one as an update to E07's session is refused |
| `samples/past/E07_2026-10-21.csv` and `.json` | E07's round-4 export, for the performance view |
| `samples/rtmtools_export/` | A real `rtmsample draw` run with reserves (`selection.csv`, its manifest, and the do-file that made it), for the leader's Step 3 |

## Folder

| Path | Content |
|---|---|
| `rtm_interview_tool.html` | The tool, built from `src/` |
| `src/` | `core.js` (log, scheduler, files), `enum_view.js` (enumerator view), `leader_core.js` (rules, planning, merge), `leader_stats.js` (analytics), `leader_risk.js` (risk models), `leader_view.js` (leader view), `app.css`, `shell.html`, `holidays_data.js` |
| `models/` | `train_risk.py` (training and backtests on the handbook's harmonized tables, kept locally), `risk_models.json` and `validation.json` (coefficients and aggregates only), `make_card.py` and `MODEL_CARD.md` |
| `holidays/make_holidays.py` | Writes the bundled holiday table (Python package `holidays`, 2025–2030) |
| `formats/` | File definitions, JSON Schemas, and `check_formats.py` |
| `samples/` | The synthetic program and the scripts that make it |
| `tests/` | Browser tests of both views, the risk models, the merge batch and the other rules, the format checker and the rtmtools import; reference implementations of the handbook's rules and of the models; the usability walkthrough and its screens |
| `notes/handbook_metric_spec.md` | How the handbook defines and computes each measure the analytics show, with the places where its text and scripts differ |
| `PROPOSAL.md`, `OPEN_ITEMS.md` | The approved design and what is still open |
| `VALIDATION.md`, `USABILITY.md` | What was tested and what the usability pass changed |

## Build and test

```
python3 build.py                           # rebuild rtm_interview_tool.html from src/
python3 samples/make_samples.py            # rebuild the synthetic program (then samples/make_protected_sample.py)
python3 tests/test_enumerator.py           # drives the enumerator view in headless Chrome
python3 tests/test_leader.py               # drives the leader view; checks the analytics against tests/ref_stats.py
python3 tests/test_risk.py                 # the risk models in the browser against the training code
python3 tests/test_validation.py           # the merge batch, the other rules, access control, holidays
python3 tests/test_formats.py              # the format checker on good and damaged files
python3 tests/test_rtmtools_import.py      # a real rtmtools replacement list through both views
python3 tests/make_validation_report.py    # writes VALIDATION.md from the results
python3 tests/usability_walkthrough.py 6   # screens for a usability pass, into tests/screens/usability_r6/
python3 formats/check_formats.py samples   # check any files or folders
```

The tests need Google Chrome and the Python packages `jsonschema` and `cryptography`. They write their
results to `tests/results_*.txt` and screenshots to `tests/screens/`.

This folder stays local, outside the public `rtmtools` repository.
