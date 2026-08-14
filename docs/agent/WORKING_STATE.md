# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-15

## Current objective

Preserve the complete validated implementation-neutral cross-cutting contract
foundation in one local checkpoint commit. Stop before production-stack
selection or application implementation.

## Current result

The required local foundation is complete. Its final repository-wide
completion audit passed.

ADR 0088 establishes `contracts/` as the repository-owned machine-contract
package. It contains:

- 54 inventoried cross-cutting objects and immutable value objects;
- 13 closed Draft 2020-12 schema files covering shared primitives, source and
  evidence, legal identity, releases and desired state, serving and
  traceability, promotion and Approval, workflow admission, capabilities,
  package inventory, fixtures, and current foundation status;
- eight closed catalogues with 55 identity prefixes, 35 reference types, 10
  results, 13 reasons, 17 failures, 35 lifecycle states, five review codes,
  and 14 capabilities;
- six closed-world lifecycle machines for Approval, Serving State, capability,
  workflow admission, bounded review, and promotion execution;
- fifteen synthetic fixtures with exact expected results covering positive,
  negative, boundary, malformed-input, retry, idempotency, identity-collision,
  allowed-transition, forbidden-transition, JCS Unicode ordering, invalid
  Unicode, negative zero, and reproducibility behavior;
- an exact manifest inventorying 76 package members other than the manifest
  itself by contained path, role, media type, byte size, and SHA-256; and
- one immutable foundation-status artifact that keeps the production stack
  `UNDECIDED`, every operational capability `DISABLED`, and external effects
  `NONE`.

The package uses strict I-JSON, RFC 8785 JCS UTF-8, safe integers, canonical
UTC timestamps, semantic schema versions, and lowercase
`sha256:<64-lowercase-hex>` fingerprints. Shared register-issued IDs use a
closed three-character lowercase prefix, underscore, and 48 lowercase
hexadecimal characters. Identity never derives from a source coordinate or
content fingerprint.

## Validation

Primary command:

```sh
node tools/validate-contracts.mjs
```

Final complete result:

- PASS — Draft 2020-12 schema structure, closed objects, and all local refs;
- PASS — closed, unique, sorted catalogues and matching schema enums;
- PASS — reachable closed-world lifecycle states and explicit forbidden
  behavior;
- PASS — contract inventory ownership, schema, identity, reference,
  lifecycle, invariant, and validation-status mappings;
- PASS — all fifteen exact-result fixtures;
- PASS — contained package paths, byte sizes, hashes, and undeclared-file
  rejection;
- PASS — repository-local Markdown links, single H1 structure, and balanced
  code fences; and
- PASS — two fresh Node processes produced byte-identical package snapshots.

Validated package-manifest JCS fingerprint:
`sha256:3cd5bb87b614b12378d4af6a357d9fdb39807de33aa5045a1427e1040fb7f79a`.

The final audit also passed `node --check tools/validate-contracts.mjs` and
`git diff --cached --check`, then confirmed the exact staged checkpoint scope.
Documentation outside `contracts/` does not change the package fingerprint.

## Files added

- `contracts/README.md`
- `contracts/foundation-status.json`
- `contracts/package-manifest.json`
- `contracts/catalogues/*.json`
- `contracts/inventory/cross-cutting-contract-inventory.json`
- `contracts/schemas/*.json`
- `contracts/transitions/*.json`
- `contracts/fixtures/**`
- `tools/validate-contracts.mjs`
- `docs/adr/0088-establish-the-cross-cutting-contract-foundation.md`

## Files updated

- `README.md`
- `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`
- `docs/agent/CONTEXT.md`
- `docs/agent/DECISIONS.md`
- `docs/agent/WORKING_STATE.md` — rewritten as the current concise handoff
  instead of retaining an endless chronological diary.

## Deliberately deferred decisions

No schema default or implementation choice was made for:

- production programming language, framework, storage, or deployment stack;
- legal coverage, source authority, or jurisdiction-specific rulebook answers;
- remaining LLM-versus-deterministic allocation;
- human-review and Approval governance policy;
- user-facing coverage, warning, or authority-note behavior;
- thresholds, evaluation values, concurrency, budgets, or cost limits;
- retention, recovery, security, incident, and service-level policy;
- Azure production activation; or
- the final Pinecone index naming contract.

Schemas require an artifact to state `CONFIGURED` or `UNDECIDED`; no missing
value is interpreted as a default. Jurisdiction- and material-specific HKeL,
Hong Kong Cases, HKEX, reconstruction, and future Australian, Singapore, or
other legal artifacts remain owned by their exact Source Rulebooks and ADRs.

## Authorization state

Authorized and performed:

- local implementation-neutral schemas, catalogues, transitions, manifests,
  synthetic fixtures, exact expected artifacts, and validation tooling;
- canonical documentation, ADR, and continuity updates; and
- read-only repository inspection and local offline validation; and
- one local checkpoint commit containing exactly the validated foundation and
  its canonical documentation and continuity files.

Not authorized and not performed:

- legacy-repository inspection;
- external source or network access;
- dependency installation;
- generative-model or embedding calls;
- real corpus, release, backup, Pinecone, Azure, routing, or deployment work;
- application implementation or production-stack selection;
- push, pull request, publication, or external message; or
- destructive action.

The repository was clean before this objective on branch `main`, which was
already two commits ahead of `origin/main`. The foundation checkpoint is the
next local commit; no remote branch was changed.

## Blockers and exact next step

No consequential product decision blocks or remains inside this checkpoint.

No implementation task is active. The user expressly stopped after this first
checkpoint step. A later task may select the production stack and authorize a
local synthetic end-to-end slice; it must begin from these versioned contracts
rather than changing them implicitly.
