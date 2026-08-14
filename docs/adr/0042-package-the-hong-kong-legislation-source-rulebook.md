---
status: accepted
date: 2026-08-12
amended_by:
  - 0044
  - "0081"
refined_by:
  - "0080"
  - "0082"
  - "0083"
  - "0084"
  - "0085"
  - "0086"
  - "0087"
refines:
  - 0018
  - 0019
  - 0028
  - 0030
  - 0031
  - 0032
  - 0033
  - 0034
  - 0041
depends_on:
  - 0003
  - 0005
  - 0011
  - 0013
  - 0016
---

# Package the Hong Kong Legislation Source Rulebook

The Hong Kong Legislation Source Rulebook is one immutable, strict,
fingerprinted policy package for the jurisdiction-and-material pair
`hk-legislation`. It binds the accepted coverage, fact authorities, evidence
rules, code meanings, decision contracts, and conformance universe needed by
the Hong Kong Legislation Legal Desk.

It is not one rulebook per Release Scope, one executable program, a source-data
archive, or a deployment package. The three accepted Hong Kong Legislation
Release Scopes remain owned by this one rulebook while carrying separate
decision-readiness states.

## Package boundary

The logical package is:

```text
hk-legislation-rulebook/
├── rulebook.json
├── coverage/
│   ├── coverage.json
│   └── release-scope-readiness.json
├── sources/
│   ├── source-role-bindings.json
│   └── source-check-policy.json
├── interpretation/
│   └── hkel-publication-specification.lock.json
├── rules/
│   ├── catalogue.json
│   └── <stable-rule-id>.json
├── codes/
│   └── catalogue.json
├── contracts/
│   └── locks.json
├── tests/
│   ├── hkel-reconciliation-fixtures.lock.json
│   ├── current-update-cases.lock.json
│   └── first-baseline-cases.lock.json
└── impact-declaration.json
```

The exact repository path may follow the later monorepo layout, but the logical
components, separation of concerns, root manifest, and hashing rules are fixed.
All paths are normalized relative POSIX paths. Absolute paths, parent traversal,
symlinks, network retrieval, and undeclared files are forbidden.

The package contains no credentials, secret locators, mutable endpoint URLs,
live health, source artifacts, runtime Observations, Legal Desk decisions,
Corpus Releases, Promotion Approvals, arbitrary executable code, or LLM
prompts. It neither calls a source nor authorizes a serving change.

## Root manifest and fingerprint

`rulebook.json` is strict Draft 2020-12 JSON with
`additionalProperties: false`. It requires:

- exact root-schema identity;
- `rulebook_id: "hk-legislation"`;
- a date-led version label in `YYYY-MM-DD.N` form, where `N` distinguishes
  multiple packages issued on the same date;
- `status: "frozen"`;
- jurisdiction `HK`, material `legislation`, and responsible Legal Desk ID;
- effective observation boundary;
- predecessor package fingerprint or an explicit initial-package marker;
- all three owned Release Scope IDs and their readiness entries;
- an ordered component inventory containing normalized path, role, media type,
  and lowercase SHA-256 for every normative component; and
- the impact-declaration path and hash.

The package fingerprint is calculated outside the root manifest over the exact
`rulebook.json` bytes and ordered `(relative path, SHA-256)` component
inventory. It is stored in the Management Register and every resulting Legal
Desk decision. It is not inserted into its own hashed manifest, avoiding a
self-referential fingerprint.

## Coverage and per-scope readiness

`coverage.json` binds the accepted complete coverage promise, exclusions,
Release Scope ownership, time boundary, and legal-material classifications.
It references the accepted rules rather than restating them as informal prose.

`release-scope-readiness.json` gives each scope exactly one state:

- `DECISION_READY` — the package contains every required scope-specific
  source, rule, code, contract, registry, and conformance binding; or
- `NOT_READY` — the exact blocking reason codes and missing or deferred
  components are declared, and the scope cannot support a Legal Desk decision
  or fresh Corpus Release under this package.

A frozen package may honestly bind a `NOT_READY` scope, but it cannot describe
the jurisdiction as wholly complete or use that scope for decisions. ADR 0005
governs any serving consequence. The other non-overlapping scopes are not
automatically invalidated merely because one scope is not ready.

Until the user completes the mandatory future HKeL Instruments & Others review
and the resulting Instrument Disposition Registry population and legal-effect
review, `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` remains `NOT_READY` with
the applicable review-required reason. This package contract does not decide
or conceal the deferred rows.

