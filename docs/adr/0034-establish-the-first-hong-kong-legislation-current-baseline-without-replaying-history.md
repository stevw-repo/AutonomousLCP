---
status: accepted
date: 2026-08-12
amended_by:
  - "0079"
  - "0080"
  - "0081"
refines:
  - 0003
  - 0005
  - 0011
  - 0012
  - 0018
  - 0019
  - 0022
  - 0023
  - 0025
  - 0026
  - 0029
  - 0032
  - 0033
depends_on:
  - 0021
  - 0028
  - 0030
---

# Establish the first Hong Kong legislation current baseline without replaying history

The first trusted Hong Kong Legislation baseline answers a limited question:

> What complete set of Hong Kong legislation does the accepted official
> evidence support as searchable current law at one fixed observation cutoff?

It does not try to replay every amendment, commencement, renumbering, repeal,
or consolidation that led to that state. For a clear item, a complete and
internally consistent current HKeL evidence bundle, the current official status
and structure signals, and no conflicting accepted evidence are sufficient to
establish its present baseline state. Historical evidence is acquired only
when a specific item, identity, status, or continuity question cannot be
resolved from the accepted current evidence.

This is intentionally narrower than historical reconstruction. The baseline
may say, “this provision is supported as operative current text at the
cutoff.” It may not invent the date or event by which the provision became
operative, claim a complete amendment history, or construct missing current
text from old versions.

## Why this boundary is needed

Requiring a complete historical event chain for every current provision would
turn the first baseline into a decades-long reconstruction project. It would
also create false confidence because surviving historical artifacts may be
incomplete, especially for older events. At the other extreme, treating an
HKeL status label or current list entry alone as proof would ignore the
accepted bilingual text, verified-copy, source-conflict, and disposition
rules.

The accepted middle course is:

- prove the complete present inventory and each searchable current payload;
- accept clear present state without proving every earlier event;
- make no historical assertion that the evidence does not support;
- open bounded historical investigation only for a named uncertainty; and
- quarantine the affected item when that uncertainty remains material and
  unresolved.

## Ordered baseline path

The first baseline uses the following order:

1. freeze one observation cutoff, source set, specification bundle, and
   rulebook version;
2. reconcile the complete current HKeL inventory into the three accepted
   Release Scopes;
3. acquire and reconcile the evidence required for every proposed current
   record and every non-searchable disposition;
4. decide whether the current evidence clearly supports present operative
   state;
5. open targeted historical investigation only where a concrete uncertainty
   remains;
6. allocate new register-owned identities without importing legacy identity
   semantics;
7. assign one disposition and construct or exclude records under the existing
   six-field serving contract; and
8. seal a first Corpus Release only after complete scope accounting passes.

A later rule cannot cure an earlier evidence failure. Historical similarity
cannot repair missing current XML or PDFs, and a current HKeL status signal
cannot cure a same-fact conflict with accepted official evidence.

## Stable baseline rules

### `HKLEG-BASE-OBS-001` — freeze one baseline observation package

Record one explicit baseline observation cutoff and the exact versions and
fingerprints of the Hong Kong Legislation Source Rulebook, Release Scope
registry, HKeL Publication Specification Bundle, current HKeL inventory, and
all other source Observations required at that cutoff.

The release-blocking current HKeL inventory and Gazette observations must be
complete and fresh under their accepted monitoring tiers. Weekly supporting
and item-specific sources must be available whenever a baseline decision
actually relies on them. Evidence from different cutoffs may not be silently
mixed into one baseline package.

### `HKLEG-BASE-INV-001` — account for the complete current inventory

Reconcile every item, resource, language, version signal, status signal,
locator, declared hash, and legal object exposed by the complete current HKeL
inventory. Route each legal object to exactly one of
`HK-LEG-ORDINANCES`, `HK-LEG-SUBSIDIARY`, or
`HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` by legal nature rather than by
file location or A-number.

Every observed object must later receive one supported disposition. Missing,
duplicate-owned, unclassified, or unaccounted objects block the affected scope
from being called complete. Instruments & Others entries require the accepted
Instrument Disposition Registry. Because its approach and row population are
flagged for future review, the constitutional-and-other-instruments baseline
cannot be called final while that gate remains open; the other non-overlapping
Release Scopes are not automatically blocked.

