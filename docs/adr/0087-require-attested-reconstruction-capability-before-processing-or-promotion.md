---
status: accepted
date: 2026-08-14
amends:
  - "0083"
refines:
  - "0005"
  - "0006"
  - "0007"
  - "0016"
  - "0018"
  - "0041"
  - "0042"
  - "0078"
  - "0080"
  - "0082"
  - "0083"
  - "0084"
  - "0085"
  - "0086"
depends_on:
  - "0003"
  - "0005"
  - "0006"
  - "0007"
  - "0011"
  - "0013"
  - "0016"
  - "0018"
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
  - "0086"
---

# Require attested reconstruction capability before processing or promotion

## Decision in simple language

Accepted design is not permission to reconstruct real legislation. The legal-
processing worker may create a real Reconstructed Consolidation Artifact only
when one exact reconstruction capability profile has been fully implemented,
tested, independently reproduced, attested, activated, and not suspended.

Even then, processing creates candidates only. It cannot embed, approve,
publish, mutate Pinecone, change Azure, or alter Ask.Legal routing. A
reconstructed record reaches production only inside the same complete frozen
Corpus Release, Desired-State Inventory, Promotion Manifest, human Approval,
backup, verification, promotion, and rollback gates as every other record.

There is no reconstruction shortcut around the repository's capability and
promotion boundaries.

## Capability identities and states

The Management Register issues:

- one immutable reconstruction capability profile ID matching
  `^rcp_[0-9a-f]{48}$`; and
- one immutable Reconstruction Capability Attestation ID matching
  `^rct_[0-9a-f]{48}$`.

Identity is separate from the canonical SHA-256 fingerprint of the profile or
attestation. One profile has exactly one state at a time through append-only
events:

| State | Permitted consequence |
|---|---|
| `DESIGN_ONLY` | Documentation exists; no implementation or real processing is authorized |
| `IMPLEMENTED_UNATTESTED` | Local code or schemas may exist under separate implementation authority; no real reconstruction |
| `ATTESTED_INACTIVE` | Exact build and contracts passed required suites; activation and runtime capability remain absent |
| `ACTIVE_FOR_CANDIDATE_PROCESSING` | The legal-processing worker may process exact in-scope real evidence into candidates under its separate source capabilities |
| `SUSPENDED` | Affected reconstruction work stops and ADR 0086 impact handling applies |
| `REVOKED` | The profile cannot be reactivated; a successor profile and attestation are required |

State is not a rollout phase or product version. It records whether one exact
capability is currently trusted and authorized. This repository remains
`DESIGN_ONLY` because no executable schemas, implementation, fixture bytes,
suite run, attestation, activation, or operational capability has been created.

## Immutable capability profile

The profile is a strict JCS JSON object binding exact identities, versions, and
fingerprints for:

- the `hk-legislation` Source Rulebook Package and all three Release Scope
  readiness entries;
- Registered Source and Fact Authority registry;
- HKeL Publication Specification Bundle and source-tree contracts;
- latest-applicable verified-or-assisted evidence rules;
- event, commencement, applicability, status, and identity contracts;
- ADR 0082 operation registry;
- ADR 0084 Plan and Execution Report contracts;
- ADR 0085 artifact, derivation, alignment, coverage, and lineage contracts;
- canonical Hong Kong legislation renderer, partitioner, measurement, warning,
  Serving Record, and Record Traceability Lookup profiles;
- later-HKeL comparison, monitoring, suspension, impact, and restart rules;
- executable conformance suite, coverage matrix, pair catalogue, fixture and
  expected-artifact inventories;
- exact legal-processing build, dependency lock, deterministic engine, and
  conformance runner;
- architecture-test, containment, malicious-input, no-network, no-provider,
  no-production-credential, and forbidden-side-effect contracts; and
- runtime capability, identity, Evidence Vault, Management Register, reporting,
  and observability interfaces.

The profile contains no mutable `latest`, environment name, branch name, image
tag alias, URL alias, directory discovery, or unbounded version range. Any
material change creates a successor profile or invalidates the existing
attestation according to the changed contract's rule.

