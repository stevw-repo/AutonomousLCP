---
status: accepted
date: 2026-08-14
refines:
  - "0054"
  - "0069"
  - "0070"
  - "0071"
  - "0072"
  - "0073"
depends_on:
  - "0011"
  - "0016"
  - "0018"
  - "0039"
  - "0040"
  - "0041"
  - "0050"
refined_by:
  - "0075"
---

# Use two linked conformance layers for HKEX Regulatory Materials

## Decision

Hong Kong Regulatory Materials conformance uses one immutable
`hk-regulatory` suite package containing two linked but non-substitutable case
catalogues and one frozen coverage matrix:

1. the **evidence-to-decision catalogue** proves that complete synthetic
   source-shaped evidence produces the correct structured source, membership,
   ownership, effective-state, disposition, record-boundary, dependency, and
   uncertainty decision; and
2. the **decision-to-artifact deterministic catalogue** starts from frozen
   accepted facts and proves exact canonical records, measurements,
   partitions, source-unit coverage, traceability, identity consequences,
   readiness results, and forbidden-side-effect behavior.

Semantic retrieval, embeddings, Pinecone ranking, crowding, and downstream-
answer behavior remain a separate later evaluation and admission gate. A
correct legal record may retrieve badly, while a malformed record may retrieve
well; one result cannot compensate for the other.

This architecture does not settle the deferred allocation of every Regulatory
processing step to deterministic code, an admitted generative-LLM proposal,
Legal Desk rules, or human review. It fixes the required answer and proof
without selecting the method. Exact final artifact construction remains
deterministic under ADR 0073 regardless of how an earlier bounded proposal was
produced.

## Why the layers remain separate

An end-to-end failure may arise because the system chose the wrong legal
meaning or because it mechanically rendered the right decision incorrectly.
One blended result could hide whether, for example:

- guidance was incorrectly classified as a rule;
- the wrong board or applicability branch was selected;
- a future rule was treated as current;
- an independent record boundary or required context was misidentified;
- the renderer omitted a qualification or table relationship;
- the partitioner used an unsupported cut; or
- the coverage proof failed to detect missing source text.

The evidence-to-decision layer owns the first group of questions. The
decision-to-artifact layer owns the exact mechanical consequences. One layer
cannot prove the other.

## Legal Desk reference boundary

The Hong Kong Regulatory Materials Legal Desk owns the accepted structured
answer for evidence-to-decision cases under the exact `hk-regulatory` Source
Rulebook. It adjudicates fixture truth before candidate processing results are
used to judge the case. The answer records exact evidence ranges, established
and unresolved facts, stable rules, permitted result dimensions, and any
genuinely acceptable equivalent structured representation.

The Legal Desk is a named rule-bound decision authority, not an LLM, test
runner, renderer, source connector, or promotion reviewer. A later model or
other proposal component may supply evidence-bound candidate facts only. It
cannot see hidden fixture truth or acquire decision authority through semantic
similarity, confidence, or persuasive prose.

## Logical suite package

The logical package is:

```text
hk-regulatory-conformance/
├── suite.json
├── coverage-matrix.json
├── decision-catalogue.json
├── deterministic-catalogue.json
├── decision/
│   └── <primary-checkpoint>/<case-id>/
│       ├── case.json
│       ├── input/
│       └── reference/
└── deterministic/
    └── <primary-checkpoint>/<case-id>/
        ├── fixture.json
        ├── input/
        └── expected/
```

The exact repository path may follow the future implementation layout. The
root manifests, two-layer separation, package boundaries, declared inventories,
and completeness semantics are fixed.

All package paths are normalized relative POSIX paths. Absolute paths, parent
traversal, empty segments, platform-specific separators, symlinks, URI
retrieval, network access, undeclared local files, mutable aliases, and
directory discovery are forbidden.

Small synthetic source-shaped artifacts and expected outputs may live in Git
under the repository's fixture policy. Real HKEX source snapshots, operational
results, corpora, credentials, and production state remain outside Git. The
suite proves the rulebook and processing contract; it does not prove that a
real artifact is current at an operational cutoff.

## Suite manifest and catalogues

`suite.json`, `coverage-matrix.json`, `decision-catalogue.json`, and
`deterministic-catalogue.json` are strict JSON Schema Draft 2020-12 documents
with `additionalProperties: false`.

`suite.json` binds at least:

