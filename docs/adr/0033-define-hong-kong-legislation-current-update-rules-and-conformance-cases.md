---
status: accepted
date: 2026-08-12
amended_by:
  - 0044
  - "0079"
  - "0080"
  - "0081"
refines:
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
  - 0031
  - 0032
depends_on:
  - 0021
  - 0028
---

# Define Hong Kong legislation current-update rules and conformance cases

The Hong Kong Legislation Source Rulebook uses the stable rules below for an
ordinary update against a previously accepted current HKeL evidence bundle.
The rules turn the accepted source and legal policies into one ordered decision
path. Each rule names the required evidence, the fact it may establish, and the
only permitted outcome.

The human-readable rules, future machine-readable rules, automated fixtures,
Legal Desk decisions, and review display all use the same stable rule IDs. A
software component may execute a named rule; it may not create a new legal rule
from source prose, text similarity, an AI result, or a convenient default.

This decision does not define the first trusted current baseline. When there is
no preserved previous accepted current bundle, the pipeline opens the separate
baseline path now defined by ADR 0034. It may acquire historical evidence on
demand under ADR 0032, but it cannot label an unproved starting state as an
ordinary no-change update.

## Ordered rule path

The rule path has six gates:

1. prove that the required source observations are complete;
2. detect a genuine affected signal;
3. acquire and reconcile the complete bilingual HKeL evidence bundle;
4. compare it with the preserved previous accepted current bundle;
5. prove the legal or official cause and present disposition; and
6. create, reuse, withhold, or retire records only through complete release
   accounting.

A later gate cannot cure failure at an earlier gate. In particular, a plausible
legal explanation cannot cure mismatched bilingual text, and a matching HKeL
bundle cannot prove commencement or repeal without the event evidence assigned
to that fact.

## Observation rules

### `HKLEG-CURRENT-OBS-001` — complete supported no change

Apply this rule only when every source observation due under the accepted
monitoring tiers is complete, fresh, reconciled, and unchanged; the current
HKeL inventory matches its previous accepted fingerprint; the ordinary and
Extraordinary Gazette inventory contains no unmatched affected event; the
Editorial-Record and publication-specification checks produce no affected
signal; and no accepted urgent signal remains open.

Processing passes with workflow result `SUPPORTED_NO_CHANGE`, legal disposition
`NOT_APPLICABLE`, no Coverage Gap, and no record output. Record the Observation
and comparison fingerprints, stop affected acquisition, AI, embedding, and
record work, and reuse the existing Corpus Release in later desired-state
composition. Do not create a zero-record release or a new release merely to
record silence.

### `HKLEG-CURRENT-OBS-002` — open bounded affected work

Any new, changed, missing, or unexpectedly reappearing item, resource,
language, version, status signal, locator, declared hash, Gazette event,
Editorial Record, or relied-on specification fingerprint opens bounded
affected work. The signal is not itself a legal conclusion.

Processing passes this observation gate with workflow result
`AFFECTED_ACQUISITION_REQUIRED`, legal disposition `NOT_APPLICABLE`, and no
record output yet. Record the exact difference and dependencies, deduplicate it
against open work, and acquire only the complete affected artifacts required
by the following rules. Disappearance or a status-field change cannot by
itself prove repeal, expiry, commencement, or identity.

### `HKLEG-CURRENT-OBS-003` — failed or incomplete observation

A stale, failed, partial, malformed, or unreconciled release-blocking current
inventory or Gazette Observation is unavailable, not no change. After bounded
retries, processing is `BLOCK` with reason
`RELEASE_BLOCKING_OBSERVATION_UNAVAILABLE`, legal disposition
`NOT_APPLICABLE`, no record output, and an exact Coverage Gap. Apply ADR 0005's
explicit carry-forward, Withholding Release, or no-jurisdiction-rebuild
decision.

If the missing source is affected-work blocking rather than release blocking,
block only the item or decision that needs it. An on-demand historical source
that was not requested creates no current-release dependency.

## Evidence rules

### `HKLEG-CURRENT-EVID-001` — official HKeL copy evidence path

For an affected Ordinance, subsidiary instrument, or other covered item,
preserve:

- matching English and Traditional Chinese current XML and required assets;
- matching English and Traditional Chinese official HKeL verified or assisted
  copies for the same version;
- the relevant current-inventory records, metadata, locators, and hashes;
- the pinned HKeL Publication Specification Bundle; and
- the deterministic parsing, mapping, and reconciliation report.

Only a complete bundle may pass to comparison. XML constructs the candidate;
the matching HKeL copies support the applicable text and version.

### `HKLEG-CURRENT-EVID-002` — evidence-class and newer-assisted-copy rule

