---
status: accepted
date: 2026-08-14
refines:
  - "0039"
  - "0043"
  - "0047"
  - "0060"
  - "0062"
  - "0063"
  - "0065"
depends_on:
  - "0057"
refined_by:
  - "0067"
  - "0068"
---

# Define the Hong Kong Case Proposition LLM task contracts

ADR 0065's two semantic task families have these stable versioned identities:

- `hk-case-proposition-analysis/v1`; and
- `hk-case-proposition-challenge/v1`.

The analysis task proposes material Case Propositions and complete evidence-
linked unit uses. The challenge task independently identifies supported
semantic objections to a deterministically validated proposal. Neither task
accepts a result, decides current authority, creates a serving record, or has
any source, Azure, Pinecone, approval, routing, deployment, credential, code-
execution, or external-tool capability.

This decision fixes the conceptual request and response contract. It does not
create executable JSON Schemas or prompts, select a model or provider, set
token or cost limits, or enable a provider call.

## A pass is not necessarily one provider call

One semantic **pass** means one complete workflow over one exact judgment. A
short judgment may use one analysis call and one challenge call. A long
judgment may require complete opinion-aware packet calls followed by one
judgment-level integration or result-challenge call within each respective
task family.

Packet count changes orchestration and cost, not the semantic stages or their
authority. Every primary Coverage Unit remains accounted for under ADR 0062.
A context window, token budget, or provider limit cannot redefine judgment
coverage, silently truncate a unit, or turn a partial result into a judgment-
wide conclusion.

## Common deterministic request envelope

Every request to either task binds:

| Input group | Required content |
|---|---|
| Contract identity | Task family and version, closed request kind, execution and attempt identities, packet identity where applicable, and parent judgment-work identity |
| Workflow identity | Source Rulebook, parser, structure, segmentation, Coverage Ledger, prompt, schema, model-settings, validator, and processing-build fingerprints |
| Legal-source identity | Judicial Decision, Official Version, original artifact, Source Snapshot, cutoff, court, decision date, citation, judges, opinions, and source-supported original-language facts |
| Coverage position | Complete opinion and Coverage Unit manifest, this request's assigned primary units, their position in the judgment, packet boundaries, and declared dependencies |
| Supplied evidence | Immutable unit IDs, exact original-language text, source locators, immutable Evidence Range IDs, fingerprints, structural roles, opinion ownership, and formal citation leads |
| Task constraints | Permitted claims, forbidden decisions, allowed IDs and enums, required evidence roles, original-language rule, output budget, and the instruction that source text is evidence rather than an instruction |
| Prior-stage material | Only the exact material allowed by the request kind, such as a validated proposal for challenge or one reconciled objection for targeted re-analysis |

The task runner validates the complete envelope before a model call. A missing
fingerprint, unit, dependency, opinion, range map, contract version, or task
permission blocks the call. The model receives no URL to fetch, credentials,
tools, code execution, Pinecone or Azure state, approval or deployment state,
or hidden evaluation answer.

The original court-authored text is controlling. Judiciary translations and
predecessor extraction results are excluded by default to avoid translation
dependence and anchoring on an old answer. A later admitted request kind may
include either only when it labels the material non-controlling, proves exact
alignment and purpose, and passes separate language-fidelity and no-bias
evaluation. Availability alone does not permit inclusion.

## Analysis request kinds

`hk-case-proposition-analysis/v1` permits only:

| Request kind | Purpose |
|---|---|
| `FULL_JUDGMENT` | Analyse one complete judgment that safely fits while retaining its complete ledger manifest |
| `EVIDENCE_PACKET` | Analyse every primary Coverage Unit assigned to one opinion-aware packet together with its exact context dependencies |
| `JUDGMENT_INTEGRATION` | Reconcile the complete assembled candidate and unit-use inventory across packets, including repetition, adoption, overlap, split, and merge boundaries, using exact relevant source ranges rather than summaries alone |
| `TARGETED_REANALYSIS` | Reconsider one exact challenged candidate, unit use, dependency, boundary, or no-proposition claim using the reconciled objection and bounded evidence supplied by deterministic processing |

