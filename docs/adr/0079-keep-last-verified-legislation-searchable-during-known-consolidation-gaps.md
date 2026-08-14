---
status: accepted
date: 2026-08-14
amends:
  - "0005"
  - "0012"
  - "0023"
  - "0025"
  - "0026"
  - "0033"
  - "0034"
  - "0038"
  - "0044"
refines:
  - "0011"
  - "0013"
  - "0050"
  - "0078"
depends_on:
  - "0019"
  - "0022"
amended_by:
  - "0080"
  - "0081"
refined_by:
  - "0086"
---

# Keep the latest applicable HKeL text searchable during known consolidation gaps

## Later decision

ADR 0080 makes exact evidence-bound `RECONSTRUCTED_CONSOLIDATION` the preferred
searchable result during a Hong Kong publication lag. This ADR remains the
mandatory fallback whenever reconstruction is unsupported, incomplete,
ambiguous, conflicting, or otherwise unable to pass. Its warned old text is
not selected alongside an eligible reconstructed record for the same serving
unit.

## Decision

When accepted official evidence proves that legislation has changed or become
operative, but the updated official consolidated text is not yet available,
Ask.Legal keeps the **latest applicable official HKeL text it validly holds**
searchable for analysis. ADR 0081 permits either verified or assisted official
HKeL copy evidence; a newer eligible assisted version is not displaced by an
older verified version.

The retained text is not called current law. It is selected through the
serving mode `KNOWN_STALE_ANALYTICAL_CARRY_FORWARD`, with a visible Coverage
Gap and a mandatory authority note. This fallback mode does not itself perform
reconstruction: it does not apply amendment instructions to the old text or
describe the retained text as the new consolidation. ADR 0080 governs the
separate reconstructed result.

This is an explicit exception to the ordinary current-only serving policy and
to ADR 0005's former rule that affirmative change evidence made carry-forward
unavailable. It implements the user's preference for useful, clearly qualified
analysis over removal of the last available official wording.

## Preconditions

Known-stale analytical carry-forward is permitted only when all of the
following are proved:

1. one exact previously accepted Official Version remains preserved and
   independently verifiable under the current Source Rulebook; an existing
   Search Record may be reused as source material but is not required;
2. accepted official event evidence proves a change, commencement, repeal,
   replacement, or other operative event and identifies the smallest safely
   bounded affected Legal Locations;
3. matching updated official consolidated text required by the applicable
   Source Rulebook is unavailable at the observation cutoff;
4. the retained `metadata.text` is byte-exact source text from the selected
   applicable official HKeL copy, not reconstructed, corrected, translated,
   summarized, or mixed with the event;
5. the affected identity and predecessor mapping are sufficiently established
   to label the old text honestly; and
6. the candidate release and coverage status account for every affected and
   unaffected location without silently treating the gap as no change.

If exact affected locations cannot be proved, the warning applies to the
smallest complete parent set that could be affected. The system may warn too
broadly while mapping is unresolved; it may not select a convenient narrower
set. If no valid applicable official HKeL text exists, there is nothing to
carry forward and only the Coverage Gap is published.

Corrupt, misattributed, incomplete, or otherwise invalid prior text is not made
searchable by this rule. Staleness caused by the known consolidation gap is
permitted; an independent evidence or record-integrity failure is not.

## Serving Record consequence

The old `metadata.text` remains exact so it can still be retrieved and
analysed. The record receives a mandatory controlled authority note with at
least these meanings:

```text
[WARNING: KNOWN STALE LEGISLATION] Official evidence shows that a change
affecting this provision is operative, but updated official consolidated text
was unavailable at the stated cutoff. This record contains the latest
applicable official HKeL text held at that cutoff, supported by a [verified or
assisted] HKeL copy dated [base version date]. Do not state it as the current
wording or reconstruct the change from this text.
```

The material-specific renderer adds the exact affected-location, event,
effective-date, base-version, evidence-class, and cutoff facts that fit its approved
controlled template. It does not quote or paraphrase resulting consolidated
wording that the official publisher has not supplied.

Changing from the former authority note, often `"None"`, to this warning
changes the six-field serving payload. Therefore:

- the warned payload receives a new Search Record ID with forward
  authority-note-revision or known-stale-carry-forward lineage when a prior
  Search Record exists, unless that exact warned payload was previously issued
  and is validly reselected;
- when the accepted Official Version has no prior Search Record, the pipeline
  may construct a warned analytical record from its exact official text only
  through the ordinary rendering, validation, release, Approval, and promotion
  gates;
