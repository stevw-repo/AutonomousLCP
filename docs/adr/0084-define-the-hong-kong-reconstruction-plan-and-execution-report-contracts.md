---
status: accepted
date: 2026-08-14
refines:
  - "0011"
  - "0016"
  - "0041"
  - "0042"
  - "0078"
  - "0080"
  - "0082"
  - "0083"
refined_by:
  - "0085"
  - "0086"
  - "0087"
depends_on:
  - "0013"
  - "0018"
  - "0025"
  - "0026"
  - "0038"
  - "0050"
  - "0078"
  - "0080"
  - "0081"
  - "0082"
  - "0083"
---

# Define the Hong Kong Reconstruction Plan and Execution Report contracts

## Decision in simple language

Before the engine changes legislative text, it must receive one complete,
immutable **Reconstruction Plan**. After attempting that plan, it must produce
one complete, immutable **Reconstruction Execution Report**.

The Plan says exactly what official evidence authorizes, which HKeL base is
used, which legal branch is affected, which English and Traditional Chinese
operations will run, and what each operation expects before and after it runs.
The Report says exactly what the engine found, applied, rejected, and produced.

Neither artifact is free-form reasoning. Both are strict closed JSON contracts.
Unknown fields, missing fields, mutable references, guessed text, undeclared
files, or a mismatch between the Plan and the Report fail validation. This
contract is internal and never changes the six-field Pinecone record.

## Identity, bytes, and fingerprints

The Management Register issues opaque immutable identities:

| Object | Required ID shape |
|---|---|
| Reconstruction Plan | `^rpl_[0-9a-f]{48}$` |
| Operation instance | `^rop_[0-9a-f]{48}$` |
| Reconstruction Execution Report | `^rex_[0-9a-f]{48}$` |
| Reconstructed Consolidation Artifact | `^rca_[0-9a-f]{48}$` |

These IDs are never derived from titles, chapter numbers, provision numbers,
URLs, filenames, operation order, source text, or hashes. They are identities,
not content proofs.

Both contracts use strict JSON Schema Draft 2020-12, I-JSON, RFC 8785 JCS
canonical UTF-8 bytes, and SHA-256 fingerprints encoded as
`sha256:<64-lowercase-hex>`. The Evidence Vault and Management Register store
the fingerprint of the complete canonical artifact outside that artifact,
avoiding a self-referential hash. Every reference to a Plan or Report contains
both its issued ID and exact artifact fingerprint.

Strings are not Unicode-normalized or silently reformatted after validation.
Duplicate keys, invalid Unicode, byte-order marks, floating-point legal facts,
unknown properties, and non-canonical registered copies are rejected. Counts
and sequence numbers are non-negative safe integers.

## Common immutable reference objects

Every internal reference uses one of two closed shapes.

An evidence or domain-object reference contains exactly:

```json
{
  "ref_type": "<registered reference type>",
  "ref_id": "<immutable registered object ID>",
  "fingerprint": "sha256:<64-lowercase-hex>"
}
```

A contract reference contains exactly:

```json
{
  "contract_id": "<immutable registered contract ID>",
  "version": "<exact version>",
  "fingerprint": "sha256:<64-lowercase-hex>"
}
```

Unknown reference types or contract IDs are invalid. A mutable URL, filesystem
path, current-version alias, title, citation, or source locator cannot replace
an immutable reference. URLs and locators remain inside preserved source
metadata reached through the evidence reference.

Reference arrays are duplicate-free. Unordered reference arrays sort by
`ref_type`, `ref_id`, and `fingerprint`; contract arrays sort by `contract_id`,
`version`, and `fingerprint`. Arrays whose order has legal or execution meaning
retain their explicitly validated sequence.

## Reconstruction Plan contract

One Plan covers exactly one:

- Hong Kong Legal Item;
- latest applicable bilingual HKeL base;
- observation cutoff;
- exact applicability branch;
- dependency-closed affected set; and
- atomic reconstructed result.

Different applicability branches or independent dependency closures receive
different Plans. A Plan never bundles unrelated work merely to reduce artifact
count.

The top-level Plan is a closed object with these required fields:

