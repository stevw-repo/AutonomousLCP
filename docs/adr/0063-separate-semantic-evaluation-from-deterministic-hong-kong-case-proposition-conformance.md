---
status: accepted
date: 2026-08-13
refines:
  - 0043
  - 0049
  - 0060
  - 0061
  - 0062
depends_on:
  - 0056
  - 0057
refined_by:
  - "0065"
  - "0067"
  - "0068"
---

# Separate semantic evaluation from deterministic Hong Kong Case Proposition conformance

Hong Kong Case Proposition extraction has two different correctness questions:

1. did the extraction method understand the judgment and produce the right
   propositions, boundaries, qualifications, attribution, and evidence; and
2. did deterministic processing completely account for the source, validate
   every link and outcome, render exact permitted records, and fail safely?

These questions use two separate linked suites. One blended score is forbidden
because strong mechanical accounting can package a legally wrong result and
strong semantic analysis can be corrupted by broken ledger, renderer, or
identity processing.

This architecture originally defined the required proof without deciding
whether semantic extraction used deterministic code, a generative LLM, the
Legal Desk, a human, or a defined combination. ADR 0065 later settles the
high-level two-pass staged hybrid allocation without changing these admission
requirements.

## Admit the complete extraction workflow

Admission applies to one exact fingerprinted workflow combination, not to a
model name or parser in isolation. The admitted identity binds every
result-affecting component, including:

- original-evidence and parser profiles;
- structural normalization, opinion attribution, Coverage Unit, segmentation,
  and dependency contracts;
- Case Proposition qualification, boundary, evidence, and Coverage Ledger
  contracts;
- task contract and any applicable model, prompt, settings, and tool boundary;
- deterministic validators, renderer, tokenizer, and payload limits;
- Source Rulebook Package and applicable Legal Desk decision contract;
- processing build and dependency lock; and
- semantic catalogue, deterministic catalogue, coverage matrix, thresholds,
  repetition rule, evaluator, and evaluation-result fingerprints.

A result-affecting change creates a new candidate workflow and impact
declaration. Success by one model version, prompt, parser, or build does not
authorize a different combination.

## Adjudicated Reference Proposition Map

Every semantic evaluation judgment has one hidden versioned **Reference
Proposition Map** prepared under the Hong Kong Cases Legal Desk. It is not one
preferred summary string. It binds the exact accepted original judgment and
opinion inventory and records:

- each required material proposition's issue, legal answer, controlling
  qualifications, opinion and authority role, necessary context, application,
  result, and exact original-language source ranges;
- unsupported interpretations, omitted qualifications, false attribution, and
  other meanings that must not pass;
- permitted equivalent derived wording and any genuinely acceptable alternate
  split or merge representation that preserves the same complete legal
  meaning;
- the exact supported zero-proposition, Quarantine, or blocked boundary when
  applicable;
- required citation-bearing and treatment-only handoffs; and
- hidden coverage-cell, pair-role, and critical-error annotations.

High-risk or genuinely contestable maps require independent second review and
recorded resolution before entering a sealed admission set. This is offline
benchmark adjudication rather than routine human review of production
judgments.

The map does not require different extraction methods to emit identical
intermediate candidate inventories. A method may explore extra candidates, but
every candidate it emits must be accounted for under ADR 0062. The final safe
legal content, evidence, and permitted output boundaries must agree with the
reference.

## Semantic extraction evaluation

The semantic suite receives only the exact preserved evidence and permitted
task inputs available to the proposed workflow. It evaluates distinct
dimensions rather than one prose-similarity score:

| Dimension | Required proof |
|---|---|
| Material-proposition recall | Every required legal answer is found |
| Supported precision | No unsupported proposition is accepted |
| Qualification completeness | Every material limit, exception, threshold, definition, and burden is preserved |
| Issue-and-answer integrity | Each proposition answers the issue actually resolved by that reasoning path |
| Opinion attribution | Joint, majority, adopted, concurring, dissenting, plurality, obiter, and other roles are exact |
| Boundary correctness | Independent propositions split and inseparable rules, limits, and applications remain together |
| Evidence sufficiency | Exact ranges prove the answer, attribution, qualifications, application, and result |
| Context and result | Minimum necessary facts, procedure, application, and result are present without distortion |
| Language fidelity | Original English, Traditional Chinese, or genuinely mixed-language reasoning remains accurate |
| Uncertainty calibration | Valid zero, propositions not selected, Quarantine, blocked work, and invalid processing remain distinct |

Derived prose is not compared byte for byte. Scoring uses the required and
forbidden meanings, exact evidence, and enumerated acceptable structural
alternatives in the Reference Proposition Map. Automated semantic scoring may
assist, but neither the evaluated method nor an uncontrolled evaluator LLM may
define its own answer key. The adjudicated map and exact deterministic evidence
checks remain controlling.

## Deterministic contract conformance

The deterministic suite starts from frozen inputs and expected artifacts. It
requires exact reproducible assertions for:

- Source Snapshot, Official Version, opinion, Coverage Unit, dependency,
  contract, and output fingerprints;
- exhaustive ordered Coverage Ledger arithmetic and final ledger result;
- exactly one outcome for every candidate actually emitted;
- existence and exact preserved-source mapping of every evidence range;
- byte-exact quotations with no invention, silent editing, or locator drift;
- ADRs 0060 and 0061's evidence, attribution, split, merge, adoption, and
  overlong-record invariants;
- canonical `metadata.text`, the six-field serving payload, pinned tokenizer
  and byte limits, and separation of `metadata.authority_note`;
- original-language, zero-proposition, Quarantine, blocked, and invalid
  behavior;
