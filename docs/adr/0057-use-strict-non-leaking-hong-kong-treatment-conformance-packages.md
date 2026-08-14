---
status: accepted
date: 2026-08-13
amended_by:
  - 0059
amends:
  - 0056
depends_on:
  - 0011
  - 0016
  - 0055
---

# Use strict non-leaking Hong Kong treatment conformance packages

Hong Kong later-treatment conformance uses permanent opaque case IDs, two
strict suite-specific manifests, two frozen case catalogues, and one frozen
coverage matrix. Package structure must prove completeness, reproducibility,
expected zero output, and absence of forbidden side effects without revealing
expected semantic answers to the model.

This contract instantiates ADR 0056's separation between semantic model
evaluations and deterministic contract fixtures. It is language-independent
and does not select an implementation stack, model, prompt, numerical
threshold, provider, or real-judgment evaluation corpus.

## Stable namespaces

Executable cases use these register-controlled namespaces:

| Namespace | Primary checkpoint |
|---|---|
| `HKCASE-TREAT-SEM-DIS-NNN` | Whole-judgment discovery evaluation |
| `HKCASE-TREAT-SEM-ANA-NNN` | Candidate-level semantic analysis evaluation |
| `HKCASE-TREAT-DET-VAL-NNN` | Deterministic proposal and evidence validation |
| `HKCASE-TREAT-DET-DEC-NNN` | Legal Desk decision and review routing |
| `HKCASE-TREAT-DET-NTE-NNN` | Authority-note rendering and budget behavior |
| `HKCASE-TREAT-DET-REC-NNN` | Search Record, embedding, lineage, and selection |
| `HKCASE-TREAT-DET-REL-NNN` | Release, update, promotion eligibility, and no-live-mutation behavior |

`HKCASE-TREAT-PAIR-NNN` identifies a required relationship between a high-risk
positive case and its near-miss. A pair ID is not an executable case.

`NNN` is a zero-padded register-issued sequence inside its namespace. The ID
never encodes the court, treatment, expected success or failure, real case name,
source locator, or expected answer. IDs are never reassigned. A changed
normative input, expected answer, assertion, or contract binding receives a new
case ID and package fingerprint; the old package remains preserved.

One case has one primary checkpoint. It may assert downstream secondary
checkpoints, but each required coverage cell still names a direct primary case.
Broad integration tests cannot substitute for missing boundary coverage.

## Logical package layout

```text
hk-case-treatment-conformance/
├── coverage-matrix.json
├── semantic-catalogue.json
├── deterministic-catalogue.json
├── semantic/
│   ├── discovery/<semantic-case-id>/
│   │   ├── evaluation.json
│   │   ├── input/
│   │   └── expected/
│   └── analysis/<semantic-case-id>/
│       ├── evaluation.json
│       ├── input/
│       └── expected/
└── deterministic/<primary-checkpoint>/<deterministic-case-id>/
    ├── fixture.json
    ├── input/
    └── expected/
```

The exact repository path may be selected with the future implementation
layout. The filenames, suite separation, package boundaries, and catalogue
semantics are fixed. Paths are normalized relative POSIX paths. Absolute paths,
`..`, empty segments, platform separators, symlinks, undeclared local files,
URI retrieval, and network access are forbidden.

Small synthetic inputs and expected artifacts may live in Git. Real judgment
evaluation bytes, protected expected answers, model outputs containing
operational data, and evaluation results remain in registered external stores.
A sealed real case uses the same logical manifest contract but exposes only an
opaque registered artifact identity and non-sensitive fingerprints where Git
policy permits them.

## Strict catalogues

`semantic-catalogue.json`, `deterministic-catalogue.json`, and
`coverage-matrix.json` are strict JSON Schema Draft 2020-12 documents with
`additionalProperties: false`.

Each frozen suite catalogue contains:

- schema identity, catalogue contract version, suite identity, status
  `"frozen"`, and catalogue fingerprint;
- exact rulebook, task or checkpoint, manifest, evidence, output, identity,
  authority-note, release, and other applicable contract identities and
  fingerprints;
- every case ID explicitly, without ranges or directory discovery;
- its manifest path and hash, or opaque registered external artifact reference;
- package fingerprint and evidence class `SYNTHETIC` or `SEALED_REAL`; and
- no duplicate, missing, unaccounted, dynamically discovered, or silently
  skipped case.

Globs, filename conventions, test-runner discovery, broad tags, and expected
counts cannot establish catalogue completeness by themselves.

## Common manifest envelope

Both `evaluation.json` and `fixture.json` contain:

- exact schema and package-contract versions;
- stable case ID, suite, primary checkpoint, frozen status, and evidence class;
- every applicable contract identity, version, and fingerprint;
- declared input slots, artifact roles, normalized paths or registered external
  references, media types, and hashes;
- primary and secondary coverage-cell IDs;
- optional pair ID and exact `POSITIVE` or `NEAR_MISS` role;
- explicit assertion scopes;
- every expected-artifact role and state;
- complete declared package inventory and package fingerprint; and
- non-normative human title and purpose.

