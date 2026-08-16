---
status: accepted
date: 2026-08-14
refines:
  - "0057"
  - "0063"
  - "0064"
  - "0065"
  - "0066"
  - "0067"
---

# Package Hong Kong Case Proposition evaluations and admission profiles

Hong Kong Case Proposition workflow admission uses four distinct immutable
objects:

1. a **Case Proposition Evaluation Suite Package** defines the exact cases,
   protected references, evaluator, fixed gates, and completeness proof;
2. a **Case Proposition Workflow Admission Profile** freezes one exact
   candidate workflow and every evidence-derived operational and numerical
   value before the sealed admission results are scored;
3. an **Evaluation Run Set** preserves every required execution, attempt,
   output, score, metric, and gate result for that exact package and profile;
   and
4. the ADR 0067 **Case Proposition Workflow Admission** binds those three
   objects and the required Legal Desk and system-owner attestations.

The objects are separate to avoid a circular fingerprint and to prevent a
candidate workflow, evaluator, threshold, or answer key from changing after a
result is known. A workflow cannot pass by referring vaguely to a model name,
an aggregate report, a mutable test directory, or the latest evaluation.

This decision defines the future executable package contract and sealed real-
judgment selection method. It does not create JSON Schemas, prompts, judgment
packages, Reference Proposition Maps, provider accounts, model candidates, or
evaluation results and does not authorize a provider call.

## Package identity and canonical bytes

Every manifest and structured artifact uses one pinned schema version,
canonical UTF-8 JSON serialization, SHA-256 content fingerprints, declared
relative paths or immutable external references, and `additionalProperties:
false`. The eventual executable contract must pin the canonicalization rules;
an ordinary file hash over an unspecified serialization is insufficient.

Every package inventory declares each file or external artifact by:

- stable role and media type;
- relative path or immutable Evidence Vault object reference;
- plaintext content fingerprint and, for encrypted external material, the
  independently verifiable encrypted-object identity;
- byte length and applicable language or evidence class;
- permitted readers and whether the artifact may reach the evaluated task;
  and
- schema and contract fingerprints where applicable.

The root package fingerprint covers the ordered inventory and every declared
artifact fingerprint. No undeclared file, directory glob, filename convention,
mutable object alias, or storage listing contributes to completeness. Missing,
extra, substituted, unreadable, or fingerprint-mismatched material makes the
package invalid before scoring.

Secrets, provider credentials, encryption keys, and access tokens are never
package content and never contribute by value to a fingerprint. The package
binds only their required capability class and secret-reference identity.

## Evaluation Suite Package

One suite package has this logical shape. The paths describe artifact roles,
not an instruction to create implementation directories now.

```text
hk-case-proposition-evaluation-suite/
├── suite.json
├── coverage-matrix.json
├── synthetic-catalogue.json
├── sealed-real-catalogue.json
├── fixed-gates.json
├── evaluator/
│   ├── evaluator.json
│   ├── scoring-contract.json
│   └── validation-catalogue.json
├── semantic/
│   ├── synthetic/<opaque-case-id>/
│   │   ├── case.json
│   │   ├── input/
│   │   ├── reference/
│   │   └── adjudication/
│   └── sealed-real/<opaque-case-id>/
│       └── case.json
└── deterministic/<opaque-case-id>/
    ├── fixture.json
    ├── input/
    └── expected/
```

`suite.json` binds:

- one stable suite ID, version, status, freeze time, owner, and predecessor;
- ADRs 0060 through 0068 and every applicable task, ledger, renderer,
  rulebook, serving, and evaluation contract fingerprint;
- the exact 132-case synthetic catalogue and its 31 high-risk pairs;
- the exact sealed real-judgment catalogue and selection-matrix fingerprint;
- the deterministic catalogue, evaluator package, fixed gates, schemas, and
  package inventory;
- every critical-error family, required dimension, required slice, and
  repetition class; and
- one root package fingerprint and explicit supersession or correction map.

The suite package contains evaluation truth and evaluator policy. It does not
contain a candidate model, prompt, candidate-specific threshold, candidate
output, or admission decision.

### Three evidence views

Each semantic case has three separately permissioned views:

| View | Contents | May reach evaluated task? |
|---|---|---:|
| Model-facing input | Exactly the source, structural manifest, Coverage Units, Evidence Range IDs, dependencies, and task information the ordinary admitted workflow would receive | Yes |
| Evaluator reference | Hidden Reference Proposition Map, required and forbidden meanings, permitted equivalents, exact evidence, slice and critical labels, and scoring assertions | No |
| Adjudication record | Mapper and reviewer roles, independence declarations, disagreements, resolutions, freeze events, and later correction history | No |

