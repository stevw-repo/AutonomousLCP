---
status: accepted
date: 2026-08-13
amends:
  - 0056
  - 0057
  - 0058
refines:
  - 0049
  - 0050
  - 0052
  - 0053
  - 0055
depends_on:
  - 0014
  - 0018
---

# Freeze the initial Hong Kong treatment conformance catalogue

The audited table in
[`HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md`](../design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md)
is the accepted initial Hong Kong later-treatment coverage universe. It freezes
**155 permanent case IDs, 155 matching primary coverage-cell IDs, and 21
high-risk positive and near-miss pair IDs** with their exact normative
scenarios and required results.

The count follows the accepted branches. It is not a target, quota, sample, or
claim that future requirements may not add cases.

## Frozen checkpoint counts

| Primary checkpoint | Direct cases and primary cells |
|---|---:|
| Semantic whole-judgment discovery | 13 |
| Semantic candidate analysis | 40 |
| Deterministic validation and package safety | 32 |
| Deterministic Legal Desk decision and routing | 22 |
| Deterministic authority-note rendering | 14 |
| Deterministic record, embedding, lineage, and selection | 12 |
| Deterministic release, update, and promotion boundary | 22 |
| **Total** | **155** |

The semantic total is 53 and the deterministic total is 102. Each case is the
direct primary case for one matching coverage cell. Every declared pair has
exactly one positive and one near-miss member.

## Frozen meaning

The accepted table directly covers:

- complete and segmented whole-judgment discovery, citation leads, unusual
  treatment language, no-proposition judgments, correction comparisons, and
  English, Traditional Chinese, and mixed-language evidence;
- every accepted treatment class, permitted expression mode, proposition
  scope, materiality boundary, opinion and court-authority boundary, and
  separately recorded appellate disposition;
- ambiguous and unbounded mapping, wrong identity, fabricated evidence,
  incomplete context, impossible hierarchy, hostile instruction-like source
  text, missing originating evidence, and HKLII-only leads;
- one exact treated proposition per resolved relationship, optional treating-
  proposition linkage, unresolved Treatment Leads, one-edge/two-view
  projection, and immutable correction-driven reverse impact;
- ordinary automatic Legal Desk acceptance, uncertainty review, the narrow
  exceptional-change route, and a separate operational anomaly pause;
- exact authority-note value, English-only Hong Kong note behavior, ordering,
  consolidation, budget overflow, forbidden strength scoring, and warning
  precedence;
- immutable record reuse, forward successors, exact former-record reselection,
  embedding reuse or generation, full and partial retirement, legacy identity
  isolation, and uncertainty;
- no-predecessor baseline behavior, old-authority retention, court-year scope
  continuity, supported no change, accounting-only and serving change, blocked
  and quarantined work, cutoff and predecessor rules, carry-forward,
  withholding, no-new-target, disappearance, promotion eligibility, and no
  live mutation; and
- strict non-leaking package admission, declared files, hashes, external
  artifacts, explicit zero output, catalogue and coverage completeness,
  reproducibility, and forbidden side effects.

## Immutability and expansion

These IDs and their normative meanings are never reassigned or silently
rewritten. A correction to a frozen scenario, input, expected answer,
assertion, coverage binding, or pair relationship requires:

1. a new case, coverage-cell, pair, catalogue, or contract version as
   applicable;
2. an impact declaration identifying affected rules, evaluations, fixtures,
   decisions, records, releases, and task admission;
3. preservation of the former package, fingerprint, and result; and
4. revalidation of every affected contract and build.

A new legal or technical requirement may add cases and cells. It does not
renumber existing IDs or merge unrelated cases merely to preserve 155.

## What this decision does not freeze

This decision does not select or authorize:

- machine-readable JSON Schemas, manifests, fixture bytes, artifact encoding,
  rule IDs, reason codes, or validators;
- the sealed representative real-Hong-Kong-judgment evaluation set;
- a model, prompt, settings, context limits, thresholds, retry policy, cost
  limits, retention, sampling, or revalidation schedule;
- the exact runtime contract for Case Proposition extraction, whose high-level
  allocation is later settled by ADR 0065;
- the Hong Kong Cases Source Register, exact court-authority and finality
  matrix, historical source boundary, or complete Source Rulebook values;
- Ask.Legal graph lookup, Query Contract implementation, or citator-style
  enumeration; or
- implementation, source acquisition, provider use, release publication,
  Pinecone or Azure access, promotion, deployment, commit, or publication.

The 53 accepted synthetic semantic cases are necessary but insufficient for
model admission. The future sealed real-judgment cases extend the semantic
catalogue and coverage matrix without replacing these cases.

## Consequences and authorization

Future executable packages and validators must implement this exact accepted
table. A Rulebook Conformance Attestation cannot pass by omitting, combining,
weakening, dynamically discovering, or marking a required case inapplicable.

This decision authorizes documentation only. It freezes design requirements;
it does not authorize implementation or any local production or remote action.
