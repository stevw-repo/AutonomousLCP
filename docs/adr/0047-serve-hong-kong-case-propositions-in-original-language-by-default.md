---
status: accepted
date: 2026-08-12
refines:
  - 0013
  - 0014
  - 0020
  - 0046
depends_on:
  - 0008
  - 0016
  - 0018
---

# Serve Hong Kong case propositions in original language by default

Each ordinary Hong Kong Case Proposition Search Record uses the original
language in which the court authored the supporting opinion or passage. An
available Judiciary translation is preserved as linked evidence but is not
placed in `metadata.text` by default.

This differs from Hong Kong Legislation. Its English and Traditional Chinese
texts are paired authentic legislation under ADR 0019. A translated judgment
is instead an optional rendering of one court-authored judgment and does not
create a second authority.

## Controlling language and identity

The court-authored original controls what the judgment said. Language is
recorded at opinion or passage level because one judicial decision may contain
genuinely mixed-language material. The pipeline preserves the exact published
script and does not silently translate, transliterate, or normalize it into a
different serving language.

One Judiciary translation is a **Judiciary Translation Artifact** linked to
the exact judgment Legal Item, Official Version, opinion, and supported
passages. It is not another Legal Item, Official Version, opinion, authority,
or language-specific duplicate Search Record.

One proposition therefore produces one original-language serving record. An
English judgment remains English-only in serving even when an official Chinese
translation exists. A Traditional-Chinese judgment remains Traditional-
Chinese-only in serving even when an official English translation exists.
Genuinely mixed original passages remain mixed.

## Translation preservation and use

Every acquired Judiciary Translation Artifact is preserved in the Evidence
Vault and linked through the Management Register and Record Traceability
Lookup. It may support:

- deterministic identity and passage alignment;
- human and Legal Desk review;
- terminology comparison;
- evaluation of proposition extraction and answer grounding;
- paired English-and-Traditional-Chinese retrieval tests; and
- design of a later, explicitly approved serving-enrichment rule.

It cannot replace the originating judgment or cure missing, unauthenticated,
or conflicting original evidence. Alignment requires the exact judgment,
Official Version, opinion, passage, and complete meaning. Matching citation or
paragraph numbers alone are insufficient.

An unmatched, incomplete, or conflicting translation is quarantined as
translation evidence while an independently proved original-language record
may proceed. If the conflict also calls the original judgment identity,
version, attribution, or wording into question, the affected case work blocks
or enters Quarantine under the ordinary case rules.

A later translation, corrected translation, or withdrawal updates translation
evidence and may open bounded review. It does not create a new judgment
Official Version or a new Search Record merely because translations remain
outside the serving payload.

Press summaries, unofficial translations, HKLII-rendered text, and
machine-generated Simplified Chinese website pages are not Judiciary
Translation Artifacts and do not replace the original judgment.

## Cross-language evaluation gate

The embedding-model and downstream-LLM compatibility decision must test
original-language records in all four directions:

1. English query to English judgment;
2. Traditional Chinese query to Traditional Chinese judgment;
3. Traditional Chinese query to English judgment; and
4. English query to Traditional Chinese judgment.

Tests measure retrieval coverage, ranking, proposition accuracy, result
diversity, and downstream answer grounding on representative Hong Kong legal
language. A provider's general claim that a model is multilingual is not
sufficient evidence.

If original-language-only serving passes the accepted thresholds, translation
adds no serving text. If it fails materially, the next design choice is the
smallest effective enrichment, normally a short, clearly labelled,
evidence-aligned translation retrieval aid for affected records. Full
proposition-and-passage duplication is a last fallback. Neither enrichment is
authorized by this ADR; either requires a later explicit accepted decision
with evidence, construction, labelling, size, evaluation, review, lineage, and
failure rules.

No future enrichment may remove or truncate controlling original text, present
a translation as court-authored original text, create an unlabeled
translation-only authority, or create duplicate language records that can
crowd retrieval.

## Authority-note behavior

ADRs 0020 and 0050 apply. `metadata.authority_note` remains English only and is
exactly `"None"` when no note applies. The authority note is internal
downstream-LLM authority context, not judgment text or translation enrichment.

## Consequences

The Hong Kong Cases Source Rulebook and serving contract must encode passage-
level original-language evidence, Judiciary Translation Artifact identity and
alignment, original-only serving, optional-translation failure isolation, and
the cross-language evaluation gate. Translation availability does not define
case coverage and a missing optional translation creates no Coverage Gap.

This decision authorizes documentation only. It does not authorize connector
implementation, source acquisition, translation generation, AI or embedding
calls, release publication, Pinecone mutation, promotion, or deployment.