An evaluated task receives the real legal identity, case name, citation, court,
and source text when ADR 0066 requires them. That is ordinary runtime evidence,
not evaluation leakage. It never receives the evaluation case ID, human test
title, selection-cell identity, pair role, expected result, Reference
Proposition Map, critical label, score, or admission status.

Synthetic references and small synthetic bytes may live in Git when the task
runner remains technically unable to read the evaluator-only paths. Complete
real judgments, sealed-set membership, real Reference Proposition Maps,
adjudications, raw model outputs, and operational results remain in registered
protected storage outside Git.

## Sealed real-judgment selection

“Sealed” does not mean that a public judgment was necessarily absent from a
provider's training data. The design makes no unverifiable unseen-text claim.
It means that exact admission-set membership, the hidden Reference Proposition
Map, adjudication, evaluator labels, raw results, and case-level diagnostics are
withheld from the evaluated task and ordinary workflow developers.

### Selection authority and timing

The Hong Kong Cases Legal Desk owns legal representativeness. The evaluation
owner owns package integrity and non-leakage. They freeze the selection matrix
and exact real-case inventory before an admission candidate's sealed results
are inspected.

A judgment is ineligible for the sealed admission set if it or its answer map
was used to design, tune, demonstrate, debug, or choose the candidate prompt,
model, packet strategy, validator, or threshold profile. Such material may be
valuable development or regression evidence, but it cannot count as pristine
sealed admission evidence.

### Branch-driven selection matrix

`sealed-real-catalogue.json` and its protected selection matrix—not a target
count—prove sufficiency. Every required cell names at least one primary real
case, and every real case is primary for at least one cell. Secondary labels
cannot hide a missing primary case.

The matrix directly covers:

- Court of Final Appeal, Court of Appeal, Court of First Instance,
  Competition Tribunal, corresponding historical superior courts, and Hong
  Kong Privy Council appeals;
- original English, original Traditional Chinese, and genuinely mixed-
  language reasoning;
- joint or majority, adopted, concurring, dissenting, plurality, obiter,
  agreement-only, and multi-opinion structures where the real corpus supplies
  them;
- short complete judgments, long segmented judgments, cross-segment
  dependencies, cross-opinion adoption, and varied accepted source formats;
- zero, one, and many propositions; familiar and novel legal answers;
  cumulative tests, independent grounds, qualifications, applications,
  treatment-only material, Quarantine, and blocked boundaries;
- contiguous and non-contiguous evidence, footnotes, tables, quotations,
  defined terms, cross-references, orders, and dispositions; and
- ordinary cases, high-risk distinctions, and every critical-error family for
  which a genuine real-judgment example can be safely and unambiguously
  adjudicated.

Synthetic cases continue to own hostile-input, malformed-package, impossible-
state, exact boundary, and other branches that cannot honestly or safely be
manufactured from a real judgment. A real case is not distorted merely to fill
a matrix cell.

Court, language, or document counts alone are not diversity. The matrix also
records decision period, source format, length band, opinion complexity,
proposition-result class, evidence form, and legal-boundary roles so several
near-identical easy judgments cannot satisfy the real extension.

The exact number of sealed real judgments is the smallest inventory that
satisfies every primary cell with adequate independent cases for the ADR 0067
repetition, canary, and diagnostic gates. The count is published only after
selection; it is not guessed in this ADR and cannot be reduced to fit a
preferred workflow's performance or cost.

### Development, admission, canary, and regression roles

Every real evaluation case has exactly one current evidence role:

- `DEVELOPMENT` — may guide workflow design and never counts for admission;
- `SEALED_ADMISSION` — protected case used for complete admission and periodic
  suite evaluation;
- `SEALED_CANARY` — protected member of a rotating canary pool; it may also be
  a sealed admission case but its rotation and case-level results stay hidden;
  or
- `REGRESSION` — preserved known failure or disclosed case required in future
  suites but no longer represented as a pristine holdout.

The protected catalogue may hold a reserve so exposed, ambiguous, withdrawn,
or obsolete cases can be replaced without weakening a required cell. Exposure
of membership, a map, or case-level expected behavior to workflow developers
removes `SEALED_ADMISSION` and `SEALED_CANARY` eligibility, records an incident
and impact assessment, and invalidates affected admission results until a
versioned replacement package is evaluated. The exposed case may remain as a
regression case.

Workflow developers receive development packages and aggregate sealed-set
dimension and slice diagnostics. They do not receive sealed case IDs, maps,
case-level results, or canary rotation. When an incident requires bounded
disclosure, the disclosed case follows the same de-sealing rule; operational
convenience never silently converts the holdout into a tuning set.

## Reference Proposition Map package

