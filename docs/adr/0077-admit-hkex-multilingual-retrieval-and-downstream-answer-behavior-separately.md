---
status: accepted
date: 2026-08-14
refines:
  - "0054"
  - "0072"
  - "0075"
depends_on:
  - "0008"
  - "0050"
  - "0073"
---

# Admit HKEX multilingual retrieval and downstream answer behavior separately

## 2026-08-25 V1 amendment

For the approved live V1, the requirement below for a complete Ask.Legal
query-path evaluation and a three-layer Ask.Legal admission package is
superseded. Ask.Legal query routing and administration are excluded from V1.
V1 instead uses the compact fixed golden evaluation defined by the live
specification, including English, Traditional Chinese, bilingual, and small
cross-language retrieval checks. The exact Ask.Legal integration and the
broader evaluation architecture in this ADR remain post-V1 work.

V1 activation is the Management Register transition to the verified Serving
State for the approved complete Pinecone index; it is not an Ask.Legal routing
change. See the
[Hong Kong Live V1 Execution Specification](../design/HK_V1_LIVE_EXECUTION_SPEC.md).

## Decision

English-only Hong Kong Regulatory Materials may serve only after one immutable
admission package proves three linked but non-substitutable evaluation layers:

1. **multilingual retrieval evaluation** tests queries against the exact frozen
   English Regulatory Search Record corpus and scores ranked record IDs;
2. **context-bound downstream-answer evaluation** supplies frozen adjudicated
   six-field record sets and tests whether the answer model uses them safely;
   and
3. **complete query-path evaluation** tests the pinned Ask.Legal query,
   retrieval, metadata-delivery, and answer workflow together.

The first layer diagnoses retrieval independently of answer generation. The
second diagnoses answer behavior independently of ranking. The third proves
their integration. An aggregate result from one layer cannot compensate for a
failure in another.

This architecture does not add Chinese source text, a Chinese metadata field,
Chinese-only record, parallel vector family, query-time legal translation, or
new runtime lookup. A multilingual embedding or other candidate retrieval
workflow must make Traditional-Chinese and mixed-language queries retrieve the
same controlling English records through the existing six-field serving
boundary.

## Immutable admission package

One Regulatory Retrieval and Answer Admission Package binds at least:

- exact evaluation-suite, relevance-judgment, query, corpus, renderer,
  authority-note, Search Record, and evidence fingerprints;
- the exact embedding model, version, dimensions, metric, query and document
  preprocessing, tokenizer, vector normalization, and cache contract;
- exact Pinecone-compatible index configuration, namespace behavior if any,
  top-k and context-selection rules, filters, tie handling, deduplication, and
  crowding behavior;
- the exact Ask.Legal Query Contract and application build used by every active
  path;
- the exact downstream answer model, system and task prompts, settings,
  context limits, metadata serialization and ordering, and repetition policy;
- pre-frozen slice gates, critical-error rules, evaluator identities, result
  artifacts, costs, and complete package fingerprint; and
- predecessor, impact declaration, monitoring, suspension, revocation, and
  revalidation rules.

Every admission applies only to that exact profile. A changed model, vector
dimension, metric, preprocessing rule, renderer, query contract, top-k,
context selector, answer prompt, corpus family composition, or other bound
input requires impact analysis and affected re-evaluation.

The exact current Ask.Legal Query Contract and application build must be
verified from their owning system before an executable profile is frozen. This
greenfield repository does not infer those bytes from legacy assumptions.

## Query and relevance universe

The frozen evaluation universe contains independently drafted, adjudicated
queries in:

- English;
- Traditional Chinese; and
- genuinely mixed English and Traditional Chinese.

Every language family directly covers:

- natural-language descriptions of English rule concepts;
- exact and approximate rule-number and cross-reference queries;
- Main Board versus GEM disambiguation;
- definitions and abbreviations;
- dates, percentages, monetary amounts, thresholds, and calculations;
- ordinary rules, notes, appendices, Practice Notes, Regulatory Forms, Fees
  Rules, and tables;
- current, future, conditional, and transitional distinctions;
- queries requiring exact applicability context or an authority note; and
- crowding against Hong Kong Legislation, Cases, Principles, and nearby
  excluded guidance concepts.

Relevance judgments bind exact Search Record IDs and graded roles such as
required primary, additionally relevant, contextually useful, and hard
negative. Hard negatives include wrong-board rules, similar but inapplicable
branches, future or historical wording, excluded guidance, detached table or
fee fragments, and records from another material family.

Queries, relevance judgments, source answers, and hard negatives are hidden
from candidate tuning and ordinary execution. Query IDs and titles do not
encode expected results.

## Retrieval evaluation

Retrieval evaluation receives only the ordinary query text and exact candidate
workflow. It records the complete ranked IDs and scores before grading. It
tests at least:

- recall of every required primary record within the exact Ask.Legal context
  budget;
- rank quality and completeness for one-record and multi-record answers;
- board, applicability branch, component class, and material-family precision;
- duplicate and crowding behavior;
- stability for rule numbers, abbreviations, dates, percentages, and monetary
  expressions; and
