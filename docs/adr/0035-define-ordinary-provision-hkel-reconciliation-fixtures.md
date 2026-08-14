---
status: accepted
date: 2026-08-12
refined_by:
  - "0080"
refines:
  - 0018
  - 0019
  - 0021
  - 0022
  - 0028
  - 0033
  - 0034
depends_on:
  - 0013
  - 0020
---

# Define ordinary-provision HKeL reconciliation fixtures

The first group in the HKeL reconciliation fixture catalogue covers ordinary
provisions: instrument titles and identifiers, sections, subsections,
paragraphs, headings, and ordinary text without tables, forms, images, or
other complex layout.

These fixtures turn the accepted XML, PDF, bilingual, and canonical-rendering
rules into small examples with fixed results. They do not create a new source
of law. They test whether an implementation applies ADRs 0021, 0022, and 0028
and the `HKLEG-CURRENT-EVID-*` evidence rules correctly.

## The three result classes

| Result class | Exact meaning | Permitted next step |
|---|---|---|
| `PASS` | Required evidence is complete and deterministic reconciliation succeeds | Continue to legal-status, identity, disposition, record, and release rules; do not publish automatically |
| `BLOCK` | Required evidence is absent, source semantics cannot presently be interpreted, or deterministic candidate construction violates its contract without creating a source-evidence conflict | Retry acquisition, complete Source Contract Review, or correct the deterministic processing defect; create no candidate record |
| `QUARANTINE` | Required evidence exists but conflicts, identifies different legal material, or cannot be reconciled faithfully | Preserve all evidence and failed comparisons for Legal Desk review; do not guess or prefer one representation |

A block and Quarantine are deliberately different. A missing PDF might become
available on retry. Two existing files that disagree on a legal word are a
conflict and must not be treated as a temporary download failure.

The more specific accepted outcomes remain:

- missing or incomplete required evidence uses
  `HKLEG-CURRENT-EVID-003` and `AFFECTED_EVIDENCE_UNAVAILABLE`;
- conflicting or unreconcilable evidence uses
  `HKLEG-CURRENT-EVID-004` and `QUARANTINE`; and
- an unknown schema element, enum, or field meaning pauses affected processing
  and opens Source Contract Review under ADR 0028.

## Fixture package contract

Every executable fixture later created from this catalogue contains:

- one immutable stable fixture ID;
- a short purpose statement;
- the smallest synthetic English and Traditional Chinese XML inputs needed to
  represent the case under the pinned HKeL specifications;
- the corresponding smallest synthetic verified-PDF content and declared
  presentation elements;
- source identities, languages, versions, locations, and required
  verification facts;
- the exact allowed presentation projection;
- the expected extracted legal content and structural mapping;
- either the exact expected canonical bilingual `metadata.text` or an explicit
  statement that no candidate payload may exist;
- the expected `PASS`, `BLOCK`, or `QUARANTINE` result and specific reason;
- the ordered accepted rule and ADR references; and
- the expected reconciliation report facts, including every ignored
  presentation occurrence and every mismatch.

The examples in this ADR state the legal and structural facts without
inventing HKeL tag names. When executable byte fixtures are created, their XML
must validate against the exact pinned HKeL schema and interpretation mapping.
Changing the representation to match the real schema cannot change the
accepted purpose or result of a fixture.

## Presentation projection boundary

Reconciliation compares legal content and legal structure, not PDF page
layout. A deterministic projection may remove only an enumerated element that
the pinned rules identify as presentation rather than legal content:

- known verification cover material that is captured and checked separately;
- known repeating page headers and footers;
- page numbers and page-break markers;
- line wrapping and pagination; and
- another exact presentation element expressly classified by the pinned
  specification and interpretation mapping.

Every removal is reported by type, page or source location, value or
fingerprint, and rule. The verifier does not apply a general “clean up the
PDF” operation.

