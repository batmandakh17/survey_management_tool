# Survey Solutions: the exports the tool reads and the files it writes

For a team that interviews in Survey Solutions rather than in this tool's enumerator view. The leader keeps the
leader view: the assignment, the plan, the merge, progress and the moves during the round. As with KoBoToolbox
(`formats/kobo/README.md`), there is no network link; a file crosses the boundary each way. The assignments
upload goes out, and the questionnaire's tabular export comes in. The leader view's **Survey Solutions** tab walks
the round's cycle in five steps.

The layouts below follow the Survey Solutions documentation (docs.mysurvey.solutions, pages opened on 6 November
2026, release 26.11; the list is at the end). Nothing here has been tried on a live server yet; a Personal Demo
Server is the place to do it.

## 1. The tool's own questionnaire `rtm_call_record`

For a program without a phone questionnaire of its own. Survey Solutions has no XLSForm import, so the
questionnaire is built once in Designer from this specification. It has one interview per household per round,
with the calls as a roster inside it. That follows the documentation's own advice for phone surveys: the phone
numbers go in identifying fields, and each contact attempt's outcome and callback are recorded in the
questionnaire.

**Cover page (identifying questions, preloaded from `assignments.tab`).** Put `hhid`, `contact_name` and
`phone_1` first: the interviewer's dashboard card shows the first three identifying fields.

| Variable | Type |
|---|---|
| `hhid` | text |
| `contact_name` | text |
| `phone_1`, `phone_1_label`, `phone_2`, `phone_2_label`, `phone_3`, `phone_3_label` | text |
| `program` | text |
| `round` | numeric (integer) |
| `planned_date` | text (YYYY-MM-DD) |
| `planned_hour` | numeric (integer) |
| `psu`, `stratum` | text |
| `kind` | text (`main` or `replacement`) |
| `replaces` | text: for a replacement, the household it replaces |
| `rank` | numeric (integer): the replacement's order |

**Section "Calls".** `n_calls`, a numeric question (integer, 1 to 30): the calls so far. It triggers the numeric
roster `calls`, which holds one item per call or per record without a call:

| Variable | Type | Values |
|---|---|---|
| `phone_slot` | single-select | 1 Number 1, 2 Number 2, 3 Number 3 (the labels can substitute `%phone_1%` and so on) |
| `call_start` | date, current time (a timestamp) | tapped when the call starts |
| `call_end` | date, current time | tapped when it ends |
| `result` | single-select | the codes below |
| `willing` | single-select | 1 yes, 2 later, 3 no, 4 not asked |
| `appointment` | text, mask `####-##-## ##:##` | the callback agreed, local time; enabled when `result` = 2 or `willing` = 2 |
| `action` | single-select | 1 keep calling, 2 release for this round, 3 ask for another enumerator next round, 4 ask to remove (no number works), 5 activate a replacement |
| `target_hhid` | text | the replacement activated; enabled when `action` = 5 |
| `note` | text | |

| `result` | Meaning | Status in the tool |
|---|---|---|
| 1 | Interview completed | `COMPLETE` |
| 2 | Appointment booked | `APPOINTMENT` |
| 3 | Partial interview | `PARTIAL` |
| 4 | Respondent not available | `NOT_AVAILABLE` |
| 5 | No answer | `NO_ANSWER` |
| 6 | Busy | `BUSY` |
| 7 | Switched off or unreachable | `SWITCHED_OFF` |
| 8 | Our number is blocked | `BLOCKED` |
| 9 | Number not in service | `DEAD_NUMBER` |
| 10 | Wrong number | `WRONG_NUMBER` |
| 11 | Refusal, may retry | `REFUSAL_SOFT` |
| 12 | Refusal, do not retry | `REFUSAL_HARD` |
| 13 | Language barrier | `LANGUAGE` |
| 14 | Other (write a note) | `OTHER` |
| 99 | No call: an action or a note only | an action without a dial |

Survey Solutions' single-select answers are numbers, so the codes are the tool's results in their order. A
redeployed questionnaire with a new code is read as "Other" until the leader maps the value once (step 3 asks).