| Field | Exact meaning |
|---|---|
| `$schema` | Exact registered executable schema identity for this contract version |
| `contract_version` | Exact Reconstruction Plan contract version |
| `reconstruction_plan_id` | One register-issued `rpl_` ID |
| `jurisdiction` | Exact string `HK` |
| `material` | Exact string `legislation` |
| `observation_cutoff` | Exact accepted cutoff in the registered canonical date-time representation |
| `legal_item_ref` | Exact Legal Item reference |
| `base` | Closed base object defined below |
| `applicability_decision_ref` | Accepted immutable legal-status and applicability decision |
| `affected_legal_location_refs` | Non-empty sorted complete dependency-closed location set |
| `contracts` | Closed object binding the rulebook, registry, source-interpretation, tree, renderer, identity, traceability, and execution contracts |
| `evidence_refs` | Non-empty complete evidence inventory for this Plan |
| `event_chain` | Non-empty legally ordered event bindings from base to cutoff |
| `dependency_closure` | Closed complete affected, governing, dependent, and independent-boundary proof |
| `language_streams` | Exactly the English and Traditional Chinese streams defined below |
| `decision_ref` | Accepted Hong Kong Legislation Legal Desk decision binding this exact Plan |

No status field appears in an executable Plan: the artifact exists only after
the Legal Desk has accepted the exact structured plan. A rejected candidate is
recorded as a no-Plan decision result and cannot be relabelled as an executable
Plan.

### Base object

`base` contains exactly:

- the base Official Version reference;
- the preserved canonical bilingual HKeL tree reference;
- the matching English XML and copy evidence references;
- the matching Traditional Chinese XML and copy evidence references;
- `evidence_class`, exactly `VERIFIED` or `ASSISTED`;
- the exact source version date and applicable-state decision reference;
- the complete base Legal Location inventory fingerprint; and
- the canonical bilingual base fingerprint.

If English and Traditional Chinese copies carry different evidence classes,
`evidence_class` is `ASSISTED` and the individual copy references preserve each
source label. The field describes the weakest relied-on copy class; it never
upgrades assisted evidence to verified.

The base must be the latest eligible applicable HKeL version under ADR 0081. A
Plan referencing an older verified base while a newer eligible assisted base
exists is invalid.

### Event chain

Each `event_chain` entry contains:

- a zero-based continuous `sequence`;
- the Legal Status Event or Editorial Event reference;
- `event_role`, exactly `TEXT_AMENDMENT`, `EDITORIAL_AMENDMENT`,
  `TEXT_AMENDMENT_WITH_EFFECT`, `EDITORIAL_AMENDMENT_WITH_EFFECT`,
  `COMMENCEMENT_OR_EFFECT`, or `APPLICABILITY_OR_TRANSITION`;
- exact amendment, commencement, and applicability evidence references;
- the effective-state and applicability decision reference;
- the affected Legal Location references;
- the authentic-language source-unit references; and
- the operation-instance IDs caused by that event.

The array order is the proved legal execution order. Every operative event
from the base to cutoff appears exactly once; future or inapplicable events do
not appear and remain accounted for in the referenced status decision. A text
or editorial amendment entry has at least one operation. A commencement,
effect, applicability, or transition entry may have no operation of its own but
must be referenced by the effect binding of at least one operation. A gap,
duplicate, cycle, unexplained order, unaccounted effect-only event, amendment
without operations, or operation without exact amendment and effect bindings
invalidates the Plan.

### Dependency closure

`dependency_closure` contains complete duplicate-free sets of:

- primary affected Legal Locations;
- governing-context Legal Locations;
- dependent Legal Locations that must be rebuilt together;
- proven independent sibling boundaries; and
- exact source units owned by the closure in each authentic language.

It also binds the dependency-rule version and closure-proof fingerprint. The
affected, governing, and dependent union must equal
`affected_legal_location_refs`. An allegedly independent sibling must not
depend on any changed governing node. Missing ownership, overlap with another
Plan at the same cutoff, or an unaccounted source unit invalidates both Plans
until reconciled.

### Authentic-language streams

`language_streams` is an ordered two-element array: English `en` first and
Traditional Chinese `zh-Hant` second. Each stream contains:

- `language`;
- `language_effect`, exactly `CHANGED` or `UNCHANGED`;
- the exact base-language tree reference and fingerprint;
- one ordered `operations` array;
- the expected final language-tree fingerprint;
- the expected complete source-unit inventory fingerprint; and
- the expected Bilingual Alignment Map side-reference.