- suite ID, version, frozen status, owner, predecessor, and impact declaration;
- ADRs 0054 and 0069 through 0074;
- the exact `hk-regulatory` Source Rulebook Package and Legal Desk identity;
- Registered Source, Fact Authority, effective-state, component-inventory,
  record-construction, renderer, table, Form, authority-note, identity,
  traceability, coverage, and result-code contract fingerprints;
- the tokenizer, token ceiling, metadata serialization, and metadata-byte
  ceiling used by overlong cases;
- both exact catalogues and the frozen coverage matrix;
- every case package and declared artifact inventory; and
- the root fingerprint without creating a self-referential hash.

Each frozen catalogue explicitly lists every case ID, primary checkpoint,
manifest path or immutable external reference, manifest hash, package
fingerprint, evidence class, and contract binding. Ranges, globs, filename
conventions, broad tags, runner discovery, and expected counts cannot establish
catalogue completeness.

## Stable non-answer-bearing namespaces

Executable cases use stable opaque IDs whose namespace identifies only the
primary checkpoint:

| Namespace | Primary checkpoint |
|---|---|
| `HKREG-DEC-SRC-NNN` | Source Fact Authority, membership, or board ownership |
| `HKREG-DEC-STA-NNN` | Effective state, trigger, transition, or disposition |
| `HKREG-DEC-BND-NNN` | Record boundary, governing dependency, or cross-reference decision |
| `HKREG-DET-RND-NNN` | Canonical English rendering and structured projection |
| `HKREG-DET-PAR-NNN` | Exact limits and official-structure partitioning |
| `HKREG-DET-COV-NNN` | Source-unit coverage, completeness, and readiness |
| `HKREG-DET-IDN-NNN` | Search Record identity, lineage, reuse, and update consequence |
| `HKREG-DET-PKG-NNN` | Package integrity, malformed input, reproducibility, and forbidden side effects |

`HKREG-PAIR-NNN` identifies one required positive and near-miss relationship
and is not executable. Coverage cells use permanent opaque IDs under one
separate namespace. No ID encodes the expected answer, pass or fail, board,
rule number, source locator, state, record count, or critical-error label. IDs
are never reassigned.

One case has one primary checkpoint and may assert named secondary checkpoints.
Every required coverage cell nevertheless names a direct primary case; a broad
integration fixture cannot substitute for missing boundary coverage.

## Common strict case envelope

Both `case.json` and `fixture.json` contain:

- exact schema and package-contract versions;
- stable case ID, suite layer, primary checkpoint, frozen status, and synthetic
  evidence class;
- every applicable contract identity, version, and fingerprint;
- synthetic cutoff, board or cross-board scope, and exact prior state needed by
  the case;
- primary and secondary coverage-cell IDs;
- optional pair ID with exact `POSITIVE` or `NEAR_MISS` role;
- declared input slots, artifacts, paths, media types, hashes, and source roles;
- explicit assertion scopes and required result dimensions;
- complete declared input, reference, and expected inventory;
- expected-artifact roles and states; and
- package fingerprint plus non-normative title and purpose.

Unknown fields, enums, source roles, evidence roles, case IDs, coverage cells,
pair roles, artifact roles, paths, contracts, rules, and reason codes fail
validation. They are not ignored for forward compatibility.

## Inputs and deliberate absence

Every required evidence slot has exactly one expected state:

- `AVAILABLE` — the declared artifact must exist, validate, and hash exactly;
- `INTENTIONALLY_ABSENT` — the missing evidence is the condition under test;
  or
- `UNREADABLE` — a declared artifact supplies the exact corrupt or unsupported
  bytes expected by the case.

Stale, conflicting, differently versioned, partially complete, or wrong-board
evidence uses available artifacts whose facts create the condition. It is not
represented by a vague magic state. This prevents an accidentally forgotten
file from passing as an intended source-failure case.

Synthetic artifacts may model catalogue entries, consolidated English
rulebooks, Forms, Fees Rules, updates, optional Chinese translations, trigger
evidence, prior register state, and earlier records. They prove no fact about
real HKEX content.

## Evidence-to-decision cases

`case.json` additionally declares:

- the complete synthetic evidence packet and every fact it is permitted to
  establish;
- exact rulebook, Legal Desk, cutoff, and prior-state context;
- the expected structured membership, ownership, branch state, component
  summary, disposition, processing, record-boundary, dependency,
  cross-reference, coverage-effect, and review result;