The projection does not casually normalize or ignore words, numbers, dates,
capitalization, quotation marks, apostrophes, hyphens, dashes, punctuation,
brackets, paragraph markers, numbering, order, headings, cross-references,
token boundaries, or legally meaningful whitespace. A line break may be
discarded only while preserving the exact token boundary on both sides. A
hyphen at a line ending is not automatically removed or inserted. A later
pinned rule may permit a specific transformation only after its legal and
source meaning is settled and corresponding fixtures are accepted.

## Bilingual pairing boundary

English and Traditional Chinese units pair only through the official item,
version, provision, and structural identifiers interpreted under the pinned
specifications. Translation similarity, matching word counts, nearby source
positions, and AI judgment cannot create or repair the pairing.

Both authentic-language units must describe the same Legal Item, Official
Version, Legal Location, and operative state. Their words do not need to be
literal translations of each other for reconciliation purposes; each language
must independently match its own applicable PDF, while their official
structural identities must align.

## Common accepted example

The pass fixtures use a synthetic ordinary location with these source facts:

| Fact | English | Traditional Chinese |
|---|---|---|
| Instrument | `Sample Ordinance (Cap. 999)` | `示例條例（第999章）` |
| Provision | `section 2` | `第2條` |
| Heading | `Application` | `適用範圍` |
| Paragraph 1 | `(1) This Ordinance applies to every specified person.` | `(1) 本條例適用於每名指明人士。` |
| Paragraph 2 | `(2) A person must keep the record.` | `(2) 任何人須備存該紀錄。` |

When the fixture requires a candidate payload, the exact expected
`metadata.text` is:

```text
[English — Authentic Text]
Instrument: Sample Ordinance (Cap. 999)
Provision: section 2
Heading: Application
Text:
(1) This Ordinance applies to every specified person.
(2) A person must keep the record.

[繁體中文 — 真確文本]
法例：示例條例（第999章）
條文：第2條
標題：適用範圍
正文：
(1) 本條例適用於每名指明人士。
(2) 任何人須備存該紀錄。
```

The example is synthetic and proves no real law. `metadata.authority_note` remains a
separate required field and is not inserted into this text.

## Accepted ordinary-provision fixtures

### `HKLEG-RECON-ORD-FIX-001` — exact legal content and structure match

Both XML languages and both applicable PDFs identify the common example's same
item, version, location, heading, paragraphs, wording, punctuation, numbering,
and order. No presentation removal is needed.

Expected result: `PASS`. Apply the applicable `HKLEG-CURRENT-EVID-001` or
eligible `EVID-002` path. The expected candidate text is the common canonical
payload above. Passing reconciliation does not itself prove commencement or
authorize a Search Record or release.

### `HKLEG-RECON-ORD-FIX-002` — enumerated PDF presentation differences

The XML legal content is the common example. The PDFs add only known repeating
headers and footers, page numbers, a page break, and line wrapping. Removing
those exact enumerated elements preserves every legal token, boundary,
paragraph, and structural relationship.

Expected result: `PASS`. The report lists every ignored occurrence and rule.
The expected candidate text remains the common canonical payload. An unknown
or unreported difference does not inherit this result.

### `HKLEG-RECON-ORD-FIX-003` — legal word, number, date, reference, or punctuation mismatch

All required files exist, but one XML legal unit differs from its applicable
PDF in a word, number, date, cross-reference, quotation mark, hyphen, or other
potentially meaningful punctuation.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Record the exact
language, location, XML value, PDF value, and comparison position. Create no
candidate payload. Similarity, translation, majority voting, and AI cannot
approve the mismatch.

### `HKLEG-RECON-ORD-FIX-004` — item, version, or provision mismatch

All required files exist, but an XML and its applicable PDF identify different
Legal Items, Official Versions, or Legal Locations.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Create no
candidate payload and do not select whichever artifact appears newer.

### `HKLEG-RECON-ORD-FIX-005` — required XML or PDF absent

At least one required English or Traditional Chinese XML or applicable PDF is
missing, unreachable, truncated, older than the required version, or otherwise
incomplete.