Interviewers may also set a **calendar event** on the interview for the next contact. Headquarters shows it, but no
export file contains it, so the callback the tool reads is the `appointment` question.

## 2. A program's own questionnaire

The tool reads any questionnaire whose calls are one level of its export:

- **a roster of calls** inside one interview per household, like the tool's own; or
- **one interview per call attempt**, with an assignment of unlimited quantity (`_quantity` = -1).

When an export's layout is not known, step 3 lists its files (the main file and each roster, with their rows and
first columns) and asks which one holds the calls. The leader can also answer "neither: the questionnaire records
interviews only"; the team then logs its calls in the tool's enumerator view. The answer is kept for every later
export of the questionnaire. The usual mapping card then opens with the export's own columns already chosen:

| Column the tool adds | From | Default role |
|---|---|---|
| `suso__interviewer` | `interview__actions`: the interviewer who held the interview when the call started, else the one who completed it | Enumerator |
| `suso__record` | the interview key, with the roster row after `#` | Record ID |
| `suso__started` | the interview's first answer (action 2, FirstAnswerSet), in the round's time zone | Call start, when the questionnaire has no call time |
| `suso__completed` | its last completion (action 3, Completed) | Call end, likewise |
| `suso__responsible`, `suso__status`, `suso__minutes` | `interview__diagnostics` and the main file | for reference |

The leader picks the household ID and the result and says what each result value means. The mapping is saved in
the session and read from then on.

## 3. Before the round: `assignments.tab`