- exact supporting evidence ranges and ordered Rule Trace;
- established and unresolved facts;
- permitted equivalent structured answers only when pre-adjudicated as legally
  immaterial; and
- designated critical-error and high-risk-pair assertions.

Free-form explanation similarity, model confidence, chain of thought, and
persuasive prose are not the acceptance rule. If a later allocation includes a
generative proposal task, that task receives only the exact ordinary evidence
and task contract. It never receives case IDs, human titles, package paths,
coverage labels, pair roles, expected results, reference decisions,
adjudication, or critical-error tags.

## Decision-to-artifact deterministic fixtures

`fixture.json` starts from one frozen accepted decision or exact accepted facts
and does not ask a model or parser to rediscover the legal answer. It declares
one expected state for every applicable artifact role:

- `EXACT` — the artifact must exist, validate, hash, and match canonical bytes;
- `NONE` — zero output is correct and requires explicit zero-count and
  no-artifact assertions; or
- `NOT_APPLICABLE` — the coverage matrix and assertion scope prove that the
  checkpoint does not apply.

An absent file never satisfies `NONE`. `NOT_APPLICABLE` cannot be selected
because an implementation failed to produce an output.

The complete expected-artifact inventory accounts for:

1. package and evidence preflight result;
2. component-inventory, membership, and board-ownership result;
3. branch-level effective-state decisions and derived component summary;
4. material disposition, processing result, reason codes, and Rule Trace;
5. record-unit, governing-dependency, and cross-reference result;
6. exact canonical `metadata.text`, `metadata.authority_note`, and six-field
   candidate records or explicit zero output;
7. table, Fees Rule, and Regulatory Form presentation-projection result;
8. exact token and metadata-byte measurements;
9. English partition frontier and final partition result;
10. HKEX English Source-Unit Coverage Proof;
11. Record Traceability Lookup entries;
12. Search Record creation, exact reuse, reselection, forward lineage, or
    omission result;
13. Waiting Room, historical, Quarantine, Coverage Gap, and Source Contract
    Review results where applicable;
14. per-board serving-readiness result;
15. forbidden-side-effect assertions; and
16. canonical fixture execution report.

Forbidden-side-effect assertions include no source, model, embedding, network,
credential, Azure, Pinecone, backup, routing, promotion, production-store, or
undeclared-file access and no live-state mutation.

## Frozen coverage matrix

`coverage-matrix.json` is the sole completeness authority for the accepted
conformance universe. Every required cell contains:

- permanent coverage-cell ID and normative boundary;
- evidence-to-decision or decision-to-artifact layer and primary checkpoint;
- one or more direct primary case IDs and permitted secondary cases;
- applicable ADR, rulebook rule, result branch, and contract fingerprints;
- ordinary direct, `POSITIVE`, or `NEAR_MISS` role;
- pair ID and both pair members for every high-risk boundary;
- critical-error classification where applicable; and
- immutable inclusion, supersession, or correction state.

Every required cell has direct primary coverage. Every executable case is
primary for at least one required cell. Every high-risk pair has both roles.
Every applicable stable rule and permitted result branch has direct coverage.
Secondary labels, counts, broad integration tests, or aggregate scores cannot
hide a missing primary case.

The exact fixture count follows the later accepted row-by-row matrix. It is not
chosen in advance or reduced to meet implementation cost, model performance,
or a round target.

Completeness does not require the Cartesian product of every independent
source, state, language, boundary, renderer, coverage, and identity fact. The
initial catalogue instead provides direct primary coverage for every stable
legal or technical result branch, both controlled sides of every designated
high-risk boundary, one direct case for each distinct mechanical failure or
result code, and selected combined cases for interactions whose composition
can change the answer. A combined case may provide secondary coverage but
cannot replace a missing direct primary branch case. This bounded
branch-and-interaction rule keeps the catalogue scalable without weakening its
completeness claim.

## Required coverage families

The exact initial matrix directly covers at least:

1. package, manifest, artifact, path, schema, hash, permission, hostile-source,
   and no-side-effect integrity;
2. all five ordinary source roles, their union, Fact Authorities, fresh and
   incomplete Observations, bounded board failures, and shared unbounded gaps;
3. rule-component, evidence-only, excluded non-rule, unresolved-membership,
   board-ownership, shared-artifact, orphan, duplicate, and wrong-board cases;
4. every ADR 0071 current, transitional, future, superseded, withdrawn,
   unknown, trigger, date, overlap, and current-product reconciliation branch;
