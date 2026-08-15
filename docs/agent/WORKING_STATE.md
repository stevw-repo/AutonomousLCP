# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-15

## Current objective

Transfer the complete validated repository state to a fresh Ubuntu 24.04 clone
through one durable handoff commit on the explicitly confirmed private GitHub
repository. Stop before production-stack selection or application
implementation.

## Current result

The required local foundation is complete. Its final repository-wide
completion audit passed and is preserved in foundation checkpoint
`ff8c21294eaa8746edeb1f15a72594409254d048`.

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
The last macOS validation used Node `v24.15.0`; no cross-platform production
runtime or minimum Node version has been selected.

## Ubuntu 24.04 resume checklist

Clone `https://github.com/DocLegalAI/AskLegal-LegalDBPipeline.git`, enter the
repository, and read these files in order before planning or editing:

1. `AGENTS.md`
2. `docs/agent/CONTEXT.md`
3. `docs/agent/DECISIONS.md`
4. `docs/agent/WORKING_STATE.md`
5. the relevant sections of
   `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`
6. the applicable ADRs, beginning with ADR 0088 for the contract foundation

Then run:

```sh
git status --short --branch
git log -3 --oneline
node --version
node tools/validate-contracts.mjs
```

The expected contract-package fingerprint is the value recorded in the
Validation section above. A clean clone should report no local changes. No
skill is mandatory for the next session; `grill-with-docs` is appropriate only
if the user wants production-stack alternatives stress-tested against the
accepted domain model and ADRs.

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
- canonical documentation, ADR, and continuity updates;
- read-only repository inspection and local offline validation;
- one local checkpoint commit containing exactly the validated foundation and
  its canonical documentation and continuity files; and
- one cross-device continuity update and local handoff commit; and
- exact origin update to the user-confirmed transferred repository;
- temporary download of official GitHub CLI v2.97.0 for macOS ARM64, with its
  archive verified against GitHub's published SHA-256 before execution;
- browser authentication as GitHub account `stevw-repo`, with the credential
  stored by GitHub CLI in the system keyring and no token disclosed; and
- authenticated remote verification plus one normal non-force push of the
  complete `main` history to `origin/main`, followed by remote-tip verification.

Not authorized and not performed:

- legacy-repository inspection;
- external source or network access;
- dependency installation;
- generative-model or embedding calls;
- real corpus, release, backup, Pinecone, Azure, routing, or deployment work;
- application implementation or production-stack selection;
- pull request, publication, or external message other than the authorized Git
  push and authentication flow; or
- destructive action.

The repository was clean before this objective on branch `main`, which was
three commits ahead of `origin/main`. The user confirmed the transferred
repository URL as
`https://github.com/stevw-repo/AskLegal-LegalDBPipeline.git`, and `origin` uses
that exact URL for fetch and push. The final handoff commit containing this
file and the complete local `main` history are pushed normally to
`origin/main`; the remote tip is verified against local `HEAD`. No force-push
or other remote mutation was performed or is required.

## Blockers and exact next step

No consequential product decision blocks or remains inside this checkpoint.

No handoff blocker remains. No implementation task is active. On Ubuntu, first
clone the confirmed private repository and verify it with the checklist above.
The next substantive conversation may select the production stack. A local
synthetic end-to-end slice requires explicit later implementation authorization
and must begin from these versioned contracts rather than changing them
implicitly.
