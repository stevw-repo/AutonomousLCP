---
status: accepted
date: 2026-08-14
amends:
  - "0083"
refines:
  - "0031"
  - "0032"
  - "0042"
  - "0079"
  - "0080"
  - "0081"
  - "0082"
  - "0083"
  - "0084"
  - "0085"
depends_on:
  - "0003"
  - "0005"
  - "0011"
  - "0013"
  - "0016"
  - "0031"
  - "0032"
  - "0041"
  - "0042"
  - "0050"
  - "0078"
  - "0080"
  - "0081"
  - "0082"
  - "0083"
  - "0084"
  - "0085"
refined_by:
  - "0087"
---

# Reconcile reconstructed Hong Kong legislation with later HKeL

## Decision in simple language

While a reconstructed record is searchable, the pipeline continues watching
HKeL for the matching official consolidation. It does not repeatedly download
large files merely because a reconstruction exists. Ordinary lightweight HKeL
inventory and fingerprint checks detect change; complete bilingual XML and
verified or assisted copies are acquired only when a changed signal or active
gap requires them.

When a valid applicable HKeL consolidation arrives, the ordinary HKeL record
replaces the reconstructed record through the next complete release, Approval,
and promotion process. HKeL replacement does not wait for the pipeline to prove
that its reconstruction was correct. Comparison is evaluation and defect
detection, not a new authority gate over valid HKeL text.

The reconstructed artifact, Plan, Report, evidence, comparison, and former
serving history remain preserved. Nothing is overwritten.

## Monitoring state

Each active Reconstructed Consolidation Artifact has exactly one append-only
monitoring state:

| State | Meaning |
|---|---|
| `AWAITING_HKEL_CONSOLIDATION` | No complete applicable HKeL consolidation covering the reconstructed effect has passed ordinary gates |
| `HKEL_CANDIDATE_OBSERVED` | A changed HKeL signal exists and bounded acquisition or validation is running |
| `COMPARISON_DEFERRED` | Valid HKeL text exists but additional overlapping changes prevent an exact common comparison basis |
| `MATCH_CONFIRMED` | Comparable HKeL and reconstructed canonical legal content agree |
| `MISMATCH_CONFIRMED` | Comparable HKeL and reconstructed legal content materially disagree |
| `SUPERSEDED_BY_HKEL` | Complete valid HKeL records have replaced the reconstruction in an approved serving state |
| `SUSPENDED_PENDING_REVALIDATION` | A relied-on reconstruction component is not admitted for new or continued affected reconstruction |
| `REVALIDATED` | A corrected component and affected results passed the required new conformance and impact gates |

State changes never mutate the reconstruction artifact. They are Management
Register events binding evidence, comparison result, impact set, responsible
Legal Desk, rulebook and build versions, and serving consequences.

`COMPARISON_DEFERRED` does not delay replacement by valid HKeL. It means only
that the reconstruction cannot yet be scored fairly against a common legal
state.

## Bounded scalable monitoring

The normal Hong Kong source schedule under ADR 0031 remains authoritative:

- lightweight current inventory, version, resource, and fingerprint signals
  run at their ordinary tier;
- an active Coverage Gap makes its exact item a known affected item but does
  not create a second full-corpus polling loop;
- unchanged complete signals trigger no large acquisition, comparison, model,
  embedding, or record work;
- a changed or newly matching item triggers bounded acquisition of the exact
  bilingual HKeL bundle and dependencies; and
- retries, outages, and incomplete observations retain the existing
  reconstruction and visible Coverage Gap unless a separate integrity defect
  makes that reconstruction ineligible.

There is no arbitrary age limit. A fully supported reconstruction remains
selected with its warning while HKeL has not supplied valid replacement text.

## Ordinary HKeL admission comes first

A later HKeL candidate must independently pass the ordinary current-law gates:

- registered source identity and complete item inventory;
- latest applicable version selection under ADR 0081;
- matching English and Traditional Chinese XML and official HKeL copies;
- deterministic XML-to-copy and presentation reconciliation;
- complete Legal Location, source-unit, status, and bilingual coverage;
- identity and lineage decisions; and
- ordinary rendering, record, release, Approval, and promotion gates.

