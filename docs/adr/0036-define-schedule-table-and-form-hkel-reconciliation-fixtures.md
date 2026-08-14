---
status: accepted
date: 2026-08-12
refined_by:
  - "0080"
refines:
  - 0011
  - 0018
  - 0019
  - 0021
  - 0022
  - 0028
  - 0035
depends_on:
  - 0013
  - 0020
---

# Define Schedule, table, and form HKeL reconciliation fixtures

The second group in the HKeL reconciliation fixture catalogue covers
Schedules, tables, and prescribed forms. These structures often carry meaning
through nesting, headings, row-and-column relationships, blank controls, and
visual grouping. The pipeline preserves that legal meaning in deterministic
plain text; it does not attempt to imitate the PDF page visually.

The ordinary-fixture result classes and evidence boundaries in ADR 0035 still
apply:

- `PASS` clears reconciliation and rendering only;
- `BLOCK` means evidence is missing, source meaning is unknown, or a
  deterministic processing defect must be corrected without a source
  conflict; and
- `QUARANTINE` means complete evidence conflicts or the official structure
  cannot be represented faithfully.

## Structured Legal Locations

Schedules, tables, and forms remain inside their parent Legal Item. Their
location hierarchy is:

- every Schedule, annex, or appendix is a Legal Location under its parent
  instrument;
- each officially identified Schedule Part, paragraph, item, table, or form
  may be a child Legal Location when it is independently locatable or can
  produce a separate Search Record;
- a table belongs under its containing provision, Schedule, or other official
  location;
- a separately identified prescribed form is a Legal Location under its
  containing instrument or Schedule; and
- an ordinary unnumbered cell, blank field, visual row, page coordinate, or
  renderer-created serving part is not automatically a permanent Legal
  Location.

An officially numbered or independently referenced table row, Schedule item,
form Part, or field group may receive a child Legal Location. Identity follows
official structure and the evidence-backed continuity rules, never a PDF page,
coordinate, column width, or output position.

## Deterministic table rendering

A plain Markdown table is not the canonical representation because merged
headers, dependent rows, and long cells can lose their relationships. The
renderer instead emits one labelled record per row in source order. Each cell
label is its complete official header path from outermost merged heading to
the leaf column, joined by the fixed separator ` > `.

For example, an English table whose merged heading `Fee` contains the columns
`Amount` and `Period` renders as:

```text
[Table]
Title: Licence fees

Row: 1
Item: 1
Licence class: General
Fee > Amount: $1,000
Fee > Period: per year

Row: 2
Item: 2
Licence class: Limited
Fee > Amount: $500
Fee > Period: per year
```

The corresponding Traditional Chinese table uses the official Chinese title,
headings, and values with the fixed scaffolding labels `[表格]`, `標題：`, and
`行：`. Official heading words remain source content; `[Table]`, `Row:`, the
separator, and their Chinese equivalents are deterministic renderer
scaffolding rather than invented law.

The renderer preserves:

- official table identity, caption, title, lead-in, units, qualifications, and
  notes that form part of the table;
- every header level and its exact cell scope;
- row and column order;
- every row label, item number, cell value, blank, dash, ditto mark, checkbox,
  symbol, and continuation relationship; and
- row groups where a row depends on a heading, spanning cell, ditto mark, or
  preceding row for meaning.

A blank, dash, zero, `N/A`, ditto mark, and omitted cell are distinct source
facts. The renderer does not replace one with another or expand a ditto mark as
though the expansion were official text. Its structural dependency is instead
preserved in the row group and traceability mapping.

Column widths, border thickness, font size, alignment, wrapping, and page
placement are presentation facts unless the pinned rulebook maps a particular
visual feature to legal meaning. Repeated page headers may be removed only
under ADR 0035's enumerated and reported projection rule.

## Deterministic form rendering

A prescribed blank form is represented as the official form structure, not as
a completed application. The renderer preserves in source order:

- form number, title, parent provision, and official instructions;
- Parts, sections, field groups, and field labels;
- blank-entry, date, signature, stamp, checkbox, radio-choice, and other known
  control types;
- every choice-group label and option;
- declarations, certifications, warnings, qualifications, and prescribed
  wording; and
- dependencies such as “complete this field only if yes”.

For example:

```text
[Form]
Form: Application Form 1

Field: Applicant's name
Control: blank entry

Choice group: Applicant type
Option: [ ] Individual
Option: [ ] Company

Declaration:
I declare that the information provided is correct.

Signature field: Applicant
Date field: Date
```