Different streams may contain different operation counts and structures. A
`CHANGED` stream requires at least one operation. An `UNCHANGED` stream requires
an empty operation array, exact official evidence that the event changes only
the other authentic language, and an expected final fingerprint equal to its
base. At least one stream must be `CHANGED`. Both streams must bind the same
event chain, applicability branch, legal effect, and final dependency closure.
Missing, duplicated, translated, Simplified-Chinese, or additional language
streams are invalid.

### Operation instance

Every operation object contains these common required fields:

| Field | Exact meaning |
|---|---|
| `sequence` | Zero-based continuous order inside the authentic-language stream |
| `operation_instance_id` | One register-issued `rop_` ID, unique across the complete Plan |
| `operation_type_id` | Exactly one `HKRECON-OP-001` through `HKRECON-OP-008` admitted by the bound registry |
| `atomic_group_id` | Immutable Plan-local group identity; every group is dependency closed |
| `amendment_event_ref` | The one text or editorial event-chain entry that supplies the operation |
| `effect_event_refs` | Non-empty complete set of commencement, effect, applicability, transition, or combined-event bindings that make it operative for this branch and cutoff |
| `source_unit_refs` | Non-empty exact authentic-language amendment source units |
| `target_selector` | One registry-defined closed structural selector |
| `before_state` | Exact expected target count, locations, structure and content fingerprint |
| `parameters` | Closed operation-type-specific source-backed parameters |
| `expected_after_state` | Exact expected locations, structure, source-unit ownership, and content fingerprint |
| `dependency_location_refs` | Complete governing and dependent location set for this operation |

The operation registry supplies eight separate `parameters` schemas. A delete
operation does not carry meaningless replacement fields; an insertion does not
pretend to have a deleted target. `null`, optional catch-all maps, free-text
patches, implementation hints, regular expressions, executable code, prompts,
or operation-private unknown fields are forbidden.

The selector uses only registered Legal Location, canonical tree-node, and
source-unit identities plus exact structural positions and before-state
anchors. It cannot contain a URL, XPath or JSONPath outside the pinned tree
contract, approximate string, vector, semantic query, unrestricted regex, or
host-language callback.

## Reconstruction Execution Report contract

One Report accounts for every operation in one Plan, including operations not
run after an earlier atomic failure. Its top-level closed object requires:

| Field | Exact meaning |
|---|---|
| `$schema` | Exact registered executable Report schema identity |
| `contract_version` | Exact Report contract version |
| `reconstruction_execution_report_id` | One register-issued `rex_` ID |
| `reconstruction_plan_ref` | Exact `rpl_` ID and complete Plan fingerprint |
| `engine_build_ref` | Immutable processing build and dependency-lock reference |
| `contracts` | Exact contract references, byte-equal to the Plan where shared |
| `base_validation` | Exact base identity, fingerprint, version, evidence-class, and latest-eligible checks |
| `event_chain_validation` | Completeness, order, applicability, and operation-binding results |
| `dependency_validation` | Closure, ownership, overlap, and independence results |
| `language_results` | English then Traditional Chinese operation results |
| `bilingual_validation` | Exact final alignment and legal-effect result |
| `processing_outcome` | Exactly `PASS`, `BLOCK`, or `QUARANTINE` |
| `source_contract_review_required` | Boolean |
| `reason_codes` | Ordered stable result reasons; success includes `RECONSTRUCTION_COMPLETE` |
| `rule_trace` | Ordered non-empty exact applied rules and decisions |
| `artifact_output` | Exactly the closed success or no-output shape below |
| `coverage_consequence` | Exact Coverage Gap continuation or failure consequence |
| `selection_consequence` | Exactly `RECONSTRUCTION`, `FALLBACK`, or `NO_RECORD` |
| `external_effects` | Exact constant `NONE` |

The deterministic Report excludes wall-clock start and end times, hostname,
temporary paths, process IDs, random seeds, log locations, stack traces, and
other run-specific noise. Operational attempt events may record those facts
separately in the Management Register. Excluding them keeps the normative
Report byte-reproducible.

### Per-operation result

Every planned operation appears exactly once in its stream and retains the
Plan order. Its result contains:

- operation instance ID and type ID;
- result exactly `APPLIED`, `FAILED_PRECONDITION`, `FAILED_EXECUTION`, or
  `NOT_RUN_AFTER_ATOMIC_FAILURE`;
