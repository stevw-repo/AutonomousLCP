# M5 Executable Legal Desk Package Protocol

Status: accepted implementation-facing design

Date: 2026-08-16

Closes: `BR-09`

## 1. Package authority

One Source Rulebook Package is the complete executable policy for one exact
jurisdiction/material family and declared Release Scope set. It determines how
preserved source facts may support legal decisions. It contains no source,
model, review, production, or deployment credential and grants no Approval.

The cross-cutting engine supplies deterministic package loading, validation,
rule execution, rule tracing, fixture execution, task admission, and lifecycle
checks. Jurisdiction packages supply legal meaning. Generic code may not invent
a fallback for an unknown jurisdiction rule.

## 2. Canonical package layout

Every package manifest inventories exact bytes under these roles:

```text
package.json
contracts/
catalogues/
sources/
scopes/
rules/
renderers/
fixtures/deterministic/
fixtures/semantic/
evaluations/
profiles/
expected/
attestations/
```

`package.json` binds package ID/version, jurisdiction, material family, Legal
Desk Owner, effective cutoff, predecessor, contract/schema/code locks, exact
files, source-universe fingerprint, scope readiness, unresolved policy codes,
impact declaration, minimum engine version, and package fingerprint.

No undeclared file is loaded. Paths are canonical, relative, Unicode-normalized,
case-exact, and traversal-free. Package order is lexical by UTF-8 byte order.
Generated caches and compiled output are never authority.

## 3. Required contents

- **Source universe:** every controlling, corroborating, discovery, trigger,
  specification, and excluded source role, endpoint family, checking tier,
  permitted use, completeness rule, and outage consequence.
- **Release Scopes:** stable non-overlapping ownership, required sources,
  item/location accounting, zero-record and withholding rules, and overlap
  proof.
- **Closed rules:** stable rule IDs, preconditions, exact evidence roles,
  deterministic result, allowed Legal Desk disposition, reason/failure codes,
  affected scope, and next path.
- **Renderers:** exact input contract, canonical output bytes, source-unit
  coverage proof, identity/lineage behavior, authority-note behavior, and
  forbidden transformations.
- **Fixtures:** complete branch and boundary coverage with exact input package
  fingerprints and expected decisions/artifacts.
- **Semantic tasks:** bounded-decision input/output schemas, exact fields within
  model authority, evidence budget, hostile-text boundary, forbidden
  decisions, deterministic validators, challenge/reconciliation flow, and
  human/Legal Desk escalation.
- **Evaluations and profiles:** protected evidence selection, leakage controls,
  evaluator contract, run set, thresholds, provider/model deployment
  fingerprint, suspension predicates, and expiry.
- **Attestations:** deterministic conformance, semantic admission where used,
  reproducibility, owner acceptance, activation, suspension, and supersession.

## 4. Rule execution result

For each admitted subject, the engine emits one immutable result containing
package/rule references, complete evidence inputs, prior state, matched
preconditions, Rule Trace, processing result, legal disposition when decided,
coverage effect, review/quarantine effect, candidate artifact refs, and exact
next action.

If zero or multiple terminal rules match where exactly one is required, the
result is `RULEBOOK_NON_TOTAL` or `RULEBOOK_AMBIGUOUS` and blocks the affected
scope. Unknown evidence, source semantics, code, or enum cannot fall through
to a permissive default.

## 5. Readiness and lifecycle

Each Release Scope is independently:

- `NOT_READY` — a named policy, source, fixture, evaluation, or attestation is
  missing;
- `DECISION_READY` — package contents are complete and reviewable but not
  executable;
- `ATTESTED_INACTIVE` — exact build and conformance passed;
- `ACTIVE` — one register lifecycle event admits the exact package/profile;
- `SUSPENDED` — new processing is blocked while existing evidence and serving
  consequences follow their own rules; or
- `SUPERSEDED` — a successor is active and old in-flight work remains pinned.

Activation binds package, engine build, contract set, deterministic suite,
semantic profile where applicable, owner attestation, and allowed Release
Scopes. Package publication or passing tests alone does not activate it.

A source specification change, fixture regression, evaluation drift, model
retirement, security event, or owner revocation suspends only affected
capabilities/scopes. In-flight results cannot silently switch packages.

## 6. Model boundary

All generative work uses the sole legal-processing task runner. The production
service boundary is Azure OpenAI models sold by Azure through Microsoft
Foundry, using stateless inference APIs only. Stateful assistants, hosted file
stores, threads, stored responses, autonomous tools, browsing, and code
execution are outside this design.

An exact task profile binds Azure resource/geography class, deployment name,
provider model ID and version, API contract, tokenizer, prompt/system bytes,
input and output schemas, limits, content-filter policy, retry policy, data-
handling profile, evaluator, thresholds, and expiry. Floating aliases are
forbidden. A replacement model is a new profile and must pass the complete
admission suite.

Provider output is an evidence-bound bounded semantic decision for the fields
named by its admitted task contract. A conforming result that survives the
independent challenge and deterministic validators is the ordinary semantic
decision; code does not independently recreate that judgment. It is never
source evidence, final source bytes, identity, a Search Record, Approval, or an
effect command. Missing provider admission disables only model-dependent
branches; deterministic packages continue where their own rules permit.

Decision 7 makes every task not already allocated to a generative decision by
an accepted decision `NO_GENERATIVE_LLM`. It uses deterministic rules or the
exact Legal Desk/human review path, with no `UNDECIDED` runtime allocation.
Gazette-event analysis/challenge and Reconstruction Plan decision/challenge are
named generative allocations. Offline evaluation uses deterministic checks and
acceptance calculations against human-adjudicated reference truth; it is not a
generative allocation. Adding any other generative task later requires a new
ADR, task contract, evaluation package, admission profile, and activation
event.

## 7. Test-only synthetic package

M7 uses one reserved package with jurisdiction `ZZZ`, environment
`LOCAL_SYNTHETIC`, and material family `TEST_LEGAL_MATERIAL`. It exercises all
cross-cutting contracts, evidence states, bilingual/structured examples,
quarantine, withholding, no-change, approval invalidation, and promotion
behavior with invented content.

The package and its identities are rejected when environment is not
`LOCAL_SYNTHETIC`. It is absent from every production Release Scope Registry,
contains no real source locator or credential, performs no real model call,
and proves no Hong Kong or other jurisdiction readiness.

## 8. Production package boundary

Hong Kong Legislation, Cases, HKEX Regulatory Materials, and later Principles
packages retain all accepted ADR and catalogue requirements. The engine and
synthetic package can be complete while one or more real scopes remain
`NOT_READY`. No roadmap or report may convert platform readiness into source,
legal, model, retrieval, or production readiness.

Source rights, complete endpoint inventories, real fixture bytes, adjudicated
evaluations, and named owners are package admission evidence. They are not
generic architecture decisions and cannot be fabricated to close design.

## 9. Required M5 proof

The package mechanism must reject missing/extra files, fingerprint drift,
unknown codes, contract mismatch, overlapping scopes, incomplete source
inventory, non-total or ambiguous rules, fixture leakage, floating models,
expired profiles, stale activation, and environment misuse. Reproducible builds
must emit byte-identical decisions and artifacts from exact inputs.

This document is design authority only and grants no rulebook implementation,
real-source, model, release, or production authorization.