### `HKLEG-BASE-EVID-001` — apply the settled current-evidence gates

Every baseline location proposed for `SEARCHABLE_CURRENT` must pass the
applicable evidence path already fixed by
`HKLEG-CURRENT-EVID-001` to `HKLEG-CURRENT-EVID-004`:

- matching English and Traditional Chinese current XML plus matching official
  HKeL verified or assisted copies under ADR 0081.

The current inventory records, pinned specifications, hashes, deterministic
mapping, bilingual alignment, and reconciliation report are part of that
evidence. A non-searchable disposition must have the evidence required to
support its own status and reason. Missing evidence blocks the affected
decision; conflicting or unreconcilable evidence enters Quarantine. Historical
text alone never substitutes for missing current evidence. ADR 0080
reconstruction requires the separate complete official base, event-chain,
operation, and bilingual proofs.

### `HKLEG-BASE-STATE-001` — establish clear present state

The baseline may establish a location as presently operative current text when
all of the following are true at the cutoff:

- `HKLEG-BASE-INV-001` accounts for the item and its Release Scope;
- `HKLEG-BASE-EVID-001` proves the exact current bilingual text and version;
- the current HKeL item and provision status and structure signals are
  complete, unambiguous, and consistent with that evidence;
- no open current Gazette, Editorial Record, constitutional-source, urgent, or
  other accepted signal conflicts with the proposed state; and
- the written rulebook supports the item's ownership and disposition.

This combined threshold proves the present baseline state. An HKeL list entry,
`InEffect` value, version date, status code, or current-copy label on its own
does not.

### `HKLEG-BASE-LIMIT-001` — limit the baseline assertion

A present-state baseline decision does not prove the complete path by which
the law reached that state. Unless exact accepted evidence is actually
preserved and a rule assigns the fact, the decision must not assert:

- a commencement, amendment, repeal, revival, expiry, or replacement event;
- the historical effective date of the current wording;
- continuity through a renumbering, split, merge, re-enactment, or source
  replacement; or
- a complete historical version or event chain.

Do not invent a date, infer an event from textual similarity, or backfill a
lineage merely to make the register look complete. The baseline records an
explicit `historical_assertion_scope: PRESENT_STATE_ONLY` or equivalent
machine-readable reason code until the exact rulebook schema is settled.

### `HKLEG-BASE-REVIEW-001` — open a targeted historical investigation

Open bounded historical work only when a named material uncertainty prevents
an otherwise required baseline decision. Triggers include:

- two current source entries may represent the same Legal Item or Location;
- present status is partial, conditional, internally inconsistent, or unclear;
- ownership, replacement, cessation, reappearance, renumbering, split, merge,
  or continuity affects the current disposition but is not proved;
- current accepted sources conflict on the same fact; or
- the rulebook expressly requires an earlier artifact or event for the item-
  specific decision.

Record the exact question, affected object, requested source roles, permitted
facts, stopping condition, and responsible Legal Desk. Do not download the
whole historical corpus merely because one item is unclear.

### `HKLEG-BASE-HIST-001` — use historical evidence only for the opened question

Acquire HKeL past inventories, past bilingual XML and matching past verified
PDFs, or official archival Gazette evidence only as required by an open
`HKLEG-BASE-REVIEW-001` task. The evidence may establish only the fact assigned
to its Registered Source and the written rule that consumes it.

Similarity, matching wording, a source move, or disappearance may identify a
candidate explanation but cannot prove identity, legal status, or an event.
If requested history is unavailable, conflicting, or insufficient, block or
quarantine only the affected decision unless its absence makes complete
Release Scope accounting impossible. Historical evidence alone cannot create a
reconstructed consolidation or replace the current evidence gate. ADR 0080's
complete reconstruction package is a separate accepted path.

### `HKLEG-BASE-ID-001` — issue greenfield identities from accepted evidence

After the relevant evidence and present-state decision pass, the Management
Register allocates new opaque Legal Item, Official Version, Legal Location,
and Search Record identities under ADR 0011. HKeL numbers, URLs, titles,
citations, visible locators, files, and any legacy Distillation or Pinecone IDs
are Identity Aliases or traceability facts, not authoritative identity inputs.

