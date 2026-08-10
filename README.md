# AskLegal Legal Database Pipeline

This repository is the greenfield modular monorepo for Ask.Legal's autonomous
legal-database pipeline.

The intended system checks official legal sources, preserves exact evidence,
assesses supported legal status, prepares validated search records, obtains one
human approval for the complete frozen update, and keeps Ask.Legal's searchable
legal corpus aligned with that approval.

## Current status

**Design only. No application code or technical stack has been selected.**

The repository currently contains the initial overall design and durable
briefing files. Documentation does not authorize source access, AI or embedding
calls, corpus publication, Pinecone access, pruning, backup mutation,
deployment, routing changes, or any other remote action.

## Start here

1. [`AGENTS.md`](AGENTS.md) — mandatory operating instructions.
2. [`docs/agent/CONTEXT.md`](docs/agent/CONTEXT.md) — stable domain language.
3. [`docs/agent/DECISIONS.md`](docs/agent/DECISIONS.md) — settled decisions.
4. [`docs/agent/WORKING_STATE.md`](docs/agent/WORKING_STATE.md) — current
   objective and exact next step.
5. [`docs/adr/0001-use-a-modular-monorepo.md`](docs/adr/0001-use-a-modular-monorepo.md)
   — accepted repository architecture.
6. [`docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`](docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md)
   — comprehensive initial design of the intended system.

## System shape

```mermaid
flowchart LR
    S["Official legal sources"]
    A["Acquire and preserve evidence"]
    D["Apply jurisdiction and material rules"]
    P["Prepare validated legal records"]
    C["Build the complete desired corpus"]
    R["Human reviews one frozen package"]
    V["Build and verify the approved serving state"]
    Q["Ask.Legal search"]

    S --> A --> D --> P --> C --> R --> V --> Q
```

## Planned monorepo shape

```text
AskLegal-LegalDBPipeline/
├── apps/
│   ├── control-plane/
│   ├── review-web/
│   ├── acquisition-worker/
│   ├── legal-processing-worker/
│   └── promotion-worker/
├── packages/
│   ├── domain/
│   ├── contracts/
│   ├── management-register/
│   ├── evidence-vault/
│   ├── source-connectors/
│   ├── legal-desks/
│   ├── processing/
│   ├── corpus/
│   ├── promotion/
│   ├── reporting/
│   └── observability/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── end-to-end/
│   └── legal-evaluations/
├── docs/
├── infra/
├── tools/
└── var/                 # ignored local runtime data only
```

The directories above describe the accepted target structure. They will be
created only when implementation is explicitly authorized.

## One repository, several security boundaries

The control plane, review application, acquisition worker, legal-processing
worker, and promotion worker are separate runnable applications. They may have
different identities, credentials, network access, scaling, and deployment
jobs even though their source code lives together.

In particular:

- acquisition cannot approve or deploy;
- legal processing cannot mutate production search;
- the review application cannot substitute different records;
- the control plane does not possess destructive production credentials; and
- only the promotion worker may apply the exact approved serving change.

## Information lives in three places

```text
Management register = what the system believes and is doing
Evidence vault      = what proves and can reproduce it
Pinecone            = what Ask.Legal currently searches
```

Git contains code, schemas, prompts, small fixtures, evaluation definitions,
infrastructure configuration, and documentation. Full legal corpora, source
snapshots, Corpus Releases, embedding caches, operational reports, backups,
credentials, and production state remain outside Git.

## Greenfield boundary

The older local Distillation, Release Store, Pinecone, and coordinator
repositories are reference material only. This repository does not inherit
their repository boundaries, internal contracts, schema, or implementation
automatically. A legacy idea may be reused only through an explicit current
decision and fresh validation.

## Design scope

The overall design describes the intended complete system and keeps unresolved
choices visible. It intentionally excludes pilot scope, staged product
versions, rollout planning, estimates, temporary operating arrangements, and
migration sequencing.
