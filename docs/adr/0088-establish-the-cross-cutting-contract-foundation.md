---
status: accepted
date: 2026-08-14
refines:
  - "0003"
  - "0004"
  - "0005"
  - "0006"
  - "0007"
  - "0008"
  - "0009"
  - "0011"
  - "0016"
  - "0018"
  - "0039"
  - "0055"
  - "0067"
  - "0078"
  - "0087"
---

# Establish the implementation-neutral cross-cutting contract foundation

## Decision

The repository now owns one implementation-neutral machine-contract package
under `contracts/`. It makes accepted shared boundaries executable without
selecting the future production programming language, application framework,
database, provider, deployment mechanism, or policy values that remain
deferred.

The package contains:

- a complete inventory of 54 shared immutable value objects, domain artifacts,
  derived eligibility concepts, and lifecycle records;
- JSON Schema Draft 2020-12 contracts for source evidence, layered legal
  identity, releases and desired state, six-field serving and traceability,
  routing and Serving State, promotion and Approval, admitted model tasks, and
  capability attestation;
- strict shared primitives for register-issued identities, immutable object
  and contract references, safe integers, canonical UTC timestamps, semantic
  versions, evidence inventories, idempotency bindings, and Rule Traces;
- eight closed catalogues for identity prefixes, reference types, results,
  reasons, failures, lifecycle states, reviews, and capabilities;
- six closed-world state machines for Approval, Serving State, capability,
  workflow admission, bounded review, and promotion execution;
- fifteen synthetic fixtures covering positive, negative, boundary, malformed-
  input, retry, idempotency, collision, allowed-transition, forbidden-
  transition, JCS Unicode ordering, invalid Unicode, negative zero, and
  reproducibility behavior; and
- an exact package manifest binding every declared file by contained path,
  role, media type, byte size, and SHA-256 fingerprint.

The common register-issued encoding is a registered three-character lowercase
prefix, underscore, and 48 lowercase hexadecimal characters. Existing exact
accepted forms such as `rec_`, `rtl_`, `rts_`, `rpl_`, `rop_`, `rex_`, `rca_`,
`rcp_`, and `rct_` remain unchanged and are included in the closed prefix
catalogue. An ID is an opaque allocated identity, never a content hash.

JSON values are strict I-JSON. Canonical serialization is RFC 8785 JCS UTF-8.
The shared contracts permit only safe integers and reject duplicate keys,
invalid Unicode, byte-order marks, non-finite numbers, floating-point legal
facts, and negative zero. Fingerprints are exactly
`sha256:<64-lowercase-hex>`. Immutable references always bind both identity and
fingerprint. Package inventories fingerprint exact file bytes; the external
root fingerprint is computed over the JCS package manifest, which does not
inventory or fingerprint itself.

## Policy and authorization boundary

The schemas require callers to state whether a configurable policy is
`CONFIGURED` or `UNDECIDED`; they do not supply a default. The current
`contracts/foundation-status.json` records that:

- the cross-cutting foundation is validated;
- the production stack remains `UNDECIDED`;
- every closed operational capability is `DISABLED`;
- the deferred legal coverage, source authority, model allocation, review,
  user-facing, threshold, budget, retention, recovery, security, service-level,
  Azure activation, and Pinecone naming decisions remain named; and
- external effects are `NONE`.

This foundation does not define jurisdiction-specific legal answers. HKeL,
Hong Kong Cases, HKEX, reconstruction, and future Australian, Singapore, or
other material artifacts remain governed by their exact Source Rulebooks and
ADRs. Runtime applications, stores, connectors, cloud adapters, and production
policy profiles remain separate implementation work.

## Validation

`tools/validate-contracts.mjs` is a dependency-free local conformance tool. It
uses the already available Node.js runtime only for offline validation and does
not constrain the production stack. It performs strict JSON parsing, JCS and
SHA-256 checks, the exact JSON Schema subset used by this package, local
reference resolution, catalogue closure and mirroring, state reachability and
forbidden-transition checks, inventory completeness, fixture execution,
package containment and hashes, local Markdown link and structure checks, and
two fresh-process byte-identical reproducibility snapshots.

The validator performs no network access, provider call, source acquisition,
production read, or external write. A later production implementation must use
an independently supported Draft 2020-12 validator and prove conformance to the
same fixtures; this local tool is not selected as its runtime library.

## Consequences

Shared application packages can now depend on one exact contract boundary
instead of inventing incompatible object shapes, codes, or transitions. A
material-specific implementation can add its own versioned closed catalogues
and schemas but cannot weaken the shared invariants or smuggle a deferred
policy into a default.

The package is a contract foundation, not application implementation or
operational readiness. It authorizes no source access, model or embedding call,
release publication, Approval, backup, Pinecone or Azure action, routing
change, deployment, commit, push, or other remote effect.
