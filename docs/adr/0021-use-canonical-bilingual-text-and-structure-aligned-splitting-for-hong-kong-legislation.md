---
status: accepted
date: 2026-08-11
amended_by:
  - 0040
refined_by:
  - "0080"
  - "0081"
amends:
  - 0019
refines:
  - 0013
  - 0020
---

# Use canonical bilingual text and structure-aligned splitting for Hong Kong legislation

Every Hong Kong legislation Search Record uses one canonical `metadata.text`
value. English comes first and Traditional Chinese second. This ordering is a
stable formatting rule, not a statement that English has greater legal
authority. Both blocks are expressly labelled as authentic text.

The normal unsplit layout is:

```text
[English — Authentic Text]
Instrument: {official English title} ({official chapter or citation})
Provision: {official English locator}
Heading: {official English heading}
Text:
{official English text}

[繁體中文 — 真確文本]
法例：{官方繁體中文名稱}（{官方章號或引稱}）
條文：{官方繁體中文定位標示}
標題：{官方繁體中文標題}
正文：
{官方繁體中文文本}
```

If the official source has no heading, the corresponding `Heading:` or
`標題：` line is omitted. If it has no chapter or citation, the parenthetical
part of the Instrument or 法例 line is omitted. A source-native structural
label is used when an instrument does not use an ordinary section number.

The payload contains the official title, official chapter, citation, or other
identifier when one exists, the exact legal locator, optional official
heading, and official text in each language. It does not contain source URLs,
internal IDs, Observation or release dates, reviewer notes, authority-note text, AI
explanations, unofficial summaries, or Simplified Chinese. A date that forms
part of the official legal text, title, heading, or locator remains because it
is source content.

Observation and publication-version dates used only for traceability stay in
the Management Register, Evidence Vault, and Record Traceability Lookup. This
prevents an unchanged legal payload from receiving a new Search Record ID just
because it was checked again.

## Canonical rendering

The renderer produces UTF-8 text normalized to Unicode NFC with LF line
endings, no trailing spaces, no leading or trailing blank lines, and exactly
one blank line between the two language blocks. It preserves official wording,
punctuation, numbering, order, paragraph boundaries, and language. It never
paraphrases or converts between Traditional and Simplified Chinese.

Lists, tables, forms, and other structured material use one versioned,
deterministic plain-text renderer. The renderer must preserve every official
label, marker, cell value, row order, and legally meaningful grouping in both
languages. Its exact conformance fixtures belong to the Query Contract. A
structure the renderer cannot represent faithfully is quarantined rather than
flattened by guesswork.

## Deterministic splitting

The complete bilingual payload is built first. Its size is then measured with
the exact tokenizer and input limit pinned by the approved embedding contract.
The embedding model and numeric limit remain open choices, but a later
implementation cannot substitute a character count or a different tokenizer.

If the complete record is too long, the system divides it only at matching
official legal boundaries, in this order where the source provides them:

1. provision or other top-level Legal Location;
2. subsection;
3. paragraph;
4. subparagraph;
5. Schedule, annex, appendix, or form item;
6. table row or legally meaningful row group; and
7. another explicit official structural unit.

ADR 0040 amends the earlier first-usable-level rule. An oversized child now
descends recursively through its next complete supported aligned children until
the largest individually safe partition frontier is found. Consecutive frontier
units remain in source order. The canonical result uses the fewest valid parts
and, among ties, puts the greatest possible number of units in each earlier
part. Every final part is re-rendered with its actual labels, total, repeated
dependencies, and complete metadata before acceptance.

Every serving part repeats the complete bilingual instrument and provision
context. The English block adds its English serving-part line directly after
`Provision:`; the Traditional Chinese block adds its Chinese serving-part line
directly after `條文：`. Their exact forms are:

```text
Serving part: 1 of 3
服務部分：第1部分，共3部分
```

The actual number and total replace the example values. These labels say
“serving part” so they cannot be mistaken for an official Part of the
legislation.

Parent introductory or lead-in text is repeated only when it is legally
necessary to understand a child unit. It is repeated in both languages and
labelled `Parent context (repeated):` and `上層脈絡（重複）：`. Each label and
its source text appear after the serving-part line and before the local `Text:`
or `正文：` line. The pipeline does not use sliding-window overlap.

English and Traditional Chinese are paired from official structure and source
identifiers, not inferred from text similarity. No serving part may contain
only one language, pair different locations, or split inside an official unit
merely to satisfy the token limit. If the two structures cannot be aligned, or
one smallest supported official unit still exceeds the limit, the candidate is
preserved in Quarantine for a Hong Kong Legislation Legal Desk decision.

## Retrieval and model acceptance

The embedding input is the complete canonical bilingual `metadata.text`.
Chinese queries can therefore match the Traditional Chinese block and English
queries the English block while each retrieval result gives the downstream LLM
both authentic texts. For a Chinese answer, the model should ground primarily
in the Traditional Chinese text and use English as a cross-check; for an
English answer, the inverse applies.

Combining both languages can weaken retrieval if the embedding model is not
genuinely multilingual or handles long inputs poorly. Before a model is
accepted, fixed evaluations must therefore cover English queries, Traditional
Chinese queries, cross-language queries, long unsplit records, and split
records. These tests validate the accepted one-record bilingual decision; poor
results require a better model or compliant split settings, not silent
creation of monolingual duplicates.

`metadata.authority_note` remains a separate required field. It is excluded
from the embedding input and, for a real Hong Kong note, remains English only
under ADRs 0020 and 0050.

## Consequences

Changing either authentic language block, a serving-part boundary, repeated
parent context, or any canonical serving label changes `metadata.text` and
therefore creates a new Search Record ID. Re-rendering identical official
content under the same renderer and embedding contract must produce byte-
identical text.

Implementation still requires selection of the multilingual embedding model,
its pinned tokenizer and limit, and executable pinned-schema fixture bytes.
ADRs 0035 through 0037 settle ordinary provisions; Schedules, tables, forms,
notes, images, and cross-references. ADR 0038 settles partial status and general
bilingual structural mismatch. ADR 0040 amends the former first-usable-level
rule with recursive official-structure descent, dependency closure, exact
final-payload measurement, primary source-unit coverage proof, and the final
overlong-record fixture group. Later choices may refine these contracts but
cannot remove either authentic language, introduce arbitrary splits, or place
operational traceability prose in `metadata.text`.
