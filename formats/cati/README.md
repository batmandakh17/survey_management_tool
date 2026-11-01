# A call-center system's log

Several L2 programs do not record call attempts in their data-collection form at all. A call-center system holds
the sample, shows each operator the households to call, dials, and logs every attempt with a status code; the
interview itself is filled in KoBoToolbox, which the system opens with the household's code on the operator's
screen. The dial log is the system's export: one row per attempt. The tool reads two programs' layouts as they are,
and any other through the mapping card of the Import tab.

## The L2Taj layout

A semicolon-separated CSV, cumulative across rounds, downloaded from the system's export address each day:

`operator_id; hh_id; round; dialing_phone; start_time; end_time; comment; NT_comment; IS_comment; status; id`

| Role | Column | Read as |
|---|---|---|
| Enumerator | `operator_id` (such as `CATI01`) | the tool's ID, through the platform code the leader gave each enumerator (Prepare tab, step 5) |
| Household | `hh_id` | `hhid` |
| Round | `round` | rows of other rounds are left out and counted; a row without a round is kept |
| Number dialed | `dialing_phone` | the household's slot (1 to 3), found in the household list; the number itself is not kept. A number not in the list leaves the slot blank and is counted |
| Call start, end | `start_time`, `end_time` (`YYYY-MM-DD HH:MM:SS`, local, no offset) | `ts`, `end_ts`, placed in the round's time zone (the calendar's) |
| Result | `status` | `status`, by the map below |
| Record ID | `id` | `event_id` |
| Note | `comment` | `note` |

| Code | Meaning | Status in the tool |
|---|---|---|
| `SCS` | Successful: interview completed | `COMPLETE` |
| `NOA` | No answer | `NO_ANSWER` |
| `NOT` | No time | `NOT_AVAILABLE` |
| `NWR` | Non-working number | `DEAD_NUMBER` |
| `WNM` | Wrong number | `WRONG_NUMBER` |
| `OOS` | Out of service | `SWITCHED_OFF` |
| `ITR` | Interrupted survey | `PARTIAL` |
| `RFS` | Refused | `REFUSAL_SOFT` |
| `PWI`, `BLN` | No label in the files seen | `OTHER`, with the code in the note, until the program says what they mean |

The meanings of the codes follow the labels another program's system gives the same codes; the two without a
label are marked in the tool's profile and in the merged log's note.

## The L2CU layout

The Uzbekistan program's system exports three tables: the baseline, the sample (one row per household with its
operator, the next call's date, the agreement and the replacement links) and the call log:

`callid; hhid; operator; round; dialing_phone; start_time; end_time; comment; NT_comment; IS_comment; status; mood; qconnect; callplace`

read like the L2Taj layout, with the codes the program's own files label: `CS` completed successfully, `NA` no
answer, `NT` no time, `NWN` non-working number, `WN` wrong number, `OSA` out of service area, `IS` interrupted
survey, `BS` busy, `HU` hangup (read as `OTHER`), `NC` no call (not a dial).

## What the tool writes for the system: `cati_assignments.csv`

The system holds the assignment, so after the leader prepares the round (and after moving households during it)
the Call log tab writes the table the system loads, in the columns of the L2CU sample table and semicolon-separated:
`hhid; operator` (the platform code); `enumerator_id; round; date_nextcall; hour_nextcall` (the planned first dial);
`phone_1; phone_2; phone_3; replacement_for; rank` (a reserve's household and order); `psu; stratum`. One row per
household and per unused replacement. It holds phone numbers and goes to the system only. How a system loads such
a table is the vendor's business; the two programs' systems take a semicolon CSV.

## The interview form against the log

When the program's KoBoToolbox export (an interview form, `formats/kobo/README.md` section 2) is added with the
log, the tool checks one against the other instead of counting both. Each interview with consent is matched to a
completed call of its household within three hours of the interview's start (an interview resumed in a later call
still matches); a matched call takes the interview's end if its own is missing. Then:

- an interview without a logged completed call is listed under *Needs your decision*: the leader counts it as a
  complete or notes it;
- a completed call without an interview is listed too: the leader keeps it as a complete or recodes it as "other".

The Import tab sums it up: interviews, matched, unmatched, completed calls without an interview. A refusal recorded
in the form is not a call to match.

## Samples

`samples/cati/l2demo_calllog_2026-11-06.csv` is the synthetic program's log in the L2Taj layout: 717 rows, of
which 340 are the round-5 calls up to 6 November (the same calls as `samples/leader/exports_R05/`) and the rest
round 4, by the operators `CATI01`, `CATI02` and `CATI07`; `samples/cati/cati_assignments.csv` is the table the
tool writes for round 5. Every number uses the invalid country code +000.

## Checked against the real files

On 1 November 2026 the tool read the Tajikistan program's round-7 log as downloaded (53,719 rows, 7,162 of round 7
by eight operators) together with the round's KoBoToolbox export: dials per operator matched a count made outside
the tool (three rows without a round number were kept), the completes were 1,269 counted plus one household with
two completed calls to decide, against 1,269 households with a successful call of three minutes or more in the file;
and 601 of the 621 interviews in the export matched a completed call within three hours, the other 20 being listed
for the leader. Aggregates only; the files stay with the program.
