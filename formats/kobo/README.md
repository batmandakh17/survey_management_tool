# KoBoToolbox: the exports the tool reads and the files it writes

For a team that interviews in KoBoToolbox rather than in this tool's enumerator view. The leader keeps the leader
view: the assignment, the plan, the merge, progress and the moves during the round. What crosses the boundary is a
file in each direction: the project's data export comes in, and a list of households goes out. The worked example
is the Philippines program's form, which records every call attempt, so the round's call log needs nothing but
KoBoToolbox; the tool was checked against that program's real export (aggregates at the end). The tool's own
call-record form is the template for a team without a form (section 2), and any other form that records each
attempt is mapped once on the Platform tab (section 3).

## 1. A form that records every call attempt: the L2PHL layout

The Philippines program's interview form is submitted once per call attempt, whether or not anyone answered. Its
first block asks the interviewer's ID (`int_id`, a `select_one` with a searchable list), the household (`hhid`, a
`select_one SN` whose list of sample IDs sits in the form's choices sheet), the attempt number (`Z8`, 1st to 3rd)
and whether someone answered (`call_status1`); then consent (`Z9`) and the interview; and in the closing block the
result of the call (`X15`, ten codes) and remarks (`X16`). KoBo's metadata give the time the form was opened
(`start`) and submitted (`end`).

**The export.** Data › Downloads › CSV with *XML values and headers* (or the project's synchronous export link,
`data_url_csv`): semicolon-separated, every submission so far. The tool recognises it by the columns `_uuid`,
`hhid`, `int_id` and `X15`, and reads:

| Role | Column | Read as |
|---|---|---|
| Household | `hhid` | `hhid` |
| Enumerator | `int_id` | the tool's ID, through the platform code the leader gave each enumerator (Platform tab, step 1, or Prepare tab, step 5); an unknown code is kept as it is |
| Call start, end | `start`, `end` | `ts`, `end_ts` (the form's open and submit times, with their offset) |
| Result | `X15` | `status`, by the map below |
| Attempt | `Z8` | kept for reference; the merge numbers the dials itself |
| Record ID, submitted | `_uuid`, `_submission_time` | `event_id`, `logged_at` |
| Note | `X16` | `note` |

| `X15` | Meaning in the form | Status in the tool |
|---|---|---|
| 1 | Complete | `COMPLETE`, when consent was given (`Z9` = 1); without it `OTHER`, noted |
| 2 | Partially complete, no more callback | `REFUSAL_HARD`, the form's label in the note: the case is closed, as the program's protocol closes it |
| 3 | Partially complete, scheduled another call | `PARTIAL` |
| 4 | Not yet started, with scheduled callback | `APPOINTMENT` |
| 5 | Refused | `REFUSAL_SOFT` |
| 6 | Nobody answering / just ringing | `NO_ANSWER` |
| 7 | Number does not exist / not ringing | `DEAD_NUMBER` |
| 8 | Phone turned off / not in service | `SWITCHED_OFF` |
| 9 | Don't know the household | `WRONG_NUMBER` |
| 10 | Reference person can't connect to the household | `OTHER`, with the code in the note |

Each submission becomes one row of the harmonized dial table (A.4); the export is split by enumerator and each
part merged as a CSV export without its JSON: unverified, cumulative, the latest file per enumerator used, every
rule of the merge applied. A complete needs a call of three minutes or more (Box 3.0), measured from the form's
open to its submit time.

**The list the tool writes back: `choices_households.csv`.** The form takes its households from the choices sheet,
so the leader view (Platform tab, step 2) writes the list in that sheet's layout: `list_name` (`SN`), `name` and `label`
(the household ID; a replacement's label says which household it replaces), `filter_int_id` (the enumerator's
platform code), and for reference `enumerator_id`, `kind`, `replaces`, `rank`. Paste the rows into the choices
sheet in place of the old SN list and redeploy; after moving households during the round, step 4 writes it again, to
paste and redeploy once more (batch the day's moves: a redeploy reaches the interviewers only when they reload the form).
With `choice_filter` set to `filter_int_id = ${int_id}` on the `hhid` question, each interviewer sees only their own
households; the Philippines form's choices sheet already has the `filter_int_id` column. The list has no phone
numbers.

## 2. The tool's own call-record form

`rtm_call_record.xlsx` (written by `make_xlsform.py`) is a minimal form for a team that has no form of its own:
one submission per call, with the household picked from a media file the leader view writes (`households.csv`, one
row per household and unused replacement with the enumerator, numbers, planned first dial and replacement links),
the number dialed, start, end, the tool's result codes, the willingness to take part (yes, later, no), a callback,
an action (release, switch request, removal request, activate a replacement) and a note. The export is recognised
by `_uuid`, `hhid`, `result` and `enumerator_id`. Upload the XLSForm as a new project, `households.csv` under
Settings › Media, and deploy; replace the media file and redeploy each round or after a move. The filter of the
household list by enumerator (`choice_filter` on a select-from-file question) depends on the KoBo Collect or
Enketo version; where it is not honoured, the enumerator searches by ID. It has not been deployed to a real project.

## 3. Any other form

A file whose columns match none of the layouts above, one row per call attempt, opens a mapping card on the Platform tab, step 3: the leader says which
column plays each role (household, enumerator, start, result, and optionally end, attempt, callback, number
dialed, round, record ID, submission time, note), and what each value of the result column means, chosen from the
tool's codes (the card lists the values with their counts). The mapping is saved in the leader's session and used
for every later file with the same columns. A value left unmapped is read as `OTHER`, with the value in the note.

## 4. Platform codes

Where the form knows enumerators by another code than the tool's ID (the L2PHL form's `int_id`, for example),
the leader enters it on the Platform tab, step 1, or on the Prepare tab, step 5, *Platform code* (the same column).
Entered before the files are written, it goes into the manifest (`platform_id`); entered later, it is kept in the
session and overrides the manifest's. It is written into the files for the platform, and every platform file is read
under the tool's ID. Codes match regardless
of case and punctuation, so `CATI07`, `CATI-07` and `cati_07` are one enumerator.

## 5. Samples

`samples/kobo/L2MN-DEMO_CATI_R05_-_all_versions_-_False_-_2026-11-06-18-00-00.csv` is the synthetic program's
round-5 calls up to 6 November in the L2PHL layout (340 submissions by three enumerators with the codes CATI01,
CATI02 and CATI07; the same calls as `samples/leader/exports_R05/`); `choices_households.csv` is the list the tool
writes for the choices sheet; `households.csv` and `rtm_call_record_2026-11-06.csv` belong to the tool's own form. Every phone
number uses the invalid country code +000.

## 6. Checked against the real file

On 1 November 2026 the tool read the Philippines program's round-10 export as downloaded (17,915 submissions by 29
interviewers, 707 columns): dials per interviewer were identical to a count made outside the tool, and the
completes were 1,079 counted plus one household with two completes to decide, against 1,080 households with a
qualifying complete in the file. Aggregates only; the file stays with the program.