The corresponding Traditional Chinese form uses the official Chinese content
and the fixed Chinese scaffolding labels. `blank entry` and `[ ]` describe the
official empty control; they do not invent an answer or say that a box was
selected. Handwriting, example data, or completed-user content is not inserted
unless it is itself part of the official prescribed source.

Spacing, line lengths, dotted lines, box dimensions, and page coordinates may
differ without changing meaning when the complete official controls and their
relationships still align. A missing field, instruction, option, declaration,
signature requirement, or conditional dependency is legal-content or
structural disagreement, not harmless spacing.

## Bilingual structural alignment

English and Traditional Chinese Schedule, table, and form units pair through
their official item, version, parent, locator, and structural identifiers under
the pinned specification mapping. Each language independently reconciles with
its applicable PDF.

The two authentic versions may use different column widths, line breaks, page
counts, and visual arrangement. They pass only when the official Schedule
items, table header paths, row roles, form Parts, field groups, controls, and
order align. Translation similarity, matching coordinates, equal row counts by
themselves, or AI judgment cannot establish the relationship.

## Safe splitting boundary

The complete bilingual structure is rendered before its size is measured with
the embedding contract's pinned tokenizer. An overlong structure may split
only at corresponding official boundaries:

- a Schedule Part, paragraph, numbered item, or other complete Schedule unit;
- a complete table row or legally inseparable row group; or
- an official form Part, section, or complete field group.

Every serving part repeats the bilingual instrument and location context and
the complete Schedule, table, or form context needed to interpret it. A table
part repeats its title, lead-in, units, qualifications, and complete header
paths. A form part repeats its form title and any instruction or condition
governing the included fields. Repeated context uses ADR 0021's explicit
English and Traditional Chinese repeated-parent labels.

The renderer must not split:

- inside a cell, logical row, or inseparable dependent row group;
- between a spanning heading and the cells it governs;
- inside a form field, choice group, declaration, certification, signature
  statement, or conditional instruction; or
- merely because the PDF begins another page.

If no faithful plain-text representation or safe smallest split unit exists,
the source candidate enters Quarantine. If a faithful split exists but an
implementation produces a different unsafe split, that is a deterministic
processing defect and blocks that output until corrected; it does not turn
consistent source evidence into a source conflict.

## Accepted Schedules, tables, and forms fixtures

### `HKLEG-RECON-STF-FIX-001` — matching Schedule structure

The Schedule identity, title, parent reference, Parts, numbered items, wording,
punctuation, nesting, and order match between each XML and its applicable PDF,
and the two authentic languages align through official identifiers.

Expected result: `PASS`. Preserve the Schedule and supported child Legal
Locations. Later legal-status and record rules still apply.

### `HKLEG-RECON-STF-FIX-002` — repeated Schedule heading after a page break

A PDF repeats the exact Schedule or column heading after a page break. The
pinned projection classifies this occurrence as a repeated presentation
heading, and removing it changes no legal token, item, or hierarchy.

Expected result: `PASS`. Report every removed heading, page, value, and rule.
An altered or unclassified repetition does not pass this fixture.

### `HKLEG-RECON-STF-FIX-003` — Schedule identity or order mismatch

Complete evidence disagrees on the Schedule number, title, parent reference,
Part, item number, nesting, wording, or source order.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Do not reorder
items or select the apparently newer representation.

### `HKLEG-RECON-STF-FIX-004` — matching rectangular table

A simple table has one header row, no spanning cells, and matching title,
headers, row labels, cell values, empty states, and order in both source
representations. Both authentic-language table structures align officially.

Expected result: `PASS`. Render each row with its official leaf headers in
source order.

### `HKLEG-RECON-STF-FIX-005` — deterministically mapped merged headings

The XML span structure and PDF layout agree that a merged outer heading governs
specific leaf columns. Every cell receives one complete, unique header path,
such as `Fee > Amount`, without inference or collision.

Expected result: `PASS`. The reconciliation report records the span-to-header-
path mapping and the canonical labelled-row output.

### `HKLEG-RECON-STF-FIX-006` — presentation-only table layout differences

Column widths, wrapping, pagination, repeated exact page headings, and other
enumerated presentation features differ, but the complete header paths, cell
scope, values, row groups, and source order are unchanged.

