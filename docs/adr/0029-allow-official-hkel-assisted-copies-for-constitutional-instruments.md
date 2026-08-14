---
status: accepted
date: 2026-08-11
amends:
  - 0019
  - 0022
  - 0023
  - 0024
  - 0025
  - 0026
  - 0027
depends_on:
  - 0018
  - 0021
  - 0028
amended_by:
  - 0030
  - 0032
  - "0081"
refined_by:
  - "0080"
---

# Allow official HKeL assisted copies for constitutional instruments

The `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` Release Scope may use
official Hong Kong e-Legislation (HKeL) assisted copies as current-text and
version evidence when HKeL does not provide matching verified copies for the
same item and version.

This is a deliberate Ask.Legal product-evidence threshold. Ask.Legal provides
legal analysis rather than legal advice, and the product does not require every
constitutional Search Record to be proved by a verified copy. The pipeline
records the assisted status accurately; it does not claim that an assisted copy
has the statutory status of a verified copy.

The official [HKeL Important Notices](https://www.elegislation.gov.hk/importantnotices)
distinguish verified copies with legal status from reference-only formats. This
decision preserves that factual distinction while choosing a less restrictive
Ask.Legal serving threshold for the limited scope below.

The exception is narrow:

- it applies only to the constitutional-and-other-instruments scope;
- when HKeL supplies matching verified copies, ADR 0022 remains the applicable
  rule;
- Ordinances and subsidiary legislation continue to require matching verified
  copies under ADR 0022; and
- a non-HKeL webpage, unofficial reproduction, search result, or convenient
  portal transcription does not become sufficient merely because an official
  HKeL assisted copy is sufficient within this scope.

## Registered Source roles

The Hong Kong Legislation Source Rulebook registers these distinct roles:

- `HK-LEG-HKEL-CURRENT-INVENTORY` supplies the small current inventory,
  language-resource, version, status-signal, locator, and hash feed;
- `HK-LEG-HKEL-CURRENT-DATA` supplies matching English and Traditional Chinese
  machine-readable text and structure when affected work requires it;
- `HK-LEG-HKEL-VERIFIED-COPIES` proves items and versions for which HKeL
  supplies matching bilingual verified copies;
- `HK-LEG-HKEL-CONSTITUTIONAL-ASSISTED-COPIES` supplies matching official HKeL
  English and Traditional Chinese assisted copies for eligible constitutional
  or other instruments without verified copies; and
- `HK-LEG-BASIC-LAW-PORTAL` supplies discovery, scope inventory, links, and
  cross-check signals for the Basic Law, Annex III, and related national and
  Hong Kong instruments. The portal does not construct serving text.

NPC, NPCSC, National Laws and Regulations Database, Gazette, or other official
material may supply item-specific status evidence and cross-checks under the
Source Rulebook. The same Source Snapshot may support more than one separately
recorded fact when its contents actually prove those facts. The design does not
require three different files merely to prove national wording, Annex III
listing, and Hong Kong promulgation when one accepted HKeL instrument contains
the applicable wording and promulgation evidence.

## Assisted-copy evidence path

For an eligible item without verified copies, the pipeline:

1. captures the complete HKeL current inventory and identifies the exact item,
   type, version, status, and language resources;
2. captures matching English and Traditional Chinese XML and required assets;
3. captures the corresponding English and Traditional Chinese HKeL assisted
   copies and records that they are assisted rather than verified;
4. validates the XML against the pinned HKeL Publication Specification Bundle;
5. constructs the canonical bilingual candidate from the XML under ADR 0021;
6. reconciles each XML language with the matching assisted copy and proves that
   both languages identify the same item, version, Legal Location, and status;
   and
7. preserves the inputs, fingerprints, mappings, source classification, and
   comparison report as one immutable evidence bundle.

Reconciliation remains deterministic and content-sensitive. The absence of a
verification mark is permitted for this path, but missing text, version
differences, conflicting language pairs, unexplained wording differences, or
uncheckable legal structures are not. Fuzzy matching or AI judgment cannot
silently repair a mismatch.

This decision does not create a PDF-only construction path. If a covered item
has no usable matching XML, it remains explicitly unavailable until a separate
accepted deterministic construction rule is defined.

## Changes, cross-checks, and conflicts

The Watcher reconciles the complete HKeL constitutional-and-other-instruments
inventory and resource fingerprints. A new, changed, removed, or reclassified
constitutional item opens affected-item review rather than being silently
published. The review determines the item identity, current status, affected
Legal Locations, bilingual alignment, and whether the change represents a new
Official Version or Legal Status Event.

The Basic Law portal and available national-authority material are useful
independent change and discrepancy signals. Their temporary absence does not
make an otherwise complete HKeL assisted-copy bundle invalid. A detected
conflict does block the affected item until the Hong Kong Legislation Legal
Desk resolves it from preserved evidence. Unrelated clear items may continue
subject to complete Release Scope accounting.

If HKeL later provides verified copies for an item previously supported by
assisted copies, the pipeline captures and reconciles them. Exact serving-
payload equality permits the existing Search Record to remain while the
register and traceability lineage append the stronger evidence. A wording,
version, status, or structure difference follows the ordinary changed-record
and Quarantine rules.

## Serving and authority-note boundary

Only the canonical bilingual text constructed from reconciled HKeL XML enters
`metadata.text`, embeddings, Pinecone, and the downstream LLM request. Source
files, assisted or verified labels, URLs, XML markup, comparison reports, and
traceability data remain outside the serving record.

Use of an eligible official HKeL assisted copy does not by itself create a
authority note. If no separate substantive note applies,
`metadata.authority_note` remains the literal string `"None"`. A genuine legal-
status, treatment, currency, or reliance issue continues to use the ordinary
authority-note warning clause,
Quarantine, or withholding rules.

ADR 0081 broadens this earlier exception. Official HKeL assisted copies may now
support ordinary current records and `RECONSTRUCTED_CONSOLIDATION` across the
covered Hong Kong Legislation scopes. The evidence label remains preserved
internally, but assisted status alone creates no special serving treatment.

## Consequences

The Basic Law and eligible Annex III or other HKeL instruments are not excluded
from search merely because HKeL labels their official copies as assisted. They
remain subject to complete inventory accounting, bilingual pairing, exact
version matching, deterministic reconciliation, status review, immutable
evidence preservation, release validation, and the single frozen promotion
approval.

ADR 0030 settles the versioned Instrument Disposition Registry, legal-nature
routing, primary-disposition, relationship, authority-note, and complete-
reconciliation rules. Populating and legally reviewing every current
Instruments & Others row remains concrete Source Rulebook work. The assisted-
copy path applies only after that registry identifies an eligible genuine
constitutional or other item; an A-series Ordinance or subsidiary instrument
continues to require the verified-copy path.

This decision does not authorize source acquisition, implementation,
publication, Pinecone mutation, or deployment. Source-specific legal
compliance remains deferred to the legal team under the project's accepted
assumption.