Expected result: `BLOCK` with `AFFECTED_EVIDENCE_UNAVAILABLE` under
`HKLEG-CURRENT-EVID-003`. Create no candidate payload. This is not a conflict
unless contradictory evidence also exists.

### `HKLEG-RECON-ORD-FIX-006` — one authentic language absent

The evidence path is otherwise complete, but English or Traditional Chinese
XML or its applicable PDF is missing.

Expected result: `BLOCK` under `HKLEG-CURRENT-EVID-003`. There is no
monolingual fallback, translation repair, or language-only Search Record.

### `HKLEG-RECON-ORD-FIX-007` — authentic languages identify different versions or locations

Each language may independently match its own PDF, but the English and
Traditional Chinese units identify different Official Versions, provisions,
or structural locations.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Create no
bilingual candidate and do not pair by translation similarity.

### `HKLEG-RECON-ORD-FIX-008` — official heading mismatch

The provision text otherwise agrees, but the XML official heading differs from
its applicable PDF heading in either authentic language, or one representation
has an official heading while the other unexpectedly lacks it.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. A heading is
part of the verified legal content and canonical payload. The rule does not
apply when the pinned specification proves that the observed source element is
presentation metadata rather than an official heading.

### `HKLEG-RECON-ORD-FIX-009` — paragraph numbering or order mismatch

All words may appear in both representations, but paragraph numbers, markers,
nesting, sequence, lead-in relationship, or continuation order differs.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. The verifier
cannot flatten the content into one bag of matching sentences.

### `HKLEG-RECON-ORD-FIX-010` — specification-defined non-legal XML metadata

The XML contains a source element that the pinned HKeL specification and
explicit interpretation mapping classify as operational metadata rather than
official legal content. The element is excluded by the exact mapping. All
remaining legal content and structure reconcile with the PDFs.

Expected result: `PASS`. The report identifies the excluded element and pinned
mapping. The metadata does not enter `metadata.text`. An element is not
excluded merely because its tag name looks administrative.

### `HKLEG-RECON-ORD-FIX-011` — unknown XML element, enum, or meaning

The XML contains an element, value, namespace, status, or structural meaning
not covered by the pinned specification and interpretation mapping.

Expected result: `BLOCK` with `SOURCE_CONTRACT_REVIEW_REQUIRED` under ADR
0028. Affected new processing pauses; the exact input and specification bundle
are preserved. Do not guess whether the input is legal text or metadata. If
review later proves a same-fact conflict, a new rulebook version may direct
Quarantine; the unknown input is not prematurely labelled a legal conflict.

### `HKLEG-RECON-ORD-FIX-012` — canonical bilingual rendering

The evidence in `FIX-001` or `FIX-002` passes. The renderer uses the reconciled
XML legal content to produce UTF-8, Unicode NFC, LF line endings, no trailing
spaces, no leading or trailing blank lines, exactly one blank line between
language blocks, English first, and Traditional Chinese second. It preserves
official wording, punctuation, numbering, paragraph boundaries, and order.

Expected result: `PASS` only when the output is byte-for-byte equal to the
common canonical `metadata.text` above. URLs, internal IDs, traceability-only
dates, source-class notes, reviewer notes, authority notes, AI explanations, and
Simplified Chinese must be absent. A different legal payload fails the
applicable content fixture; a renderer-only contract deviation blocks the
candidate until corrected and does not change the preserved source evidence.

## Consequences and remaining catalogue groups

Ordinary provisions now have stable examples separating acceptable PDF
presentation differences, missing evidence, source-interpretation uncertainty,
and actual evidence conflict. An implementation may use different libraries or
internal data structures, but it must produce the same fixture outcomes and
canonical payload.

ADR 0036 settles the Schedules, tables, and forms group, ADR 0037 settles
notes, images, and cross-references, and ADR 0038 settles partial status and
general bilingual structural mismatch. ADR 0040 subsequently settles recursive
general overlong-record partitioning, and ADR 0041 settles the common machine-
readable package and catalogue contract. Exact executable HKeL-schema fixture
bytes remain later implementation work and must preserve these accepted IDs and
results.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
