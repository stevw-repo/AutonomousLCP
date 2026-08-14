---
status: accepted
date: 2026-08-14
refines:
  - "0041"
  - "0042"
  - "0043"
  - "0080"
  - "0081"
depends_on:
  - "0025"
  - "0026"
  - "0028"
  - "0032"
  - "0038"
  - "0080"
  - "0081"
refined_by:
  - "0083"
  - "0084"
  - "0085"
  - "0086"
  - "0087"
---

# Use a closed deterministic Hong Kong reconstruction operation registry

## Decision in simple language

Hong Kong legislation reconstruction uses a closed list of exact amendment
operations. The engine may apply an amendment only when the official evidence
identifies the old text or structure, the exact change, its legal effect, its
effective time, its applicability, and the authentic English and Traditional
Chinese results sufficiently for deterministic execution.

The engine never makes a best-effort reconstruction. It does not use fuzzy
matching, infer a missing amendment, improve drafting, translate one authentic
language into the other, or ask a model to write final legislative text. When
one required operation is unsupported or ambiguous, the affected reconstruction
does not exist. ADRs 0079 and 0081 then keep the latest applicable official
HKeL text held searchable with the stale warning.

This is the clearly preferable default because an allow-list can expand after
evidence and tests prove a new operation, while a broad catch-all can silently
publish wording that no official amendment proves.

## Registry boundary

The **Hong Kong Reconstruction Operation Registry** is an immutable, versioned,
fingerprinted part of the `hk-legislation` Source Rulebook Package. It defines
every executable operation type, its exact inputs, preconditions, ordering,
postconditions, failure reasons, traceability requirements, and covering
conformance cases.

There is no generic `OTHER`, `CUSTOM`, `MODEL_EDIT`, free-text patch, or
implementation-private operation. An unknown operation ID, version, parameter,
selector, evidence role, or structural meaning fails closed. Adding or changing
an operation requires a new registry and rulebook version, an impact
declaration, complete conformance coverage, and a new build attestation.

Each admitted operation instance records at least:

- its stable operation-type ID and registry version;
- the exact amending instrument, authentic-language source units, evidence
  hashes, event identity, commencement evidence, effective time, and
  applicability branch;
- the base Legal Item, Official Version, Legal Locations, base artifact
  fingerprint, authentic language, and exact target selector;
- exact before-state text or structure and its hash;
- source-supplied insertion or replacement content and its hash, when present;
- the expected target count and every actual matched location;
- its atomic group, predecessor operations, and deterministic order;
- exact after-state text or structure, affected locations, and hashes;
- bilingual-alignment and dependency-closure consequences; and
- its ordered Rule Trace, execution result, and any failure reason.

The target selector uses registered Legal Location and source-unit identity,
structural position, and exact before-state anchors. It never selects by vector
similarity, approximate text, title similarity, or an unbounded regular
expression.

## Closed operation set

The initial registry admits these operation classes:

| Stable operation ID | Permitted exact change |
|---|---|
| `HKRECON-OP-001` | **Exact text substitution** — replace one exact source-supported text range at one exact location. This includes words, punctuation, numbers, dates, references, headings, and labels when the official instruction supplies the before and after content. |
| `HKRECON-OP-002` | **Closed-scope occurrence substitution** — replace every exact occurrence named by an official instruction inside one completely enumerated scope. The engine records every match and fails if the scope, phrase, exclusions, or match set is not exact. |
| `HKRECON-OP-003` | **Insert complete node** — insert a complete official provision, paragraph, definition, heading, Schedule unit, table unit, Form unit, note, or other supported structural node at an exact parent and order position. |
| `HKRECON-OP-004` | **Delete complete node** — repeal, omit, or remove one completely identified structural node and only the source units that belong to it. |
| `HKRECON-OP-005` | **Replace complete node** — substitute one completely identified node with complete authentic-language replacement content, preserving exact parent and order rules. |
| `HKRECON-OP-006` | **Renumber or relabel node** — change the official number, letter, identifier, heading label, or structural locator of an exact node. No unstated cross-reference update is inferred. |
| `HKRECON-OP-007` | **Move complete node** — relocate a complete identified node to an exact new parent and order position only when the official instruction and all dependency effects are explicit. |
| `HKRECON-OP-008` | **Replace closed structured region** — replace a complete table region, Form region, Schedule region, formula block, diagram-backed unit, or other renderer-supported bounded structure using complete official replacement content. |

These are tree-and-text operations, not legal guesses. Different amendment
phrases may map to the same operation only through a pinned Source Rulebook
mapping with exact semantics. An implementation cannot broaden an operation's
meaning because a source instruction looks similar.

`HKRECON-OP-008` may proceed only when the existing canonical renderer can
represent every legally meaningful part without loss. A missing image,
unrepresentable spatial relationship, incomplete table header, or other
presentation-dependent meaning produces no reconstructed result.

## Ordering and atomicity

The engine starts from the latest applicable bilingual HKeL base admitted by
ADR 0081. It accounts for every operative amendment and editorial event between
that base and the observation cutoff. Operations are ordered by proved legal
effect, explicit source ordering, and then source position only where the
pinned rulebook proves that sequence. Publication order alone does not decide
legal order.

If two operative changes interact and their order cannot be proved, the
affected dependency closure fails. If a later operation expects a before-state
hash that the earlier operation did not produce, it fails rather than searching
for similar text.

All operations needed for one dependency-closed serving unit succeed or none
of them is selected. The engine never publishes a half-amended provision.
Independently separable siblings may proceed when complete evidence proves that
the failed branch cannot affect them. Each run creates new immutable artifacts;
it never edits a preserved HKeL base or an earlier reconstruction in place.