Expected result: `PASS`. Report every ignored presentation occurrence. Border
or alignment differences pass only when the pinned mapping classifies them as
non-legal presentation.

### `HKLEG-RECON-STF-FIX-007` — table relationship or order mismatch

Complete evidence disagrees on row order, column order, a value's assigned
cell, header scope, spanning-cell scope, nesting, or continuation relationship.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Matching all
words somewhere in the table does not prove the same table.

### `HKLEG-RECON-STF-FIX-008` — blank and symbol disagreement

One representation has a blank or omitted cell while the other has a dash,
zero, `N/A`, ditto mark, checkbox state, symbol, or other value.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. These states are
not interchangeable, and the pipeline does not invent an expansion.

### `HKLEG-RECON-STF-FIX-009` — bilingual tables differ only visually

The English and Traditional Chinese tables use different widths, wrapping,
page counts, or other permitted visual arrangements. Each independently
matches its PDF, and official table identity, complete header paths, row roles,
cell roles, and order align.

Expected result: `PASS`. Visual symmetry and equal coordinates are not
required.

### `HKLEG-RECON-STF-FIX-010` — bilingual table structures cannot align

The authentic languages disagree or cannot be mapped on row identity, column
role, header scope, cell assignment, row group, or order under the pinned
official identifiers.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Do not repair the
mapping using translation similarity or AI.

### `HKLEG-RECON-STF-FIX-011` — matching prescribed form

The form number, title, parent reference, Parts, field labels, control types,
choice groups and options, instructions, dependencies, declarations,
signature blocks, dates, prescribed wording, and order match in XML and the
applicable PDFs. Both authentic-language structures align officially.

Expected result: `PASS`. Render the official blank form structure without
inventing answers or selected choices.

### `HKLEG-RECON-STF-FIX-012` — form spacing differs without structural change

The authentic form uses different field widths, dotted-line lengths, box
sizes, line wrapping, pagination, or page placement, but every official field,
control, label, instruction, dependency, choice, declaration, and order aligns.

Expected result: `PASS` when those differences are enumerated as presentation
and reported. Visual coordinate equality is not required.

### `HKLEG-RECON-STF-FIX-013` — form content or order mismatch

Complete evidence omits, adds, changes, or reorders a field, label, control,
instruction, option, conditional dependency, declaration, certification,
signature requirement, date field, or prescribed statement.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. The pipeline
cannot fabricate a missing control or treat it as empty spacing.

### `HKLEG-RECON-STF-FIX-014` — unknown span or form-control construct

An XML table-span, row-group, form-control, dependency, or other structural
construct is unknown under the pinned schema and interpretation mapping.

Expected result: `BLOCK` with `SOURCE_CONTRACT_REVIEW_REQUIRED` under ADR
0028. Preserve the input, pause affected new processing, and do not guess its
meaning. A later reviewed mapping and fixture version may permit processing.

### `HKLEG-RECON-STF-FIX-015` — legal visual relationship cannot be represented faithfully

The evidence consistently shows a visual or spatial relationship that carries
legal meaning, but the accepted deterministic plain-text grammar cannot
preserve that relationship without ambiguity or invention.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Preserve the
complete source evidence. Do not flatten the structure or substitute a prose
summary. ADR 0037 defines the image-specific source treatment.

### `HKLEG-RECON-STF-FIX-016` — safe structure-aligned split

An overlong bilingual Schedule, table, or form has corresponding official
boundaries at complete Schedule units, table rows or inseparable row groups, or
form Parts or field groups. Every serving part fits after repeating the exact
required bilingual location, headings, units, instructions, dependencies, and
parent context.

Expected result: `PASS` only for the deterministic longest-consecutive-group
split required by ADR 0021. A structure with no faithful smallest split unit
follows `FIX-015` and enters Quarantine. A renderer that ignores an available
safe boundary produces a blocked invalid candidate until corrected.

## Consequences and remaining catalogue groups

Schedules, tables, and forms now have stable location, rendering, bilingual
alignment, and splitting examples. The target is a legally faithful plain-text
representation, not a visual replica or AI-generated description.

ADR 0037 settles footnotes, statutory and publisher notes, images, and cross-
references. ADR 0038 settles partial status and general bilingual structural
mismatch. ADR 0040 subsequently settles recursive general overlong-record
partitioning. ADR 0041 settles the common machine-readable package and catalogue
contract. Exact executable pinned-schema bytes remain later implementation work
and cannot change these accepted IDs or outcomes.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