An incomplete, mismatched, corrupt, differently versioned, or otherwise
invalid HKeL candidate neither replaces the reconstruction nor becomes
comparison truth. It records the exact source or evidence failure and keeps
monitoring. A valid assisted HKeL copy is not delayed for a verified label.

Once valid ordinary HKeL records cover an affected serving unit, they are the
preferred serving result even if comparison is deferred or a material mismatch
is under investigation. The reconstruction warning disappears only when those
ordinary records are actually selected in the approved serving state.

## Exact common comparison basis

The pipeline compares only equivalent legal states. A **Reconstruction
Comparison Basis** binds:

- the same Legal Item and safely reconciled Legal Locations;
- the same authentic languages;
- the reconstruction base and complete event horizon;
- the exact applicability branch and operative period;
- the later HKeL version and the events it incorporates;
- permitted presentation projection rules; and
- the exact common source-unit and dependency boundary.

A direct comparison is valid when later HKeL includes the reconstructed event
chain and no additional overlapping change prevents isolation of that same
result. Independent later changes outside the compared closure do not prevent
comparison. Additional overlapping amendments, editorial changes, identity
changes, or applicability changes that cannot be separated from the target
result produce `COMPARISON_DEFERRED`.

The pipeline does not reverse later amendments, reconstruct an artificial HKeL
past version, or subtract text to manufacture a comparison. It may later use an
ordinary preserved HKeL past version when that version independently passes its
applicable evidence and reconciliation gates.

## Comparison classes

One comparable affected unit receives exactly one result:

| Comparison class | Exact consequence |
|---|---|
| `EXACT_CANONICAL_MATCH` | Authentic-language trees, legal content, structure, locations, and operative state match exactly; record positive evaluation evidence |
| `PRESENTATION_ONLY_MATCH` | Differences are limited to already permitted HKeL presentation projection; canonical legal content still matches exactly |
| `MATERIAL_MISMATCH` | Wording, punctuation, number, heading, structure, location, asset relationship, language alignment, operative state, or another legal-content fact differs materially |
| `COMPARISON_NOT_ISOLATABLE` | Valid HKeL includes additional overlapping change and no exact common comparison basis exists; replace with HKeL but do not score the reconstruction |
| `HKEL_CANDIDATE_INVALID` | Candidate did not pass ordinary HKeL gates; retain eligible reconstruction and do not compare |

An item may have exact results for independent units and deferred or mismatched
results for others. The comparison inventory accounts for every reconstructed
location; a convenient matching subset cannot hide an unaccounted location.

## Material mismatch attribution

A material mismatch is preserved and classified only after comparing exact
evidence and artifacts. The Legal Desk assigns one or more proven attribution
classes:

| Attribution class | Component whose admission is affected |
|---|---|
| `BASE_SELECTION_DEFECT` | Base-selection rule, evidence bundle, or applicable-version decision |
| `SOURCE_INTERPRETATION_DEFECT` | HKeL, Gazette, Editorial Record, or publication-specification mapping |
| `EVENT_CHAIN_DEFECT` | Missing, extra, duplicated, or wrongly ordered legal event |
| `APPLICABILITY_DEFECT` | Commencement, transition, cohort, period, or location decision |
| `OPERATION_MAPPING_DEFECT` | Mapping from official instruction to an ADR 0082 operation type or parameters |
| `OPERATION_EXECUTION_DEFECT` | Deterministic implementation of one admitted operation class |
| `BILINGUAL_OR_DEPENDENCY_DEFECT` | Authentic-language alignment, governing context, or affected closure |
| `RENDERING_OR_PARTITION_DEFECT` | Ordinary canonical rendering, measurement, or record partitioning |
| `IDENTITY_OR_LINEAGE_DEFECT` | Legal Location continuity, split, merge, replacement, or ownership |
| `SOURCE_EVIDENCE_DEFECT` | A particular preserved source artifact or fact was wrong, incomplete, or misattributed without proving a general rule defect |
| `UNRESOLVED_RECONSTRUCTION_MISMATCH` | Current evidence cannot safely bound the cause |