Each semantic case binds one exact original artifact, Official Version,
opinion and Coverage Unit inventory, and one immutable Reference Proposition
Map version. The map encodes:

- required propositions, issues, answers, qualifications, authority roles,
  context, application, result, and exact Evidence Range IDs;
- forbidden propositions, broadened meanings, wrong opinion paths, invalid
  merges or splits, false zeroes, and other critical or high-risk errors;
- permitted equivalent derived meanings and expressly acceptable alternate
  boundaries, without reducing evaluation to prose similarity;
- the correct zero, Quarantine, blocked, or treatment-handoff result;
- dimension, slice, pair, and critical-error annotations; and
- exact evaluator assertions and any required human semantic adjudication.

The primary mapper completes the map without seeing evaluated candidate
outputs. Every high-risk, critical, genuinely contestable, plurality,
uncertain-attribution, or alternate-boundary map receives an independent
second legal review. A disagreement must be resolved in a structured
adjudication record before the case is eligible. Unresolved reference
ambiguity makes the case `EVALUATOR_BLOCKED`; it cannot be scored as a
candidate failure or pass.

If a workflow output exposes a legally equivalent meaning or boundary not
already represented in the frozen map, the evaluator cannot grant an ad hoc
pass. A blinded Legal Desk adjudication either rejects it or creates a new map
and suite version. Every affected candidate is then re-evaluated under the
same new reference so one workflow does not receive a private exception.

Official correction, source-fingerprint change, map correction, changed
selection role, or adjudication correction creates a new immutable case or map
version and an impact declaration. Prior maps, results, and admission history
remain reproducible.

## Evaluator package and scoring

The evaluator is a fingerprinted deterministic component of the suite. It uses
versioned human-adjudicated reference truth and cannot invent or change that
truth. Decision 7 of proposed ADR 0099 excludes model assistance from the
acceptance path: deterministic checks and scoring apply the frozen map, and a
blinded human adjudication resolves any disputed equivalent meaning.

The evaluator applies these layers in order:

1. **package preflight** — schemas, inventories, fingerprints, permissions,
   completeness, non-leakage, and model-facing input parity;
2. **execution integrity** — exact workflow identity, requests, attempts,
   retries, response binding, assigned-object coverage, and forbidden side
   effects;
3. **deterministic conformance** — ledger arithmetic, IDs, ranges, quotation
   bytes, renderer, limits, traceability, reproducibility, and exact expected
   artifacts;
4. **semantic comparison** — proposition matching, required and forbidden
   meanings, opinion roles, evidence, qualifications, boundaries, context,
   language, and uncertainty against the hidden map; and
5. **gate evaluation** — repetitions, critical families, high-risk pairs,
   dimensions, required slices, context, operational profiles, and complete-
   workflow identity.

Semantic matching records the produced-to-reference mapping explicitly. It
reports unmatched required propositions, unmatched accepted outputs, and each
dimension's numerator, denominator, aggregation rule, and case contribution.
No opaque similarity score, evaluator explanation, or blended average can
replace these facts.

The evaluator and all deterministic scoring paths must pass a frozen
validation catalogue containing positive cases, near-miss mutations for every
critical family, missing and extra artifact cases, answer-leakage cases, and
two clean byte-identical executions. An evaluator change creates a new suite
identity and requires impact-scoped or complete re-evaluation; it never
silently re-scores preserved outputs under mutable logic.

## Evaluation Run Set

One run set binds one exact suite fingerprint and one exact frozen candidate
profile fingerprint. It contains:

- the predeclared run plan and complete case-by-repetition matrix;
- one immutable receipt for every request, provider attempt, repair,
  re-analysis, challenge, validation, reconciliation, Legal Desk decision,
  ledger, renderer, and failure path;
- raw structured outputs and exact request, response, evidence, task, model,
  prompt, setting, tokenizer, build, and evaluator fingerprints;
- token, context-reserve, packet, latency, retry, timeout, currency, and
  concurrency observations;
- deterministic expected-artifact and two-run reproducibility results;
- per-run semantic assertions, proposition matching, critical errors,
  high-risk pair results, dimension metrics, and slice metrics;
- completeness, repetition, leakage, capability, and forbidden-side-effect
  reports;
- every invalid, blocked, interrupted, or not-run result and its exact cause;
  and
- the final gate report and candidate `ELIGIBLE` or `NOT_ELIGIBLE` result.

`ELIGIBLE` means only that the exact evaluated workflow may proceed to ADR
0067's dual attestations and admission event. It is not production Approval,
release eligibility, source permission, or deployment authority.

Every planned execution has one status:

- `PASS` — all applicable assertions passed;
- `FAIL` — the workflow produced a validly evaluated wrong or unsafe result;
- `INVALID_RUN` — infrastructure, binding, package, or execution integrity
  prevented a valid evaluation;
