---
status: accepted
date: 2026-08-12
refined_by:
  - "0080"
refines:
  - 0013
  - 0016
  - 0018
  - 0019
  - 0020
  - 0021
  - 0022
  - 0026
  - 0028
  - 0035
  - 0036
---

# Define note, image, and cross-reference HKeL reconciliation fixtures

The third group in the HKeL reconciliation fixture catalogue covers footnotes,
statutory notes, HKeL publisher notes, images, and cross-references. The main
purpose is to keep four different things separate:

- exact legislative text delivered in `metadata.text`;
- an English-only reliance warning clause delivered in `metadata.authority_note`;
- official publisher context preserved for evidence and review but not mixed
  into the legislation; and
- internal relationships and source facts that are never required at query
  time.

The `PASS`, `BLOCK`, and `QUARANTINE` meanings in ADRs 0035 and 0036 still
apply. `PASS` clears only the evidence-reconciliation and deterministic-
rendering gate. A later legal-status, authority-note, record, release, approval, or
promotion gate may still withhold the candidate.

## Classify a note before using it

The pipeline does not decide a note's legal character from its visual style or
from the word “note”. The pinned HKeL Publication Specification Bundle and the
Hong Kong Legislation Source Rulebook must classify it into one of these
categories:

| Category | Meaning | Serving treatment |
|---|---|---|
| Statutory note | The note is part of the legislation or prescribed legal structure | Preserve its exact bilingual wording and attachment in `metadata.text` |
| HKeL publisher note | HKeL supplies official explanatory, editorial, navigation, or source context that is not legislative text | Preserve it in evidence and internal traceability; exclude it from `metadata.text` |
| Material reliance note | Non-legislative publisher context reveals a limitation that materially affects safe reliance on the record | Do not copy it into the law; require an approved controlled English warning clause in `metadata.authority_note` or withhold the record |
| Unknown | The pinned specification and rulebook do not establish the note's category or effect | `BLOCK` and open Source Contract Review |

A material reliance note is a consequence category, not permission to copy a
publisher's prose into `metadata.authority_note`. The Legal Desk must approve the
controlled English warning required by ADRs 0013 and 0020. The warning remains
separate from `metadata.text` and from embeddings. A record with no applicable
authority note continues to carry the exact string `"None"`.

An inline HKeL publisher note is also different from an **HKeL Editorial
Record** under ADR 0026. The Editorial Record proves its stated official
editorial event. It is never inserted into `metadata.text`; the reconciled
updated legislation supplies the searchable wording.

## Keep note markers and bodies attached

A statutory footnote marker, its body, its official order, and the location it
qualifies form one source relationship. The canonical renderer preserves all
of them. Splitting must keep the marker and complete body in the same Search
Record serving part as the material it qualifies, with any necessary repeated
parent context. If that cannot fit under the embedding contract without an
unsafe cut, no candidate is produced under this fixture group; the later
general overlong-record rules must decide whether a faithful larger split is
possible.

The renderer does not renumber footnotes, move a footnote to a different
location, combine several notes, or turn a note into an unlabelled paragraph.
Each authentic language independently reconciles with its applicable PDF, and
the official bilingual note relationships must align.

## Preserve only source-supported image meaning

Images fall into four treatment classes:

- decorative logos, seals, borders, ornaments, and other enumerated
  presentation-only images are excluded from serving text and reported;
- official captions and legends are source text and are preserved exactly;
- where HKeL explicitly supplies structured official text as a complete
  equivalent of a meaningful diagram, map, plan, symbol set, or formula, the
  renderer uses that official text and preserves the image as evidence; and
- where a meaningful image has no complete official textual equivalent, the
  affected location enters Quarantine because the downstream LLM can receive
  only text metadata.

An **official textual equivalent** must be supplied by the publisher and
explicitly mapped as complete by the pinned specification and rulebook. OCR,
AI-generated alt text, a reviewer summary, or a convenient nearby paragraph is
not an official textual equivalent. Separate human research tools may use OCR
or other assistance outside the automated pipeline, but their output cannot
become source proof or searchable legal wording.

