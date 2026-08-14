---
status: accepted
date: 2026-08-11
amends:
  - 0011
  - 0015
---

# Use jurisdiction-specific Principles terminology

The canonical material-family name for publisher-derived secondary legal
material is **Principles**, always qualified by jurisdiction when naming a
scope, profile, desk, rulebook, release, report section, or configuration.
Examples include:

- **Australian Principles**;
- **Singapore Principles**;
- **United Kingdom Principles**; and
- **Hong Kong Principles**.

The system must not define one general cross-jurisdiction “Reference Works”
material family, Release Scope, or source rulebook. Each jurisdiction's
Principles has its own Registered Sources, coverage promise, Legal Desk,
source rulebook, Release Scopes, Corpus Releases, and evidence requirements.

## Record and source terminology

- **Principles** is the jurisdiction-specific material family.
- A **Principle** is one source-faithful paragraph or deterministic serving
  part derived from an approved publisher source.
- A **Principles Title** is one independently publisher-maintained title or
  work tracked as a Legal Item.
- A publisher collection or platform may group several Principles Titles but
  is not itself one Legal Item merely because it hosts them.
- A Principle remains a Pinecone Search Record with `metadata.type` equal to
  `"principle"`; `metadata.jurisdiction` identifies the jurisdiction.

“Reference work” may still be used in ordinary prose to describe the kind of
publisher source. It is not the canonical material-family, profile, scope, or
rulebook name.

Case-derived material remains separate. A judicial **Case Proposition** is not
a Principle, even when both express a legal rule.

## Shared rules and jurisdiction ownership

ADR 0015's publisher-evidence-backed identity, paragraph continuity, authority-note,
withholding, and licence-expiry-freeze rules remain the shared Principles
continuity policy. They are applied separately by each jurisdiction's
Principles rulebook.

For example, Australian Principles and Singapore Principles may use the same
general rule for a paragraph split while relying on different publisher IDs,
edition evidence, update feeds, currency notices, and checking schedules. One
jurisdiction's successful source check cannot prove another jurisdiction's
Principles complete or current.

Licence expiry creates a **Frozen Principles Scope** for only the affected
jurisdiction and source scope. It does not freeze or change another
jurisdiction's Principles.

## Consequences

Source registers, rulebooks, release-scope registries, schemas, reports,
evaluations, and configuration use jurisdiction-qualified Principles names.
Shared code may implement common Principles behavior, but ownership,
completeness, evidence, and releases remain jurisdiction-specific.

The existing ADR 0015 filename retains “reference-work” as historical context;
its accepted terminology and application are amended by this decision.
