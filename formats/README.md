# File formats of the RTM interview tool

The tool has no server and no shared database. Everything moves between people as files, which the tool
reads when they are opened and writes when they are saved or exported. This folder defines those files.

- Each JSON file names its format in its `schema` field, for example `"schema": "rtm-assign-1.0"`. The tool
  refuses a file whose format it does not know, and says which button the file belongs to.
- The JSON Schemas in this folder (`rtm-*.schema.json`, draft 2020-12) are the exact definitions.
- `check_formats.py` checks any file or folder against them, and also checks integrity and privacy:

```
python3 formats/check_formats.py samples/
python3 formats/check_formats.py /path/to/common/folder --ask-passphrase
```

## The files at a glance

| File | Name | Format | Written by | Goes to | Names and numbers |
|---|---|---|---|---|---|
| Assignment | `E07_assignment_R05.json` | `rtm-assign-1.0` | Leader | That enumerator only, through a personal folder | Yes, that enumerator's households only |
| Call-log export | `E07_2026-10-27.csv` and `.json` | `rtm-calllog-1.0` | Enumerator | The common folder | Never |
| Contacts file | `E07_2026-10-27_contacts.json` | `rtm-contacts-1.0` | Enumerator, only when a number changed | The leader directly | Yes, the changed numbers |
| Saved session | `E07_project_R05.json` | `rtm-project-1.0` | Enumerator | The enumerator's own folder | Yes |
| Household list | `household_list.csv` | CSV, below | Leader | The leader's own folder | Yes |
| Replacement list | `selection.csv` (rtmtools) | CSV, below | Sampling tool | The leader | No |
| Round manifest | `L2MN_R05_manifest.json` | `rtm-roundmanifest-1.0` | Leader view | The leader; the merge reads it | Never |
| Merged round files | `L2MN_R05_calls.csv`, `_actions.csv`, `interviews.csv`, `outcome_codes.csv`, `calendar.csv`, `_merge_report.csv` | CSV, below | Leader view | The analysis folder | Never |
| Contact updates | `L2MN_R05_contact_updates.csv` | CSV, below | Leader view | The leader's own folder | Yes, the changed numbers |
| Passphrase list | `passphrases_L2MN_R05.csv` | CSV, below | Leader view, when files are protected | The leader only; each enumerator gets theirs privately | Passphrases |
| Leader session | `leader_L2MN_R05.json` | `rtm-leader-1.0` | Leader view | The leader's own folder | Yes |
| Risk lists | `L2MN_R05_risk_dropout.csv`, `_risk_return.csv` | CSV, below | Leader view | The leader only | No, IDs and tiers |
| Risk models | `models/risk_models.json`, bundled in the page | `rtm-riskmodels-1.0` | `models/train_risk.py` | Inside the tool | No, coefficients and aggregates |
| Protected file | any of the above | `rtm-sealed-1.0` | Leader or tool | as the file it protects | Encrypted |

Names use the enumerator ID, a two-digit round (`R05`), and for exports the local date of the export. The
log export is named exactly `{enumerator_id}_{date}`. Each export holds the whole round so far, so a newer
export replaces an older one. When a browser saves a second file of the same name, it may add " (1)" to the
name. The leader view therefore finds the newest export of each enumerator by the time inside the file, not
by its name, and pairs each CSV with the JSON of the same name whose rows it matches.

## Rules for every file

- **Text.** UTF-8, without a byte-order mark. Household and enumerator IDs are text, so leading zeros survive.
- **Times.** Logged events give instants in ISO 8601 with their offset, for example
  `2026-10-27T13:00:00+08:00`. The CSV gives local wall-clock time (`2026-10-27 13:00:00`) and the offset
  in its own `utc_offset` column, the form the handbook's harmonized dial tables and Stata read directly.
- **Who and when.** Every logged event carries `logged_by` (the enumerator ID) and `logged_at`.
- **Nothing is overwritten.** The log only grows. A correction is a new event that points to the event it
  corrects. Voiding a dial, or undoing an action, is also a new event. The CSV shows dials with
  corrections applied and voided dials left out, and marks corrected rows with `corrected = 1`.
- **Integrity.** Each event carries the hash of the event before it (`prev_hash`) and its own `hash`. The
  first event's `prev_hash` is the fingerprint of the round's first assignment (`chain_genesis`). Removing,
  reordering or editing an event after it was logged breaks the chain. This is an integrity check, not a
  signature: it shows that a log was changed, not who typed it.

