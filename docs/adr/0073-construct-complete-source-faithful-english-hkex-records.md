---
status: accepted
date: 2026-08-14
refines:
  - "0054"
  - "0069"
  - "0070"
  - "0071"
  - "0072"
depends_on:
  - "0008"
  - "0011"
  - "0040"
  - "0050"
refined_by:
  - "0074"
---

# Construct complete source-faithful English HKEX records

## Decision and meaning of complete

Every searchable current or transitional-current HKEX applicability branch is
rendered as one or more complete source-faithful English Search Records. The
normal record unit is the smallest complete official rule-bearing unit that is
independently usable with its required governing context. The pipeline does
not summarize, translate, simplify, silently correct, or replace official rule
text.

`Complete` means that the selected official semantic unit is uncut and retains
every qualification needed to understand it. It does not mean that every
subrule sharing one visible rule number must appear in every record. A rule
with one coherent obligation may remain one record, while independently usable
numbered subrules or definition entries may form separate records. Related
conditions, exceptions, provisos, and notes remain together when their combined
logic is inseparable.

This decision adapts ADR 0040's safe structural partitioning discipline to
English-only HKEX Regulatory Materials. It does not transfer Hong Kong
Legislation's bilingual alignment, HKeL source model, or legislation-specific
Legal Location rules.

## English source-unit tree

The accepted current English product is represented internally as one ordered
tree of source-supported semantic units. Depending on the component, units may
include:

- Chapters, Parts, official headings, rules, subrules, paragraphs,
  subparagraphs, list items, and definition entries;
- incorporated notes, qualifications, exceptions, provisos, transition text,
  and local scope statements;
- appendix and Practice Note paragraphs and their official children;
- table captions, headers, rows, legally inseparable row groups, units, and
  notes;
- Regulatory Form Parts, instructions, declaration groups, field groups,
  signing requirements, and controls; and
- Fees Rule categories, brackets, amounts, calculation bases, timing rules,
  units, and attached notes.

A website container, navigation label, PDF page, line wrap, blank field,
individual table cell, or renderer-created serving part is not automatically a
legal source unit or Legal Location. Presentation elements are classified
explicitly rather than silently discarded.

The source structure must be proved through the accepted English product and
the `hk-regulatory` Source Rulebook. The optional online rulebook may assist
discovery but cannot override the controlling English product. Unknown or
ambiguous structure opens Source Contract Review or quarantines the smallest
affected branch; an LLM may not guess a boundary.

## Default record units by component class

Record boundaries are decided from official structure and legal meaning before
size optimization:

| Component class | Normal record boundary |
|---|---|
| Ordinary rule | One complete rule, or one complete numbered subrule when the subrules contain independently usable requirements |
| Definition rule | One defined term and its complete definition, including every note or qualification attached to that term |
| Numbered or bulleted list | One independently usable item with its governing lead-in, or the complete inseparable item group when alternatives, cumulative conditions, conjunctions, exceptions, or shared qualifications require the group |
| Incorporated note | The exact rule, definition, or branch it qualifies; a note is not stranded in another record |
| Appendix or Practice Note | One complete official paragraph or independently usable structural unit under the same rules as an ordinary rule |
| Table | One complete table or the smallest complete legally inseparable row group with its caption, governing lead-in, full headers, units, and attached notes |
| Fees Rules | One complete fee category, bracket group, or calculation branch with amount, currency, basis, timing, and every applicable note |
| Regulatory Form | One complete Part, instruction group, declaration, undertaking, certification, or logically connected field group; never one record per blank field |

Separate rules, definitions, table branches, Form Parts, or other normal units
are not combined merely because they are short or would fit in one embedding.
There is no target record size and no minimum fill ratio. A normal unit is not
split merely to produce smaller vectors; only an exact hard-limit failure opens
overlong partitioning.

## Governing dependency closure

Every record carries the smallest source-supported governing context needed to
understand its primary unit correctly. Required context may include:

- a grammatical parent lead-in;
- a local definition or local scope statement;
- a qualification, exception, proviso, or transition condition;
- an incorporated note attached to the unit;
- a table caption, header, unit, or calculation basis;
- a Form Part instruction or declaration scope; or
- another exact official parent whose omission would materially change the
  meaning of the selected unit.

Required source text is labelled as `Required governing context` when repeated
outside its one primary ownership. Every repetition points internally to the
exact source unit and fingerprint and does not count as primary coverage again.
Useful background and retrieval enrichment are not dependency closure. The
pipeline cannot add overlap merely to improve semantic search.

Global definitions remain separately searchable definition records and are
not copied into every rule using the term. A definition embedded locally for
one rule or branch remains with that branch because it is governing context.

## Cross-references do not recursively copy target rules

The record preserves the exact referring words and target locator. When an
official target heading exists and materially assists identification, the
canonical context may also include that exact heading under `Referenced
locations`. It does not copy the target rule text merely because a
cross-reference exists.