## Source roles without endpoint churn

`source-role-bindings.json` binds every stable Registered Source ID used by the
rulebook to:

- its exact permitted Fact Authorities and forbidden uses;
- responsible Legal Desk;
- applicable Release Scopes and rule stages;
- outage-impact class and evidence requirements; and
- the rules allowed to rely on that source role.

Mutable endpoint records remain in the separately versioned Source Register.
A URL move, generated download route, connector setting, or current source
health does not change the rulebook package while stable source identity, Fact
Authority, and result-determining policy remain unchanged.

`source-check-policy.json` contains the normative completeness, maximum-
freshness, supported-no-change, bounded-failure, and release-effect conditions
that can change a decision. Deployment clock times, timeouts, retry scheduling,
backoff, and provider throttling remain operational configuration but must
prove conformance with this policy. An operational change that alters a
result-determining threshold or failure meaning becomes a normative rulebook
change.

## Interpretation lock

`hkel-publication-specification.lock.json` binds the exact accepted HKeL XSD,
data dictionaries, Important Notices, catalogue descriptions, verification
meanings, and explicit interpretation mapping required by ADR 0028. It records
artifact identities and fingerprints; the preserved specification artifacts
remain in the Evidence Vault rather than being copied into this policy package.

A changed or unknown relied-on source meaning opens Source Contract Review.
Acceptance of a changed interpretation requires a new rulebook package and
impact declaration. A live documentation outage alone does not rewrite the
accepted lock.

## Declarative rules

`rules/catalogue.json` contains every permitted stable rule ID and its package-
local path and hash. Each strict rule object requires:

- stable rule ID, title, and plain-language meaning;
- stage, ordering dependencies, and applicable Release Scopes;
- required established facts and accepted Registered Source roles;
- complete preconditions and forbidden shortcuts;
- exact facts the rule may establish;
- permitted processing, legal-disposition, coverage, authority-note, identity,
  lineage, and review consequences;
- failure and unresolved-fact behavior;
- responsible Legal Desk decision authority and review requirement; and
- every conformance fixture or case that exercises the rule and each permitted
  branch.

The rule catalogue must be acyclic where it declares ordering dependencies.
Every path ends in an explicit permitted result. There is no implicit success,
newest-source-wins, similarity fallback, or catch-all no-change rule.

The rule objects are declarative contracts, not arbitrary scripts. Processing
code implements the contracts and proves conformance. A rule may state Legal
Desk and human-review authority, but it does not decide whether a future
implementation uses deterministic code or an explicitly approved LLM proposal
task. That allocation remains under the user's separate deferral and ADR
0039's future amendment process.

## Stable code catalogue

`codes/catalogue.json` defines the complete versioned vocabulary used by rules,
fixtures, decisions, reports, and review screens:

- source and legal event types;
- processing outcomes;
- legal dispositions;
- coverage effects and Coverage Gap reasons;
- evidence, identity, lineage, and processing reason codes;
- Source Contract Review and other review states; and
- authority-note-template IDs with exact controlled English text where a template is
  permitted.

Each code has one stable meaning, applicable stage, permitted combinations, and
deprecation state. A code is never silently redefined or reused. Deprecated
codes remain interpretable for historical decisions. Free text may explain a
decision but cannot replace the required stable codes.

Processing outcome, legal disposition, coverage effect, and review state remain
separate dimensions under ADR 0041. In particular, `PASS` does not mean
`SEARCHABLE_CURRENT`, and a Coverage Gap is not a disposition.

## Contract locks and decision records

`contracts/locks.json` binds exact schema and contract identities and
fingerprints for every object the rules produce or consume, including:

- Legal Desk decision and Rule Trace;
- Status Coverage Map and Bilingual Alignment Map;
- reconciliation and presentation-projection reports;
- Primary Source-Unit Coverage Proof;
- serving record and authority note;
- Record Traceability Lookup entry;
- Legal Item, Official Version, Legal Location, Search Record, and lineage;
- Coverage Gap, Quarantine, Waiting Room, and Source Contract Review result;
  and
- complete release-accounting and conformance reports.

Every Legal Desk decision records the exact rulebook ID, version, package
fingerprint, Observation cutoff, rule trace, evidence identities and hashes,
established and unresolved facts, all result dimensions, identity and serving
effects, responsible Legal Desk, and required human review. A decision cannot
cite a rule, code, source role, or contract absent from the exact package.