- English, Traditional-Chinese, mixed-language, and cross-family slices
  separately.

Recall at the real consumable context boundary is the primary completeness
measure. Graded ranking measures such as nDCG and reciprocal rank may diagnose
ordering, but a high average cannot hide a failed mandatory slice or missing
required record. Exact metric names and values are frozen from adjudicated
baseline evidence before sealed candidate results are examined; they are not
lowered to admit a preferred workflow.

No retrieval score proves that a Search Record is legally correct. ADR 0075's
complete conformance result remains an independent prerequisite.

## Context-bound downstream-answer evaluation

This layer bypasses retrieval and supplies exact frozen six-field record sets
that represent correct, incomplete, crowded, conflicting, and hard-negative
contexts. The downstream model receives no Management Register, source package,
coverage proof, Record Traceability Lookup, hidden classification, or extra
metadata.

Direct evaluation proves that it:

- uses `metadata.text` as the controlling English rule source;
- receives and follows `metadata.authority_note`, including exact `"None"` and
  every approved Regulatory warning family;
- distinguishes Main Board and GEM and states material applicability limits;
- does not present future, superseded, withdrawn, unknown, or excluded material
  as current merely because it appears in an adversarial context;
- may explain the controlling English rule in Chinese while preserving legal
  terms, dates, numbers, currencies, conditions, and uncertainty;
- never claims its Chinese explanation is HKEX's official translation;
- never fabricates or presents a Chinese quotation as source text;
- does not treat optional Chinese evidence as controlling or imply that an
  English-only record contains Chinese source wording;
- does not infer omitted cohort, transition, table, fee, Form, or cross-
  reference context; and
- abstains, qualifies, or reports insufficient retrieved support under the
  pinned answer contract instead of inventing missing law.

Because answer generation may be nondeterministic, the profile pins repeated
runs and requires every critical behavior to satisfy its zero-tolerance rule
across all required repetitions.

## Complete query-path evaluation

The end-to-end layer proves that every active Ask.Legal path:

- embeds or otherwise processes the query under the exact admitted retrieval
  profile;
- queries the exact candidate index and preserves ranked identity and context
  selection;
- passes all six metadata strings, including `metadata.authority_note`,
  unchanged to the downstream model;
- never joins the Record Traceability Lookup or hidden pipeline state;
- produces an answer satisfying the same board, state, authority-note,
  language, quotation, applicability, and non-invention rules; and
- records the exact Serving State, routing generation, query profile, retrieved
  IDs, answer profile, and evaluation result needed for reproducibility.

Unknown-type fallback, a general multilingual claim, manual demonstrations, or
a few successful queries do not establish compatibility.

## Critical errors and slice gates

The admission package has zero tolerance for at least:

- an active path dropping, renaming, rewriting, or failing to transmit
  `metadata.authority_note`;
- a wrong-board, future, historical, unknown, or excluded item being asserted
  as the governing current rule;
- a mandatory applicability limitation or authority warning being omitted or
  contradicted;
- a fabricated English or Chinese source quotation;
- a generated Chinese explanation being represented as HKEX's official text;
- material numerical, currency, date, threshold, condition, table, fee, or Form
  meaning changing in explanation;
- hidden lookup or undeclared metadata entering the answer path; or
- one mandatory language, board, component, state, or crowding slice failing
  while an aggregate score still passes.

Every slice receives a pre-frozen gate appropriate to its risk and sample
support. Small critical slices use exact case pass requirements rather than an
unstable percentage. Statistical intervals, repetition, and minimum case counts
are fixed before sealed execution.

## Failure and later language decision

If an otherwise accepted English-only workflow fails a mandatory Traditional-
Chinese or mixed-language retrieval or answer gate, Hong Kong Regulatory
Materials do not serve through that workflow. The system first tests another
candidate multilingual retrieval workflow under a new exact profile.

Only if supported English-only candidates still cannot pass does a genuine
product decision arise between a compact source-faithful official-Chinese
retrieval aid and full bilingual serving. That later decision requires its own
source, record, identity, cost, evaluation, and query-contract evidence. This
ADR does not choose prematurely and permits no silent Chinese field, duplicate,
vector family, or runtime translation workaround.

## Monitoring and revalidation

After admission, representative query and answer monitoring remains separate
from legal-source monitoring. Drift, a critical incident, a relevant new HKEX
structure, a corpus composition change, an embedding or answer model change, a
query-contract or prompt change, a renderer change, a context-budget change, or
an evaluation defect suspends or reopens the affected profile according to its
frozen rules.

Observed production queries may inform privacy-controlled future regression
cases only after adjudication and immutable suite expansion. They never edit a
sealed expected answer merely to match current behavior.

## Consequences and authorization

This decision completes the high-level English-only Regulatory retrieval and
downstream-answer admission architecture. Exact query bytes, relevance
judgments, models, thresholds, repetitions, costs, profiles, runner code, and
results remain later executable artifacts derived from evidence.

This ADR authorizes documentation only. It does not authorize implementation,
source acquisition, embedding or model calls, evaluation execution, index
construction, Pinecone or Azure access, release publication, promotion,
deployment, commit, push, or any remote action.