This boundary prevents recursive rulebook expansion, widespread duplication,
ambiguous primary ownership, and unnecessary rebuilds whenever one referred
rule changes. Internal Cross-Reference Relationships and the Record
Traceability Lookup preserve exact target resolution outside Pinecone.

If a proposed child cannot be safely understood with its complete referring
words and locator, it is not an independent record unit. The renderer keeps a
larger official parent together. If no faithful unit plus required context can
fit, the affected branch is quarantined; target text is not silently copied or
paraphrased to force a result.

## Canonical `metadata.text`

The ordinary layout is:

```text
Context:
Material: HKEX Listing Rule — non-statutory exchange regulatory rule
Market: Main Board | GEM
Component: <exact English rulebook, appendix, Practice Note, Form, or Fees Rule component>
Location: <exact source-native English locator>
Official heading: <included only when HKEX supplies one>
Effective context: <included only for a material current applicability branch>
Serving part: X of N <included only when overlong material is split>

Required governing context:
<exact repeated English context; block omitted when none is required>

Referenced locations:
- <exact locator and official heading; block omitted when none is required>

English rule text — prevailing language:
<complete exact primary English source text>
```

The `Effective context` line uses a closed deterministic English template over
accepted ADR 0071 branch facts. It is omitted for an ordinary unrestricted
current branch. The exact substantive source transition wording remains in the
primary text or required governing context; the controlled line cannot replace,
broaden, narrow, or paraphrase away that source text.

The renderer preserves exact source wording, numbering, punctuation,
capitalization, order, meaningful headings, table relationships, form labels,
fee entries, transition text, and incorporated notes. Its closed presentation
projection uses UTF-8 NFC, LF line endings, no trailing spaces, no leading or
trailing blank lines, and stable block ordering.

The renderer excludes source URLs, page numbers, repeated page headers or
footers, web controls, navigation, internal IDs, fingerprints, observation and
processing dates, reviewer prose, model output, and optional Chinese evidence.
An ambiguous character, ownership, or substantive layout cannot be silently
normalized or corrected.

`metadata.authority_note` remains a separate required English string under ADR
0050. It is `"None"` when no approved note applies and is never copied into
`metadata.text`. The embedding input remains `metadata.text` only.

## Tables, fees, and forms

Tables use one closed line-based representation that preserves caption, column
ownership, row order, units, spans, notes, and the exact relationship between
labels and values. A record cannot contain an amount without its currency and
activation basis, a table value without its header, or a fee without its
calculation and timing rules. One row or legally inseparable row group is never
divided merely to fit.

Regulatory Forms preserve official instructions, labels, declarations,
undertakings, certifications, selection controls, and substantive signing
requirements. A blank field is presentation structure rather than a separate
Search Record. The executable renderer pins a closed neutral marker vocabulary,
such as `[BLANK FIELD]`, for input areas and selection controls. Markers identify
uncompleted form structure; they cannot invent a completed value or alter the
official form obligation.

The exact table grammar and form-marker vocabulary are versioned technical
contract bytes. They may not weaken this semantic and source-fidelity contract
or vary between clean builds.

## Exact fit checks and recursive overlong partitioning

The complete final candidate is rendered before any fit decision. Measurement
includes the final context blocks, governing dependencies, referenced-location
labels, table or form projection, actual `Serving part: X of N` labels, all
other `metadata.text` bytes, and the complete six-field metadata payload,
including `metadata.authority_note`.

Two independent hard ceilings apply:

1. the exact pinned embedding tokenizer and token ceiling over final
   `metadata.text`; and
2. the exact pinned compact serving-metadata serialization and byte ceiling
   over all six metadata strings.

Character estimates, another tokenizer, preferred sizes, average sizes, or
unverified safety margins cannot replace either check.

When a normal complete unit exceeds either ceiling, the partitioner recursively
descends through its official English child structure:

1. render every candidate child with all context needed for it to stand as a
   serving part;
2. keep a complete child whole when it fits;
3. replace only an oversized child with its complete official children and
   repeat;
4. form the ordered English partition frontier from the largest safe complete
   units;
5. choose the valid contiguous partition with the fewest parts;
6. among equal-part solutions, place the greatest possible number of
   consecutive frontier units in the earliest part and repeat that rule for
   each later part; and
7. render the real final total and revalidate every complete part against both
   ceilings.

The partition cannot cross the normal record unit's official boundary or pack
an unrelated short rule into an overlong sibling. Different branches may
descend to different official depths.

Page, sentence, punctuation, whitespace, token-position, character-count,
visual-column, and sliding-window cuts are forbidden unless the same point is
independently proved as an official semantic boundary. Governing context is
never removed to force a fit. If the smallest complete unit plus required
context cannot fit, the smallest affected dependent branch is quarantined and
a Coverage Gap is recorded. If fixed metadata such as a mandatory authority
note alone makes every otherwise valid part too large, additional text
partitioning cannot cure the result and the affected records do not serve.

## English source-unit coverage proof

