---
status: accepted
date: 2026-08-14
amends:
  - "0054"
refines:
  - "0069"
  - "0070"
  - "0071"
depends_on:
  - "0008"
  - "0050"
refined_by:
  - "0073"
  - "0074"
  - "0077"
---

# Serve HKEX Regulatory Materials in English only

## Decision

Hong Kong Regulatory Materials Search Records contain the complete prevailing
English HKEX rule text and English applicability context only. The pipeline no
longer places the official Traditional-Chinese translation in
`metadata.text`, creates a Chinese-only duplicate, or creates a parallel
Chinese vector.

This ADR amends only ADR 0054's HKEX bilingual serving and mandatory-
translation gate. It does not change Hong Kong Legislation's authentic
bilingual design, Hong Kong Cases' original-language design, or any other
jurisdiction-and-material rulebook.

HKEX Main Board rule 1.07 and GEM rule 1.08 state that the Listing Rules are
issued in English with a separate Chinese translation and that English prevails
on conflict. The Chinese publication is useful, but it is not needed to
establish the controlling rule meaning. Serving only the prevailing source
reduces record size, avoids bilingual retrieval dilution, and prevents a late
or missing translation from blocking an otherwise supported current English
rule.

## Serving payload

The canonical ordinary layout is:

```text
Context:
Material: HKEX Listing Rule — non-statutory exchange regulatory rule
Market: Main Board | GEM
Chapter and rule: <exact English locator and heading>
Effective context: <only when required for current application>

English rule text — prevailing language:
<exact current English text>
```

The exact source-native English locator, heading, numbering, wording,
punctuation, order, tables, form labels, fee entries, transition text, and
minimum required dependency context remain preserved. The renderer does not
summarize, translate, simplify, or replace the official rule.

UTF-8 NFC, LF line endings, no trailing spaces, no leading or trailing blank
lines, and a closed versioned presentation-projection rule make output
reproducible. Source URLs, internal IDs, fingerprints, observation dates,
review explanations, and optional Chinese evidence remain outside
`metadata.text`.

`metadata.authority_note` remains the standardized required English string. It
is `"None"` when the labelled rule and context state everything needed. A
controlled English warning may communicate a material transition, scope,
source, representation, or unresolved-reference limitation already permitted
by ADRs 0050, 0054, and 0071. It cannot repair missing or conflicting English
source text.

Changing the English text, material English applicability context, serving-part
boundary, repeated dependency, or `metadata.authority_note` changes the six-
field payload and requires a new Search Record identity. A Chinese-only change
does not change the serving record unless it also establishes that the English
identity, wording, effective state, completeness, or source contract may be
wrong.

## English evidence is the required release path

For current search, the applicable HKEX-maintained English consolidated
rulebook, English Regulatory Form, or English Fees Rule is the mandatory
wording and structure evidence. Final English update packages provide their
assigned amendment, date, condition, transition, mapping, and withdrawal facts
under ADRs 0070 and 0071. The existing approval, effective-state, inventory,
completeness, and no-reconstruction rules continue to apply.

The following outcomes are exact:

- complete supported English evidence may continue through later gates even if
  the Chinese translation is missing, late, stale, or unavailable;
- missing, unreadable, stale, conflicting, or incomplete required English
  evidence blocks or quarantines the affected boundary under the existing
  source and release rules;
- a Chinese artifact is never substituted when required English evidence is
  unavailable; and
- no warning, LLM translation, online-rulebook text, or similarity inference
  may repair missing or conflicting controlling English evidence.

English-only serving does not make every English artifact authoritative. The
HKEX-maintained current products retain ADR 0070's fact-specific precedence
over the Thomson Reuters-maintained presentation, and future or conditional
English changes remain outside current search until ADR 0071's exact effective
facts and current-product reconciliation pass.

## Traditional-Chinese material remains non-serving support

Official Traditional-Chinese HKEX translations may be preserved in the
Evidence Vault and linked in the Management Register for:

- Chinese terminology and evaluation design;
- source investigation and publisher-change detection;
- identifying a possible English inventory, identity, version, or effective-
  state problem;
- later reconsideration of an official-Chinese retrieval aid or bilingual
  serving; and
- audit and traceability when the material was actually used.

