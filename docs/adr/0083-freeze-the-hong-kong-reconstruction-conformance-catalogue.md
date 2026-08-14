---
status: accepted
date: 2026-08-14
amended_by:
  - "0086"
  - "0087"
refines:
  - "0041"
  - "0042"
  - "0080"
  - "0082"
depends_on:
  - "0005"
  - "0011"
  - "0013"
  - "0016"
  - "0038"
  - "0041"
  - "0042"
  - "0050"
  - "0078"
  - "0079"
  - "0080"
  - "0081"
  - "0082"
refined_by:
  - "0084"
  - "0085"
---

# Freeze the Hong Kong reconstruction conformance catalogue

## Later expansion

ADR 0086 adds permanent cases and cells `057` and `058` plus controlled pairs
`031` and `032` for a later HKeL version that cannot be compared at a common
event horizon and for an invalid later HKeL candidate. The current catalogue is
later expanded again by ADR 0087 with readiness cases `059` through `063` and
pairs `033` through `035`. It now has 63 direct cases, 63 primary cells, and 35
pairs; the original IDs and 56-case freeze below remain unchanged historical
members.

## Decision

The canonical catalogue in
[`HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md`](../design/HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md)
is the accepted initial conformance universe for Hong Kong publication-lag
reconstruction. It freezes:

- **56 permanent direct case IDs**;
- **56 matching permanent primary coverage-cell IDs**; and
- **30 permanent high-risk controlled-pair IDs**.

The count results from direct coverage of every ADR 0082 operation class and
the distinct chain, applicability, bilingual, dependency, artifact, fallback,
serving, security, reproducibility, and later-HKeL branches. It is not a target,
sample size, pass-rate denominator chosen for convenience, or Cartesian product
of independent facts.

Every case, cell, and pair is required. An average score, broad integration
test, secondary assertion, or successful real-world example cannot compensate
for a missing or failed direct branch.

## Two linked conformance layers

The suite separates two causes of failure:

1. **Evidence-to-plan decision conformance** contains 32 cases. It proves that
   exact synthetic source-shaped evidence produces the correct admitted
   Reconstruction Plan or the correct block, Quarantine, Source Contract
   Review, Coverage Gap, and fallback consequence.
2. **Plan-to-artifact deterministic conformance** contains 24 cases. It starts
   from a frozen accepted or deliberately invalid plan and proves exact
   execution, atomicity, reproducibility, artifacts, serving output, fallback,
   traceability, and later-HKeL replacement behavior.

One layer cannot prove the other. A correct operation decision can still be
rendered incorrectly, and byte-perfect execution of the wrong legal plan is
still wrong.

No case calls a model. If ADR 0043 later admits an LLM plan-proposal or
challenge task, that workflow receives a separate semantic evaluation and
admission package. The deterministic catalogue remains the authoritative final
output contract.

## Frozen coverage counts

| Coverage group | Direct cases and cells |
|---|---:|
| Eight operation classes and their unsafe near-misses | 16 |
| Base, amendment-chain, order, commencement, and applicability | 8 |
| Authentic languages, alignment, structure, and governing dependency | 8 |
| Atomic compound execution, bounded siblings, retry, and reproducibility | 6 |
| Plan and report integrity, undeclared input, and forbidden patching | 6 |
| Serving warning, fallback, zero-record, exclusivity, and leakage | 6 |
| Later HKeL match, mismatch, attribution, partial replacement, and monitoring | 6 |
| **Total** | **56** |

Cases `HKLEG-RCN-DEC-001` through `032` belong to the evidence-to-plan
decision layer. Cases `HKLEG-RCN-DET-033` through `056` belong to the
plan-to-artifact deterministic layer. Primary cells use
`HKLEG-RCN-CELL-001` through `056`; each case is the direct primary case for
the cell with the same ordinal. Controlled pairs use
`HKLEG-RCN-PAIR-001` through `030`.

IDs are permanent, opaque, and non-answer-bearing. They do not encode success,
failure, operation meaning, expected record count, warning state, or pair role.
They never enter ordinary proposal evidence or serving metadata.

## Logical suite package

The future executable package has this fixed logical boundary:

```text
hk-legislation-reconstruction-conformance/
├── suite.json
├── coverage-matrix.json
├── pair-catalogue.json
├── decision-catalogue.json
├── deterministic-catalogue.json
├── decision/
│   └── <case-id>/
│       ├── case.json
│       ├── input/
│       └── reference/
└── deterministic/
    └── <case-id>/
        ├── fixture.json
        ├── input/
        └── expected/
```

The exact repository path may follow the future implementation layout. The
root manifests, catalogue separation, declared inventories, package-local
paths, strict schemas, hashes, frozen coverage matrix, pair catalogue, and
case-package boundaries are fixed.

Absolute paths, parent traversal, symlinks, URI retrieval, network access,
directory discovery, undeclared local files, mutable aliases, credentials, and
live state are forbidden. Small synthetic source-shaped evidence and exact
expected artifacts may live in Git. Real source snapshots, corpora, operational
reports, credentials, and production state do not.

