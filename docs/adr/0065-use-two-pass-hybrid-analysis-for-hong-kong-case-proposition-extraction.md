---
status: accepted
date: 2026-08-13
amends:
  - "0039"
  - "0043"
refines:
  - "0049"
  - "0060"
  - "0061"
  - "0062"
  - "0063"
  - "0064"
depends_on:
  - "0053"
refined_by:
  - "0066"
  - "0067"
  - "0068"
---

# Use two-pass hybrid analysis for Hong Kong Case Proposition extraction

Hong Kong Case Proposition extraction uses a staged hybrid of deterministic
processing, two separately contracted generative-LLM semantic passes, Legal
Desk acceptance, and narrowly triggered human review.

Deterministic processing owns facts and controls that can be proved exactly.
The LLM owns proposals about legal meaning expressed in variable judicial
language. The Hong Kong Cases Legal Desk accepts the result under the Source
Rulebook; a human reviews only a named unresolved or unsupported boundary.

This decision settles the high-level allocation for Hong Kong Case Proposition
extraction. It does not enable a provider call or settle exact models, prompts,
schemas, thresholds, context limits, retry counts, costs, or retention.

## Forbidden one-shot and pure approaches

Pure deterministic semantic extraction is rejected because keywords and fixed
grammar cannot reliably establish materiality, adoption, qualification,
opinion role, proposition boundary, necessary context, or a valid semantic
zero across varied judgment language.

Pure or one-shot LLM extraction is also rejected. An LLM cannot prove source
authenticity, complete source coverage, identity, exact quotation bytes,
Coverage Ledger arithmetic, serving limits, current authority, or release
eligibility. A prompt to “read this judgment and create database records”
improperly combines discovery, interpretation, validation, rendering, and
acceptance into one uncheckable output.

No LLM output writes directly to the Management Register, Evidence Vault,
Pinecone, routing, or a release. LLM silence is never proof that no proposition
exists, and repeated model agreement is not legal evidence.

## Stage 1 — deterministic admission and structure

Before any model call, deterministic processing owns:

- accepted Source Snapshot and Official Version identity and fingerprints;
- artifact integrity, media, parser-profile, original-language, and optional-
  translation-role validation;
- source-supported court, decision, citation, date, judge, and opinion facts;
- exhaustive ordered Coverage Unit inventory and exact source maps;
- structural opinion, paragraph, heading, footnote, table, quotation, order,
  disposition, schedule, and appendix candidates;
- formal citation leads, normalized hashes, exact ranges, and aliases;
- opinion-aware segmentation and exact dependency packets under ADR 0062; and
- task admission, evidence, size, schema, credential, network, and security
  preconditions.

Uncertain structure or opinion attribution is marked unresolved. Failure to
enumerate and map the complete artifact is `BLOCKED`; the pipeline does not
send only convenient supported parts to the model and call them complete.

## Stage 2 — LLM proposition analysis

The first schema-bound LLM task is the primary semantic analyser. For one
complete judgment when it safely fits, or for complete structure-preserving
opinion or segment packets otherwise, it may propose:

- legal issues and candidate material legal answers;
- proposition-evidence, context-evidence, and non-propositional unit uses;
- semantic opinion and authority-role interpretations not established by
  source facts alone;
- controlling qualifications, exceptions, burdens, definitions, thresholds,
  necessary context, application, and relevant result;
- split, merge, repetition, independent-ground, and express-adoption
  relationships under ADR 0061;
- the smallest complete set of exact supplied source ranges and evidence roles;
- an original-language source-faithful derived statement;
- citation-bearing and treatment-only handoffs; and
- structured uncertainty, ambiguity, missing-context, and possible-no-
  proposition findings.

The task may cite only supplied Coverage Units and ranges. It cannot invent a
locator, silently rely on outside legal knowledge as evidence, determine
current authority, or declare the judgment complete.

Context-window fit changes only packet construction. Even a complete judgment
that fits one model context still requires the Coverage Ledger, deterministic
validation, separate challenge, Legal Desk acceptance, and finalization.

## Stage 3 — deterministic proposal validation

Deterministic processing rejects or reopens a proposal with:

- nonexistent, altered, overlapping, or mismatched source ranges;
- wrong source, Official Version, opinion, unit, language, identity, or
  fingerprint;