A required image asset that is absent, unreachable, truncated, or unreadable
is missing evidence and therefore blocks. A present image that consistently
contains meaning which the accepted text grammar cannot represent is a
faithful-source limitation and therefore enters Quarantine. These are not the
same failure.

## Preserve cross-reference words; resolve targets internally

Every cross-reference keeps the exact official referring words in
`metadata.text`. The pipeline separately resolves its target, when possible,
through official item, version, location, and structural identifiers. That
evidence-backed relationship lives in the Management Register and Record
Traceability Lookup. It is not a query-time join and the target's wording is
not pasted into the referring record.

The pipeline does not silently expand, modernize, repair, or “correct” an
apparently old or mistaken reference. If XML, PDF, English, and Traditional
Chinese evidence point to different official targets, the affected candidate
enters Quarantine. If the exact source reference reconciles but its target
cannot be resolved, reconciliation may still pass with an internal
`UNRESOLVED_REFERENCE` relationship state. The source text remains unchanged.

An unresolved relationship then receives a separate record-eligibility
decision. If the inability to identify the target materially affects safe
standalone use, the record is blocked until the Legal Desk approves an English
authority note or withholds it. If the target is intentionally outside the corpus,
the record may pass while explicitly recording that Ask.Legal makes no target-
coverage claim. Being outside scope does not by itself create an authority note.

## Accepted note, image, and reference fixtures

### `HKLEG-RECON-NIR-FIX-001` — matching statutory footnote

The pinned rulebook classifies the footnote as legislative text. Its marker,
body, wording, numbering, order, attachment, and bilingual relationship match
between each XML and applicable PDF.

Expected result: `PASS`. Preserve the exact statutory note in
`metadata.text` at the location it qualifies.

### `HKLEG-RECON-NIR-FIX-002` — statutory footnote relationship differs

Complete evidence disagrees on a statutory footnote's marker, body, number,
order, or attachment to the legal material it qualifies.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Do not move,
renumber, merge, or select one representation.

### `HKLEG-RECON-NIR-FIX-003` — required footnote evidence is missing

A required footnote body, authentic language, applicable PDF evidence, or
other artifact needed to prove the complete note relationship is unavailable
or incomplete.

Expected result: `BLOCK` under `HKLEG-CURRENT-EVID-003`. No monolingual or
marker-only candidate is produced.

### `HKLEG-RECON-NIR-FIX-004` — non-legislative HKeL publisher note

The pinned specification and rulebook explicitly classify an HKeL note as
publisher context rather than legislation, and the legal text reconciles
without it.

Expected result: `PASS`. Exclude the note from `metadata.text`, preserve its
exact evidence and classification internally, and report the projection.

### `HKLEG-RECON-NIR-FIX-005` — publisher note materially qualifies reliance

A non-legislative HKeL note reveals a limitation that materially affects safe
reliance on the otherwise reconciled record.

Expected result: source reconciliation may pass, but record eligibility is
`BLOCK` until the Legal Desk approves the controlled English
warning clause in `metadata.authority_note` or chooses to withhold the record.
Do not paste the raw note
into legislation text or automatically use it as the authority note.

### `HKLEG-RECON-NIR-FIX-006` — note category or legal effect is unknown

An observed note construct cannot be reliably classified as legislative text,
publisher context, or material reliance context under the pinned bundle.

Expected result: `BLOCK` with `SOURCE_CONTRACT_REVIEW_REQUIRED` under ADR
0028. Preserve it and do not infer its meaning from style, wording, or AI.

### `HKLEG-RECON-NIR-FIX-007` — statutory note remains attached during splitting

The source evidence reconciles and an available structure-aligned split keeps
the complete statutory footnote marker and body with the material it qualifies
in both authentic languages.

Expected result: `PASS` for that relationship. A split that separates them is
an invalid blocked candidate. If no safe fitting boundary exists, produce no
candidate until the general overlong-record fixture group supplies a permitted
outcome.

### `HKLEG-RECON-NIR-FIX-008` — decorative image

The pinned rulebook classifies a logo, seal, border, ornament, or other image
as presentation-only and its removal changes no legal wording, relationship,
or identity.