The system does not blame an operation class merely because that class appears
in the Plan. Attribution requires a reproducible causal difference. A source-
evidence defect does not suspend unrelated operations; an execution defect does
not invalidate correct source evidence.

## Suspension and impact set

Suspension uses the smallest complete safe scope:

- one evidence item, event mapping, applicability branch, source construct,
  operation mapping, operation type and engine build, renderer construct,
  identity rule, or exact combination thereof;
- every active reconstruction and pending Plan that references the suspended
  component forms the mandatory impact set; and
- if the cause cannot be bounded, all reconstruction under the affected
  `hk-legislation` rulebook and build profile is suspended.

New affected reconstruction stops immediately. Every active affected record is
re-evaluated through complete release accounting. Until corrected eligibility
is proved, select the latest applicable ADR 0079/0081 warned HKeL fallback when
available; otherwise select no record and retain the Coverage Gap. A possibly
defective reconstruction is not kept merely because it is newer.

Unaffected operation classes, items, branches, and independently proven
artifacts continue. Suspension cannot expand through shared deployment merely
for administrative convenience, but it also cannot be narrowed below an
unresolved dependency.

Ordinary HKeL records proceed whenever valid. The mismatch investigation never
blocks valid HKeL replacement.

## Safe correction and restart

A suspended component returns to use only after all of the following exist:

1. preserved mismatch evidence and a complete impact declaration;
2. a corrected immutable source interpretation, rule, registry, schema,
   renderer, or engine build as applicable;
3. a new permanent regression case, primary cell, and controlled pair when the
   mismatch exposed a previously uncovered distinction;
4. all affected former cases plus the complete current reconstruction suite
   pass in two clean runs;
5. the complete ordinary Hong Kong Legislation suite also passes when the
   component can affect it;
6. every active impacted Plan, Report, artifact, record, and fallback is
   reprocessed or explicitly accounted for; and
7. a new Rulebook Conformance Attestation binds the corrected exact package and
   build.

Restart is an append-only admission event. It does not erase the suspension,
mismatch, former attestation, artifact, or serving history. Ordinary bounded
corrections and revalidation are automated and reported. Human review follows
the project's existing high exceptional-change threshold and is required only
when legal effect, attribution, scope, or the governing rule remains genuinely
uncertain or exceptional.

## Conformance-catalogue expansion

ADR 0083's immutable expansion rule applies. This decision adds without
renumbering:

- `HKLEG-RCN-DET-057` / `HKLEG-RCN-CELL-057` — valid later HKeL contains an
  additional overlapping change, so the system replaces serving with HKeL,
  records `COMPARISON_NOT_ISOLATABLE`, and does not score or reverse-reconstruct
  the earlier artifact;
- `HKLEG-RCN-DET-058` / `HKLEG-RCN-CELL-058` — a changed HKeL candidate fails
  ordinary bilingual evidence gates, so it neither replaces nor becomes
  comparison truth and the eligible reconstruction remains selected; and
- `HKLEG-RCN-PAIR-031` controls case `051` exact comparable match against case
  `057` non-isolatable additional change;
- `HKLEG-RCN-PAIR-032` controls case `051` valid comparable HKeL against case
  `058` invalid HKeL candidate.

At this ADR checkpoint the reconstruction catalogue contained **58 direct
cases**, **58 primary cells**, and **32 controlled pairs**. With the 121-case
ordinary baseline, that made **179 direct cases**. ADR 0087 later expands the
current catalogue to 63 cases, 63 cells, and 35 pairs.

## Authorization and next topic

This monitoring and reconciliation topic has one clear result and requires no
new product choice: valid HKeL replaces reconstruction, fair comparisons use a
common legal state, defects suspend only their complete impact scope, and safe
restart requires regression proof.

ADR 0087 later settles reconstruction readiness and activation: the exact
package, attestation, capability, and release gates required before any real
reconstructed record can be produced or promoted.

This ADR authorizes documentation only. It does not access HKeL, implement a
watcher or comparison engine, run tests, call a model or embedding provider,
create a release, mutate Pinecone or Azure, promote, deploy, commit, push, or
perform another remote action.