Chinese artifacts are not an ordinary current-release dependency, do not need
complete cutoff freshness to approve an English record, and do not enter
Pinecone merely because they were preserved. Their availability, timestamps,
or wording do not create a new Search Record.

A Chinese discrepancy is non-blocking when it is confined to the optional
translation. It opens or affects current processing only when it is positive
evidence that the English product may have the wrong board, component,
location, version, current wording, effective branch, or completeness. The
resulting investigation concerns the English controlling decision; it does not
promote Chinese to a competing wording authority.

Chinese material may be observed or acquired on a bounded signal or evaluation
need. This ADR creates no permanent release-blocking Chinese monitoring SLA and
no requirement to build a complete live bilingual alignment map.

## Chinese-language query behavior

English-only serving is allowed only through a pinned multilingual retrieval
workflow that passes complete evaluation for Traditional-Chinese and mixed-
language queries. The downstream LLM receives the approved English
`metadata.text` and may explain the controlling English rule in Chinese.

The downstream contract must prevent the model from:

- claiming its Chinese explanation is HKEX's official translation;
- fabricating or presenting a Chinese quotation as source text;
- silently changing the meaning of an English legal term;
- treating an optional Chinese artifact as controlling; or
- implying that the English-only record contains a Chinese source block.

Before the Regulatory family can serve, fixed evaluation must cover at least:

- Traditional-Chinese descriptions of English rule concepts;
- mixed English-and-Chinese questions;
- exact rule-number and cross-reference queries;
- Main Board versus GEM disambiguation;
- definitions, abbreviations, dates, percentages, and monetary requirements;
- Practice Notes, appendices, Regulatory Forms, Fees Rules, and tables;
- current, future, conditional, and transitional branches; and
- retrieval crowding against legislation, cases, and Principles.

Exact models, queries, thresholds, repetition, evaluator, and admission
artifacts remain later decisions. Unknown-type fallback, general claims of
multilingual capability, or a few successful examples do not prove admission.

If the accepted English-only workflow fails the Chinese or mixed-language
gates, Regulatory Materials do not serve through that workflow. The design
must then explicitly choose and evaluate either a compact source-faithful
official-Chinese retrieval aid or full bilingual serving. The pipeline may not
silently add Chinese text, another metadata field, language duplicates, or a
second vector family.

## Record construction and overlong material

Later record-construction rules measure the complete rendered English payload
against the exact pinned tokenizer, embedding ceiling, and metadata ceiling.
Overlong material splits only at complete source-supported English semantic
boundaries with the minimum dependency closure required for independent
meaning. It does not wait for or align to Chinese boundaries.

ADR 0073 later settles the final conceptual renderer, class-specific record
units, governing-context and cross-reference boundaries, overlong partition
algorithm, and exact source-unit coverage proof. Executable schema bytes,
fixture catalogue, numerical limits, embedding model, and retrieval thresholds
remain later detailed design subjects.

## Conformance requirements

The executable Hong Kong Regulatory Materials conformance catalogue must cover
at least:

- complete English current evidence with no Chinese artifact;
- complete English evidence with a late, stale, or conflicting optional
  Chinese translation;
- missing English with an available Chinese translation;
- a Chinese signal that exposes a possible English identity or version defect;
- English future, conditional, and transitional branches;
- English Forms, Fees Rules, tables, notes, appendices, and Practice Notes;
- presentation-only English changes with byte-identical canonical output;
- a material English payload change requiring a successor Search Record;
- prohibited Chinese insertion, Chinese-only duplication, and parallel vectors;
- prohibited fabricated Chinese quotation; and
- every mandatory Chinese-query retrieval slice above.

## Consequences and authorization

The full-bilingual reconciliation-map proposal is rejected for ordinary HKEX
serving. Its general structure-alignment concepts remain valid only if a later
accepted decision reintroduces official Chinese serving. ADR 0054's family,
classification, scope, `type: "regulatory"`, six-field envelope, and English-
precedence labels remain otherwise unchanged.

This ADR defines serving policy and evidence boundaries only. It does not
select an embedding model, allocate LLM tasks, register live endpoints,
acquire source artifacts, implement schemas or applications, construct or
publish a corpus, access Pinecone or Azure, promote, deploy, commit, push, or
perform any other production action.