Step 2 writes the assignments upload from the current manifest. It is a tab-delimited file with one row per
household and per reserve (under the leader's approval, only the released reserves). `_responsible` is the
interviewer's login, from the codes table of step 1, which the KoBoToolbox tab shares. `_quantity` is 1, or -1 for
one interview per call attempt. For the tool's own questionnaire every other column is an identifying variable of
section 1. For a program's own questionnaire the file carries the household ID alone, under the name of its
variable, and the program's own preload supplies the rest.

Upload it in Headquarters under **Survey Setup › Questionnaires › the questionnaire › Upload assignments**. Every
column must be a variable of the questionnaire (Headquarters offers the questionnaire's template to compare the
names), every row needs a login in `_responsible`, and each login must exist with the interviewer or supervisor
role. Step 2 names any enumerator still without a login before it writes the file. The file of the
tool's own questionnaire holds phone numbers: they go to the Survey Solutions server, which keeps them as it keeps
the answers, and nowhere else.

## 4. Each day: the export

In Headquarters, **Data Export**: the questionnaire, **Tab separated**, all statuses (or those the team follows).
Download the zip and add it whole on step 3. The tool opens the zip in the browser and keeps:

- the main file, named after the questionnaire: `interview__key`, `interview__id`, the answers, `ssSys_IRnd`,
  `has__errors`, `interview__status`, `assignment__id`;
- each roster file: `interview__key`, `interview__id`, `<roster>__id` and the roster's answers;
- `interview__actions`: `date` and `time` in UTC, `action` (1 InterviewerAssigned, 2 FirstAnswerSet, 3 Completed,
  and so on), `originator`, `role` (1 interviewer, 2 supervisor), `responsible_name`, `responsible_role`;
- `interview__diagnostics`: `responsible`, `interview__duration` (DD.HH:MM:SS) and the error counts;
- `assignment__actions`: `assignment__id`, `date` and `time` (UTC), `action` (1 Created, 4 ReceivedByTablet,
  7 Reassigned), `responsible_name` (the login that holds the assignment after the action): who holds each assignment,
  and whether a tablet has received it.

It leaves out `interview__errors` and `interview__comments`, which it does not read.

The calls level is joined to its interview by `interview__id`. Each call goes to the interviewer who held the
interview when the call started. The time comes from `interview__actions`: each action names the interviewer
responsible after it, so a household reassigned between two calls keeps its earlier calls with the first
interviewer. The login is read as the tool's ID through step 1's codes, whatever its case or punctuation. Each
record becomes one row of the harmonized dial table (A.4). The event ID is the record, `interview__key#calls__id`.
The export is split by interviewer and each part merged as a CSV export without its JSON: unverified, cumulative,
the latest file per enumerator used, every rule of the merge applied.

**Times.** A timestamp answer is written in the device's time zone without an offset (`2026-11-06T14:23:11`), so
the tool places it in the round's time zone. The times of `interview__actions` are UTC, and the tool shows them in
the round's zone too.

**Missing values.** `##N/A##` (text) and `-999999999` (numeric) mean a question was due but not answered. The tool
reads both as empty.

**Statuses.** Step 3 summarises the export: interviews by `interview__status`, those held by more than one
interviewer (`interviewers` in the diagnostics, or a change of holder in the actions), those with `has__errors` = 1,
and those rejected (status 65 or 125). A rejected interview is read as it stands and a complete it holds counts, since
the interviewer corrects and resubmits it; the merge report carries one information line per such household
(`suso_rejected`). An interview with status -1 (deleted) is left out.

## 5. After moves: the list to reassign in Headquarters

Survey Solutions has no file route for reassigning, so step 4 writes `{program}_R{nn}_suso_moves.csv`. It has one
row per household moved this round, with its last move: `hhid`, `moved_at`, `from_enumerator`, `from_login`,
`to_enumerator`, `to_login`, and, from the latest export, `assignment_id`, `interview_keys`, `interview_status`,
`in_hq` and `received_on_tablet`. `in_hq` is `done` when the export shows the assignment (a Reassigned action) or an
interview of the household (an InterviewerAssigned action) passed to `to_login` at or after `moved_at`; `pending` when
the export holds the household but shows no such change; `not in the export` when it holds neither an assignment nor
an interview of it (export again after the upload). `received_on_tablet` is `yes` when an assignment or interview of
the household has a ReceivedByTablet action. Reassign each pending household in Headquarters:

1. Under **Assignments**, filter by `from_login`, tick the household's assignment and choose Assign, then pick
   `to_login`.
2. An interview already started is reassigned under **Interviews** the same way. A completed interview is rejected
   first.

Batch the day's moves. The documentation warns that reassigning work a tablet has already received can create extra
interviews, and Headquarters asks for a confirmation in that case: the `received_on_tablet` column says when it
applies. The merge flags a call the previous interviewer makes after the move as a double call.

## 6. Interviews to look at: `{program}_R{nn}_suso_review.csv`

Every call behind a merge question that needs or had the leader's decision, with its record. The record is the
interview key (`12-34-56-78`) and, after `#`, the row of the calls roster. Under Interviews, paste the key into the
search box: Headquarters matches a value from its start (the whole key or the household ID works, a middle part does
not); open the interview, and reject it to the interviewer with a comment when a call should be corrected.

## Samples

`samples/suso/assignments.tab` is the synthetic program's round-5 upload, with the logins `CATI01` and so on.
`samples/suso/rtm_call_record_1_Tabular_All.zip` is the enumerators' round-5 calls up to the export of 6 November
18:00, the same calls as `samples/leader/exports_R05/` and `samples/kobo/`. It holds 107 interviews, 342 call
records and 953 interview actions, with `interview__actions`, `interview__diagnostics` and `assignment__actions`
(every assignment created by the upload and received by a tablet). One completed interview of CATI02 is rejected by
the supervisor. Every number uses the invalid country code +000. `samples/make_samples.py` writes both.

## Pages of the Survey Solutions documentation used

- Uploading many assignments at a time; Errors in user-supplied files for preloading; Protecting pre-loaded answers
- Distributing assignments to interviewers; Interviews tab; Excessive interviews (FAQ)
- Data export tab; System-generated export file anatomy; Missing values; Merging files; Identifying records
- Date and time formats (FAQ)
- Interviewer dashboard and dashboard card; CATI protocols for the tablet and the web interviewer; Call-centre use
- Release notes 20.12 (calendar events) and 26.11
