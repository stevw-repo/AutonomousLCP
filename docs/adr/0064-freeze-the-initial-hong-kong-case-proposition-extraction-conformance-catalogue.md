---
status: accepted
date: 2026-08-13
refines:
  - "0063"
depends_on:
  - "0057"
  - "0060"
  - "0061"
  - "0062"
refined_by:
  - "0065"
  - "0067"
  - "0068"
---

# Freeze the initial Hong Kong Case Proposition extraction conformance catalogue

The exact initial conceptual Hong Kong Case Proposition extraction catalogue in
`docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md`
is accepted and frozen.

It contains **132 permanent direct case IDs**, **132 matching primary coverage-
cell IDs**, and **31 permanent high-risk pair IDs**. The cases are divided into
these exact checkpoint counts:

| Suite and checkpoint | Cases |
|---|---:|
| Semantic materiality and discovery | 18 |
| Semantic proposition content and evidence | 18 |
| Semantic boundary and opinion attribution | 22 |
| Semantic court, language, length, uncertainty, and safety | 20 |
| Deterministic structure and Coverage Ledger | 20 |
| Deterministic candidate, evidence, renderer, and output | 16 |
| Deterministic correction, package, security, and admission | 18 |
| **Total** | **132** |

The count follows direct coverage of ADRs 0060 through 0063. It is not a target
chosen in advance, a permanent ceiling, or a claim that executable task
admission now has enough real judgments.

## Frozen identity and meaning

Each catalogue row is the direct primary case for one matching primary
coverage cell. Every accepted ID, scenario, required result, group assignment,
pair ID, and pair membership is normative. IDs are permanent and non-answer-
bearing: they identify only suite, checkpoint, and ordinal and never reveal the
court, language, proposition count, expected answer, pair role, success,
failure, or critical-error result.

All 31 pairs have exactly one declared positive and one declared near-miss
member. A case may participate in several pairs only where its one unchanged
frozen scenario directly proves each boundary, and the future coverage matrix
must list every role explicitly.

Catalogues, manifests, and coverage matrices must enumerate exact IDs.
Directory discovery, glob patterns, numeric ranges, broad tags, aggregate
counts, secondary coverage, or a model score cannot substitute for one missing
primary case, coverage cell, or pair member.

## Semantic and deterministic boundaries

The 78 semantic rows are synthetic boundary cases. They cover:

- materiality, familiar applied rules, adopted and unadopted submissions or
  quotations, true no-proposition and treatment-only results;
- proposition meaning, qualifications, context, application, result, evidence,
  exact quotations, and supported equivalent derived wording;
- cumulative tests, independent grounds, repetition, legal branches, joint and
  separate opinions, concurrence, dissent, plurality, obiter, and express
  adoption;
- every accepted Hong Kong court family, original English, original
  Traditional Chinese, genuinely mixed-language reasoning, and auxiliary
  translation behavior;
- short and long segmented judgments, cross-segment and cross-opinion
  dependencies, overlong propositions, Quarantine, blocked structures,
  corrections, and hostile source text.

The 54 deterministic rows cover exact:

- opinion, Coverage Unit, segment, dependency, resolution, primary-use,
  evidence-role, candidate, and final-ledger arithmetic;
- evidence existence and mapping, quotation bytes, renderer output, six-field
  payload, token and byte limits, traceability, and zero, one, or many records;
- correction and split-or-merge lineage, impact behavior, catalogue and package
  completeness, answer non-leakage, sealed-artifact integrity,
  reproducibility, forbidden side effects, and full-workflow admission identity.

Every future executable deterministic artifact role remains explicitly
`EXACT`, `NONE`, or `NOT_APPLICABLE`. Missing output cannot pass as an empty or
zero result.

## Sealed real-judgment extension remains mandatory

Synthetic semantic cases do not admit an extraction workflow. Before any
extraction method is enabled, the semantic catalogue and coverage matrix must
add sealed real-judgment cases across the court, language, opinion, length,
materiality, evidence, boundary, uncertainty, and safety dimensions in ADR
0063. Each real case requires an independently adjudicated hidden Reference
Proposition Map, exact artifact fingerprints, and the applicable critical-error
and coverage labels.

Development cases and the sealed admission set remain separate. Real-judgment
selection cannot merely repeat easy synthetic shapes or cases used to tune the
workflow. The future real cases extend this catalogue; they do not replace,
renumber, or rewrite the frozen synthetic cases.

## Immutable expansion and correction

A later new requirement adds a new case, coverage cell, or pair with a new
permanent ID. It never silently changes an existing scenario or reuses an ID.
Correcting an erroneous frozen row requires a new versioned catalogue, an
explicit supersession or correction mapping, an impact declaration, preserved
prior packages and results, and re-evaluation of every affected workflow.

The seven group counts and 132-case total therefore describe this exact initial
catalogue version. They do not constrain future evidence-backed expansion.

## Consequences

ADR 0065 later settles the high-level Hong Kong Case Proposition
LLM-versus-deterministic extraction allocation, ADR 0066 fixes the semantic
task contracts, and ADR 0067 fixes the complete-workflow admission and
monitoring policy. ADR 0068 later fixes the evaluation-suite, protected
evidence, sealed real-judgment selection, evaluator-result, and admission-
profile package contracts. Exact executable schemas, fixture bytes, selected
real judgments and maps, ordinary numerical thresholds, evaluator
implementation, model, prompt, settings, costs, retention values, and run
results remain later task-enablement artifacts.

This decision authorizes documentation only. It does not authorize
implementation, source acquisition, model or embedding calls, evaluation runs,
release publication, Pinecone or Azure access, promotion, deployment, commit,
or any remote action.