The deferred LLM proposal allocation is not smuggled into this profile. If ADR
0043 later admits a reconstruction model task, its separately admitted exact
task and model profile becomes another mandatory profile binding. Until then,
the active reconstruction profile contains no model provider capability.

## Attestation requirements

A Reconstruction Capability Attestation exists only after independent
validation proves:

1. every bound schema, code catalogue, package, fixture, and expected artifact
   exists, validates, hashes correctly, and is completely inventoried;
2. all 121 ordinary Hong Kong Legislation cases pass;
3. all current reconstruction cases, cells, and controlled pairs pass;
4. every operation class, Plan, Report, artifact, renderer, warning,
   traceability, fallback, later-HKeL, suspension, and restart branch has direct
   accepted coverage;
5. two isolated clean runs produce byte-identical inventories, decisions,
   Plans, Reports, artifacts, records, lookups, coverage results, and reports;
6. architecture tests prove application and credential boundaries;
7. malicious source text, malformed packages, unknown operations, path escape,
   undeclared files, and hostile structured input cannot acquire tools, code
   execution, secrets, model access, or approval authority;
8. failure, retry, restart, duplicate delivery, overlap, stale capability,
   suspended operation, and recovery behavior are exact and idempotent;
9. no test accesses a real source, model, embedding provider, Pinecone, Azure,
   backup, routing, deployment target, or production store; and
10. two accountable attesters bind the exact profile, build, suite results,
    evidence, limitations, and expiry or revalidation triggers.

Every required case must pass. There is no waiver, percentage, average,
expected failure, skipped branch, or temporary exception inside an attestation.
A structural test failure and a valid negative case expecting no reconstruction
are different outcomes.

## Activation

Activation is an append-only Management Register event binding:

- the exact `rcp_` profile and fingerprint;
- the exact valid `rct_` attestation and fingerprint;
- the legal-processing application build and runtime identity;
- allowed jurisdiction `HK`, material `legislation`, operation registry, and
  Release Scopes;
- the exact capability grants for Management Register and Evidence Vault reads
  and candidate writes;
- activation cutoff, expiry or revalidation deadline, responsible owner, and
  monitoring obligations; and
- confirmation that no suspension, revocation, stale contract, or unresolved
  critical incident applies.

Activation grants candidate-processing authority only. Source network access
remains a separate acquisition-worker capability. An LLM provider remains a
separate task-runner capability. Embedding, backup, Pinecone, Azure, release
publication, promotion, and routing credentials remain exclusive to their
separate applications and gates.

The processing worker validates the active event and every bound fingerprint
before each real Plan. A cached activation may be used only within its explicit
freshness and revocation-check contract. Missing, expired, stale, mismatched,
revoked, or unverifiable activation blocks before source text is changed.

## Runtime processing gate

One real reconstruction job may begin only when all of these are exact:

- active profile, attestation, build, contracts, and operation class;
- complete preserved evidence and source capability lineage;
- latest applicable HKeL base and exact observation cutoff;
- accepted Legal Desk applicability and event decisions;
- no overlapping active Plan for the same dependency closure and branch;
- available Evidence Vault and Management Register writes for immutable Plan,
  Report, artifact, decision, and failure records; and
- sufficient reserved time and resources to finish atomically or record an
  exact failure without publishing partial output.

The worker rechecks suspension immediately before execution and before
registering successful output. If suspension arrives during execution, it may
finish isolated computation for diagnosis but registers no eligible artifact;
the Report records the suspension and fallback consequence.

Every job is idempotent. The same exact evidence, cutoff, profile, and accepted
Plan reselect existing immutable output or failure artifacts rather than
minting duplicates or applying operations twice.

## Invalidation and suspension

The attestation or activation becomes unusable when any bound fingerprint,
schema, rulebook, registry, source interpretation, renderer, warning, identity,
traceability, engine build, dependency lock, suite, fixture, expected artifact,
security boundary, or runtime capability changes materially.

It also becomes unusable for the affected scope when:

