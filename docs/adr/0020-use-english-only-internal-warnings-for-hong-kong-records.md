---
status: accepted
date: 2026-08-11
amended_by:
  - 0050
  - 0055
refined_by:
  - "0080"
  - "0081"
amends:
  - 0019
refines:
  - 0013
---

# Use English-only internal authority notes for Hong Kong records

Every Hong Kong Search Record carries the required
`metadata.authority_note` string from ADRs 0013 and 0050. The exact value
`"None"` remains the only valid no-note sentinel. When a real note is required,
all warning and support clauses use controlled English only. The pipeline does
not append or generate a Traditional Chinese translation of the note.

This applies to Hong Kong Legislation, Hong Kong Cases, and Hong Kong
Principles. It does not change the bilingual Hong Kong legislation text rule in
ADR 0019: `metadata.text` still contains the corresponding English and
Traditional Chinese legal text in one Search Record.

## Different purposes

The two fields have different jobs:

- `metadata.text` contains the legal material used for retrieval and legal
  grounding. For Hong Kong legislation, Traditional Chinese is an equally
  authentic legal text. Including it also improves retrieval and answer
  grounding when a user queries in Chinese.
- `metadata.authority_note` is a controlled internal authority and reliance note for the
  downstream LLM. It tells the model how the retrieved record may or may not be
  safely used. It is not source text and is not a user-facing translation.

The downstream LLM receives the English authority note unchanged regardless of
the query language. It must apply every warning clause when reasoning and may
communicate the resulting qualification in the language of its answer.
Ask.Legal does not translate, rewrite, remove, or replace the note before
sending it to the model.

The authority note remains excluded from embedding input. Chinese queries
therefore retrieve against the bilingual `metadata.text`, while the English
note is applied only after retrieval.

## Validation and future boundary

End-to-end compatibility tests must include Chinese-language queries that
retrieve a Hong Kong record with a real authority note. The tests prove that:

- the bilingual `metadata.text` reaches the downstream LLM;
- the exact English `metadata.authority_note` reaches it unchanged;
- the model does not ignore a warning clause because the query is Chinese; and
- the answer reflects the required qualification in the answer language.

Changing the English authority note still selects a different exact Search
Record under ADRs 0013, 0050, and 0055. A new payload receives a new ID; a
former exact supported payload may be reselected without backward lineage. The
full evidence and structured authority-note facts remain in the Management
Register, Evidence Vault, and Record Traceability Lookup.

This decision depends on the authority note being an internal model instruction. If a
future Ask.Legal interface displays `metadata.authority_note` verbatim to end users,
the language and presentation rule must be reconsidered through a new explicit
decision rather than silently exposing the internal English template.

ADR 0080 adds one narrower answer rule without exposing the complete field: if
a reconstructed consolidation supports an answer, the model reproduces the
English warning portion before `[INSTRUCTION: ...]`, but never the instruction
portion itself. This does not authorize a user interface to display the whole
authority note verbatim or translate it.

## Consequences

Hong Kong authority-note templates, controlled vocabulary, tests, and review
guidance are authored in English only. The exact English templates and maximum
length remain contract details. No Traditional Chinese authority-note renderer
or translation step is required.