## Complete conformance universe

The test locks bind three non-overlapping catalogues:

1. ADR 0041's eighty-nine HKeL evidence, reconciliation, rendering, status,
   bilingual-structure, and partition fixtures;
2. `HKLEG-CURRENT-CASE-001` through `-018`; and
3. `HKLEG-BASE-CASE-001` through `-014`.

The initial complete conformance universe therefore contains 121 accepted
fixtures and cases. Every stable ID, package or case path, expected Rule Trace,
result, and fingerprint is bound. Missing, duplicate, unlisted, or
unexpectedly changed entries fail validation.

ADR 0080 later adds searchable reconstruction. The 121 cases remain the exact
pre-reconstruction baseline; they do not prove the reconstruction capability.
A Source Rulebook Package that enables `RECONSTRUCTED_CONSOLIDATION` must also
bind the future frozen supported-operation registry, reconstruction-specific
cases, expected fallback and official-reconciliation results, and their exact
artifacts. Until those additions are frozen and pass, the package may validate
the baseline but is not reconstruction-ready.

Each rule and every permitted result branch must be exercised by at least one
accepted fixture or case before the relevant Release Scope becomes
`DECISION_READY`. When one case covers several rules, the exact ordered Rule
Trace remains normative. Passing final output with the wrong rule trace fails.

## Rulebook validation and build attestation

Before registration, package validation proves:

1. strict schema validity and exact component hashes;
2. path containment and absence of undeclared normative files;
3. complete scope, source-role, interpretation, rule, code, contract, and test
   inventories;
4. unique IDs and no dangling or circular invalid references;
5. every rule input, result, code, and review state is defined and permitted;
6. every rule path terminates explicitly and no default success exists;
7. each `DECISION_READY` scope has complete rule-branch test coverage;
8. all 121 baseline fixture and case IDs, expected traces, and result
   dimensions are present, and any reconstruction-enabled profile also contains
   its complete ADR 0080 conformance extension;
9. the impact declaration is complete; and
10. two independent package validations produce the same inventory and
    fingerprint.

Package validity does not prove that one processing build implements it. A
separate immutable **Rulebook Conformance Attestation** binds:

- rulebook package fingerprint;
- exact processing build and dependency-lock fingerprint;
- conformance runner and contract fingerprints;
- complete 121-test baseline input and result fingerprints plus any enabled
  ADR 0080 reconstruction-extension fingerprints; and
- successful structural, semantic, clean-reproduction, and architecture-test
  results.

The attestation remains outside the package because it depends on both package
and build. A processing build may apply the package only while an exact valid
attestation exists. Attestation does not authorize a source call, release,
Approval, or production operation.

## Activation, replacement, and impact

Only frozen validated packages are registered. Working drafts have no decision
authority. The Management Register records append-only registration,
activation, supersession, revocation, and effective-boundary events rather than
mutating the package.

Exactly one active Hong Kong Legislation rulebook package applies at one
Observation cutoff. Every open decision lineage remains on its selected package
fingerprint. If a new package becomes active during an open run, the system
finishes the old cutoff under its original package or refreezes and restarts;
it never mixes rules or components.

Any change to coverage, Fact Authority, result-determining source policy,
interpretation, rule, code meaning, authority-note text, contract lock, expected test
outcome, or scope readiness creates a new package. A routine new source
artifact, live outage, endpoint move, or implementation build does not.

Every package includes an `impact-declaration.json` identifying whether it is
initial or replacing, changed components and rules, affected scopes and facts,
and whether existing items, decisions, authority notes, Quarantines, Coverage Gaps,
releases, or serving records require re-evaluation. Re-evaluation creates new
immutable decisions and lineage; it never rewrites history or authorizes
promotion by itself.

## Consequences and remaining work

The Hong Kong Legislation Source Rulebook package boundary is settled. The
package makes policy, implementation, source evidence, endpoint operations,
decision state, and promotion authority separately versioned and auditable.

The package's executable schemas and components remain implementation work.
The constitutional-and-other-instruments scope remains not ready until the
user's mandatory future Instruments & Others review and row-level work. Exact
deployment schedules and connector tuning remain operational configuration,
and generative-LLM allocation remains separately deferred.

This decision authorizes documentation only. It does not authorize source
access, implementation, dependency installation, AI or embedding calls,
release publication, Pinecone mutation, promotion, or deployment.