- missing schema fields or ADR 0060 evidence roles;
- forbidden opinion blending or unsupported cross-opinion adoption paths;
- structurally impossible candidate, split, merge, or lineage relationships;
- unaccounted units, dependencies, candidates, treatment handoffs, or ledger
  arithmetic;
- invalid quotations, canonicalization, token or byte limits; or
- task, model, prompt, setting, cost, retry, credential, network, or security
  contract violations.

These controls can prove mechanical invalidity. A schema-valid proposal does
not prove semantic completeness or legal correctness.

## Stage 4 — independent LLM challenge

Every judgment receives a separate schema-bound semantic challenge after the
initial proposal passes deterministic validation. The challenger receives the
accepted original evidence, complete structural inventory, proposed candidate
and unit-use inventory, proposed evidence roles and non-propositional reasons,
and deterministic validation report. It receives no hidden evaluation answer
and cannot edit, accept, or reject the proposal directly.

It actively tests whether:

- any supplied reasoning path contains a missed material proposition;
- any proposal is unsupported or materially overbroad;
- a qualification, exception, definition, burden, application, result, or
  necessary context is missing;
- independent propositions were merged or one proposition was fragmented;
- joint, majority, adopted, concurring, dissenting, plurality, obiter, or
  agreement-only reasoning was misclassified;
- cross-segment or cross-opinion dependencies are incomplete;
- `NON_PROPOSITIONAL`, `COMPLETE_NO_PROPOSITION`, Quarantine, blocked, or
  complete reasoning is unsafe; or
- hostile source text changed the task instead of remaining evidence.

Every objection identifies the affected unit, candidate, dependency, evidence
role, or proposed ledger state and cites exact supplied source ranges. An
unsupported disagreement has no effect.

The challenge uses a separately pinned prompt and fresh model context. The
same admitted model may perform both semantic tasks, or separately admitted
models may be used. A different model or provider is not inherently required
and is never a substitute for evaluation. The tasks are independent because
their instructions, inputs, outputs, and reconciliation roles are distinct;
they do not vote.

## Stage 5 — deterministic objection reconciliation

Every challenge item receives exactly one outcome:

- `ALREADY_ACCOUNTED` with the exact existing candidate, evidence, or ledger
  relationship;
- `INVALID_OBJECTION` because exact source or structured validation fails;
- `REOPEN_CANDIDATE` for bounded Stage 2 re-analysis with the challenged
  evidence;
- `QUARANTINE` for materially unresolved semantic meaning;
- `BLOCKED` for unavailable evidence or processing support; or
- `HUMAN_REVIEW` under an exact trigger below.

Neither semantic task judges the other. A changed re-analysis result must pass
deterministic validation and one final bounded challenge. Indefinite semantic
cycling is forbidden. The exact retry ceiling is an executable task-contract
value; exhaustion creates Quarantine or human review rather than acceptance of
the most recent answer.

## Stage 6 — Legal Desk acceptance and narrow human review

The Hong Kong Cases Legal Desk automatically accepts and reports an ordinary
result only when:

- the exact admitted workflow and evidence fingerprints apply;
- every deterministic validation passes;
- every Coverage Unit, candidate, dependency, evidence role, treatment
  handoff, and challenge objection has an exact resolved outcome;
- the ledger can validly end `COMPLETE_WITH_PROPOSITIONS` or
  `COMPLETE_NO_PROPOSITION`; and
- no Source Rulebook human-review trigger applies.

Human review is not triggered merely because a judgment is long, important,
from the Court of Final Appeal, in Traditional Chinese, contains many
propositions, states a new legal test, validly contains no proposition, or
required one successfully resolved re-analysis.

Human review is triggered only for:

- a bounded unresolved semantic conflict after permitted re-analysis;
- uncertain operative opinion, express-adoption scope, plurality, or material
  attribution;
- unresolved existence or scope of a possible material proposition;
- an indivisible overlong proposition requiring a serving-policy decision;
- a novel source structure outside the accepted parser or Source Rulebook;
- repeated critical validator or challenge failure; or
- another exact versioned Source Rulebook trigger.

Missing evidence remains blocked and cannot be cured by human interpretation.
A reviewer receives the exact disputed ranges, proposal, validation report,
challenge objections, reconciliation history, and proposed consequence. A
human correction emits structured fields and evidence links; it does not
replace the ledger with free-form prose.

