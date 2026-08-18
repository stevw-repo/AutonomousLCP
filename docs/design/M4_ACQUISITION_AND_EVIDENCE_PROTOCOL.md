# M4 Acquisition and Evidence Protocol

Status: accepted implementation-facing design

Date: 2026-08-16

Closes: `BR-07` and `BR-08`

## 1. Evidence object and package layout

The Evidence Vault stores immutable bytes; the Management Register stores
their meaning, ownership, lifecycle, and exact references. A URL or mutable
blob name is never evidence identity.

Every preserved artifact has:

- register-issued artifact ID and exact version ID;
- SHA-256 of raw bytes, byte length, declared and detected media type;
- source, observation cutoff, acquisition time, and acquisition method;
- sanitized transport metadata and exact source locator as evidence, not
  identity;
- content-encoding and character-encoding facts without silent conversion;
- owning package/observation and retention/hold profile references; and
- primary and recovery vault exact-version receipts.

Raw content objects use the deterministic logical key
`objects/sha256/<first-two-hex>/<remaining-62-hex>`. Package manifests use
`packages/<package-kind>/<object-id>/<manifest-fingerprint>.json`. Logical keys
contain no credential, query secret, personal access token, or unbounded source
path.

Deduplication may reuse identical raw bytes, but every acquisition retains its
own immutable evidence record and context. Hash equality does not prove legal
identity or source continuity.

## 2. Manifest-last commit protocol

1. The acquisition worker allocates an upload/package identity in the register.
2. Bytes are streamed into a bounded staging write while SHA-256, size, media
   checks, malware/hostile classification, and transport receipts are computed.
3. The worker rejects truncation, decompression bombs, path traversal,
   recursive archive excess, invalid encoding declarations, size excess, and
   inconsistent length or digest. Rejected bytes may be preserved in an
   isolated hostile class when policy requires investigation.
4. Each validated content object is created with conditional single-assignment
   semantics. An existing object is accepted only after exact byte-length and
   read-back hash equality.
5. The complete package inventory is canonicalized, fingerprinted, and written
   last. No reader treats staged objects or a package without its exact
   manifest as committed evidence.
6. The recovery copier copies the exact primary versions, reads every recovery
   version back, verifies bytes and manifest, and appends one copy receipt.
7. The register marks the Source Snapshot `PRESERVED` only after the required
   primary and recovery receipts pass. Legal processing cannot begin earlier.

Failure leaves immutable diagnostic evidence and an incomplete package record;
it never publishes a partial snapshot. Cleanup of abandoned staging material
is exact-ID-based, retention-aware, and separately authorized.

## 3. Read and corruption behavior

Readers request an immutable reference and required use. The vault adapter
resolves the exact version, checks size and hash while streaming, enforces the
caller's artifact class and purpose, and records an access receipt. It never
falls back to a newer version, source URL, mirror, or recovery copy silently.

A primary mismatch immediately blocks use, records corruption, and compares
the exact recovery version. Recovery may restore a new primary version under a
recovery lineage; it never overwrites or relabels the corrupt version. A
primary/recovery disagreement is an incident and cannot be resolved by taking
whichever copy is convenient.

## 4. Connector request contract

Every Watcher or Scraper request binds:

- Registered Source and Source Endpoint immutable references;
- exact Source Rulebook/source-contract version;
- pipeline run, work item, observation cutoff, and previous accepted
  Observation/Snapshot references;
- allowed host, path family, method, redirect, authentication class, media
  types, size, page/item ceiling, and time budget;
- conditional request facts permitted by the source contract;
- retry/throttle profile and complete-inventory rules; and
- required capture roles and expected evidence package shape.

Connectors receive credentials only through their acquisition-worker adapter.
They cannot access the Management Register with general credentials, interpret
legal status, call a model, build records, approve, or publish.

## 5. Watcher result contract

A Watcher returns exactly one result:

- `SUPPORTED_NO_CHANGE` — all required lightweight checks completed and exact
  evidence supports no admitted change;
- `POSSIBLE_CHANGE` — a declared signal differs and names the affected capture
  boundary without asserting legal effect;
- `SOURCE_UNAVAILABLE` — bounded retries ended without a complete admitted
  observation;
- `SOURCE_CONTRACT_CHANGED` — redirects, structure, specification, media,
  authentication, or semantics moved outside the active contract;
- `INCOMPLETE_OBSERVATION` — some required member or page could not be
  accounted for; or
- `UNSAFE_RESPONSE` — hostile or policy-forbidden response.

HTTP `304`, equal timestamp, equal length, equal page hash, or an empty result
is no-change only when the Source Rulebook explicitly says the complete
admitted check proves it. A Watcher never schedules model, embedding, or
promotion work directly.

## 6. Scraper result contract

After `POSSIBLE_CHANGE` or scheduled full reconciliation, a Scraper returns:

- `SNAPSHOT_PRESERVED` with a complete package, item/page inventory,
  completeness proof, and both-vault receipts;
- `SUPPORTED_NO_CHANGE_AFTER_CAPTURE` when full admitted capture proves the
  signal was non-material;
- `PARTIAL_CAPTURE`, `SOURCE_UNAVAILABLE`, `SOURCE_CONTRACT_CHANGED`, or
  `UNSAFE_RESPONSE`, each with preserved attempt evidence and no candidate
  processing authorization.

Pagination follows source-provided stable cursors or a rulebook-defined
ordering. The connector records first/last page facts, every cursor, duplicate
and missing member checks, declared totals when available, cutoff crossing,
and termination proof. A changing inventory during capture triggers a bounded
clean restart; repeated instability becomes incomplete, never a best-effort
snapshot.

Redirects cross no unregistered host or scheme. Evidence capture never executes
active content. ADR 0100 permits a separate isolated Patchright session to
execute active content for non-controlling locator and request discovery only;
its output cannot prove completeness, no change, legal text, or processing
eligibility, and discovered source bytes must be fetched again inertly.
Archives and documents are parsed later in an isolated processing
boundary from preserved bytes; acquisition does not trust embedded links,
macros, scripts, instructions, filenames, or metadata.

## 7. Retry, throttling, and source conduct

Retries are only for closed transient classes, use the same work/input
fingerprints, honor source-specific rate and concurrency ceilings, and stop at
the earlier deadline or attempt ceiling. Authentication failure, forbidden
response, contract drift, deterministic invalid bytes, and size excess are not
blindly retried.

The retry profile records backoff algorithm, bounded jitter seed policy,
`Retry-After` handling, maximum elapsed time, and operator stop control. Local
tests use a deterministic clock and jitter stream. Robots, licence, contract,
and permitted-use requirements live in the Registered Source profile; an
unconfigured or expired authorization blocks the connector.

## 8. Coverage consequences

Every admitted source observation has one register result. Missing or failed
evidence creates the Source Contract Review, Coverage Gap, Quarantine, or
release-blocking result dictated by the exact Source Rulebook. Independent
unaffected scopes may continue only when their completeness proofs do not rely
on the failed source.

No failure becomes an empty release, no-change, inferred retirement, or silent
carry-forward. The control plane publishes the known gap even when no new
serving target can be built.

## 9. Local and Azure proof boundary

M4 local fakes must implement conditional create, staged/incomplete packages,
manifest-last visibility, exact-version reads, read-back mismatch, two-vault
copy, corrupt primary, corrupt recovery, retention hold, hostile bytes,
pagination changes, throttling, lost acknowledgement, and restart.

Azure WORM, RBAC, private network, region, redundancy, Confidential Ledger,
clean-room restore, and retention claims remain M8/M9 evidence gates, not
changes to this protocol.

This document is design authority only and grants no source access, storage
mutation, or other external authorization.
