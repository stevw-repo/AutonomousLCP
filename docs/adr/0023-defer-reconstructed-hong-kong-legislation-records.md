---
status: accepted
date: 2026-08-11
amended_by:
  - 0029
  - "0079"
  - "0080"
  - "0081"
amends:
  - 0019
refines:
  - 0005
  - 0012
  - 0022
---

# Defer reconstructed Hong Kong legislation records

## Later decision

ADR 0080 supersedes this deferral. Exact evidence-bound reconstructed
consolidations may now be materialized and selected as ordinary Hong Kong
Legislation Search Records with the approved mandatory warning. This document
remains the historical record of the earlier safe state. ADRs 0079 and 0081 now
supply the warned latest-applicable-HKeL fallback whenever ADR 0080
reconstruction cannot pass.

The paragraphs below record the former design and are retained only as the
rationale that ADR 0080 superseded. Under the current design, ADR 0081 permits
either matching verified or assisted official HKeL copies across covered
scopes and for the reconstruction base.

The former Hong Kong Legislation design did not reconstruct consolidated
legislative text from Gazette instruments, amendment instructions, or Legal
Status Events. It waited for matching HKeL English and Traditional Chinese XML
and the then-applicable copy evidence before new or changed consolidated text
could become searchable.

This rule applies to both internal and serving artifacts. The pipeline does not
materialize reconstructed consolidated text as a shadow version, Official
Version, Search Record, `metadata.text`, embedding input, Corpus Release,
Desired-State Inventory entry, or Pinecone record. An authority note cannot
turn stale or derived wording into supported current text. Under ADR 0079, an
authority note may instead identify unchanged last-verified official wording
as a known-stale analytical record; it still does not make that wording
current.

## Events are not reconstructed text

The pipeline may still become aware of legal change before HKeL publishes the
matching consolidation. It may:

- preserve Gazette instruments and other accepted event evidence;
- create evidence-backed Legal Status Events;
- record commencement and observation dates separately;
- map an event to the exact affected Legal Items and Legal Locations; and
- preserve structured amendment operations for audit and later comparison.

These actions record what happened and where it matters. They do not apply the
operations to an older HKeL version or claim what the resulting consolidated
wording is.

If accepted event evidence proves that an amendment has commenced but matching
applicable HKeL consolidated-text evidence is not available, the pipeline
records the event and exact affected locations and publishes a Coverage Gap.
It does not create the unavailable current wording. Instead, ADR 0079 requires
a warned `KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` record for every affected
location for which valid last-verified official text is held. The text remains
unchanged official wording and must never be presented as current. If no such
text exists, there is no record to create and the Coverage Gap remains visible
without reconstructed text.

## Future option remains open

This is a deliberate deferral, not a permanent rejection of reconstruction.
Ask.Legal may later decide to place reconstructed records in searchable
Pinecone. Nothing in the current design authorizes that behavior.

Enabling it requires a new explicit accepted ADR that changes this decision
and the affected contracts. At minimum, that decision must define:

- how reconstructed records are unmistakably labelled as derived rather than
  source-published HKeL text;
- whether they use a separate material type, index, namespace, or query path;
- how the six-field serving contract prevents the downstream LLM from
  confusing reconstructed and verified text;
- the authority-note, review, release, approval, replacement, and retirement rules;
- a deterministic bilingual amendment engine with exact effective-date and
  event-order handling;
- unsupported-operation and ambiguity behavior;
- historical back-testing against later verified HKeL XML and PDFs, including
  exact acceptance thresholds; and
- the required changes to ADRs 0005, 0012, 0019, and 0022.

## Consequences

The searchable text may temporarily lag a proved legal event, but the system
does not hide the lag: it records the event, exposes the Coverage Gap, and
marks the retained record as last verified rather than current. This preserves
analytical usefulness while still preferring official consolidated wording
over reconstructed freshness. The architecture retains the identities, event
evidence, affected-location mappings, and approval boundaries needed to
reconsider reconstruction later without treating that future choice as
already approved.
