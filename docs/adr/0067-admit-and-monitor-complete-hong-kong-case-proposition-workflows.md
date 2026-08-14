---
status: accepted
date: 2026-08-14
refines:
  - "0039"
  - "0057"
  - "0063"
  - "0064"
  - "0065"
  - "0066"
refined_by: "0068"
---

# Admit and monitor complete Hong Kong Case Proposition workflows

Hong Kong Case Proposition LLM use is admitted only as one exact complete
fingerprinted workflow. A model name, provider reputation, prompt result, or
aggregate score cannot be admitted by itself.

The admitted object binds source and parser contracts, Coverage Ledger,
packet construction, both ADR 0066 task contracts, models, prompts, settings,
deterministic validators, objection reconciliation, Legal Desk rules,
renderer, evaluation packages and thresholds, and processing build. A result-
affecting change creates a different candidate workflow and requires recorded
impact and the applicable re-admission.

Admission permits only the declared Hong Kong Case Proposition task, source,
court, language, artifact, opinion, length, structure, and request-kind scope.
It is not source-access permission, production Approval, Pinecone permission,
or general authorization to use the model elsewhere.

## Admission states

The Management Register records immutable transitions among:

| State | Meaning |
|---|---|
| `CANDIDATE` | A complete proposed workflow exists but cannot make operational provider calls |
| `EVALUATING` | The exact workflow may run only against registered evaluation evidence under separate evaluation authorization |
| `ADMITTED` | The exact workflow passed every gate and may process permitted new work through the sole task runner |
| `SUSPENDED` | New calls stop immediately while an evidence, drift, provider, cost, or security concern is investigated |
| `REVOKED` | The workflow cannot process new work; restoration requires a new admitted identity or an exact evidence-backed re-admission event |
| `SUPERSEDED` | A later admitted workflow replaces it for new work while historical results remain reproducible |

Only `ADMITTED` may process ordinary new judgments. Suspension, revocation,
or supersession does not silently delete or invalidate earlier results. A
bounded impact review decides which preserved results require reprocessing,
Quarantine, withholding, or no change.

## Exact admission package and attestations

One immutable admission package binds:

- complete workflow identity and every result-affecting fingerprint;
- permitted task families and all eight ADR 0066 request kinds;
- admitted source, artifact, court, opinion, language, length, structure, and
  request scope;
- provider endpoint, exact model snapshot or immutable model version, API
  contract, tokenizer, region, and provider data-handling contract;
- prompts, schemas, decoding settings, output limits, packet builder,
  validators, reconciliation rules, renderer, and processing build;
- frozen synthetic and sealed real-judgment evaluation packages and results;
- repetition, threshold, context, retry, cost, concurrency, timeout,
  retention, monitoring, and revalidation profiles;
- semantic attestation by the Hong Kong Cases Legal Desk; and
- deterministic, security, capability, and operational attestation by the
  responsible system owner.

The Legal Desk attests legal evaluation and semantic-boundary correctness.
The system owner attests technical conformance and operational controls.
Neither may waive the other's failed gate. These attestations are not the
later human Approval for one production Promotion Manifest.

## Model selection and fallback

Every evaluated candidate uses an exact model and settings identity. Floating
aliases such as `latest` are forbidden. A silent model upgrade, snapshot,
tokenizer, API-behavior, or result-affecting provider safety-filter change
breaks admitted identity and suspends new calls pending impact assessment and
the applicable re-admission.

Analysis and challenge may use the same admitted model or different admitted
models. Different providers are not required. Independence comes from
separate prompts, fresh contexts, different inputs and outputs, and
deterministic reconciliation rather than brand diversity or voting.

When several complete workflows pass every gate, the selected workflow may
optimize total cost, latency, capacity risk, and operational complexity within
the passing set. Quality and safety gates are never weakened to prefer a
cheaper candidate. Automatic model fallback is forbidden unless that exact
fallback combination has its own complete admission and an explicit
deterministic routing rule.

## Context and packet safety

Before each call, the task runner counts tokens using the admitted tokenizer.
The measured fixed prompt and schema, supplied evidence and prior-stage data,
and maximum permitted response together may occupy no more than **80% of the
admitted model's total context window**. At least 20% remains a hard safety
reserve.