Apply this rule to every covered Hong Kong Legislation scope. Preserve the
exact verified or assisted HKeL classification in the evidence bundle and
traceability. A newer applicable complete assisted-copy bundle may proceed
instead of an older verified bundle.

This rule cannot convert a non-HKeL copy, portal transcription, search-result
page, unofficial scan, or unproved version into serving evidence. Verification
status cannot cure a content, version, structure, or bilingual mismatch.

### `HKLEG-CURRENT-EVID-003` — unavailable required artifact

If a required XML language, matching official HKeL verified or assisted copy,
required asset, version, or source capture is absent, older, unreachable, or incomplete,
processing is `BLOCK`, legal disposition is `NOT_APPLICABLE`, reason is
`AFFECTED_EVIDENCE_UNAVAILABLE`, and record output is none. Record the affected
acquisition or evidence gap. If supported current-law coverage or a release
claim depends on the missing artifact, expose an exact Coverage Gap and apply
the exact ADR 0005 outcome required for the affected scope. An uncommenced item
remains incompletely supported outside current search rather than
manufacturing a current-law Coverage Gap. Missing evidence is not a source
conflict and is never silently repaired.

### `HKLEG-CURRENT-EVID-004` — conflicting or unreconcilable evidence

If the two authentic languages identify different items, versions, locations,
or operative states; XML conflicts with its applicable PDF; a required
verification mark is absent; a material structure cannot be represented and
checked faithfully; or two assigned sources conflict on the same fact,
processing is `QUARANTINE` with legal disposition `NOT_APPLICABLE` at this
checkpoint and no record output. Complete release accounting later records the
affected legal object's supported disposition, normally `QUARANTINE` while the
conflict remains.

There is no monolingual fallback, fuzzy legal-text match, translation inference,
AI override, or automatic preference for the newest artifact. Preserve every
artifact and the exact failed comparison.

## Difference and cause rules

### `HKLEG-CURRENT-DIFF-001` — compare accepted current bundles

Compare the newly reconciled current bundle with the pipeline's preserved
previous accepted current bundle. Historical HKeL feeds are not part of the
ordinary comparison.

Classify each affected item and Legal Location as exact unchanged, serving-
payload changed, added, removed, moved, renumbered, split, merged, or otherwise
structurally changed. The comparison reports observable differences only.
Similarity, matching wording, numbering, or disappearance cannot decide legal
identity or status.

When the newly supported Official Version leaves all six serving fields exact
and continuing legal support is proved, later record selection may reuse the
Search Record under `HKLEG-CURRENT-REC-001`. A changed payload must continue to
the cause and disposition rules.

### `HKLEG-CURRENT-DIFF-002` — no accepted predecessor

If no preserved previous accepted current bundle exists, processing is `BLOCK`
with reason `INITIAL_BASELINE_REQUIRED`, legal disposition `NOT_APPLICABLE`, no
Coverage Gap, and no record output. Do not apply `HKLEG-CURRENT-OBS-001`, infer
a before-state, or use textual similarity as continuity evidence. Open a
separate complete baseline task and acquire historical or archival evidence
only when that task requires it.

### `HKLEG-CURRENT-CAUSE-001` — prove the cause of a material change

Every material wording, structure, identity, or legal-status difference must
be bound to the exact accepted evidence assigned to its cause. Examples include
the applicable Gazette instrument and operative provision, an HKeL Editorial
Record, an express official correction, or an official identity mapping.

Record the exact affected Legal Items and Legal Locations, publication and
effective dates, before-and-after bundles, source-role facts, rulebook version,
and evidence fingerprints. A status signal or HKeL appearance may corroborate
the decision but cannot replace the assigned event evidence.

A source artifact may change bytes without a legal change. Treat it as a
non-serving technical republication only when the pinned deterministic rules
prove that the item, version, legal content, legally meaningful structure,
operative state, and six serving fields are exact. A schema or specification
change instead follows Source Contract Review under ADR 0028.

### `HKLEG-CURRENT-CAUSE-002` — unexplained or conflicting change

If a material HKeL difference has no accepted cause, the assigned cause
evidence is incomplete, or the cause conflicts with the resulting HKeL bundle,
processing is `QUARANTINE`, legal disposition is `NOT_APPLICABLE` at this
checkpoint, and record output is none. Preserve the before-and-after evidence
and make no new identity, status, or current-text assertion.

### `HKLEG-CURRENT-EVENT-001` — event proved before consolidated text

If accepted Gazette or other event evidence proves that an affected change has
become operative but matching current HKeL XML and applicable PDF evidence is
not yet available, record the Legal Status Event and exact affected locations,
and apply ADR 0080's reconstruction decision.

Processing passes the event-fact gate and creates an exact Coverage Gap with
reason `EVENT_PROVED_CONSOLIDATION_MISSING`. A fully proved operation produces
one warned `RECONSTRUCTED_CONSOLIDATION` result. If it cannot pass, ADR 0079
requires a warned `KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` payload for each
affected location with valid latest applicable official HKeL text; otherwise record
output is none. Exactly one result is selected per affected serving unit.