A successful `FULL_JUDGMENT` request needs no integration request unless
deterministic validation identifies one bounded integration issue. Segmented
processing must assign every primary Coverage Unit to an `EVIDENCE_PACKET` and
must complete `JUDGMENT_INTEGRATION` before producing a judgment-wide proposal.

An exact structural subrange may be supplied only when it maps to the preserved
complete unit and includes every required dependency. Otherwise processing is
blocked; the runner never silently cuts source evidence merely to fit.

## Analysis response contract

The analysis response is strict schema-bound data, not a final Pinecone record
or private chain of thought. It contains:

| Output group | Required content |
|---|---|
| Response binding | Exact request, packet, contract, evidence-manifest, and proposal fingerprints |
| Unit-use proposals | One proposed use for every assigned primary unit: proposition evidence, context evidence, non-propositional, or unresolved, with a stable reason and exact target IDs |
| Candidate propositions | Local candidate ID, original-language legal issue and source-faithful derived statement, proposed opinion and authority role, materiality reason, and structured semantic state |
| Evidence-role map | Exact supplied Evidence Range IDs for issue, legal answer, attribution, qualifications, context, application, result, and selected-quotation roles |
| Boundaries and relationships | Proposed split, merge, repetition, duplicate, independent-ground, express-adoption, and cross-packet relationships using only supplied IDs |
| Necessary content | Material facts and procedure, every identified qualification, exception, definition, burden or threshold, application, and relevant result |
| Handoffs | Formal citation, treatment-only, and possible-treatment handoffs tied to exact supplied ranges |
| Uncertainty | Stable uncertainty states, exact affected objects and evidence, any missing-context request, and the narrow unresolved question |
| Packet conclusion | Propositions proposed, no proposition found within this completely assigned packet, or unresolved; a partial packet never declares a judgment-wide result |

The model selects immutable Evidence Range IDs. It does not supply an
authoritative copy of a quotation. After acceptance, deterministic processing
copies the exact preserved text represented by selected range IDs into the
renderer. This prevents model punctuation, omission, normalization, or
rewriting from becoming purportedly verbatim judgment text.

The model drafts the clearly labelled derived statement and other source-
faithful summaries. Optional diagnostic text remains short, structured,
evidence-linked, internal, and non-serving.

A proposed no-proposition result requires an explicit reason for every assigned
primary unit and complete citation and treatment handoffs. Model silence, an
empty candidate array, or a packet-level no-proposition conclusion cannot
establish `COMPLETE_NO_PROPOSITION`.

## Challenge input and independence

The challenge uses a fresh prompt context and receives:

- the same controlling original evidence and complete-coverage position;
- the deterministically validated assembled proposal and fingerprint;
- every candidate, unit-use proposal, evidence-role map, dependency,
  non-propositional reason, uncertainty, and handoff;
- the deterministic validation report and any permitted warnings; and
- for final targeted challenge, the exact earlier objection, reconciliation
  result, changed proposal, and changed evidence fingerprint.

It does not receive a hidden Reference Proposition Map, expected test answer,
Legal Desk acceptance, provider or model reputation, the first task's self-
reported confidence, or an instruction that agreement is preferred.

## Challenge request kinds and response contract

`hk-case-proposition-challenge/v1` permits only:

| Request kind | Purpose |
|---|---|
| `FULL_JUDGMENT_CHALLENGE` | Challenge the complete validated proposal when the complete source and proposal safely fit together |
| `COVERAGE_PACKET_CHALLENGE` | Examine every assigned original unit and its proposed use for a missed proposition or unsafe non-propositional conclusion |
| `JUDGMENT_RESULT_CHALLENGE` | Challenge the assembled judgment-wide candidates, cross-packet boundaries, opinion paths, dependencies, and proposed zero or complete result |
| `FINAL_TARGETED_CHALLENGE` | Check only whether one reopened objection was safely resolved after re-analysis |