- `EVALUATOR_BLOCKED` — reference truth or evaluator support was not adequate
  to decide the result; or
- `NOT_RUN` — the declared execution did not occur.

Only `PASS` satisfies a required repetition. `INVALID_RUN` may be rerun only
under the same frozen suite, profile, request identity, and ADR 0067 attempt
rules, with every attempt preserved. `EVALUATOR_BLOCKED` requires a versioned
reference or evaluator correction before every affected candidate is rerun.
`NOT_RUN` makes the package incomplete. Neither invalidity nor uncertainty is
converted into a candidate pass or ordinary semantic failure.

## Candidate Admission Profile

A draft profile has no evaluable identity. Freezing it creates one immutable
profile that must be used without change for the complete run set. It binds:

- every complete-workflow component and scope required by ADR 0067;
- exact provider endpoint, model snapshot, API and tokenizer contract,
  prompts, executable schemas, decoding settings, validators, packet builder,
  reconciliation, Legal Desk rules, renderer, and processing build;
- the evaluation-suite and evaluator fingerprints;
- fixed architectural gates copied from ADR 0067;
- thresholds for every semantic dimension and required slice;
- input, dependency, output, call, packet, and per-judgment token limits;
- timeout, backoff, concurrency, capacity, per-call, per-judgment, rolling,
  and currency limits;
- provider training, retention, logging, region, encryption, abuse-monitoring,
  and deletion facts;
- weekly canary, 90-day suite, drift-warning, automatic-stop, and
  revalidation values; and
- value provenance, owners, attestations, freeze time, predecessor, and root
  fingerprint.

For every non-architectural value the profile records its unit, scope,
measurement method, evidence references, sample and observation period,
estimator, uncertainty or safety margin, responsible owner, rationale, and
applicable warning and stop behavior. A naked number is invalid.

### Fixed rules versus evidence-derived values

The profile serializes but cannot weaken these fixed ADR 0067 gates:

- every 132-case synthetic case and every selected real case is accounted for;
- two byte-identical deterministic executions;
- three ordinary and five high-risk or critical semantic repetitions;
- every high-risk distinction passes every repetition;
- no critical error in any repetition;
- every required dimension and slice passes separately;
- at least 20% context reserve;
- one initial provider attempt and at most two transient retries, one
  representation-only repair, one targeted re-analysis, and one final
  targeted challenge;
- complete per-judgment cost reservation; and
- weekly canaries, a complete suite at least every 90 days, automatic
  suspension, and evidence-backed restart.

Evidence-derived values use development or calibration evidence, provider and
capacity facts, Legal Desk risk policy, and measured safety margins. They are
frozen before sealed admission scoring. The sealed admission set is not used
to tune a candidate until it passes. A failed result may motivate a new
workflow or profile, but the old result and profile remain preserved and the
new candidate must run the complete applicable suite.

Every dimension and slice threshold declares exact aggregation and missing-
data behavior. Where a slice is too small for a defensible rate, it uses an
exact per-case or per-distinction gate rather than a misleading percentage.
No threshold may be lowered after viewing a candidate result merely to make it
pass. A later threshold change creates a new profile, rationale, impact
declaration, and complete applicable re-evaluation.

## Attestation and admission boundary

The final admission evidence binds:

- one exact suite package;
- one exact frozen candidate profile;
- one complete run set and gate report;
- one Hong Kong Cases Legal Desk semantic attestation; and
- one system-owner deterministic, security, capability, data-handling, and
  operational attestation.

Neither attestor may waive a failed, missing, invalid, or blocked gate. The
admission event records `ADMITTED` only when the run set is `ELIGIBLE` and both
attestations are valid for the same fingerprints. Otherwise the candidate
remains not admitted. An admission record never incorporates secrets and is
not the later human Approval for a Promotion Manifest.

## Consequences and authorization

This decision settles the package composition, fingerprint order, protected
evidence views, sealed real-judgment selection method, Reference Proposition
Map adjudication, evaluator result contract, run statuses, threshold-freeze
rule, and admission binding for Hong Kong Case Proposition evaluation.

Actual executable schemas, synthetic bytes, real-judgment identities and
artifacts, Reference Proposition Maps, prompts, provider and model candidates,
threshold numbers, token and cost values, evaluator implementation, run
results, and attestations remain future specification or implementation
artifacts. They must instantiate this decision without changing ADRs 0060
through 0068.

This decision authorizes documentation only. It does not authorize source
acquisition, implementation, model or embedding calls, evaluation execution,
release publication, Pinecone or Azure access, promotion, deployment, commit,
or any remote action.