5. mandatory English, optional Chinese, harmless Chinese discrepancy, English-
   defect signal, and prohibited Chinese serving paths;
6. coherent rules, independent and inseparable subrules, definitions, lists,
   notes, qualifications, local scope, required versus merely helpful context,
   cross-references, and unsafe child boundaries;
7. appendices, Practice Notes, tables, row groups, headers, units, notes, Fees
   Rules, Form Parts, declarations, fields, blank controls, selection controls,
   and signing requirements;
8. canonical rendering, presentation-only change, exact fit, token overflow,
   metadata overflow, label-induced overflow, recursive partitioning,
   indivisible overlong material, and prohibited fallback cuts;
9. primary source-unit ownership, repeated dependencies, missing, duplicated,
   reordered, orphaned, and wrong-board units plus every non-serving state; and
10. exact record reuse, successor, reselection, authority-note-only change,
    partition change, supported no change, per-board readiness, and no direct
    serving mutation.

## High-risk pairs and critical errors

High-risk distinctions use linked positive and near-miss cases differing by one
controlled fact where possible. Required pair families include at least:

- incorporated Regulatory Form versus a nearby non-rule checklist;
- matching effective current product versus passed date or trigger with a
  conflicting product;
- harmless optional-Chinese difference versus a Chinese signal exposing an
  English defect;
- independent subrules versus inseparable cumulative conditions;
- required governing context versus merely helpful background;
- exact cross-reference retention versus recursive target copying;
- complete fee bracket versus an amount detached from its header, currency, or
  calculation basis;
- presentation-only reflow versus a legal-text change;
- complete source-unit ownership versus one omitted, duplicated, or reordered
  unit; and
- complete serving-ready accounting versus complete accounting that exposes a
  quarantined current unit.

No aggregate score compensates for a designated critical error. Critical
families include guidance promoted as a rule, wrong-board ownership, future
wording served as current, reconstructed current wording, omitted material
transition, Chinese substituted for required English, invented or silently
corrected source text, arbitrary splitting, incomplete primary coverage,
unknown state repaired with an authority note, or a forbidden external effect.

## Package validation and conformance attestation

Package validation proves strict schemas, exact hashes, path containment,
complete declared inventories, valid references, complete coverage-matrix
arithmetic, both members of every pair, every rule and result branch, exact
artifact-role states, no answer leakage, and no fingerprint cycle.

Every deterministic fixture must match exact canonical bytes. Two isolated
clean executions produce byte-identical artifacts, measurements, inventories,
reports, and fingerprints. Reproducibility cannot excuse a semantically invalid
or incomplete result.

A valid suite does not prove that one processing build implements it. A
separate immutable Regulatory Rulebook Conformance Attestation binds the exact
suite, rulebook package, processing build, dependency lock, conformance runner,
complete case results, two-run reproducibility proof, architecture tests, and
successful final result. The attestation does not authorize source access,
release creation, approval, Pinecone, or deployment.

## Change, runtime, and retrieval boundaries

Every suite, matrix, catalogue, package, input, reference decision, expected
artifact, rule, reason code, and fingerprint is immutable once used. A
normative correction creates a new identity, impact declaration, and preserved
supersession relationship. Expected output cannot be edited merely to make a
failing implementation pass.

If a later real HKEX source exposes a new structure or failure, the runtime
preserves it, opens the applicable Source Contract Review or incident path, and
adds a new synthetic regression case only after the meaning and expected result
are accepted. Real-source freshness and completeness remain cutoff-bound
operational evidence rather than fixture truth.

This suite stops before embeddings and Pinecone. Multilingual query retrieval,
ranking, cross-family crowding, and downstream-answer reliance are designed and
admitted separately.

## Consequences and authorization

ADR 0075 later freezes the resulting exact initial Regulatory catalogue at 284
direct cases, 284 matching primary coverage cells, and 57 high-risk pairs. The
count follows exhaustive direct result-branch coverage, positive/near-miss
coverage of high-risk boundaries, direct mechanical failure coverage, and
targeted interaction cases rather than an unbounded all-combinations product.
A later `hk-regulatory` Source Rulebook Package binds the frozen suite and per-
board decision readiness without merging conformance with activation or
promotion.

This decision authorizes documentation only. It does not authorize schemas,
fixtures, implementation, source acquisition, LLM or embedding calls,
evaluation execution, corpus construction, release publication, Pinecone or
Azure access, promotion, deployment, commit, push, or any remote action.