## Reference decisions and exact artifacts

The Hong Kong Legislation Legal Desk owns the accepted structured reference
decision for each evidence-to-plan case under the exact Source Rulebook and
operation-registry fingerprints. References bind exact evidence ranges,
established and unresolved facts, operations or explicit zero operations,
ordering, applicability, dependency closure, result dimensions, reason codes,
fallback consequences, and Rule Trace.

Deterministic cases bind separately hashed expected artifacts as applicable,
including:

- Reconstruction Plan or explicit no-plan result;
- Reconstruction Execution Report;
- reconstructed English and Traditional Chinese source trees and canonical
  bytes;
- Bilingual Alignment Map and dependency-closure proof;
- Reconstructed Consolidation Artifact;
- exact six-field Serving Records and authority-note bytes;
- Record Traceability Lookup entries and identity or lineage result;
- Coverage Gap, fallback-selection, Quarantine, or Source Contract Review
  result;
- later-HKeL reconciliation and operation-class monitoring result; and
- complete suite execution and reproducibility reports.

Every artifact role is exactly `EXACT`, `NONE`, or `NOT_APPLICABLE`. A missing
file cannot pass as an expected zero result. Expected JSON and JSONL use their
pinned canonical serialization and schemas; byte comparison cannot be replaced
by semantic equivalence.

## Coverage and pair rules

Every stable operation class has a direct admitted case and a direct controlled
near-miss. Cross-cutting cases cover only interactions that can change the
answer. Each primary cell names one direct case; secondary assertions cannot
fill an uncovered cell.

Each of the 30 controlled pairs declares two unchanged cases and the one
material fact that separates their required outcomes. A case may participate
in more than one pair when the scenario itself is unchanged. Runners cannot
rewrite a case packet to create an easier pair.

The coverage matrix enumerates every applicable ADR 0080 through ADR 0083
branch, operation ID, result reason, artifact role, serving consequence,
fallback branch, and later-HKeL branch. Each required branch has at least one
direct primary case. Unknown or uncovered normative behavior makes the suite
invalid rather than optional.

## Critical errors and pass rule

Every structurally valid case, coverage cell, and pair member must pass. There
is no percentage threshold. Critical errors include:

- applying an unregistered, ambiguous, fuzzy, translated, inferred, model-
  authored, human-authored, or incomplete amendment operation;
- selecting the wrong HKeL base, omitting an operative event, including an
  uncommenced event, or guessing order or applicability;
- publishing a partial atomic result or allowing a failed governing dependency
  to leak into an allegedly independent child;
- losing, generating, merging, or misaligning authentic-language content;
- accepting an unexpected match set, wrong before-state, missing source unit,
  unknown parameter, undeclared input, forged hash, or incomplete report;
- producing non-reproducible bytes, applying an amendment twice, or mutating a
  preserved base or prior artifact;
- selecting both reconstruction and fallback, omitting the exact warning,
  leaking internal operation data into `metadata.text`, or serving a record
  when no valid result exists;
- failing to prefer a newer eligible assisted HKeL base or fallback over an
  older verified one;
- retaining reconstruction after a matching HKeL consolidation is admitted,
  or ignoring a material mismatch with later HKeL; and
- any source, model, network, credential, Pinecone, Azure, backup, routing,
  promotion, deployment, production-store, or other forbidden side effect.

Invalid, incomplete, blocked, not-run, or infrastructure-failed test packages
are distinct from valid cases that correctly expect no reconstruction. They do
not count as passes or disappear from the denominator.

Two isolated clean executions must produce byte-identical catalogue inventory,
plans, reports, final artifacts, identities, lookups, coverage results, and
execution reports. Reproducibility does not excuse a wrong reference result;
all semantic and byte-level assertions must also pass.

## Immutable expansion and correction

New legal or technical behavior adds new case, cell, and pair IDs without
renumbering existing ones. Correcting a frozen scenario, reference result,
artifact, assertion, cell, or pair requires a new catalogue version, explicit
correction or supersession mapping, impact declaration, preservation of the
former package and results, and revalidation of affected rulebooks, contracts,
tasks, and builds.

The frozen count does not cap future evidence-backed expansion. It prevents an
implementation from weakening the current requirements by combining, omitting,
discovering dynamically, or marking difficult cases inapplicable.

## Readiness and authorization

The existing 121 Hong Kong Legislation cases remain the pre-reconstruction
baseline. A reconstruction-enabled profile must pass all 121 plus these 56
cases: **177 direct cases in total**, with all 30 reconstruction pairs and all
ordinary package, coverage, attestation, and clean-reproduction gates.

This ADR freezes conceptual cases, cells, pairs, and required behavior. It does
not create executable schemas, manifests, fixture bytes, expected artifact
bytes, validators, source evidence, a conformance run, or an attestation. It
does not authorize implementation, source access, model or embedding calls,
release publication, Pinecone or Azure access, promotion, deployment, commit,
push, or another remote action.

The next topic is the exact Reconstruction Plan and Execution Report artifact
contracts that the future fixture packages and engine must validate.
