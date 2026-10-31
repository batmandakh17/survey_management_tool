# The call record as a KoBoToolbox form

For a team that records its calls in KoBoToolbox (KoBo Collect or web forms) instead of this tool's enumerator
view. The leader keeps the leader view: the assignment, the plan, the merge, progress and the moves during the
round. What crosses the boundary each day is a CSV in each direction. Everything here follows KoBoToolbox's own
documentation (support.kobotoolbox.org: XLSForm question types, *Selecting options from an external file*,
*Pulling data from an external CSV*, *Uploading media files*, *Exporting and downloading your data*, *Using the API
for synchronous exports*).

## The form

`rtm_call_record.xlsx` is the XLSForm, written by `make_xlsform.py`. One submission is one call attempt.

| Question | Type | What it does |
|---|---|---|
| `enumerator_id` | text | The enumerator's ID, as in the assignment |
| `hhid` | `select_one_from_file households.csv` | The household, from the leader's household file, filtered to the enumerator's own list (`choice_filter enumerator_id = ${enumerator_id}`); replacements appear once the leader's file lists them for that enumerator |
| `program`, `round`, `contact_name`, `phone_1`–`phone_3` and labels, `planned_date`, `planned_hour`, `replaces`, `psu`, `stratum` | calculate, `pulldata('households', …, 'hhid', ${hhid})` | Filled from the household file: shown to the enumerator, and exported with the record so that the leader view can check the round and link a replacement to the household it replaces |
| `phone_slot` | select 1–3 | Which number was dialed; the labels show the numbers |
| `call_start`, `call_end` | datetime | Start and end of the call; `call_start` defaults to now |
| `result` | select | The tool's dial codes `COMPLETE` … `OTHER`, and `NONE` for a record without a call (an action or a note) |
| `willing` | select | Willing to take part: yes, later, no, not asked (asked when the household was reached) |
| `appointment` | datetime | The callback agreed |
| `action` | select | Keep calling, `RELEASE`, `SWITCH_REQUEST`, `REMOVE_REQUEST`, `ACTIVATE_REPLACEMENT` |
| `target_hhid` | `select_one_from_file households.csv` | The replacement activated, filtered to the household's own replacements (`kind = 'replacement' and replaces = ${hhid}`) |
| `note` | text | Operational only |
| `start`, `end`, `deviceid` | metadata | When the form was opened and closed, and the device |

Upload the XLSForm as a new project, upload `households.csv` under the project's **Settings › Media**, and deploy.
The file name must be exactly `households.csv`; the form refers to it as `households` in `pulldata()`. When the
leader writes a new household file (a new round, or after moving households during the round), upload it again
under the same name and redeploy. The select question's filter on a column of the external file needs a recent
KoBo Collect or Enketo; where it is not honoured, the enumerator finds the household by typing its ID
(`autocomplete`).

## The household file (`households.csv`)

Written by the leader view (Call log tab, *households.csv*) from the round's manifest and the household list, so
it never lists a household twice and follows every move the leader makes. One row per household and per unused
replacement:

`name`, `label` (what the enumerator sees: the ID and the contact name), `hhid`, `enumerator_id`, `program`,
`round`, `contact_name`, `phone_1`, `phone_1_label`, `phone_2`, `phone_2_label`, `phone_3`, `phone_3_label`,
`planned_date`, `planned_hour`, `psu`, `stratum`, `kind` (`main` or `replacement`), `replaces` (the household a
replacement belongs to), `rank` (its order of use).

It holds phone numbers. It goes to the KoBoToolbox project, which stores the numbers in any case, and nowhere else.

## The daily export

Download the data under **Data › Downloads** (CSV, with *XML values and headers*, so that the columns carry the
question names and the choice codes), or use the project's synchronous export link (`data_url_csv`, listed under
`/api/v2/assets/<project uid>/export-settings/`). The export is cumulative: every submission so far. Add it on the
leader view's Import tab, under *Add platform files*. The tool recognises it by its `_uuid` and `_submission_time`
columns, splits it by `enumerator_id`, turns each submission into a row of the harmonized dial table (A.4:
`ts` from `call_start`, `end_ts` from `call_end`, `status` from `result`, `phone_slot`, `appointment_ts`, `action`,
`replaces`, `note` with the willingness appended as `willing: later`, `event_id` from `_uuid`, `logged_at` from
`_submission_time`), and merges each enumerator's part as it merges a CSV export: unverified, the latest file used,
every rule of the merge applied. A submission with `result = NONE` becomes an action without a call; an
`ACTIVATE_REPLACEMENT` records the replacement's ID.

The CSV export leaves repeat groups out, which is why the form has none. A submission edited in KoBoToolbox
after the export shows its new content in the next export; the tool takes the latest export as it stands.

## The calling service

The example in the manual uses Twilio Programmable Voice, whose call log (the Call resource: `sid`, `from`, `to`,
`start_time`, `end_time`, `duration`, `status`) can be exported from the Console or the API. Any service whose
call-detail export gives the number called, the start, the end or the duration and the status is read the same way;
the column names are matched regardless of case and spaces. Added on the Import tab, the log is matched to the
recorded calls by the household's number (from the household list, so the list must be open) and a start within
three minutes; a call end the enumerator left blank is filled from the service; calls to a panel number that nobody
recorded are listed for the leader; calls to numbers outside the list are counted apart. The numbers stay on the
leader's computer: the merged call log carries the slot, never the number.

## Samples

`samples/kobo/households.csv` and `samples/kobo/rtm_call_record_2026-11-06.csv` are the synthetic program's
round-5 household file and the enumerators' 342 records up to 6 November (the same calls as
`samples/leader/exports_R05/`, in KoBoToolbox's export layout, semicolon-separated); `samples/calls/service_calls_2026-11-06.csv`
is the calling service's log for the same calls, with three calls nobody recorded and two to numbers outside the
list. Every number uses the invalid country code +000.