Unknown fields, enums, roles, references, task IDs, checkpoints, coverage cells,
or files fail validation. Human titles, purposes, package IDs, coverage labels,
pair data, and expected-answer metadata never enter a model evidence packet.

## Semantic evaluation manifest

`evaluation.json` additionally declares:

- exact discovery or candidate-analysis task contract;
- complete synthetic evidence packet or sealed registered evidence reference;
- expected coverage-ledger requirements;
- one or more explicitly accepted structured results;
- exact supporting passages and proposition evidence;
- human adjudication role, state, record, and fingerprints;
- scoring dimensions and designated critical-error categories; and
- required output accounting for every supplied opinion or segment applicable
  to the task.

Several accepted results are permitted only when a human-approved adjudication
record proves the difference legally immaterial. Free-form prose similarity is
not the acceptance rule. Chain-of-thought is neither requested nor stored.

The model task receives only the exact admitted evidence packet and task
contract. It never receives the case ID, package path, title, purpose, coverage
cells, pair ID, expected result, adjudication, score, or critical-error tags.

## Deterministic fixture manifest

`fixture.json` additionally declares:

- exact prior Management Register, evidence, treatment graph, Search Record,
  Corpus Release, Desired-State Inventory, and Serving State facts applicable
  to the checkpoint;
- synthetic cutoff, identity, hierarchy, opinion, finality, rulebook, and
  contract state;
- frozen candidate proposal or Legal Desk decision under test;
- ordered assertion scopes; and
- one required state for every deterministic artifact role.

Each artifact role is exactly one of:

- `EXACT` — the declared expected artifact must exist, validate, hash, and
  match canonical bytes;
- `NONE` — the correct result is explicitly zero output, with zero-count and
  no-artifact assertions; or
- `NOT_APPLICABLE` — the coverage matrix and assertion scope prove that this
  checkpoint is outside the case.

An absent file never satisfies `NONE`. `NOT_APPLICABLE` cannot be chosen merely
because an implementation did not produce the result.

## Deterministic expected-artifact roles

Every fixture accounts for these roles:

1. validation result and ordered reason codes;
2. accepted Legal Desk decision and ordered Rule Trace;
3. treatment-graph delta and treatment-screening accounting;
4. exact authority-note bytes and fingerprint;
5. created, reused, reselected, withheld, and retired Search Record inventory;
6. forward Search Record lineage and append-only Search Record Selection
   Events;
7. embedding plan stating exact `REUSE`, `GENERATE`, or `OMIT`;
8. Corpus Release diff and complete record arithmetic;
9. Desired-State Inventory diff and complete record arithmetic;
10. ordinary-update outcome;
11. human-review route;
12. separate operational-control result;
13. promotion-eligibility result;
14. forbidden-side-effect assertions; and
15. canonical fixture execution report.

Forbidden-side-effect assertions include no network, source, AI, embedding,
Azure, Pinecone, backup, routing, credential, production-store, or undeclared-
file access and no direct live-state mutation.

Structured expected artifacts first validate against their pinned schemas and
semantic rules, then match canonical expected bytes. Two isolated clean
executions must produce byte-identical artifacts, inventory, arithmetic, and
execution reports. Reproducibility does not excuse a semantically invalid
result.

## Coverage matrix

`coverage-matrix.json` is the conformance completeness authority. Every required
cell contains:

- stable coverage-cell ID and normative description;
- semantic or deterministic suite and applicable task or checkpoint;
- one or more primary case IDs;
- permitted secondary case IDs where useful;
- required `POSITIVE`, `NEAR_MISS`, or ordinary direct-coverage role;
- pair ID and both pair members for every high-risk boundary;
- applicable contract version and fingerprint; and
- immutable inclusion and supersession state.

Secondary tags do not satisfy a missing primary case. Every executable case is
the primary case for at least one required cell. Every high-risk cell has both
pair roles. No required cell or case may be skipped, weakened, silently marked
inapplicable, removed, or replaced by an aggregate score. Any change creates a
new frozen matrix and catalogue versions with an impact declaration.

## Fingerprints and immutability

Each artifact hash is SHA-256 over its exact bytes. Canonical serialization,
Unicode, newline, JSON, JSONL, text, and other format rules belong to pinned
artifact contracts and are never normalized after hashing merely to make a test
pass.

The package fingerprint binds the exact manifest bytes and ordered declared
artifact inventory. Each catalogue fingerprint binds its exact bytes, contract
bindings, ordered case entries, manifest or registered artifact references,
and package fingerprints. The coverage-matrix fingerprint binds every required
cell, case relationship, pair, role, and contract binding.

Silently editing expected output to match a failing implementation is
forbidden. A normative correction requires the applicable rulebook, contract,
or ADR change, new package identity, new fingerprints, impact declaration, and
preservation of the former package and result.

## Consequences

The next design task is the exact initial coverage-cell and case table. Its
legal and technical rows determine the initial case count; this ADR does not
choose a count first. Later implementation must instantiate the accepted table
through schemas and packages without changing its meaning.

This decision authorizes documentation only. It does not authorize fixture
implementation, source or real-judgment acquisition, LLM or embedding calls,
release publication, Pinecone or Azure access, promotion, or deployment.
