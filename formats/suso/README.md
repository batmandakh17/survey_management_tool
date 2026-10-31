# The call record as a Survey Solutions questionnaire

For a team that records its calls in Survey Solutions (the Interviewer app or web interviews) instead of this
tool's enumerator view. Survey Solutions has no XLSForm import, so the questionnaire is built once in Designer from
the specification below; the leader view writes the assignments upload and reads the data export. The file layouts
follow the Survey Solutions documentation (docs.mysurvey.solutions: *Uploading many assignments at a time*, the
export file anatomy pages, *Date and time formats*, the CATI interviewer instructions).

## The questionnaire `rtm_call_record`

One interview per household per round. The household's fields are **identifying** questions, so that they can be
preloaded and are visible to the interviewer before the interview opens; the calls are a roster.

| Variable | Type | Scope |
|---|---|---|
| `hhid` | text | identifying |
| `enumerator_id` | text | identifying |
| `program`, `round` | text, numeric | identifying |
| `contact_name` | text | identifying |
| `phone_1`, `phone_1_label`, `phone_2`, `phone_2_label`, `phone_3`, `phone_3_label` | text | identifying |
| `planned_date`, `planned_hour` | text, numeric | identifying |
| `psu`, `stratum` | text | identifying |
| `replacement_1`, `replacement_1_name`, `replacement_1_phone`, `replacement_2`, … | text | identifying (the household's first two replacements) |
| `n_calls` | numeric, 1–12 | the roster's trigger: how many calls so far |
| roster `calls` (numeric roster on `n_calls`): `phone_slot` (categorical 1–3), `call_start` (date with current time), `call_end` (date with current time), `result` (categorical: the tool's codes `COMPLETE` … `OTHER`, and `NONE` for a record without a call), `willing` (categorical: yes, later, no, not asked), `appointment` (date with current time), `action` (categorical: none, `RELEASE`, `SWITCH_REQUEST`, `REMOVE_REQUEST`, `ACTIVATE_REPLACEMENT`), `target_hhid` (text: the replacement activated), `replaces` (text: for a replacement's calls, the household it replaces), `note` (text) | | |

Categorical answers are exported as the codes above when the category *values* are the codes (Designer allows text
values for categorical questions through their labels; where only numeric values are allowed, map them once in the
leader view when it asks, as it does for a program's own result codes).

## The assignments upload (`assignments.tab`)

Written by the leader view (Call log tab, *assignments.tab*) from the round's manifest and the household list: one
tab-delimited row per household with the identifying variables above, `_responsible` (the enumerator's ID, which
should be their Survey Solutions login; edit the column if the logins differ) and `_quantity` (1). Upload it under
**Survey Setup › Questionnaires › the questionnaire › Upload assignments**. After moving households during the round,
write the file again; new assignments for the moved households go to their new interviewers, and the earlier
assignments of those households are archived in Headquarters.

It holds phone numbers. It goes to the Survey Solutions server, which stores them in any case, and nowhere else.

## The daily export

Export the questionnaire's data (tabular format) from **Data Export**. The zip holds `rtm_call_record.tab` (one
row per interview: `interview__key`, `interview__id`, the identifying variables, `interview__status`,
`has_errors`, `ssSys_IRnd`) and `calls.tab` (one row per call: `interview__key`, `interview__id`, `calls__id`, the
roster's variables). Add the zip itself on the leader view's Import tab, under *Add platform files* (the browser
opens it), or the two `.tab` files together. The tool joins the calls to their interview by `interview__id`
(`ParentId1` and `Id` in the older layout), splits them by `enumerator_id`, turns each into a row of the
harmonized dial table (A.4; the event ID is `interview__id:calls__id`), and merges each enumerator's part as it
merges a CSV export. A roster without its main file, or an interview without calls, is reported, not merged.

Survey Solutions exports timestamps in the device's time zone without an offset (`YYYY-MM-DDThh:mm:ss`); the tool
reads them in the leader's computer's time zone, which is the program's. The export is cumulative; interviews
edited after an export show their new content in the next one.

## The calling service

As for KoBoToolbox: `formats/kobo/README.md`, section *The calling service*.

## Samples

`samples/suso/assignments.tab` is the synthetic program's round-5 upload; `samples/suso/rtm_call_record.tab`,
`calls.tab` and `rtm_call_record_export.zip` are the enumerators' 107 interviews and 342 call records up to
6 November, the same calls as `samples/leader/exports_R05/`. Every number uses the invalid country code +000.