- immutable identities, correction impact, traceability, and expected zero,
  one, or many Search Records; and
- absence of source, model, embedding, Azure, Pinecone, routing, credential,
  production-store, network, or undeclared-file side effects.

Every expected artifact role is explicitly `EXACT`, `NONE`, or
`NOT_APPLICABLE`. Missing output cannot pass as empty output. Two isolated
clean deterministic runs must produce identical canonical artifacts and
fingerprints.

## Coverage-driven catalogues

The exact number of cases follows the required branches and is not selected in
advance. Direct primary coverage must include at least:

- every in-scope Hong Kong court and separately accounted historical source;
- original English, original Traditional Chinese, and genuinely mixed-language
  reasoning;
- zero, one, and many propositions;
- joint, lead, adopted, concurring, dissenting, plurality, agreement-only, and
  court opinions;
- ratio, material obiter, familiar applied rules, new rules, procedure,
  remedies, jurisdiction, and treatment-only reasoning;
- cumulative tests, qualifications, exceptions, definitions, independent
  alternative grounds, repetition, applications, and cross-opinion adoption;
- contiguous and non-contiguous support, footnotes, tables, quotations,
  submissions, defined terms, cross-references, and dispositions;
- short and long segmented judgments, cross-segment dependencies, indivisible
  overlong propositions, and unsupported source structures;
- corrected judgments and result-affecting source, parser, contract, or
  processing changes; and
- hostile instruction-like text, malformed input, false locators, hidden
  truncation, and other model or pipeline safety failures.

High-risk distinctions require linked positive and near-miss pairs. Required
pair families include adopted and unadopted quotations, operative majority and
dissent, express adoption and shared outcome, cumulative tests and independent
grounds, repeated applications and distinct legal branches, genuine no-
proposition judgments and missed propositions, controlling qualifications and
optional repetition, and treatment-only reasoning and a proposition of the
later judgment.

Small synthetic boundary packages may live in Git. Complete real judgments,
adjudicated maps, protected model outputs, and operational results remain in
registered sealed evaluation storage. Permanent non-answer-bearing IDs, strict
manifests, exact hashes, frozen catalogues, a frozen coverage matrix, and hidden
expected results prevent answer leakage. Development cases and the sealed
admission set remain separate. Later production failures create new versioned
regression cases rather than rewriting accepted answers.

## Admission gates

No aggregate score can compensate for a failed critical or high-risk boundary.
One workflow is admitted only when:

1. every deterministic conformance case passes exactly;
2. no designated critical error occurs in the frozen semantic admission set;
3. every separately pinned semantic dimension meets its minimum threshold;
4. every required high-risk slice meets its own threshold, so success on
   English, short, or single-opinion judgments cannot hide weak Chinese,
   segmented, multi-opinion, zero-result, or Quarantine behavior;
5. repeated semantic runs satisfy the pinned stability rule without averaging
   away a critical failure; and
6. every workflow, package, contract, build, model, prompt, setting, evaluator,
   and result fingerprint matches the proposed admitted combination.

Designated critical errors include:

- a fabricated or unsupported proposition;
- fabricated, altered, nonexistent, or materially mismapped judgment support;
- false `COMPLETE_NO_PROPOSITION` when a material proposition exists;
- omission of a qualification that materially broadens the proposition;
- presenting dissent, concurrence, plurality, or obiter as operative majority
  reasoning;
- merging incompatible opinions or manufacturing a common majority path;
- treating required uncertainty, missing structure, or incomplete coverage as
  a confident complete result; and
- allowing hostile source content to alter the task, contract, evidence
  boundary, or permitted output behavior.

Zero tolerance applies to those errors in the finite frozen admission set. It
does not claim that a probabilistic method can never fail on unseen production
material. ADR 0067 later fixes three ordinary and five high-risk semantic
repetitions, exact deterministic repetition, separate slice gates, and the
runtime monitoring and revalidation policy. ADR 0068 later assigns the sealed
real-judgment inventory and Reference Proposition Maps to the candidate-
independent Evaluation Suite Package and the ordinary diagnostic thresholds
and other candidate values to the pre-frozen Workflow Admission Profile.
Neither may be relaxed merely to admit a preferred method.

## Runtime and retrieval boundaries

Admission does not replace runtime protection. Every production judgment still
requires ADR 0062's Coverage Ledger, deterministic validation, honest
Quarantine or blocked outcomes, correction and drift monitoring, risk-based
sampling, and regression expansion. Clear ordinary results may proceed under
an admitted workflow; material ambiguity follows the accepted uncertainty and
review boundary.

Extraction correctness remains separate from retrieval quality. English and
Chinese query retrieval, Pinecone crowding, embedding, ranking, and downstream-
answer evaluation are a later independent gate. A legally correct proposition
may retrieve badly, and an incorrect proposition may retrieve well.

## Consequences

ADR 0064 later freezes the exact conceptual Case Proposition extraction
coverage matrix and catalogue, ADR 0065 settles the high-level extraction
allocation, ADR 0066 fixes the semantic task contracts, and ADR 0067 fixes the
complete-workflow admission and monitoring policy. ADR 0068 later fixes the
evaluation-suite, protected evidence, real-judgment selection, evaluator-result,
and pre-frozen admission-profile package contracts. Exact schemas, fixture
bytes, selected real judgments and maps, ordinary numerical thresholds,
evaluator implementation, and evidence-derived profile values remain later
executable artifacts.

This decision authorizes documentation only. It does not authorize
implementation, source acquisition, model or embedding calls, evaluation runs,
release publication, Pinecone or Azure access, promotion, deployment, commit,
or any remote action.