- every old Search Record remains immutable and preserved;
- the exact `metadata.text` embedding may be reused when the complete admitted
  embedding contract is unchanged; and
- the Record Traceability Lookup binds the warned record to the selected
  applicable official HKeL copy and Official Version, exact event evidence,
  Coverage Gap, Legal Desk Decision, release, and authority-note evidence.

This serving mode is a selection and presentation consequence, not a claim
that the old Official Version remains legally current. Internal legal history
records the proved event and any superseded, repealed, replaced, or otherwise
affected status separately.

## Coverage-status and downstream behavior

Every active known-stale selection appears in the signed coverage-status
channel. The application displays a warning independently of the downstream
LLM and passes a deterministic coverage context through the approved six-field
metadata context. That context may state only accepted event facts such as the
official event, affected locations, effective date, base version and evidence
class, and
missing-consolidation condition. It is not embedded, indexed, or treated as a
Search Record.

The downstream LLM may:

- analyse the retained official text as the stated HKeL base version;
- explain the accepted official event facts supplied in the coverage context;
- compare those facts with other retrieved authorities; and
- say that current consolidated wording cannot yet be confirmed.

It must not:

- quote, synthesize, or claim the unavailable current consolidated wording;
- describe the retained text as current merely because it was retrieved;
- treat missing new text as proof that the law did not change; or
- make an unqualified completeness or no-law claim for the affected scope.

The user interface warning remains mandatory even when the LLM produces no
answer or fails to mention the gap.

## Release and replacement behavior

The gap does not silently reuse the former record. Corpus construction creates
one complete candidate release that selects warned Search Records for the exact
affected locations and ordinary exact records for unaffected locations. The
Desired-State Inventory and Promotion Manifest show the known-stale selection,
Coverage Gap, record replacements, reused embeddings where eligible, and exact
rollback state. Production selection still requires the ordinary complete
Approval and promotion gates.

When matching updated official consolidated text later becomes available and
passes every evidence, bilingual, rendering, identity, coverage, and release
gate:

- construct the true current Search Records from that official text;
- replace the warned analytical records in the current serving inventory;
- resolve the Coverage Gap only after complete reconciliation;
- preserve the warned records and their serving history outside the new
  current selection; and
- record exact forward lineage and selection events without mutation.

No arbitrary age limit removes a known-stale analytical record while the gap
remains unresolved. The signed coverage status, reports, monitoring, and review
deadline remain active until official current text is available or another
explicit evidence-backed user policy supersedes this rule.

## Hong Kong rule and fixture amendments

For Hong Kong Legislation, `HKLEG-CURRENT-EVENT-001` still records the operative
event and reason `EVENT_PROVED_CONSOLIDATION_MISSING`. Under ADR 0080 it first
selects an eligible reconstructed result. This ADR then requires
`KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` records for every affected location for
which valid latest applicable official HKeL text is held only when
reconstruction cannot pass.

`HKLEG-CURRENT-CASE-006`, `HKLEG-BASE-CASE-012`, and
`HKLEG-RECON-PSB-FIX-005` keep their permanent IDs and fact patterns. ADR 0080
supersedes their primary result. This ADR defines their fallback result: exact
Coverage Gap, warned records carrying the latest applicable official HKeL text
and lookup entries wherever valid text is held, coverage context, and complete
release accounting. If no valid applicable official HKeL text exists, they
require an exact zero carry-forward result and the Coverage Gap.

The initial Hong Kong Legislation conformance count remains 121 because this
changes the required result of an existing covered branch rather than adding a
new branch. Executable expected artifacts must be versioned and regenerated;
old expected artifacts remain immutable historical evidence and cannot pass
under the amended rulebook.

## Consequences

Pinecone remains primarily a current-law serving copy, but it now contains one
explicit, narrowly defined analytical exception: the latest applicable
official HKeL legislation text held whose official change is known but whose
updated official consolidated text is not yet available. The fallback is never
silent and cannot be generalized to drafts, invalid records, unknown-source
text, or ordinary historical material. ADR 0080 separately controls
reconstructed law.

This decision trades current-only purity for continued analytical usefulness.
The mandatory warning, signed coverage status, separate event facts, unchanged
source text, new payload identity, and strict separation from ADR 0080
reconstruction are the controls that make that fallback explicit.

This ADR authorizes documentation only. It does not authorize schema or
application implementation, source acquisition, model or embedding calls,
release publication, Pinecone mutation, promotion, Azure changes, deployment,
commit, push, or another remote action.