**Canonical JSON and hashes.** A hash is the SHA-256 of the canonical JSON of an object: keys sorted, no
spaces, UTF-8 text not escaped. In Python:

```python
import hashlib, json
canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
sha = lambda o: hashlib.sha256(canon(o).encode("utf-8")).hexdigest()

def chain_ok(events, genesis):
    prev = genesis
    for e in events:
        body = {k: v for k, v in e.items() if k not in ("hash", "private")}
        if e["prev_hash"] != prev or sha(body) != e["hash"]:
            return False
        prev = e["hash"]
    return True
```

- An event's `hash` covers the event without `hash` and without its private part.
- An assignment's `fingerprint` covers the file without `fingerprint`.
- A saved session's `checksum` covers the file without `checksum`.

## Assignment file (`rtm-assign-1.0`)

One enumerator's households for one round. The leader writes one file per enumerator, and no file holds
another enumerator's contact information.

| Part | Fields |
|---|---|
| Header | `schema`, `program`, `country` (ISO code, picks the bundled holiday table), `round`, `enumerator_id`, `generated_by`, `generated_at`, `revision` (1 before the round, 2, 3… for files revised during it), `supersedes` (the earlier file's fingerprint, in a revised file), `rule`, `matching` (when the leader set criteria: `criteria`, the columns matched on, and `enumerator`, this enumerator's values), `replacement_policy`, `fingerprint` |
| `calendar` | `window_start`, `window_end`, `working_weekdays` (1 Monday to 7 Sunday), `call_hours` (`start`, `end`, whole hours), `time_zone` (IANA), `holidays` (`date`, `name`, `estimated`, `working`), `ramadan` (`dates`, `break_fast_hour`), `dial_cap` (the stopping rule, in dials), `day_list` (how many households the Today tab offers at most each day: the calls due, then households pulled forward from later days) |
| Each household | `hhid`, `psu`, `stratum`, `tz` (only where a program spans time zones); `contact` (`name`, `phones` with `slot`, `number`, `label`, `last_status`); `history` (`joined_round`, `last_interview` with `round`, `date`, `hour`; `last3`; `last_enumerator`); `assignment` (`reason`, `previous_enumerator`, `matched` when the round has criteria); `criteria` (the household's own values, when the round has criteria); `plan` (`first_dial_date`, `target_hour`); `handover` (only for a household moved to this enumerator during the round: `from`, `moved_at`, `dials` made before the move, `last_status`, `last_ts`); `replacements` (`hhid`, `rank`, `contact`, in order of use); `note` |

**Rules** (`rule.name`): `keep_same`, `equal_split`, `share_of_total`, `random`, `manual`. Keeping the
same enumerator is the handbook's stated default (Section 3.5.3): keep the same enumerator, rotate a
planned share of households each round (`rule.rotation_share`), and switch the enumerator for a household
that becomes hard to reach.

**Rule** (`rule`): `name` (`keep_same`, `random`, `equal_split`, `share_of_total` or `manual`) and `seed`; for
`keep_same`, `rotation_share`, `hard_to_reach` and `fallback`; for equal split and share of total, `order_by`, the
column the list is ordered by; for share of total, `method`, `blocks` or `random`. The enumerator view words a
household's reason by these.

**Reasons** (`assignment.reason`) say why the enumerator has each household: `keep`, `rotation`,
`switch_hard_to_reach`, `enumerator_unavailable`, `new`, `manual`, `capacity`, and `replacement` for an
activated replacement, and `rule` for a household that changes enumerator under a rule other than the
default: dealt at random (random, or share of total at random) or placed by a block of the list (equal split,
or share of total in blocks). The file's `rule` says which. `manual` is a household the leader's list or a move
by hand placed. `rule` was added in the review loop; files written before it gave `rotation` to a household
dealt at random, and `manual` to one placed by a block. Two reasons were added on 31 October 2026: `match`, a
kept household moved because its enumerator did not match the leader's criteria (language, sex, area), and
`mid_round`, a household moved during the round from an enumerator who would not finish to one with spare
days; both keep `previous_enumerator`.

**Matching criteria** (`matching`), when the leader set any: `criteria` lists the columns of the household list
matched on; `enumerator` gives this enumerator's values for each. A household goes only to an enumerator whose
values include the household's; a household without a value can go to anyone. Each household's own values are in
its `criteria`, and `assignment.matched` says whether its enumerator matches (false only when the leader moved it
by hand regardless).

**Revisions.** A file written during the round after households were moved has `revision` 2, 3… and `supersedes`,
the fingerprint of the file it replaces. The enumerator opens it with "Load updated assignment", which keeps the
log; a file older than the one in the session is refused. A revised file may omit `plan` and `history` for
households the enumerator already had: the view keeps them from the earlier file, beside the new one, so that the
new file's fingerprint still verifies. A household moved in carries `handover`: the previous enumerator's dials,
which count toward the dial cap.

**Replacement policy.** `active` turns replacements on for the round. `triggers` lists when the enumerator
may activate the next replacement: `REFUSAL_HARD`, `ALL_NUMBERS_DEAD`, `CAP_REACHED`.

The tool refuses an assignment that has no households, a household listed twice, a replacement listed for
two households or also listed as a main household, or a calendar it cannot use. It opens one whose
fingerprint does not match, with a warning, and records the mismatch in the log.

## Call-log export (`rtm-calllog-1.0`)

**The CSV** has one row per dial, in these columns and this order. The names are those of the handbook's
harmonized dial table where one exists: `hhid`, `round`, `attempt`, `ts`, `end_ts`, `dur_min`, `is_cmp_code`
and `operator`. `status` holds the tool's own fixed codes; the handbook's table keeps each program's code as
`status_raw`.

| Column | Content |
|---|---|
| `program`, `round` | The round (Box 3.0) |
| `hhid` | Household ID. A case is a household in a round (Box 3.0) |
| `attempt` | Dial number within the case, in time order: 1, 2, … |
| `ts`, `end_ts`, `utc_offset` | Dial start and end, local time, and the offset that gives the instant |
| `dur_min` | Minutes, two decimals; empty when the end is unknown |
| `status` | The dial's disposition, one of the codes below |
| `is_cmp_code` | 1 when `status` is `COMPLETE`. Analysis applies Box 3.0's 3-minute rule on top |
| `operator` | The account that dialed: the enumerator ID |
| `phone_slot` | Which of the household's numbers the dial used. The number itself is never exported |
| `appointment_ts` | The callback booked on this dial, if any |
| `action` | A case action taken with this dial, not a disposition (3.3 box) |
| `replaces` | For a replacement's dials, the household it replaces |
| `note` | Operational note; the screen warns against personal details |
| `corrected` | 1 when a later correction changed this dial |
| `logged_by`, `logged_at` | Who entered the dial and when; a call logged afterwards keeps its own `ts` |
| `event_id`, `prev_hash` | The dial's event, and the hash of the event before it |

**Dispositions** (`status`). The tool's codes are fixed. A program will map its own codes onto them once,
in the leader view (Step 3).

| Code | Meaning | Category |
|---|---|---|
| `COMPLETE` | Interview completed | complete |
| `PARTIAL` | Interview started, not finished | contact, no interview |
| `APPOINTMENT` | Contact made, callback booked | contact, no interview |
| `NOT_AVAILABLE` | Household reached, respondent not available | contact, no interview |
| `REFUSAL_SOFT`, `REFUSAL_HARD` | Refusal that can, or cannot, be retried | refusal |
| `NO_ANSWER`, `BUSY` | Rings without answer; busy | non-contact |
| `SWITCHED_OFF` | Phone off or unreachable | non-contact |
| `DEAD_NUMBER` | Number not in service or does not exist | not eligible on this number |
| `WRONG_NUMBER` | Someone unrelated to the household answers | not eligible on this number |
| `LANGUAGE`, `OTHER` | Language barrier; other, with a note | contact, no interview |

A complete shorter than 3 minutes is accepted, and the screen says that Box 3.0 will count it as an
appointment contact.

**Actions** are case actions, not dispositions (3.3 box): `RELEASE` (stop calling for this round; the
household stays in the panel, 3.3.5), `SWITCH_REQUEST` (ask for another enumerator next round),
`REMOVE_REQUEST` (no number works), `ACTIVATE_REPLACEMENT` (with `target_hhid`).

**The JSON** carries what the CSV cannot:

| Part | Content |
|---|---|
| Header | `program`, `round`, `enumerator_id`, `assignment_fingerprint`, `chain_genesis`, `exported_at`, `exported_by`, `event_count`, `last_hash`, `chain_verified`, `contains_contact_information` (always `false`), `contacts_file` |
| `events` | Every event of the round so far, each with its hash, without private parts |
| `dials` | The CSV's rows, the same values |
| `actions` | Actions taken on their own, not with a dial |
| `corrections` | The correction events, each pointing to the event it corrects (`target`) |
| `contact_updates` | Which numbers changed, by household and slot, without the numbers |

**Event types:** `session` (the session started, or an updated assignment was opened; with the
assignment's fingerprint and whether it matched), `dial`, `action`, `correction` (`changes`, or `void`),
`contact_update` (`slot`, `change` as `add`, `correct` or `mark_dead`, `label`, and `private_digest`), and
`export`.

## Contacts file (`rtm-contacts-1.0`)

New or corrected numbers reported during the round, written only when a number changed. Each update gives
the household, the slot, the change, the number, and `private_digest`, the same digest as in the logged
event. The leader can therefore match each number to its event without the number ever entering the call
log. This file goes to the leader directly, not to the common folder.

## Saved session (`rtm-project-1.0`)

Everything needed to continue later: the assignment as opened, every event with its private part, the
earlier logs loaded for the performance view, the view state, the last export, and a checksum. Saving
overwrites the same file where the browser allows it (Chrome, Edge). Elsewhere each save downloads a new
file with the time in its name, for example `E07_project_R05_2026-11-04_1842.json`, and the screen shows
the name of the latest one.

## Protected files (`rtm-sealed-1.0`)

Protection is optional (decision D11) and off unless the leader turns it on. A protected file is an
envelope:

- **Key.** A key is derived from the passphrase with PBKDF2-SHA-256 (600,000 iterations, 16-byte salt).
- **Encryption.** The file is encrypted with AES-256-GCM, in the browser and offline.
- **Label.** The envelope's label stays readable: what it contains, the program, the round and the
  enumerator. The label is bound to the encryption, so it cannot be moved onto another file.
- **Passphrase.** The passphrase is never stored. The derived key stays in memory for the session only.

When a session starts from a protected assignment, its saved sessions and contacts files are protected
with the same passphrase. Its call-log exports are not, because they hold no names or numbers.

## The leader's inputs

**Household list** (proposal A.1). One row per household, CSV in UTF-8 (Excel users save it as CSV UTF-8).

| Column | Content |
|---|---|
| `hhid`, `psu`, `stratum` | Required. IDs are text |
| `phone_1` … `phone_3` | At least one number; `phone_1_label` … say whose number it is |
| `contact_name`, `respondent_member`, `language`, `tz` | Optional; `tz` is an IANA name, only where a program spans time zones |
| `status` | `active` (the default), `removed` (kept in the list, never deleted) or `reserve` (a replacement not yet used) |
| any other column | Kept with the household. `language` and any other column with few distinct values (for example `respondent_sex`, `dialect`, `region`) can be a matching criterion in step 5: households then go only to enumerators whose values include theirs |

A household listed as a replacement, never activated and without a status is treated as a reserve, so a list
without a `status` column works too. The list includes the replacements, whose contacts the assignment
files need.

**Replacement list** (A.2). Either the sampling tool's `selection.csv`, read as rtmtools writes it, or a
program's own file with `hhid, replacement_hhid, rank`. From `selection.csv` the tool uses `unit_id`,
`stratum` (the PSU, in a phone-sample draw), `selected` (1 for a main household, with its `rank` in the
selection order) and `reserve` (the reserve's rank, 1, 2, …). Each PSU's reserve is dealt round-robin to its
main households in selection order (D6). An export whose IDs were written in scientific notation
(`1.10e+08`, as rtmtools wrote numeric IDs before its fix of 27 October 2026) is refused with a message
saying so. `samples/rtmtools_export/` holds a real export, which `tests/test_rtmtools_import.py` reads.

**Earlier rounds.** Any of: the merged files the leader view exports for each round (`_calls.csv`,
`_actions.csv`, `_manifest.json`); a program's own dial log in the same columns (at least `hhid`, `round`,
`ts`, `status`, best with `end_ts` or `dur_min` and `operator`), whose own result codes the leader maps once
onto the tool's; or interview records with `hhid, round, interview_date, outcome, enumerator` (an outcome of
`complete` counts as interviewed). A file name with `_R05` gives the round when the rows have none.

## The round manifest (`rtm-roundmanifest-1.0`)

Written with the assignment files. It lists every enumerator of the round with their number of households
and the fingerprint of their assignment file, the enumerators away, the rule with its seed, the calendar,
and every household with its enumerator, the reason, the previous enumerator and its unused replacements,
all as IDs. It holds no names or phone numbers. The merge checks every export against it.

When the leader set matching criteria, `matching` records them with every enumerator's values, and each household
has `matched`. When households are moved during the round, the leader view writes the manifest's next `revision`
(with `supersedes`, the fingerprint of the one it replaces): the moved households carry the reason `mid_round` and
their previous enumerator, `moves` lists every move with the household, from, to, when and by whom, and each
revised enumerator's roster entry keeps `previous_fingerprints`, so that a log begun from the earlier file still
belongs to the round. The merge accepts the previous enumerator's dials on a moved household up to the move and
flags any made after it as a double call (`after_move`), for the leader to keep or leave out.

## The leader's outputs for the round

| File | Content |
|---|---|
| `{program}_R{rr}_calls.csv` | The merged call log: every enumerator's dials, corrections applied, voided dials and dials the leader left out excluded, in the same 21 columns as an enumerator's CSV. `attempt` counts the dials to a household across enumerators. The handbook's analysis scripts read it as a program's log, and the leader view reads it back as an earlier round |
| `{program}_R{rr}_actions.csv` | Every case action: `program, round, hhid, action, target_hhid, reason, note, via, logged_by, logged_at, event_id`; `via` is `dial` when the action was taken with a dial |
| `interviews.csv` | One row per household of the round, `hhid` first, for the Section 4.2 round template: `hhid, interview_date, outcome, enumerator` |
| `outcome_codes.csv` | `code, meaning, note` for every outcome used in `interviews.csv`; copy the codes into the template's outcome map |
| `calendar.csv` | `round, start, end` for the template's register |
| `{program}_R{rr}_merge_report.csv` | Every situation the merge found: `type, severity, status, enumerator, hhid, file, detail, decision, resolved_by, resolved_at, note, key` |
| `{program}_R{rr}_contact_updates.csv` | New or corrected numbers from the contacts files, with `digest_ok` when the number matches the call log. Holds phone numbers |
| `passphrases_{program}_R{rr}.csv` | When files are protected: `enumerator_id, file, passphrase`. Shown once and never stored by the tool |

Outcomes in `interviews.csv`: `COMPLETE` (the counted complete), `REFUSED`, `CONTACT_NO_INTERVIEW`,
`NO_CONTACT`, `NUMBER_NOT_WORKING`, `REPLACED`, `NOT_DIALED`, `NOT_REPORTED` (the enumerator's export is
missing) and `CONFLICT` (two completes the leader has not resolved). The round template uses only the meaning
`complete`. A completed household's `interview_date` is the date of its complete; another household's is the
date of its last dial.

## The leader session (`rtm-leader-1.0`)

Everything needed to continue: the settings, the inputs (the household list included), the assignment and
its manifest, every imported file, the leader's decisions on the merge, and the leader's own log, in which
every action carries `logged_by` and `logged_at` and is hash-chained like the enumerators' logs. A checksum
covers the file; a session changed outside the tool is refused. It holds contact information, and can be
protected with a passphrase.

## The risk lists and the risk models (Step 4)

**Risk lists** (`{program}_R{rr}_risk_dropout.csv`, `_risk_return.csv`), for the leader only: `model, round, hhid,
enumerator_id, tier, relative_to_round_average, chance, model_version, driver_1, driver_2, driver_3`.
`relative_to_round_average` is the household's score divided by the round's average score: it orders households and
is not a chance, and the backtests check the ordering, not the ratio. `chance` stays empty until the model is
recalibrated on the program's own rounds. Each driver ends with (+) when it raises the score and (−) when it lowers
it. Tiers never go into assignment files and enumerators never see them (D7).

**Risk models** (`models/risk_models.json`, schema `rtm-riskmodels-1.0`), written by `models/train_risk.py` and bundled
into the page by `build.py`: for each model, its features with their means, standard deviations and coefficients, the
programs' intercepts and their average, the groups of features its explanations use, the tier shares, the result codes
read as each category, and a summary of the backtests. It holds coefficients and aggregates only, never a household.
`models/MODEL_CARD.md` is written from it and from `models/validation.json`.

## Changes from the proposal, made in Step 2 and approved on 27 October 2026

- **Times in the CSV.** The proposal gave `ts` and `end_ts` in ISO 8601 with offset. The CSV gives local
  wall-clock time with a separate `utc_offset` column, because the handbook's harmonized dial tables and
  Stata read that form directly. The JSON events keep full ISO 8601.
- **Phone numbers.** The proposal put contact updates in the JSON export, flagged. The numbers now go to a
  separate contacts file, so that nothing placed in the common folder ever holds a phone number. The
  export keeps a `contact_updates` list without the numbers.
- **Protection of derived files.** Decision D11 covered assignment files. A session opened from a protected
  assignment also protects its saved sessions and contacts files, which hold the same numbers.

## Additions made in Step 3, approved on 27 October 2026

- **A `reserve` status** in the household list, besides `active` and `removed`, so that unused replacements
  can travel in the same list. A list without it still works: reserves are recognised from the replacement
  list and the history.
- **An actions file** for each round (`_actions.csv`). The proposal's merged call log has one row per dial,
  so actions taken without a dial (a switch request, an activated replacement) needed their own file; the
  leader view reads it back as history.
- **`outcome_codes.csv`** documents the codes of `interviews.csv`. The Section 4.2 template keeps its codes in
  its configuration block, not in a file, so the leader copies them there.
- **One passphrase per enumerator** when assignment files are protected (D11), made by the tool and shown
  once, so that one enumerator's passphrase never opens another's file.

## Files of KoBoToolbox, Survey Solutions and a calling service (1 November 2026)

For a team that records its calls in KoBoToolbox or Survey Solutions rather than in this tool's enumerator view
(proposal K; `formats/kobo/README.md` and `formats/suso/README.md` have the forms and the daily cycle).

| File | Direction | Written or read as |
|---|---|---|
| `households.csv` | Leader view → the KoBoToolbox project (Settings › Media) | One row per household and unused replacement: `name`, `label`, `hhid`, `enumerator_id`, `program`, `round`, `contact_name`, `phone_1`–`phone_3` with labels, `planned_date`, `planned_hour`, `psu`, `stratum`, `kind`, `replaces`, `rank`. Has phone numbers |
| `assignments.tab` | Leader view → Survey Solutions (Upload assignments) | One tab-delimited row per household: the identifying variables, up to two replacements, `_responsible` (the enumerator's login), `_quantity` (1). Has phone numbers |
| KoBoToolbox data export | KoBoToolbox → Import tab | The form's CSV export ("XML values and headers"), one row per call record, recognised by `_uuid` and `_submission_time`; split by `enumerator_id` and merged as a CSV export of each enumerator |
| Survey Solutions export | Survey Solutions → Import tab | The export zip, or `rtm_call_record.tab` (one row per interview, `interview__id`, `interview__key`, the identifying variables) with `calls.tab` (one row per call, `interview__id`, `calls__id`); joined and merged the same way |
| Calling service log | The service → Import tab | A CSV with at least the number called, the start, the end or duration and the status (Twilio's Call resource names; case and spaces ignored); matched to the recorded calls by number and time, never re-exported |

Each call record carries `hhid`, `enumerator_id`, `program`, `round`, `phone_slot`, `call_start`, `call_end`, `result`
(the tool's codes, or `NONE` for an action or a note without a call), `willing` (yes, later, no, not asked),
`appointment`, `action`, `target_hhid`, `replaces` and `note`; in the merged call log the willingness appears in
`note` as `willing: later`, and the event ID is KoBo's `_uuid` or Survey Solutions' `interview__id:calls__id`.

## Additions made on 31 October 2026, from the supervisor's requests of 28 October, for the author's approval

- **Matching criteria.** `matching` in the assignment file and the manifest; `criteria` and `assignment.matched`
  for each household; the reason `match`. Any column of the household list can be a criterion.
- **The day list.** `calendar.day_list`, the leader's number or 1.5 × the planned first dials per enumerator per
  day. The enumerator's Today tab fills the list with households "ahead of plan".
- **Moves during the round.** `revision` and `supersedes` in the assignment file and the manifest; `handover` for a
  moved household; the reason `mid_round`; `moves` and `previous_fingerprints` in the manifest; the merge issue
  `after_move`. The enumerator's saved session gains `carry`, the plans and history kept from an earlier file.
- Files written before these additions read as before: every new field is optional.
