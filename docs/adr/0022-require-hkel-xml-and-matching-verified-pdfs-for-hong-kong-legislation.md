---
status: accepted
date: 2026-08-11
amended_by:
  - 0029
  - 0032
  - "0080"
  - "0081"
amends:
  - 0019
refines:
  - 0012
  - 0021
depends_on:
  - 0018
---

# Require HKeL XML and matching verified PDFs for Hong Kong legislation

## Later decision

ADR 0081 supersedes the verified-only evidence gate below. Matching official
HKeL assisted copies may now support ordinary current records and ADR 0080
reconstruction across the covered Hong Kong Legislation scopes. Complete
bilingual XML-to-copy reconciliation remains mandatory. This document remains
the historical record of the stronger earlier rule.

Every new or changed current-law Search Record constructed from Hong Kong
e-Legislation (HKeL) requires two representations of the same official
material:

1. the matching English and Traditional Chinese HKeL XML, used to construct
   the record deterministically; and
2. the corresponding English and Traditional Chinese HKeL verified PDF copies,
   used as the legal-text and version evidence.

Neither representation is sufficient by itself. XML is structured and
machine-readable, so it is the reliable operational input for inventories,
language pairing, Legal Location boundaries, change detection, canonical
`metadata.text`, and structure-aligned splitting. Only a verified HKeL PDF
bearing the verification mark has the stated legal status. The PDF proves that
the XML-built payload corresponds to the verified official copy; it is not the
serving payload.

This is the mandatory current-text rule for HKeL-derived Ordinances and
subsidiary legislation. It also applies to an item in the constitutional-and-
other-instruments scope when HKeL supplies matching verified copies. It does
not make an informational Basic Law portal page a serving-text source. Each
remaining constitutional or other instrument still requires its own accepted
source assignment. ADR 0029 supplies the narrow exception that allows matching
official HKeL assisted copies for eligible constitutional or other instruments
when verified copies are unavailable.

ADRs 0080 and 0081 add the publication-lag reconstruction path and permit its
base bundle to use matching verified or assisted official HKeL copies. The
result is not another HKeL Official Version, but it follows ordinary serving
rules with the mandatory reconstruction authority note.

## Dual-representation evidence bundle

For each applicable Official Version, the acquisition and processing flow is:

1. capture the complete current English and Traditional Chinese inventories;
2. capture the corresponding XML files and required assets, preserve their
   source metadata and hashes, and validate them against the pinned HKeL data
   model;
3. capture the matching English and Traditional Chinese verified PDFs and
   prove that each bears the verification mark;
4. build the canonical bilingual candidate payload from the XML under ADR
   0021;
5. compare each XML language deterministically with its corresponding verified
   PDF, and confirm that the two languages identify the same instrument,
   version, Legal Location, and operative state;
6. preserve the XML, PDFs, parsing results, mappings, hashes, and comparison
   report as one evidence bundle; and
7. make only a successfully reconciled candidate eligible for normal
   validation, release construction, and eventual promotion.

The Evidence Vault retains the exact captured files. The Record Traceability
Lookup contains only pointers and fingerprints connecting each Search Record
to its evidence bundle; it does not duplicate the files or enter the ordinary
Ask.Legal query path.

## Deterministic reconciliation

The comparison is legal-content and structure equality, not byte-for-byte file
equality. PDF page layout naturally adds presentation details that the XML does
not share. A versioned reconciliation contract may ignore only enumerated
presentation-only differences, such as known page headers and footers, line
wrapping, and pagination. It must not ignore or approximately match legal
content.

The reconciliation proves, where applicable:

- instrument title, chapter, citation, and other official identifiers;
- Official Version identity and date, including relevant Part or Schedule
  update dates and remarks;
- provision or structural locator and heading;
- exact wording, punctuation, numbering, order, lead-ins, continuations, and
  relevant footnotes;
- lists, tables, forms, Schedules, annexes, and other legally meaningful
  structures; and
- alignment of the English and Traditional Chinese versions.

Fuzzy similarity, translation inference, or an AI model cannot establish this
equality. An implementation may automate PDF extraction and propose a mapping,
but the accepted deterministic rules and conformance fixtures must decide
whether the comparison passes. A structure that cannot be verified faithfully
is quarantined for the Hong Kong Legislation Legal Desk.

## Failure and reuse rules

The rule fails closed:

| Evidence result | Outcome |
|---|---|
| Both XML languages and both matching verified PDFs reconcile | The candidate may proceed to the remaining validations |
| XML is newer but a matching verified PDF is absent or older | Block the candidate; XML alone cannot prove the current verified text |
| A verified PDF is newer but the matching XML is absent or older | Block the candidate; the pipeline cannot construct the deterministic payload from stale XML |
| English and Traditional Chinese identify different versions or cannot be structurally aligned | Quarantine; no monolingual fallback |
| A PDF lacks the verification mark | Treat it as insufficient for this verified-copy rule; ADR 0029 may separately admit an official HKeL assisted copy for an eligible constitutional or other instrument |
| A table, form, Schedule, footnote, or other material structure cannot be reconciled | Quarantine the affected candidate and account for it under the unavailable-scope rules |
| A new verified Official Version has an exactly unchanged six-field payload | Create the new Official Version; reuse the Search Record only when exact payload equality and continuing legal support are proved under ADRs 0011 and 0012 |

A mismatch is never silently accepted, corrected by AI, or converted into a
supported no-change result. The affected item remains visibly accounted for in
Quarantine or the unavailable-scope process. Unrelated clear material may
continue only when the complete Release Scope accounting remains valid.

## Serving boundary

The canonical bilingual text built from reconciled XML is the only part of
this bundle that can enter `metadata.text`, embeddings, Pinecone, and the
downstream LLM request. PDF bytes, PDF-extracted text, XML markup, source URLs,
verification marks, comparison reports, and internal mappings remain outside
the six-field serving record.

This separation keeps the query record small and deterministic without asking
the downstream LLM to decide whether the source was authoritative. The
pipeline makes and proves that decision before release construction.

## Consequences and remaining work

ADR 0032 assigns the stable IDs `HK-LEG-HKEL-CURRENT-INVENTORY`,
`HK-LEG-HKEL-CURRENT-DATA`, and `HK-LEG-HKEL-VERIFIED-COPIES`. The small
inventory supplies routine change and completeness signals; full XML and PDFs
are acquired only when affected work requires them. All roles remain bound to
complete bilingual reconciliation, bounded retries, and explicit Quarantine
outcomes.

Implementation still requires executable pinned-schema XML fixtures, concrete
PDF extraction and verified-mark checks. ADRs 0035 through 0037 settle ordinary
provisions; Schedules, tables, forms, notes, images, and cross-references. ADR
0038 settles partial status and general bilingual structural mismatch. ADR 0040
settles recursive general overlong partitioning. Remaining details may refine execution,
but outside ADR 0029's narrow constitutional-instrument exception they cannot
make an unverified representation sufficient, permit fuzzy legal-text
matching, put PDF material in the serving record, or remove either authentic
language.

Later decisions settle HKeL past data and Editorial Records in ADR 0026,
Gazette evidence and detailed event rules in ADR 0025, and the exclusion of
LegCo Bills and proceedings in ADR 0027. ADR 0028 settles the pinned HKeL
publication-specifications interpretation role. Item-specific constitutional
assisted-copy evidence is settled in ADR 0029; item-by-item instrument
disposition remains Source Rulebook work.