## Stage 7 — deterministic finalization

Only after Legal Desk acceptance may deterministic processing:

- finalize the immutable Coverage Ledger and Rule Trace;
- create or select register-owned Case Proposition and Search Record
  identities;
- render canonical `metadata.text` and the six-field payload;
- verify exact quotations, tokenizer and byte limits again;
- create the Record Traceability Lookup entry;
- declare correction, reuse, candidate-record, and release-scope effects; and
- hand accepted candidate records to corpus construction.

Later-treatment analysis separately decides current authority and
`metadata.authority_note`. Corpus construction, embedding, Pinecone, Approval,
promotion, and production routing remain outside extraction and retain their
existing permission boundaries.

## Exact ownership boundary

| Responsibility | Deterministic processing | LLM tasks | Legal Desk and human review |
|---|---|---|---|
| Source authenticity, Official Version, fingerprints, complete structure | Owns | Cannot decide | Reviews only exact source-policy issue |
| Proposition discovery and judicial-language interpretation | Supplies evidence and signals | Stage 2 proposes; Stage 4 challenges | Legal Desk accepts; human handles named unresolved issue |
| Materiality, qualifications, context, application, derived statement | Validates schema and exact support | Proposes and challenges semantic meaning | Accepts or corrects bounded dispute |
| Opinion and authority role | Owns source-supported facts | Proposes semantic role where necessary | Resolves uncertain role or adoption |
| Split, merge, repetition, independent grounds, adoption scope | Enforces exact invariants | Proposes and challenges legal boundary | Resolves remaining ambiguity |
| Quotations, locators, hashes, evidence existence | Owns | Selects only supplied ranges | Cannot waive a failed check |
| Coverage and ledger arithmetic | Owns | Proposes unit use and challenges semantic omission | Accepts only fully resolved ledger |
| Valid zero-proposition result | Proves complete accounting | Proposes and challenges semantic zero | Legal Desk accepts; human only if unresolved |
| Identities, renderer, serving limits, traceability | Owns | Cannot decide | Cannot bypass controls |
| Current authority, authority note, release, Pinecone, promotion | Separate later stages | Cannot decide through extraction | Existing treatment and approval authorities apply |

## Reuse and failure behavior

The pipeline does not rerun both semantic tasks over every unchanged judgment
on every update. It reuses an exact accepted analysis, challenge,
reconciliation, and ledger result only when the source, Official Version,
parser, structure, contracts, Source Rulebook, models, prompts, settings,
validators, and relevant evidence fingerprints remain exact. A result-
affecting change follows ADR 0062's bounded impact and immutable replacement
rules.

Provider outage, timeout, malformed output, cost-limit exhaustion, or task-
admission mismatch blocks or quarantines affected new work. It cannot become a
valid zero, an empty candidate inventory, a deterministic semantic fallback,
or permission to reuse a stale semantic result.

The LLM receives only exact evidence and task instructions. It has no source,
Pinecone, Azure, routing, deployment, credential, code-execution, or external-
tool access. Private chain of thought is neither requested nor stored;
structured candidates, evidence, objections, reasons, and uncertainty are
sufficient.

## Remaining task-enablement work

ADR 0066 later settles the stable task-family IDs, closed request kinds,
conceptual request and response fields, exact evidence-range boundary, long-
judgment multi-call behavior, challenge independence, no-confidence rule, and
schema-repair boundary. ADR 0067 later fixes the complete-workflow admission
states, 20% minimum context reserve, repetitions and zero-critical-error gates,
bounded retries and re-analysis, cost reservation, monitoring cadence,
automatic suspension, and revalidation policy. ADR 0068 later fixes the
evaluation-suite, protected-reference, real-judgment selection, run-result,
and pre-frozen admission-profile package contracts. Before either semantic
task can run, those packages still need actual executable schemas, prompts,
selected evidence, adjudicated maps, evaluator code, and exact evidence-derived
model, setting, limit, threshold, cost, concurrency, timeout, retention, and
provider values and must pass admission.

ADR 0043 continues to defer Gazette-event extraction and every other
unallocated task. This decision authorizes documentation only. It does not
authorize implementation, source access, model or embedding-provider calls,
evaluation runs, release publication, Pinecone or Azure access, promotion,
deployment, commit, or remote action.