- actual target count and exact matched location and source-unit IDs;
- actual before-state fingerprint;
- actual after-state fingerprint only when applied;
- ordered reason codes;
- the atomic-group result; and
- the provisional output-tree fingerprint after that operation when applied.

An operation may be computationally applied before a later atomic failure, but
its provisional bytes never become an artifact or Search Record. All remaining
operations are explicitly `NOT_RUN_AFTER_ATOMIC_FAILURE`; none disappear from
the Report.

### Successful artifact output

When `processing_outcome` is `PASS`, `artifact_output` contains exactly:

- one `rca_` Reconstructed Consolidation Artifact reference;
- English and Traditional Chinese final tree references and fingerprints;
- canonical bilingual output reference and fingerprint;
- complete Bilingual Alignment Map reference;
- complete dependency and source-unit coverage proof references;
- exact affected Legal Location inventory and fingerprint; and
- the reconstruction artifact's complete traceability-binding fingerprint.

`selection_consequence` is `RECONSTRUCTION`, and the exact Coverage Gap remains
required until matching HKeL consolidation passes. Successful execution does
not itself create, approve, embed, publish, promote, or select a Search Record.
Those later capabilities consume the immutable artifact through their own
gates.

### No-output result

When `processing_outcome` is `BLOCK` or `QUARANTINE`, `artifact_output`
contains exactly:

- `record_output: "NONE"`;
- `reconstructed_artifact_count: 0`; and
- an empty `artifact_refs` array.

The Report still records every validation and operation result. It sets
`selection_consequence` to `FALLBACK` only when a separately validated ADR
0079/0081 fallback-selection reference is present in
`coverage_consequence`; otherwise it is `NO_RECORD`. A failed execution cannot
itself assert that stale text is valid.

## Cross-artifact validation

A Report is valid only when it proves all of the following:

1. its Plan reference resolves to byte-exact canonical Plan bytes;
2. shared contract references are identical;
3. every Plan event, location, source unit, operation, atomic group, and
   dependency is completely accounted for in the required Report position;
4. Report order equals Plan order;
5. actual before state equals the Plan expectation before an operation applies;
6. every applied after state equals the Plan expectation;
7. language results independently cover their complete source units;
8. final bilingual alignment, dependency closure, and canonical rendering are
   complete;
9. output and selection dimensions agree with processing and reason codes;
10. every referenced artifact exists, validates, and matches its fingerprint;
11. no undeclared input or external effect occurred; and
12. two isolated clean executions produce byte-identical Reports and outputs.

Equal fingerprints do not replace exact byte equality at registration and
collision checking. A Report cannot repair an invalid Plan, and a valid Plan
cannot excuse a defective Report.

## Serving and traceability boundary

The Plan and Report remain in the Evidence Vault and Management Register. The
Record Traceability Lookup reaches them through typed evidence references and
fingerprints. Their IDs, operation details, evidence class, reasons, internal
facts, hashes, and reports do not enter `metadata.text`, the embedding input,
or a new Pinecone field.

The reconstructed Serving Record continues to use exactly the six fields in
ADR 0078 and the exact warning in ADR 0080. The Plan and Report do not authorize
source access, model calls, rendering, release creation, embedding, Approval,
promotion, Pinecone mutation, or routing.

## LLM and human boundaries

ADR 0043 still decides whether a future LLM may propose or challenge a
structured Plan. If admitted, its output is an untrusted candidate that must be
converted into this exact contract using only evidence ranges and registry
operations, then accepted by the Legal Desk and deterministically validated.
The model never supplies final legislative wording.

Routine exact plans and reports do not create a new human-approval step.
Uncertainty follows the existing narrow review rules; unsupported work uses the
warned fallback. A human may correct evidence or propose a new registry and
contract version, but cannot edit final bytes or bypass a failed precondition.

## Consequences and next topic

The internal artifact boundary is now exact enough for executable JSON Schemas
and fixture bytes to be implemented later without another product choice. The
next topic is the Reconstructed Consolidation Artifact contract: the immutable
final bilingual tree and canonical-output package that a successful Report may
reference.

This ADR authorizes documentation only. It does not create schema files or
implementation and does not authorize source access, model or embedding calls,
release publication, Pinecone or Azure access, promotion, deployment, commit,
push, or another remote action.
