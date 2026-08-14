---
status: accepted
date: 2026-08-12
amends:
  - 0024
refines:
  - 0014
  - 0018
depends_on:
  - 0016
---

# Register HKLII as a non-controlling automated discovery source

The Hong Kong Cases Source Rulebook registers the Hong Kong Legal Information
Institute under stable source role `HK-CASE-HKLII-DISCOVERY`. The source may be
used through an automated connector for discovery, inventory cross-checking,
aliases, historical leads, citation leads, and candidate later-treatment
relationships.

This replaces ADR 0024's deferral of formal registration and automation. It
does not change ADR 0024's data-quality boundary: HKLII remains non-controlling
and is never the sole evidence for a judgment's authentic wording, Official
Version, identity, court authority, opinion attribution, legal proposition,
later treatment, authority note, or retirement.

## Exact Fact Authority

An HKLII snapshot may establish only that HKLII displayed a named candidate
item, locator, label, citation, alias, link, or candidate relationship at the
recorded observation time. It may open bounded acquisition or reconciliation
work.

Before any Case Proposition or legal-treatment decision proceeds, the pipeline
must obtain and preserve the matching originating judgment from the Hong Kong
Judiciary, relevant court registry, Judiciary Library, Privy Council artifact,
or another source expressly accepted by the Hong Kong Cases Source Rulebook.
Unmatched HKLII material remains a discovery lead; it creates no serving record
and proves no adverse treatment.

This is a technical reliability rule. It prevents a discovery index, derived
markup, generated link, incomplete copy, or delayed update from silently
becoming the legal database's source of truth.

## Monitoring and failure behavior

HKLII is a nonblocking source:

- its availability is not required to prove official-source completeness or
  supported no change;
- an outage, redesign, delay, missing result, or failed connector does not block
  an otherwise complete originating-source release;
- an observed HKLII difference opens only the affected discovery or
  reconciliation work; and
- no result may receive an authority-note revision, retirement, or
  reinstatement merely because an HKLII link appeared, disappeared, or changed.

ADR 0052 fixes how those leads behave during an ordinary update: candidate
judgment, inventory, alias, citation, and possible-treatment differences are
resolved against accepted originating evidence, evidentially dismissed, or
remain explicit affected work. They never become legal results by themselves.

The future connector must still be versioned, retryable, fingerprint-bound,
auditable, bounded in scope, and isolated from source text as instructions. Its
exact endpoints, parser, rate controls, and fixtures are implementation work.

## Legal and policy review is deferred

At the user's direction, legal, licence, copyright, policy, and permission
review of HKLII use is deferred to the legal team and is not a prerequisite to
the technical design or later implementation. The design assumes the intended
registered use is legally compliant.

This deferral removes a legal-policy clearance gate; it does not expand
HKLII's Fact Authority or make its content technically complete or official.
If later legal review requires the connector to stop, the source role can be
deactivated without invalidating serving records because no accepted record is
allowed to depend solely on HKLII.

## Consequences

The Hong Kong Cases rulebook must include the source role, permitted discovery
facts, nonblocking outage behavior, reconciliation path, and connector
conformance cases. HKLII material outside the accepted Hong Kong Cases coverage
does not enter another material family merely because the source indexes it.

This decision authorizes documentation only. It does not authorize connector
implementation, HKLII access, automated collection, source acquisition, AI or
embedding calls, release publication, Pinecone mutation, promotion, or
deployment.