No historical predecessor is required merely to allocate a new identity for a
clear present object. But the pipeline must not assert an unproved predecessor,
successor, split, merge, or continuation relationship. A duplicate or
continuity ambiguity that affects current identity follows
`HKLEG-BASE-REVIEW-001` and remains quarantined if unresolved.

### `HKLEG-BASE-DISP-001` — assign the existing five dispositions

Apply the legal tests in `HKLEG-CURRENT-DISP-001` to assign exactly one primary
disposition to every baseline legal object:

- `SEARCHABLE_CURRENT`;
- `WAITING_ROOM`;
- `EVIDENCE_ONLY`;
- `HISTORICAL`; or
- `QUARANTINE`.

Clear current HKeL evidence can establish present searchability under
`HKLEG-BASE-STATE-001`; it cannot turn ambiguous, partially commenced,
conflicting, or unsupported material into current search. Non-searchable
objects remain fully accounted for outside Pinecone.

### `HKLEG-BASE-REC-001` — construct first-baseline records

For every `SEARCHABLE_CURRENT` location, construct and validate the canonical
bilingual payload under ADR 0021 and all six required metadata fields under
ADRs 0013, 0020, and 0050. Use exact `metadata.authority_note: "None"` when no
approved substantive note applies.

Because there is no accepted greenfield predecessor, allocate a new Search
Record ID under `HKLEG-BASE-ID-001`; do not carry forward a legacy ID merely
because its text or locator appears to match. Passing this rule creates a
candidate record only. It authorizes no embedding, Pinecone mutation,
promotion, or deployment.

### `HKLEG-BASE-REL-001` — prove complete first-release accounting

Before the first Corpus Release for a Hong Kong Legislation Release Scope may
be sealed, account for every current-inventory object and location, every
candidate and non-searchable disposition, every missing or conflicting
artifact, every open or completed historical investigation, every Quarantine,
every Coverage Gap, and every identity decision.

The first release explicitly records that it has no accepted predecessor and
is an initial baseline rather than a delta or no-change release. It preserves
the ordered Rule Trace, rulebook and source fingerprints, cutoff, completeness
proof, and unresolved facts. An unaccounted item or unresolved completeness
gap blocks sealing or requires ADR 0005's explicit unavailable-scope outcome.

### `HKLEG-BASE-CHANGE-001` — do not mix a later source change into the freeze

If an accepted source changes after the baseline cutoff but before the
baseline is ready for use, preserve the original frozen package and record the
new Observation separately. The pipeline must either:

- abandon and re-freeze the affected baseline work at a later cutoff; or
- complete the internally consistent baseline at its original cutoff, accept
  it as the predecessor bundle, and process the later signal through the
  ordinary `HKLEG-CURRENT-*` update rules before any state claiming later
  currency is promoted.

It may not silently mix old and new source artifacts, update only convenient
items, or continue to call the older cutoff freshly current.

## Conformance cases

The future executable baseline rules must pass at least these fixtures:

