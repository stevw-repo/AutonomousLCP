# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-10

## Current objective

Complete the initial design of the greenfield modular monorepo before selecting
the technical stack or implementation sequence. The repository is the accepted
home of the entire rebuilt pipeline, but the design is not yet a final
specification.

## Settled repository architecture

- `AskLegal-LegalDBPipeline` is the greenfield implementation repository.
- It is one modular monorepo, not a wrapper around legacy repositories.
- The planned runnable applications are:
  - control plane;
  - human review application;
  - source acquisition worker;
  - legal-processing and AI worker; and
  - tightly restricted production promotion worker.
- Shared packages own domain language, versioned contracts, register and
  evidence interfaces, source connectors, Legal Desks, processing, corpus
  construction, promotion rules, reporting, observability, and test support.
- Application identities, credentials, network access, and deployment remain
  separate even though code is colocated.
- Large legal data and runtime state remain outside Git.
- The older local repositories are reference material only.

The accepted reasoning is recorded in
`docs/adr/0001-use-a-modular-monorepo.md`.

## Repository contents

- `README.md` — human entry point and target repository shape.
- `AGENTS.md` — mandatory agent operating instructions.
- `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md` — canonical initial
  overall-system design.
- `docs/adr/0001-use-a-modular-monorepo.md` — accepted repository decision.
- `docs/agent/CONTEXT.md` — stable domain glossary.
- `docs/agent/DECISIONS.md` — settled decisions.
- `docs/agent/WORKING_STATE.md` — this live handoff.

No application directories, dependencies, or technical stack have been created
or selected.

## Current unresolved design areas

The detailed list is in section 18 of the overall design. The highest-impact
areas are:

1. replacement serving target and Ask.Legal routing model;
2. all-at-once visibility across several jurisdiction targets;
3. exact Desired-State Inventory and Promotion Manifest contracts;
4. final query metadata and stable parent Legal Item identity;
5. source and legal-status rulebooks for each jurisdiction-and-material pair;
6. AI acceptance criteria and legal evaluation corpus;
7. backup location, retention, recovery targets, and drill frequency;
8. Approval validity, authorized reviewers, and emergency authority; and
9. anomaly, cost, capacity, Quarantine, and service-level policies.

## Recommended next discussion

Decide whether the intended system will:

1. build fresh replacement targets for every affected jurisdiction;
2. fully verify their inventory, content, and search behavior while Ask.Legal
   continues serving the previous verified target set; and
3. switch one application routing manifest to the complete new target set only
   after every target passes.

Recommendation: **yes**. This is the clearest way to make one approved update
visible as one controlled change without exposing a mixture of old and new law.
This recommendation is not yet a settled decision.

## Validation performed

- Repository documentation was rewritten around the accepted greenfield
  modular-monorepo decision.
- Legacy repository dependencies and inherited ownership assumptions were
  removed from the repository briefing files.
- The repository architecture ADR is present and linked.
- All six relative documentation links in `README.md` resolve to files.
- The overall design contains 16 Mermaid diagrams and 34 balanced Markdown
  fence lines; no Mermaid renderer is installed locally, so diagram validation
  was limited to structural and manual syntax review.
- Searches found no stale coordinator-wrapper language and no staged `v1`,
  `v2`, MVP, rollout, or implementation-phase plan. The only `v2` text is
  Mermaid's standard `stateDiagram-v2` declaration.
- Whitespace checks and `git diff --check` pass.
- The overall design remains documentation only.

## Authorization state

Documentation changes only. No application implementation, dependency
installation, commit, push, source access, AI or embedding-provider call,
Pinecone operation, backup change, deployment, routing change, or other remote
action has been performed or authorized.