Expected result: `PASS`. Exclude it from serving text and report the exact
asset and projection rule.

### `HKLEG-RECON-NIR-FIX-009` — matching official caption or legend

An official image caption or legend is source text, and its wording, order,
attachment, and bilingual relationship reconcile with the applicable PDFs.

Expected result: `PASS`. Preserve the exact official wording in
`metadata.text` at the location it qualifies.

### `HKLEG-RECON-NIR-FIX-010` — required image asset is missing

XML or another required source representation refers to an image needed to
understand or verify the legal material, but the asset is absent, unreachable,
truncated, or unreadable.

Expected result: `BLOCK` under `HKLEG-CURRENT-EVID-003`. Do not substitute OCR,
alt text, a thumbnail, or a generated description.

### `HKLEG-RECON-NIR-FIX-011` — complete official textual equivalent exists

A meaningful source image and its applicable PDFs reconcile, and HKeL
explicitly supplies a complete structured textual equivalent mapped by the
pinned specification and rulebook.

Expected result: `PASS`. Use the exact official textual equivalent in the
canonical record and preserve the image as evidence. AI and OCR are not the
equivalent.

### `HKLEG-RECON-NIR-FIX-012` — meaningful image has no faithful official textual equivalent

Complete consistent evidence shows that a map, plan, diagram, symbol, formula,
or other image carries legal meaning, but HKeL supplies no complete official
text that the accepted serving grammar can faithfully use.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Preserve the
image and related evidence; do not invent searchable prose.

### `HKLEG-RECON-NIR-FIX-013` — image identity, caption, legend, or language conflict

Complete evidence disagrees on the required image asset, its caption or
legend, its attachment, or the official relationship between authentic-
language image structures.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Visual
similarity, translation similarity, OCR, and AI cannot repair the conflict.

### `HKLEG-RECON-NIR-FIX-014` — matching resolvable cross-reference

The exact cross-reference words reconcile in each authentic language, official
identifiers establish the same source-supported target, and the bilingual
structures align.

Expected result: `PASS`. Preserve the exact referring words in
`metadata.text` and record the resolved relationship internally without
copying target wording into the record.

### `HKLEG-RECON-NIR-FIX-015` — cross-reference target conflict

XML, PDF, English, or Traditional Chinese evidence points to a different item,
version, location, or structural target.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Do not choose the
apparently current target or repair the reference through translation.

### `HKLEG-RECON-NIR-FIX-016` — exact source reference cannot be resolved

The cross-reference wording and source structure reconcile, but the target
cannot be identified from accepted official identifiers.

Expected result: reconciliation `PASS` with an internal
`UNRESOLVED_REFERENCE` relationship state. Preserve the exact source words.
Record eligibility is separately blocked only when the unresolved target
materially affects safe use, pending an approved authority note or withholding
decision.

### `HKLEG-RECON-NIR-FIX-017` — target is intentionally outside corpus coverage

The exact official cross-reference reconciles and its target is known, but the
target is outside the accepted Ask.Legal corpus or Release Scope coverage.

Expected result: `PASS`. Preserve the reference, record the target and explicit
out-of-scope status internally, and make no claim that the target is searchable.

### `HKLEG-RECON-NIR-FIX-018` — renderer expands, rewrites, or corrects a reference

Source evidence reconciles, but candidate construction pastes target wording
into the referring record, modernizes a citation, rewrites it, or silently
“corrects” its target.

Expected result: `BLOCK` as a deterministic processing defect. Correct the
renderer without changing the preserved source evidence or treating the defect
as a source conflict.

## Consequences and remaining catalogue groups

Notes, images, and cross-references now have stable classification, serving,
authority-note, evidence, and relationship examples. Exact source words remain
separate from controlled authority-note clauses, publisher context, and internal target
resolution. The pipeline never asks AI to invent a text equivalent for
non-text law.

ADR 0038 settles partial legal status and general bilingual structural
mismatch. ADR 0040 subsequently settles recursive general overlong-record
partitioning. ADR 0041 settles the common machine-readable package and catalogue
contract. Exact executable pinned-schema bytes remain later implementation work
and cannot change these accepted IDs or outcomes.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
