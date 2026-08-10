---
status: accepted
date: 2026-08-10
---

# Use a modular monorepo

The greenfield legal-database pipeline will be implemented in
`AskLegal-LegalDBPipeline` as one modular monorepo. The complete pipeline is one
product whose domain model, contracts, legal rules, approval workflow, and
end-to-end tests must evolve together; separate repositories would introduce
coordination and contract-drift costs without an established organizational
boundary.

The monorepo will still contain separately runnable and separately permissioned
applications for control, human review, source acquisition, legal processing,
and production promotion. Large legal data, evidence, releases, caches,
backups, credentials, and runtime state remain outside Git. The existing local
repositories are reference material only and do not define the target
architecture.

## Considered options

- one undifferentiated repository and application — rejected because it would
  collapse trust and credential boundaries;
- multiple repositories matching the legacy pipeline — rejected because the
  rebuild does not inherit those boundaries; and
- one repository per source or jurisdiction — rejected because it would create
  excessive coordination and fragmented ownership.

## Consequences

Repository boundaries do not provide security. Separate application identities,
secrets, networks, deployment jobs, approval checks, versioned contracts, and
automated dependency rules must enforce the intended boundaries. A component
should be extracted to a separate repository only if a real long-term team,
access, distribution, or release-lifecycle boundary emerges.