| Case | Facts | Required rule trace and result |
|---|---|---|
| `HKLEG-BASE-CASE-001` | A current Ordinance is completely inventoried; bilingual XML and verified PDFs reconcile; HKeL's current item and provision signals are unambiguous; no accepted signal conflicts | `OBS-001`, `INV-001`, `EVID-001`, `STATE-001`, `LIMIT-001`, `ID-001`, `DISP-001`, `REC-001`, `REL-001` → create a new greenfield current record without replaying its amendment history |
| `HKLEG-BASE-CASE-002` | The clear item in Case 001 has no complete historical amendment chain | `OBS-001`, `INV-001`, `EVID-001`, `STATE-001`, `LIMIT-001`, `ID-001`, `DISP-001`, `REC-001`, `REL-001` → create the current record with present-state-only scope; make no historical event or effective-date assertion |
| `HKLEG-BASE-CASE-003` | HKeL lists an item as current or `InEffect`, but a required current XML language or any matching official HKeL copy is missing | `OBS-001`, `INV-001`, `EVID-001` plus `HKLEG-CURRENT-EVID-003` → affected evidence unavailable; no Search Record; history cannot cure the missing current bundle |
| `HKLEG-BASE-CASE-004` | Current English XML conflicts with its matching HKeL copy | `EVID-001` plus `HKLEG-CURRENT-EVID-004` → Quarantine; no current-state conclusion |
| `HKLEG-BASE-CASE-005` | Current evidence shows mixed or partial provision status and does not clearly identify which locations are operative | `OBS-001`, `INV-001`, `EVID-001`, `STATE-001` fails, `REVIEW-001` → targeted event or historical investigation; affected locations remain outside current search until resolved |
| `HKLEG-BASE-CASE-006` | Targeted official event evidence proves that only sections 2 and 5 commenced and matching current bundles exist | `OBS-001`, `INV-001`, `EVID-001`, `REVIEW-001`, `HIST-001`, `STATE-001`, `LIMIT-001`, `ID-001`, `DISP-001`, `REC-001`, `REL-001` → only sections 2 and 5 are current; other locations receive their supported non-searchable dispositions |
| `HKLEG-BASE-CASE-007` | Two current entries may be duplicates or a renumbered continuation, but no accepted evidence proves the relationship | `OBS-001`, `INV-001`, `EVID-001`, `REVIEW-001`, `HIST-001` → Quarantine the affected identity decision; do not merge by wording similarity |
| `HKLEG-BASE-CASE-008` | The requested past-data or archival source is unavailable during Case 007 | `HIST-001` → block the affected identity decision; unrelated clear items continue unless complete scope accounting is impossible |
| `HKLEG-BASE-CASE-009` | Historical sources are unavailable, but no baseline item or decision requires them | `OBS-001`, `INV-001`, `EVID-001`, `STATE-001`, `LIMIT-001`, `ID-001`, `DISP-001`, `REC-001`, `REL-001`; no `REVIEW-001` or `HIST-001` rule is invoked → the clear baseline is not blocked |
| `HKLEG-BASE-CASE-010` | A clear present item has a matching legacy Distillation or Pinecone record ID | `ID-001`, `REC-001` → allocate new greenfield identity; preserve the old ID only as a non-authoritative alias or migration trace fact |
| `HKLEG-BASE-CASE-011` | A validly enacted item has a complete bilingual current bundle, but its present commencement is not proved | `STATE-001` fails; `REVIEW-001`, then `DISP-001` → Waiting Room or Quarantine according to the available evidence; no current record |
| `HKLEG-BASE-CASE-012` | A current Gazette event proves an operative change, but matching current HKeL evidence is absent | Apply `HKLEG-CURRENT-EVENT-001` and ADR 0080 → record the event and Coverage Gap; select an eligible warned `RECONSTRUCTED_CONSOLIDATION`, otherwise ADR 0079 warned carry-forward, otherwise no record |
| `HKLEG-BASE-CASE-013` | One Instruments & Others entry lacks an accepted reviewed registry disposition | `INV-001` → the constitutional-and-other-instruments scope is not final or sealable; Ordinances and subsidiary scopes are not automatically blocked |
| `HKLEG-BASE-CASE-014` | A blocking source changes after the frozen cutoff while baseline work is still open | `CHANGE-001` → re-freeze, or finish the original cutoff and run a separate ordinary update before claiming later currency; never mix cutoffs |

In this table, shortened baseline forms such as `OBS-001` mean the complete ID
`HKLEG-BASE-OBS-001`. Explicit `HKLEG-CURRENT-*` references retain their full
ordinary-rule meaning. A case passes only when its ordered Rule Trace, evidence,
assertion limits, identity effects, and outcome all match.

## Consequences and remaining work

The first trusted baseline no longer requires an artificial replay of decades
of Hong Kong legislative history. It remains strict where present use matters:
complete inventory, current bilingual text and applicable PDFs, clear present
status, conflict checks, one disposition per object, new greenfield identity,
and complete release accounting.

The baseline is not proof of historical completeness. Future research may add
supported events and relationships append-only, but it may not retroactively
pretend those facts were known at the baseline cutoff. ADRs 0035 through 0038
and 0040 settle all five conceptual HKeL reconciliation groups. ADR 0041 fixes
their strict fixture package, and ADR 0042 fixes the frozen rulebook package
and per-scope readiness model. Exact executable schemas, fixture bytes,
validators, and code catalogues remain implementation work. The user-flagged
Instruments & Others approach and row population remain a required future
review before that Release Scope is final or implementation-ready.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