- ADR 0086 suspends a relied-on component;
- a new mandatory conformance case exposes an uncovered branch;
- source semantics become unknown or incompatible;
- a reproducibility, containment, identity, warning, traceability, or external-
  effect failure appears;
- an attester revokes the result; or
- activation expires or cannot be checked under its freshness contract.

Scope follows ADR 0086: a bounded operation, mapping, source construct, branch,
or build component may suspend only its complete impact set; an unbounded cause
suspends the whole affected reconstruction profile. Reactivation requires the
complete ADR 0086 correction and restart path plus a successor or renewed exact
attestation and activation event.

## Release and promotion remain separate

An active reconstruction profile may produce candidate records only. Corpus
construction still must:

- render ordinary six-field records with the exact reconstruction warning;
- create complete Release Scope inventories and coverage status;
- select exactly one reconstruction, fallback, ordinary record, or no record
  per serving unit;
- build the complete Record Traceability Lookup and bind Plan, Report,
  artifact, evidence, decisions, and Coverage Gap;
- freeze the Corpus Release, Desired-State Inventory, backup and recovery
  evidence, and Promotion Manifest; and
- obtain one complete human Approval bound to the exact immutable promotion
  package.

Only the promotion worker can consume that Approval and production credentials.
A reconstruction capability, attestation, Legal Desk decision, warning, or
successful suite is never a substitute for Approval. A stale or changed Plan,
record, lookup, release, target, embedding, backup, manifest, or recovery fact
invalidates the Approval under ADR 0007.

The promotion worker does not reconstruct, reinterpret evidence, or repair a
record. It validates and executes only the exact approved manifest. Without a
valid exact Approval it performs no Pinecone, backup, Azure, or routing change.

## Conformance-catalogue expansion

This readiness topic adds five permanent cases and three controlled pairs under
ADR 0083's expansion rule:

- `HKLEG-RCN-DET-059` / `HKLEG-RCN-CELL-059` — exact active profile,
  attestation, build, and capability permit isolated candidate processing but
  no production side effect;
- `HKLEG-RCN-DET-060` / `HKLEG-RCN-CELL-060` — stale, expired, missing,
  revoked, or fingerprint-mismatched attestation or activation blocks before
  execution;
- `HKLEG-RCN-DET-061` / `HKLEG-RCN-CELL-061` — one operation class is
  suspended, so referencing Plans use fallback while an independently admitted
  operation class continues;
- `HKLEG-RCN-DET-062` / `HKLEG-RCN-CELL-062` — a complete reconstructed release
  without exact manifest-bound Approval produces no promotion authorization or
  external effect;
- `HKLEG-RCN-DET-063` / `HKLEG-RCN-CELL-063` — exact Approval and immutable
  manifest pass the promotion authorization validator in an isolated fake
  adapter without contacting production;
- `HKLEG-RCN-PAIR-033` controls case `059` active exact capability against case
  `060` stale or mismatched capability;
- `HKLEG-RCN-PAIR-034` controls case `059` admitted operation against case
  `061` suspended affected operation; and
- `HKLEG-RCN-PAIR-035` controls case `063` exact Approval against case `062`
  missing Approval.

The current reconstruction catalogue therefore contains **63 direct cases**,
**63 primary cells**, and **35 controlled pairs**. With the ordinary 121-case
baseline, a reconstruction-enabled profile contains **184 direct cases**.

## Current authorization and next topic

No readiness gate in this ADR is currently reached. The repository remains
design-only. No implementation, source access, suite execution, attestation,
activation, release, Approval, or production capability is implied.

The remaining cross-cutting topic that could materially change this design is
the deferred LLM-versus-deterministic allocation under ADR 0043—particularly
whether a model may propose or challenge Reconstruction Plans or Gazette event
extraction. That is a genuine product and trust decision rather than an obvious
mechanical optimum, so it should be presented to the user rather than silently
chosen.

This ADR authorizes documentation only. It does not implement, test, activate,
access sources, call providers, create releases, approve, mutate Pinecone or
Azure, promote, deploy, commit, push, or perform another remote action.