Retrying the same evidence, registry, engine, and cutoff must produce the same
ordered plan, bytes, hashes, reports, and identities. Reapplying an operation
to an already changed before-state fails its precondition; job-level retry
reselects the existing exact result instead of applying the amendment twice.

## Authentic-language and applicability rules

English and Traditional Chinese are applied as separate authentic-language
operation streams. They may have different grammar, segmentation, match counts,
or operation sequences when the official sources do, but they must end in one
complete Bilingual Alignment Map for the same legal effect and operative
state. One language is never generated from the other.

Only amendments proved operative for the exact cutoff and applicability branch
enter the plan. Future or uncommenced operations remain outside ordinary
current-law search. Partial, cohort-specific, transitional, retrospective, or
conditional effects may proceed only when the applicable locations, periods,
and branches are exact. Otherwise the smallest unsafe dependency closure has
no reconstruction.

An instruction that changes a definition, governing heading, lead-in, Schedule,
Form, table, or other shared context expands the affected set to every dependent
serving unit proved by the source and rulebook. The engine cannot reconstruct a
convenient child while ignoring changed governing context.

## Explicitly unsupported behavior

The registry rejects, among other things:

- implied, consequential, editorial, or drafting corrections not expressed by
  complete accepted evidence;
- “with necessary modifications”, “as appropriate”, or similar judgment-based
  transformations whose exact edits are not enumerated;
- automatic cross-reference repair after renumbering unless the exact repair is
  itself proved and represented by admitted operations;
- open-ended global substitution, an unexpected zero or multiple match, or a
  target selected only by approximate wording;
- an incomplete amendment chain, unresolved commencement, uncertain
  applicability, conflicting instruments, or unresolved event order;
- OCR repair, translation, paraphrase, normalization that changes authentic
  wording, or a model-authored patch;
- a structure, formula, image, table, Form, or Schedule that cannot be rendered
  completely by the pinned canonical contracts; and
- mixing source text from different versions, cutoffs, applicability branches,
  or authentic-language pairs.

Unsupported does not mean that the system chooses to ignore the amendment. It
records the exact Coverage Gap and reason, emits no reconstructed result for
the unsafe unit, and uses the ADR 0079/0081 fallback where eligible.

## Plans, execution reports, and traceability

Before text changes, the engine receives one immutable **Reconstruction Plan**
containing the complete ordered operation chain and evidence bindings. A plan
is not executable unless deterministic validation proves chain closure,
preconditions, ordering, applicability, language completeness, dependency
closure, and registry membership.

Execution produces an immutable **Reconstruction Execution Report** recording
every before state, exact match, operation result, after state, bilingual check,
coverage result, and fingerprint. The Reconstructed Consolidation Artifact and
Record Traceability Lookup bind the accepted plan and report, the base HKeL
evidence, all amendment and commencement evidence, the registry and Source
Rulebook versions, the exact engine build, final bilingual bytes, rendering,
release, and later HKeL reconciliation.

The plan, report, evidence class, operation IDs, hashes, and internal reasoning
do not enter Pinecone `metadata.text`. The searchable record keeps the ordinary
Hong Kong legislation format and ADR 0080 warning.

## LLM, Legal Desk, and human boundaries

This ADR does not decide whether a future admitted LLM task may propose or
challenge a structured Reconstruction Plan. That allocation remains governed
by ADR 0043. Regardless of proposal method:

- only registry operations may enter an accepted plan;
- exact source spans supply all old and new legislative wording;
- deterministic validation and execution produce the final bytes;
- the Hong Kong Legislation Legal Desk issues the evidence-bound decision; and
- ordinary exact changes do not require routine human approval, while the
  project's existing uncertainty and exceptional-change review triggers remain
  unchanged.

A human cannot bypass the registry by typing preferred consolidated wording
into the serving artifact. A genuinely unsupported operation requires a new
versioned operation contract and conformance evidence or uses the warned
fallback.

## Required outcomes and reason codes

Successful execution records `RECONSTRUCTION_COMPLETE` and each admitted
operation records `RECONSTRUCTION_OPERATION_APPLIED`. Failure records the
smallest applicable stable reason, including at least:

- `UNSUPPORTED_RECONSTRUCTION_OPERATION`;
- `RECONSTRUCTION_CHAIN_INCOMPLETE`;
- `RECONSTRUCTION_TARGET_NOT_EXACT`;
- `RECONSTRUCTION_BEFORE_STATE_MISMATCH`;
- `RECONSTRUCTION_EVENT_ORDER_UNRESOLVED`;
- `RECONSTRUCTION_APPLICABILITY_UNRESOLVED`;
- `RECONSTRUCTION_LANGUAGE_EVIDENCE_INCOMPLETE`;
- `RECONSTRUCTION_BILINGUAL_RESULT_MISMATCH`;
- `RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE`;
- `RECONSTRUCTION_STRUCTURE_UNSUPPORTED`; and
- `RECONSTRUCTION_REPRODUCIBILITY_FAILURE`.

These reasons do not all mean Quarantine. The future reconstruction conformance
catalogue must distinguish a supported negative result and warned fallback from
conflicting evidence, an unknown source contract, and an engine defect.

## Consequences and next topic

The operation policy no longer requires a product decision. Exact source-backed
tree and text edits proceed; anything outside the closed contract fails safely.
The next topic is the reconstruction conformance catalogue: the exact positive,
near-miss, compound, fallback, bilingual, reproducibility, and later-HKeL cases
that prove every registry branch.

This ADR authorizes design documentation only. It does not authorize source
access, implementation, model or embedding calls, release publication,
Pinecone mutation, promotion, Azure changes, deployment, commit, push, or
another remote action.