Every construction result creates one immutable **HKEX English Source-Unit
Coverage Proof**. It binds the exact board, applicability branches, current
English artifacts, source-unit tree, Source Rulebook and renderer versions,
finished records, non-record outcomes, totals, and canonical fingerprint.

The proof demonstrates that:

- every meaning-bearing current or transitional-current English source unit
  has exactly one primary owner or one explicit blocked or quarantined result;
- source order and Main Board or GEM ownership remain exact;
- every repeated dependency points to its one source-unit owner and exact
  fingerprint and does not count as primary coverage again;
- context-only and presentation-only units have explicit classifications;
- every table header, row group, note, Form Part, field group, and meaningful
  control is accounted for;
- every future branch is accounted for in the regulatory Waiting Room;
- every superseded or withdrawn branch is historical outside Pinecone;
- excluded non-rule material remains excluded; and
- nothing is silently dropped, duplicated as primary content, reordered,
  translated, summarized, corrected, or invented.

A source unit may be primary once and appear again as labelled governing
context. A heading or other structural unit that exists solely to provide
context may be classified context-only rather than forced into a meaningless
standalone record. Presentation-only omission never authorizes removal of a
substantive note, form control, table relationship, or visual rule content.

The coverage proof remains in the Management Register, Evidence Vault, and
Record Traceability Lookup. It does not add a Pinecone metadata field or
operational prose to `metadata.text`.

Complete source-unit accounting is not the same as serving readiness. A proof
may completely expose one quarantined current fee branch; the affected Release
Scope then remains not serving-ready even though no source unit was silently
lost. Record counts, page counts, parser success, and text-presence checks
cannot substitute for the proof.

## State, identity, and update behavior

Only supported `CURRENT` and `TRANSITIONAL_CURRENT` branches may create
ordinary Search Records after all other gates pass. Future branches remain in
the Waiting Room, superseded and withdrawn branches remain historical,
`UNKNOWN` branches remain quarantined, and excluded material produces no
Regulatory record. Internal preparation of future material does not create a
serving record or count as current serving readiness.

Main Board and GEM records remain separate even when their source wording is
identical. Register-issued immutable Search Record identity continues under
ADR 0011. Changed primary English text, material applicability context,
governing dependency closure, referenced-location rendering, table or form
projection, canonical partition boundary, serving-part label, or
`metadata.authority_note` changes the six-field payload and selects a different
exact Search Record. An unseen payload receives a new Search Record ID and
typed forward lineage.

A URL move, page reflow, web-navigation change, or other presentation-only
change creates no new Search Record when canonical six-field bytes remain
identical. A preserved exact payload may be reselected only with current legal
support and append-only serving-selection evidence under the accepted identity
rules.

## Required conformance coverage

The future executable conformance catalogue must directly cover at least:

- one coherent whole rule and several independently usable subrules;
- cumulative and alternative list items, shared lead-ins, provisos,
  qualifications, exceptions, and incorporated notes;
- one large Rule 1.01-style definition collection producing term-level records
  without losing its global scope text;
- local versus global definitions;
- ordinary, chained, unresolved, and cross-board cross-references without
  recursive target copying;
- Practice Notes, appendices, tables, row spans, units, footnotes, and
  presentation-only PDF changes;
- fee brackets whose amounts, currency, calculation basis, timing, and notes
  must remain together;
- Regulatory Form Parts, instructions, declarations, signing requirements,
  blank fields, selection controls, and a presentation-only blank;
- ordinary current, several concurrent transitional-current branches, future,
  historical, unknown, and excluded material;
- exact-fit, token-only overlong, metadata-byte-only overlong, recursively
  overlong, and indivisible-overlong units;
- the minimum-part earliest-full partition rule with actual final part labels;
- missing, duplicated, reordered, wrong-board, orphaned, and unlabelled-
  dependency source units;
- byte-identical clean builds and presentation-only source changes producing
  identical canonical records; and
- changed legal text, governing context, branch context, partition, or
  authority note producing the correct immutable identity consequence.

Tests must compare exact canonical output, measurements, coverage proof,
evidence mappings, reason and rule IDs, and record-lineage consequences. A
fixture passing semantic retrieval does not excuse a deterministic source-
fidelity or coverage defect.

ADR 0074 later fixes the strict two-layer conformance package, catalogue,
coverage-matrix, high-risk-pair, critical-error, reproducibility, and separate
build-attestation architecture that will encode this required coverage.

## Allocation and authorization boundary

This ADR defines required outputs, evidence, boundaries, and failure behavior.
It does not settle the still-deferred allocation of every parsing, semantic,
Legal Desk, LLM-assisted, or human-review step. No allocation may permit a
model to invent source text, a missing structural boundary, cross-reference
content, table ownership, form meaning, applicability facts, or coverage.

This decision authorizes documentation only. It does not create schemas,
fixtures, source artifacts, records, embeddings, or indexes; select a model or
technical stack; call an LLM or embedding provider; access Pinecone or Azure;
publish a release; promote; deploy; commit; push; or perform any remote action.
