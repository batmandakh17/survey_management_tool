# A call-center system's exports

Several L2 programs record no call attempts in their data-collection form. A call-center system holds the sample,
shows each operator the households to call, dials, and logs every attempt with a status code; the interview itself
is filled in KoBoToolbox, which opens with the household's code from the operator's screen. The tool reads the
Uzbekistan program's system as it is (the L2CU layout: three daily exports), the Tajikistan program's log as a second
layout, and any other through the mapping card of the Import tab.

## 1. The L2CU layout: three exports a day

The system's export address gives three semicolon-separated tables each day, the leader's do-files download them
under `odbc/<date>/`:

| Table | What it holds | What the tool does with it |
|---|---|---|
| `calllog` | one row per dial: `callid; hhid; operator; round; dialing_phone; start_time; end_time; comment; NT_comment; IS_comment; status; mood; qconnect; callplace` | the dials of the round, under the tool's enumerator IDs |
| `sample` | one row per household: `…; hhid; catiid; date_nextcall; …; agreement; refusal_reason; smpl_status; last_status; last_status_date; round; round_comp_date; operator; replaced_by; replacement_for; …; date_schedule` | the system's view of the assignment, checked against the manifest |
| `baseline` | the roster with names and numbers (`respondent_phone`, `phone_second`, `phone_member`, `phone_paynet`) | not read: the household list already holds the numbers |

The operator's code is written three ways across the program's files (`CATI-02` in the log, `CATI_02` in the sample
table and the KoBo form); the tool matches a platform code regardless of case, hyphens, underscores and spaces, so the
leader enters it once (`CATI02` will do) on the Prepare tab, step 5.

**The call log.** Recognised by `callid`, `hhid`, `operator`, `dialing_phone`, `status`, `start_time`.

| Role | Column | Read as |
|---|---|---|
| Enumerator | `operator` | the tool's ID, through the platform code |
| Household | `hhid` | `hhid` |
| Round | `round` | rows of other rounds are left out and counted; a row without a round is kept |
| Number dialed | `dialing_phone` | the household's slot (1 to 3), found in the household list; the number itself is not kept. A number not in the list leaves the slot blank and is counted |
| Call start, end | `start_time`, `end_time` (`YYYY-MM-DD HH:MM:SS`, local, no offset) | `ts`, `end_ts`, placed in the round's time zone (the calendar's) |
| Result | `status` | `status`, by the map below |
| Record ID | `callid` | `event_id` |
| Note | `comment` | `note` |

| Code | Meaning (the program's own label) | Status in the tool |
|---|---|---|
| `CS` | Completed successfully | `COMPLETE` |
| `NA` | No answer | `NO_ANSWER` |
| `NT` | No time | `NOT_AVAILABLE` |
| `NWN` | Non-working number | `DEAD_NUMBER` |
| `WN` | Wrong number | `WRONG_NUMBER` |
| `OSA` | Out of service area | `SWITCHED_OFF` |
| `IS` | Interrupted survey | `PARTIAL` |
| `BS` | Busy | `BUSY` |
| `HU` | Hangup | `OTHER`, with the code in the note |
| `NC` | No call | not a dial |

A complete needs a call of three minutes or more (Box 3.0). The system closes some successful calls early (the
program's own rule treats short "completed" calls as appointment contacts), so a matched interview lends its end to
a short call, see section 3.

**The sample table.** Recognised by `hhid`, `catiid`, `date_nextcall`, `replaced_by`, `replacement_for`. The rows of
the round (and rows without a round) are read against the manifest:

- a household the system has with another operator than the manifest is listed under *Needs your decision*: if the
  system is right, move the household on the Progress tab and write the files again; if the manifest is right,
  correct the system;
- a replacement the system has activated (`replaced_by`) is counted as activated for the household's enumerator,
  and noted;
- households the system has with an operator but the manifest does not know are counted in one note.

The Import tab sums it up: households of the round, with an operator, differing, replacements activated, unknown.

## 2. What the tool writes for the system: `cati_assignments.csv`

The system holds the assignment, so after the leader prepares the round (and after moving households during it)
the Call log tab writes the table the system loads, semicolon-separated, in the sample table's names where they
exist and the baseline's names for the numbers: `hhid; catiid; operator` (the platform code); `enumerator_id; round;
date_nextcall; hour_nextcall; date_schedule` (the planned first dial); `hhcategory` (1 a household of the round, 2 a
replacement); `replacement_for; rank` (a reserve's household and order); `respondent_phone; phone_second;
phone_member; psu; stratum`. One row per household and per unused replacement. It holds phone numbers and goes to
the system only. How a system loads such a table is the vendor's business; it is the shape the program's own system
exports.

## 3. The interview form against the log

When the program's KoBoToolbox export (an interview form that records no attempts, `formats/kobo/README.md`
section 2) is added with the log, the tool checks one against the other instead of counting both. Each interview with
consent is matched to a completed call of its household within three hours of the interview's start (an interview
resumed in a later call still matches). A matched call that the system closed early, or without an end, takes the
interview's end, with "end from the questionnaire" in the note. Then:

- an interview without a logged completed call is listed under *Needs your decision*: the leader counts it as a
  complete or notes it;
- a completed call without an interview is listed too: the leader keeps it as a complete or recodes it as "other".

A refusal recorded in the form is not a call to match. Without a log, the export is read as the completes and
refusals.

## 4. The L2Taj layout

The Tajikistan and Kyrgyzstan programs' system exports one cumulative table, `operator_id; hh_id; round;
dialing_phone; start_time; end_time; comment; NT_comment; IS_comment; status; id`, read like the L2CU log with the
codes `SCS` successful, `NOA` no answer, `NOT` no time, `NWR` non-working number, `WNM` wrong number, `OOS` out of
service, `ITR` interrupted survey, `RFS` refused; `PWI` and `BLN` have no label in the files seen and read as "other"
until the program names them. Its interview form (`hhid`, `ocode`, `agreement`, `refusal`) is read as the L2CU one.

## 5. Samples

`samples/cati/calllog_2026-11-06.csv` is the synthetic program's log in the L2CU layout: 717 rows, of which 340
are the round-5 calls up to 6 November (the same calls as `samples/leader/exports_R05/`) and the rest round 4, by
the operators `CATI-01`, `CATI-02` and `CATI-07`; `samples/cati/sample_2026-11-06.csv` is the system's sample table
for the same day, with one household the system has with another operator and one replacement it has activated;
`samples/cati/cati_assignments.csv` is the table the tool writes for round 5. Every number uses the invalid country
code +000.

## 6. Checked against the real files

On 1 November 2026 the tool read the Uzbekistan program's round-82 exports as downloaded, with a manifest built from
the system's own sample table (5,261 households, 2,004 with an operator): the log's 4,231 rows by nine operators
gave 4,228 dials, identical per operator to a count made outside the tool (the three rows coded "no call" are not
dials); the completes were 1,935, of which 1,913 from calls of three minutes or more, as counted outside the tool,
and 22 from short calls whose matched interview lasted longer; the sample table matched the manifest for every
household; and of the 2,004 submissions of the round's KoBoToolbox export (2,001 with consent), 1,976 matched a
completed call within three hours and 25 were listed on each side, the same 25 an independent count finds. The
Tajikistan round-7 log was read the same way (7,162 rows of the round, dials per operator identical, 1,269
completes agreeing). Aggregates only; the files stay with the programs.