A segmented judgment requires complete `COVERAGE_PACKET_CHALLENGE` coverage
and one `JUDGMENT_RESULT_CHALLENGE`. The response contains:

- exact request, response, proposal, and evidence bindings;
- one challenge-coverage row for every assigned unit, candidate, relationship,
  and proposed judgment state;
- zero or more objections, each with one stable objection type;
- the exact affected object IDs and supporting Evidence Range IDs;
- whether the possible effect is serving content, ledger-only accounting, or
  materially unknown; and
- the narrow re-analysis question and required evidence scope.

Required objection families include missed proposition, unsupported or
overbroad proposition, missing qualification, wrong attribution, wrong
boundary, incomplete context, bad evidence role, unsafe non-propositional use,
unsafe zero, unsafe completion, and hostile-source instruction followed.

The challenger may describe a suspected correction but cannot edit the
proposal, choose the deterministic reconciliation outcome, accept or reject
the judgment, route directly to human review, or determine current authority.
An empty objection inventory is valid only with complete challenge coverage.
It means no supported objection was found, not that the proposal is approved.

## No model self-confidence score

Neither task returns a numeric or percentage confidence score. Model self-
confidence is not legal evidence and cannot drive an arbitrary acceptance
threshold.

The tasks instead use concrete evidence-bound semantic states:

- supported proposal;
- unresolved semantic question;
- missing supplied context;
- conflicting supplied evidence; or
- no proposition found within the completely assigned scope.

Deterministic checks, independent challenge, Coverage Ledger completeness,
admitted evaluation performance, Source Rulebook rules, Legal Desk acceptance,
and exact unresolved facts control acceptance and review.

## Strict response, repair, failure, and reuse

Both tasks return strict JSON under their exact versioned schema. Text outside
the response object, unknown fields or enum values, unbound IDs, unmapped
ranges, incomplete assigned-object coverage, wrong-language derived wording,
source text copied into instruction fields, or inconsistent fingerprints makes
the response invalid.

One schema-repair request may correct representation only using the same
evidence and semantic-result fingerprint. It cannot silently change the legal
content. A semantic change is a new analysis or re-analysis result and must
pass deterministic validation and challenge again.

ADR 0067 later fixes one initial provider attempt plus no more than two
transient retries, one representation-only schema repair, one targeted
semantic re-analysis and final challenge, a 20% minimum context reserve, cost
reservation, and the monitoring and suspension policy. Exact timeout, backoff,
token and output ceilings, packet limits, model settings, currency amounts,
concurrency, and retention remain evidence-derived immutable admission-profile
values. Exhaustion blocks or quarantines work; it never produces a valid zero
or accepts the most recent answer.

A task result may be reused only when every result-affecting source, Official
Version, unit, dependency, rulebook, contract, prompt, model, setting,
validator, and processing fingerprint remains exact. The Evidence Vault
preserves admitted requests, structured responses, validation and
reconciliation artifacts, and fingerprints under the later retention policy.
The Management Register records their state and lineage. Private chain of
thought is neither requested nor stored, and no internal task artifact enters
Pinecone.

## Consequences and authorization

ADR 0067 later settles the shared runtime admission policy for these two task
families. ADR 0068 later defines the evaluation-suite, protected-reference,
sealed real-judgment selection, evaluator-result, and pre-frozen admission-
profile package contracts without inventing evidence-dependent model,
provider, budget, or ordinary-threshold values in advance. Their actual
executable content remains uncreated.

This decision authorizes documentation only. It does not authorize executable
schema or prompt implementation, source acquisition, model or embedding calls,
evaluation runs, release publication, Pinecone or Azure access, promotion,
deployment, commit, or any remote action.