The maximum response is reserved even when ordinary responses are shorter. A
caller cannot borrow the reserve, rely on provider truncation, or silently
lower the response ceiling. A request that does not fit is deterministically
repacked into smaller complete opinion-aware packets with exact dependencies.
A Coverage Unit is not cut merely to fit; an exact structural subrange is
permitted only under ADR 0066. If safe packet construction still cannot fit,
the work is `BLOCKED` or enters the applicable structural Quarantine.

The 20% reserve is a minimum rather than a target. Each admission profile also
pins exact input, dependency, output, and per-judgment token ceilings derived
from the largest passing evaluation cases.

## Complete-workflow evaluation gate

Admission evaluates the assembled workflow rather than an isolated model,
prompt, or response. It requires:

1. every deterministic conformance case to pass exactly in two clean isolated
   runs with byte-identical deterministic artifacts;
2. all 132 frozen synthetic Case Proposition cases to run and be accounted;
3. every required sealed real judgment to be assessed against its hidden,
   independently adjudicated Reference Proposition Map;
4. every required court, original-language, opinion, length, zero-result,
   Quarantine, segmentation, boundary, and hostile-text slice to meet its own
   gate;
5. no critical error in any admission run; and
6. every analysis, challenge, validation, reconciliation, Legal Desk, ledger,
   renderer, and failure-path fingerprint to match the candidate workflow.

Every ordinary semantic case and sealed real judgment runs independently
**three times**. Every case in a high-risk pair or carrying a critical-error
label runs **five times**. Every deterministic case passes exactly, every
high-risk pair distinction passes every repetition, no critical error occurs
in any repetition, and every separately pinned semantic dimension and
required slice meets its own threshold.

Equivalent source-faithful derived wording and expressly permitted alternate
boundaries remain valid under the hidden Reference Proposition Map; model prose
need not be byte-identical. One blended average is forbidden. A critical or
high-risk failure cannot be hidden by easy successes, and weak Traditional-
Chinese, segmented, multi-opinion, zero-result, or Quarantine performance
cannot be averaged away.

If no candidate passes, LLM processing remains disabled. The workflow or model
may improve and be evaluated again; gates are not weakened merely to admit a
preferred candidate.

The executable result also publishes each semantic dimension and slice for
diagnosis: material-proposition recall, supported precision, qualification
completeness, issue-and-answer integrity, opinion attribution, boundary
correctness, evidence sufficiency, context and result, language fidelity, and
uncertainty calibration. Retrieval and downstream-answer quality remain a
separate later gate.

Critical errors retain ADR 0063's zero-tolerance definitions, including
fabricated propositions or evidence, false complete-no-proposition results,
materially broadened rules, operative-opinion inversion, synthetic majority
reasoning, unsafe completion over uncertainty or incomplete coverage, and
hostile source text escaping the task boundary. A model-created quotation
presented as verbatim judgment text is also critical under ADR 0066's Evidence
Range ID boundary.

## Bounded attempts and semantic reconsideration

Attempt classes remain separate:

- one initial provider attempt plus at most **two transient retries** for an
  admitted timeout, rate limit, or provider transport failure;
- exactly **one representation-only schema repair** for a semantically bound
  response that fails the strict JSON representation;
- exactly **one targeted semantic re-analysis** for one deterministically
  reconciled objection batch, followed by exactly one final targeted
  challenge; and
- no retry merely because an answer is inconvenient or repeated sampling may
  eventually produce a passing answer.

Transport retries use the same immutable request and idempotency identity and
preserve every provider attempt. A different response is never silently
substituted. Schema repair cannot alter semantic fields. A material objection
remaining after targeted re-analysis and final challenge enters Quarantine or
ADR 0065's exact human-review route.

Per-call timeouts and backoff are pinned from measured provider behavior in the
admission profile. Exhaustion never becomes a valid zero, empty candidate
inventory, accepted latest answer, or permission for unadmitted fallback.

## Cost reservation and concurrency

Before the first semantic call for one judgment, deterministic planning
calculates its complete possible analysis, integration, challenge, repair, and
permitted re-analysis plan. The task runner reserves the profile's hard per-
judgment budget before starting. It does not knowingly begin work it cannot
afford to complete safely.

The admission profile pins maximum input and output tokens and currency cost
per call; maximum calls, tokens, and currency cost per judgment; maximum
concurrent calls by task and provider; rolling provider and total-pipeline
budgets; and exact behavior at 80%, 90%, and 100% of each budget.

- At 80%, report and reduce non-urgent concurrency.
- At 90%, stop admitting new ordinary judgment work while allowing already
  reserved complete work to finish.