## Disposition and record rules

### `HKLEG-CURRENT-DISP-001` — assign one supported disposition

After the evidence, difference, cause, identity, and status gates pass, assign
each affected legal object exactly one primary disposition:

- `SEARCHABLE_CURRENT` for supported presently operative text;
- `WAITING_ROOM` for validly enacted, made, or adopted material not yet proved
  operative;
- `EVIDENCE_ONLY` when the artifact's relevant present effect is fully
  represented by another tracked current authority;
- `HISTORICAL` when accepted evidence proves that the material ceased,
  expired, was repealed, was superseded, or otherwise no longer supplies
  current searchable authority; or
- `QUARANTINE` when identity, effect, ownership, evidence, bilingual alignment,
  replacement, or conflict remains unresolved.

If an event is proved operative but the required current consolidation is
missing, apply `HKLEG-CURRENT-EVENT-001`; do not use the Waiting Room to hide a
current-law Coverage Gap. Publication alone does not select
`SEARCHABLE_CURRENT`. HKeL `InEffect`, a
status code, disappearance, source category, or A-number is a signal rather
than a final disposition. Instruments & Others also require the accepted
Instrument Disposition Registry, whose row population remains explicitly
deferred for future review.

### `HKLEG-CURRENT-REC-001` — create or reuse immutable Search Records

For `SEARCHABLE_CURRENT` locations, render and validate the canonical bilingual
payload and one required English-only Hong Kong authority-note string, using
exact `"None"` when no substantive note applies.

- Reuse an existing Search Record only when all six metadata fields are exact
  and continuing legal support is proved.
- If any serving field changes, allocate a new Search Record ID and record the
  exact predecessor and change reason.
- A location split or merge follows the accepted one-to-many or many-to-one
  identity rules; record ordering or textual similarity cannot preserve an ID.
- Non-searchable dispositions create no Pinecone record, but their identity,
  evidence, reason, and history remain preserved.

Passing this rule makes a record eligible for a candidate Corpus Release. It
does not authorize embedding, Pinecone mutation, promotion, or deployment.

### `HKLEG-CURRENT-REL-001` — complete scope accounting

Before a Hong Kong Legislation Corpus Release may be sealed, account for the
complete Release Scope: every unchanged selected record and every observed
affected item, location, event, prior selected record, new candidate, reuse,
replacement, authority-note revision, Waiting Room item, evidence-only item,
historical retirement, Quarantine, and Coverage Gap.

Every decision records the ordered applied rule IDs, rulebook version and
fingerprint, input Observations and Source Snapshots, established and unresolved
facts, identity effects, serving disposition, responsible Legal Desk, review
state, and reason. An unaccounted signal, record, or decision blocks release
sealing or requires ADR 0005's explicit unavailable-scope outcome. Nothing is
silently omitted or directly written to Pinecone.

## Conformance cases

The future executable rules must pass at least these fixtures using the exact
rule IDs shown:

| Case | Facts | Required rule trace and result |
|---|---|---|
| `HKLEG-CURRENT-CASE-001` | All due inventories and fingerprints are complete and unchanged; no event or urgent signal is open | `OBS-001` → `SUPPORTED_NO_CHANGE`; reuse the existing Corpus Release; no acquisition, AI, embedding, or new record |
| `HKLEG-CURRENT-CASE-002` | HKeL current inventory reports a new version; matching bilingual XML and HKeL verified or assisted copies reconcile; an accepted Gazette instrument explains a commenced change; the resulting location is operative | `OBS-002`, `EVID-001`, `DIFF-001`, `CAUSE-001`, `DISP-001`, `REC-001`, `REL-001` → create or reuse each exact current record according to its six-field payload |
| `HKLEG-CURRENT-CASE-003` | Changed English and Chinese XML exists, but neither a matching verified nor assisted HKeL copy is complete | `OBS-002`, `EVID-001`, `EVID-003` → affected Coverage Gap; no candidate record |
| `HKLEG-CURRENT-CASE-004` | Both language copies exist, but English XML disagrees with its matching HKeL copy on legal wording | `OBS-002`, `EVID-001`, `EVID-004` → Quarantine; AI cannot approve the mismatch |
| `HKLEG-CURRENT-CASE-005` | English and Traditional Chinese resources identify different Official Versions | `OBS-002`, `EVID-004` → Quarantine; no monolingual fallback |
| `HKLEG-CURRENT-CASE-006` | Gazette evidence proves an amendment commenced, but HKeL has not published the matching current bundle | `OBS-002`, `EVENT-001`, `REL-001` plus ADR 0080 → record the event and Coverage Gap; select an eligible warned `RECONSTRUCTED_CONSOLIDATION`, otherwise ADR 0079 warned carry-forward, otherwise no record |
| `HKLEG-CURRENT-CASE-007` | A material HKeL text change reconciles with its PDFs, but no accepted Gazette event, Editorial Record, correction, or other assigned cause explains it | `OBS-002`, `EVID-001`, `DIFF-001`, `CAUSE-002` → Quarantine |
| `HKLEG-CURRENT-CASE-008` | A validly made item and current bundle exist, but commencement has not been proved | `DISP-001`, `REL-001` → Waiting Room; no current Search Record |
| `HKLEG-CURRENT-CASE-009` | A newly supported Official Version changes only material elsewhere; one location's six metadata fields remain exact and its legal support continues | `DIFF-001`, `CAUSE-001`, `DISP-001`, `REC-001` → reuse that location's Search Record and record the new Official Version lineage |
| `HKLEG-CURRENT-CASE-010` | An item disappears or an HKeL status signal says it ceased, but no assigned operative evidence proves repeal, expiry, or cessation | `OBS-002`, `DIFF-001`, `CAUSE-002` → Quarantine; do not retire the current record by inference |
| `HKLEG-CURRENT-CASE-011` | An eligible constitutional item has no verified copies; matching bilingual XML and official HKeL assisted copies reconcile, and accepted item-specific event and status evidence supports current use | `EVID-002`, `DIFF-001`, `CAUSE-001`, `DISP-001`, `REC-001` → eligible current record, accurately traced as assisted evidence |
| `HKLEG-CURRENT-CASE-012` | An operative Ordinance has only matching official assisted copies and complete bilingual XML | `EVID-001`, `EVID-002`, then ordinary cause, disposition, record, and release rules → eligible current record; do not wait for an older verified copy |
| `HKLEG-CURRENT-CASE-013` | There is no preserved previous accepted current bundle | `DIFF-002` → separate initial-baseline task; no ordinary no-change conclusion |
| `HKLEG-CURRENT-CASE-014` | An unrelated historical HKeL or archival Gazette endpoint is unavailable, but the current update requires no historical evidence | No historical-source rule is invoked; the current update is not blocked |
| `HKLEG-CURRENT-CASE-015` | A commencement notice names only sections 2 and 5 | `CAUSE-001`, `DISP-001`, `REL-001` → change only the named Legal Locations; every unnamed location remains in its prior supported state |
| `HKLEG-CURRENT-CASE-016` | An Editorial Record corrects punctuation, matching updated bilingual HKeL evidence reflects it, and a serving field changes | `OBS-002`, `EVID-001`, `DIFF-001`, `CAUSE-001`, `DISP-001`, `REC-001`, `REL-001` → new Search Record linked as an editorial change |
| `HKLEG-CURRENT-CASE-017` | A release-blocking current HKeL inventory or Gazette Observation remains stale, failed, partial, malformed, or unreconciled after bounded retries | `OBS-003` → processing `BLOCK`, reason `RELEASE_BLOCKING_OBSERVATION_UNAVAILABLE`, exact Coverage Gap, no record output, and one explicit ADR 0005 release choice; never supported no change |
| `HKLEG-CURRENT-CASE-018` | One item-specific affected-work source is unavailable after retries, while another affected item has complete independent evidence | `OBS-002`, `OBS-003`, `REL-001` → block only the dependent item with no record output; independent work proceeds, and exact release accounting must resolve the blocked item before sealing |

In the conformance table, shortened forms such as `OBS-002` mean the complete
stable ID `HKLEG-CURRENT-OBS-002`. A fixture passes only when the complete
ordered rule trace, evidence requirements, identity effects, and final outcome
match. Schema-valid output with the wrong rule trace fails.

## Consequences and remaining work

The ordinary Hong Kong current-update path now has stable rule IDs and concrete
pass, fail, boundary, conflict, and regression cases. A future implementation
must encode these rules without weakening their evidence boundaries and must
run the same cases against human-readable and executable representations.

ADR 0034 supplies the complete first-baseline rule set. ADRs 0035 through 0038
and 0040 settle all five conceptual HKeL reconciliation groups. ADR 0041 fixes
their strict fixture-package contract, ADR 0042 fixes the frozen Source
Rulebook Package, and ADR 0044 separates processing, disposition, coverage,
review, record-output, and reason dimensions while adding the two missing
`OBS-003` cases.

Implementation still requires the exact machine-readable schemas, fixture
bytes, validators, code catalogue, authority-note templates, clock and retry values,
and provider limits. The user-flagged Instruments & Others review and registry
row population remain deferred. Equivalent concrete rules remain required for
Hong Kong Cases, Hong Kong Principles, and every other
jurisdiction-and-material pair.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