- At 100%, make no new provider call.

Urgent work requires a separately authorized budget change. Urgency never
permits partial coverage or weaker validation. Exact currency and concurrency
values are evidence-derived versioned profile settings and require a new ADR
only if they change the accepted safety or authority boundary.

## Provider data handling and internal evidence

The admitted provider arrangement must prohibit training on task data and use
the shortest provider-side retention compatible with approved operational
need. Provider logging, region, encryption, abuse-monitoring exceptions, and
deletion behavior are pinned and reviewed during admission. A material change
suspends new calls pending impact review.

The Evidence Vault preserves exact admitted requests, structured responses,
provider-attempt metadata, validations, objections, reconciliations, Legal Desk
decisions, evaluation results, and fingerprints for as long as necessary to
reproduce dependent accepted records and releases, subject to the later cross-
cutting retention and deletion policy. Private chain of thought is neither
requested nor stored.

## Runtime monitoring and revalidation

Every production judgment retains 100% deterministic validation, complete
Coverage Ledger accounting, independent challenge, objection reconciliation,
and Legal Desk acceptance. There is no reduced-quality runtime mode.

Monitoring records request, response, schema-repair, retry, and failure rates;
challenge-objection, re-analysis, Quarantine, and blocked rates; token, cost,
latency, and packet distributions; results by court, language, opinion
structure, length, and request kind; provider snapshot, endpoint, tokenizer,
safety-policy, and API drift; and every deterministic or critical semantic
incident.

A small sealed canary subset covering every critical-error family and high-
risk slice runs **weekly**. The complete admitted evaluation suite runs at
least every **90 days**. Immediate complete or impact-scoped revalidation
follows any result-affecting source, parser, structure, task, prompt, schema,
model, setting, validator, renderer, rulebook, provider-policy, or build change,
and any production critical incident.

Canary and full-suite results use already adjudicated sealed evaluation
material. Routine human review is not added to clear production judgments;
humans enter ordinary work only through ADR 0065's exact exceptional triggers.

## Automatic suspension and restart

New provider calls suspend immediately when:

- any critical canary or complete-suite case fails;
- an exact admitted model, endpoint, tokenizer, prompt, schema, validator,
  rulebook, or build fingerprint no longer matches;
- a deterministic invariant, Evidence Range ID, ledger, quotation,
  capability, or no-side-effect check fails;
- provider retention, training, security, or region behavior changes
  materially or becomes unknown;
- an admitted quality, cost, latency, schema-failure, retry, Quarantine, or
  drift stop threshold is crossed; or
- a security or data-handling incident affects the task boundary.

Suspension stops new calls and preserves in-flight and prior evidence. The
system reports the exact affected scope. Restart requires recorded resolution,
impact analysis, every required revalidation result, and a new admission event
for the exact applicable identity. It is never an informal toggle.

## Values assigned by later suite and profile packages

This decision does not select a provider or model. ADR 0068 later separates
the remaining content rather than placing protected truth and candidate values
in one object:

- the candidate-independent Evaluation Suite Package owns the sealed real-
  judgment inventory, Reference Proposition Maps, and executable evaluator;
  and
- the frozen Workflow Admission Profile owns the exact provider, model
  snapshot, prompts, executable schemas, decoding settings, token and output
  ceilings, timeout, backoff, concurrency and currency limits, ordinary
  diagnostic thresholds, provider retention, region and security values, and
  non-critical runtime warning and stop thresholds.

The actual contents are selected from development, calibration, provider,
capacity, and Legal Desk evidence and frozen before sealed candidate scoring.
They cannot weaken the accepted complete-workflow identity, context reserve,
repetition rules, deterministic exactness, zero-critical-error and high-risk
gates, bounded retries, cost reservation, capability restrictions, suspension,
or human-review boundaries.

## Consequences and authorization

ADR 0068 later defines the executable evaluation-suite, protected evidence,
sealed real-judgment selection, evaluator-result, and pre-frozen threshold-
profile package contracts without choosing unsupported values in advance.
Actual schemas, evidence, maps, models, prompts, numerical values, evaluator
code, evaluation runs, and attestations remain uncreated.

This decision authorizes documentation only. It does not authorize executable
implementation, source acquisition, evaluation or production provider calls,
release publication, Pinecone or Azure access, promotion, deployment, commit,
or any remote action.
