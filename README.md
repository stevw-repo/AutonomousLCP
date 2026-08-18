# AskLegal Legal Database Pipeline

This repository is the greenfield modular monorepo for Ask.Legal's autonomous
legal-database pipeline.

The intended system checks official and approved publisher sources, preserves
exact evidence,
assesses supported legal status, prepares validated search records, obtains one
human approval for the complete frozen update, and keeps Ask.Legal's searchable
legal corpus aligned with that approval.

## Current status

**The architecture and implementation-facing design baseline is accepted
through ADR 0099, including all six M2–M7 protocols and all seven material
decisions. M1 through M7 are implemented and proved locally. The repository
now has the complete local domain and Management Register kernel, five
separately runnable application boundaries, synthetic acquisition and
two-vault evidence preservation, and an executable Legal Desk package/rule
engine with a bounded two-profile semantic-task gate, plus immutable corpus,
proposal, named-human Approval, replacement-target, backup, routing, rollback,
and exact-retirement behavior using deterministic local fakes. The complete
32-scenario offline conformance runner connects those boundaries through the
stable `asklegal-local` CLI, including duplicate, restart, cancellation,
hostile-input, stale-approval, overlap, recovery, rollback, and deletion-denial
proofs in two path-distinct executions. The only enabled legal package is the
reserved `ZZZ` / `LOCAL_SYNTHETIC` test package; every real
jurisdiction package remains `NOT_READY` and every real external effect remains
disabled.**

The first real-package readiness checkpoint is also present under
`packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/`.
It selects `HK-LEG-ORDINANCES` as the current local implementation target and
binds the accepted Hong Kong Legislation source-role and scope inventory with
explicit blockers. Its first 27 offline rule slices implement the ordered
`HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001` → `HKLEG-BASE-EVID-001` →
`HKLEG-BASE-STATE-001` → `HKLEG-BASE-LIMIT-001` →
`HKLEG-BASE-ID-001` → `HKLEG-BASE-DISP-001` → `HKLEG-BASE-REC-001` →
`HKLEG-BASE-REL-001` clear path, the bounded `HKLEG-BASE-REVIEW-001` →
`HKLEG-BASE-HIST-001` branch, and the orthogonal `HKLEG-BASE-CHANGE-001` cutoff
guard, plus `HKLEG-CURRENT-OBS-001` through `HKLEG-CURRENT-EVID-004` and
`HKLEG-CURRENT-DIFF-001` through `HKLEG-CURRENT-DIFF-002` and
`HKLEG-CURRENT-CAUSE-001` through `HKLEG-CURRENT-CAUSE-002`, plus the
`HKLEG-CURRENT-EVENT-001` missing-consolidation router, and the ordinary
`HKLEG-CURRENT-DISP-001` → `HKLEG-CURRENT-REC-001` →
`HKLEG-CURRENT-REL-001` completion path, with 127 exact
synthetic fixtures. They cover cutoff/source/lock consistency;
complete, missing, duplicate, or misassigned inventory accounting; and
matching verified or assisted bilingual evidence, missing evidence, conflict
quarantine, forbidden historical substitution, clear present operative state,
missing or unknown signals, partial-status ambiguity, source conflict,
unproved operative effect, and missing rulebook support.
The ordinary difference gate classifies only observable payload, structure,
location, evidence-bundle, and object-addition changes. Exact equality is
reuse-eligible only with separately proved continuing support; it never infers
legal identity, status, repeal, or continuity and emits no record.
The cause gate requires exact assigned Gazette or Editorial Record evidence,
recognizes a non-serving technical republication only when all legal and six
serving fields are exact, quarantines missing or conflicting causes, and sends
source-contract drift to bounded review.
The limit gate also blocks unsupported historical events, effective dates,
continuity relationships, and complete-event-chain claims. The identity gate
requests new opaque register identities, keeps source and legacy identifiers
as aliases, blocks unproved lineage, and quarantines similarity-based identity
ambiguity. The disposition gate assigns exactly one supported primary result,
keeps operative-event consolidation gaps visible, and blocks single-signal
shortcuts. The record gate constructs the exact English-first canonical
bilingual payload and six-field candidate, while excluding non-searchable,
legacy-ID, incomplete, non-canonical, or unapproved-note paths. The release-
accounting gate requires total first-baseline accounting and forbids a false
predecessor before candidate release construction. The review gate opens only
one named, source-bounded, fact-bounded historical question and rejects broad
history acquisition. It contains no real source
evidence artifacts, complete executable ruleset, model profile, owner acceptance, or
activation authority, so every real scope remains `NOT_READY`.

The first official-source access boundary is implemented under
`packages/source-connectors/`. A fingerprinted register binds all 14 Hong Kong
Legislation source roles to 78 exact endpoint contracts and keeps every role
fail-closed unless both legal and operational admission permit it. The
AskLegal legal team's clearance for all 14 roles is recorded separately from
the unchanged publisher notices. Five roles are fully configured, five are
partially configured, and four remain technically blocked; disabled endpoints
still reject access before transport. The connector verifies TLS, media type,
size, and hostile content and
permits no redirects, proxies, cookies, ambient credentials, uploads, or
writes. RSS is a discovery signal only and cannot prove completeness or no
change.

Build readiness is reported separately from legal admission for all 14 roles
and 78 endpoints. Item-specific official URL templates use strict relative-
path binding, complete HKeL inventories require the exact English and
Traditional Chinese member pair, and JavaScript products use a Patchright
`1.62.1` discovery boundary in the acquisition worker. The browser is
ephemeral, exact-host, and non-controlling: it returns a sanitized request map,
not legal evidence. Official direct APIs are used when their exact read
contract is known; the NPC application, enumeration, aggregate, and website-
configuration APIs are discovery metadata only, while every incomplete source
path remains fail-closed.

Python 3.14, the FastAPI and
strict Python boundary toolchain, the Azure SQL
Management Register boundary, the five-environment Azure Container Apps
hosting topology, managed Durable Task workflow boundary, and Azure-only Blob
Evidence Vault and Recovery Vault boundary, private attested container-image
supply chain, and split Application Gateway and Entra API edge are selected;
repository-owned Bicep and Azure Pipelines with workload federation, stateless
private Managed DevOps Pools and the Azure Monitor operational-audit boundary
are also selected. Azure OpenAI/Foundry is selected for generative work and
embeddings to match Ask.Legal Backend. Human Review and Control use one
`PipelineAdministrator` role with no action-specific step-up or independent
Approval TTL. A separate restricted App Service `candidate` slot is selected
for manual validated production swap and reverse-swap rollback; the existing
development slot stays development-only. Pinecone naming uses the approved
environment/jurisdiction/date/state format. Coverage delivery uses the approved
fingerprint-bound, protected, cached mechanism without signing keys. Decision 7
selects LLM-assisted Gazette-event analysis/challenge and Reconstruction Plan
decision/challenge; offline evaluation is deterministic against human-
adjudicated truth, and every other unallocated task defaults to deterministic
handling for now.
Quarantine/review work uses severity, named assignment, immediate urgent
notification, optional due times, and no fixed SLA. The five applications and canonical shared-package roles
remain separately secured. Azure infrastructure implementation and every real
operational capability remain unauthorized.**

The repository currently contains the initial overall design and durable
briefing files, together with locally validated shared schemas, closed
catalogues, lifecycle definitions, and synthetic conformance fixtures under
[`contracts/`](contracts/README.md). These artifacts do not authorize source access, AI or embedding
calls, corpus publication, Pinecone access, pruning, backup mutation,
deployment, routing changes, or any other remote action.

The approved local spike under [`packages/contracts/`](packages/contracts/README.md)
pins Python 3.14.7, the Python dependency lock, and official Pyright. It proves
strict raw-byte JSON, offline Draft 2020-12 validation, strict closed Pydantic
binding, RFC 8785 JCS, SHA-256, all existing synthetic fixtures and exact
artifacts, and fresh-process reproducibility. It adds no application, database,
cloud adapter, source connector, or external capability.

The bounded M2 domain implementation under
[`packages/domain/`](packages/domain/) now includes the five accepted lifecycle
machines and the generic immutable command/effect objects. It distinguishes
the one durable applied/rejected Command Result from replay, conflict, and
indeterminate submission resolution; validates exact references, timestamps,
versions, sorted inputs, deadlines, retries, stop conditions, and predeclared
compensation; and requires terminal Effect Receipt details to match their
status. These objects record authority only and perform no register write or
external effect.

The completed type-boundary spike adds repository-wide official Pyright strict
and a repository-owned fail-closed checker. It discovers future Python package
and application trees, rejects explicit `Any`, bare collection annotations,
unapproved casts and error suppressions, and prevents protected packages from
importing infrastructure or leaking HTTP frameworks into contract/domain code.
All eight current exceptions are exact, explained, and rejected when stale.

The completed synthetic Management Register spike under
[`packages/management-register-adapter/`](packages/management-register-adapter/README.md)
pins `mssql-python==1.12.0`, exact forward-only migrations, stored-procedure
capabilities, append-only SQL ledger facts, idempotency, concurrent Approval
consumption, Serving State activation, atomic inbox/outbox behavior, bounded
deadlock retry, and lost-ack recovery. Its separate integration proof passes
against digest-pinned SQL Server 2025 CU7 Developer in Docker; the ordinary
suite needs no running database.

The completed local durability spike under
[`packages/durable-task-adapter/`](packages/durable-task-adapter/README.md)
pins Microsoft's standalone `durabletask==1.9.0` and
`durabletask-azuremanaged==1.7.0`. The always-on in-memory SDK proof and a
separate digest-pinned Docker emulator proof cover fresh-worker replay,
buffered duplicate and stale human events, explicit numeric workflow versions,
64 KiB opaque history payloads, fake-register reconstruction, and two activity
deliveries producing exactly one effect receipt. It does not prove Scheduler
persistence across emulator termination or any Azure behavior.

The completed package spike is governed by
[`tools/package_spike_manifest.json`](tools/package_spike_manifest.json) and
[`tools/package_spike.py`](tools/package_spike.py). It proves that every
current workspace member is covered, builds 19 byte-identical wheels in two
path-distinct workspaces, verifies each wheel's complete RECORD, installs each
member and only its workspace dependency closure into a clean environment from
the unchanged lock with uv network access disabled, and creates byte-identical
wheel-plus-lock container-input bundles. It builds no OCI image and authorizes
no remote action.

The completed local image-admission spike is governed by
[`tools/image_admission_spike_manifest.json`](tools/image_admission_spike_manifest.json)
and [`tools/image_admission_spike.py`](tools/image_admission_spike.py). Two
network-disabled clean BuildKit builds produce the same synthetic OCI image and
normalized provenance; pinned Syft and Grype produce a reproducible SPDX SBOM
and fail-closed vulnerability result; the closed synthetic licence policy
checks required obligations; ORAS copies and restores the exact subject and
referrer graph; and a Notation-generated local test root is used by OpenSSL to
sign and verify the canonical evidence payload. The test root is incapable of production
trust. No Azure registry, signing service, deployment, or production resource
was used.

The completed local architecture spike is governed by
[`tools/architecture_spike_manifest.json`](tools/architecture_spike_manifest.json)
and [`tools/architecture_spike.py`](tools/architecture_spike.py). Its closed
policy covers 5 applications and 14 shared packages, 80 permitted direct
dependency edges, and 31 declared capability ports. It rejects future
undeclared members, metadata or dependency drift, imports outside direct
boundaries, package-to-application dependencies, cycles, declaration drift,
and incorrect ownership of approval, source access, provider, serving, backup,
routing, recovery, or proposal-preparation effects.

The accepted V1 POC Ubuntu topology is recorded in
[`infrastructure/poc/topology.json`](infrastructure/poc/topology.json) and
validated by [`tools/v1_poc_topology.py`](tools/v1_poc_topology.py). The
contract is secret-free and disabled by default: all 16 services are off, only
3 artifacts currently have exact digests, and the other 13 remain
`PIN_REQUIRED`. Its gate rejects unknown topology fields, embedded secrets,
floating artifacts, public listeners, network-membership drift, collapsed
vault separation, false scheduler-resume semantics, or real Pinecone write
authority. Run it without network access with:

```sh
uv run --frozen --offline --all-packages python tools/v1_poc_topology.py
uv run --frozen --offline --all-packages pytest -o addopts='' -q \
  tools/tests/test_v1_poc_topology.py
```

The companion Ubuntu host-admission policy is
[`infrastructure/poc/host_admission_policy.json`](infrastructure/poc/host_admission_policy.json).
Its validator accepts only supplied read-only host facts and performs no host
inspection or mutation itself. Even perfectly matching synthetic facts remain
`admitted=false` until exact host-package locks, private subnets, and the
file-only SQL/Versity credential interface are proved:

```sh
uv run --frozen --offline --all-packages python tools/v1_poc_host_admission.py
```

The disabled systemd input contract at
[`infrastructure/poc/systemd_unit_inputs.json`](infrastructure/poc/systemd_unit_inputs.json)
binds all 16 service units, two bootstrap one-shots, five cadence-unresolved
timers, exact dependencies/identities/credential files/write paths, and the
common hardening profile. It installs or enables nothing:

```sh
uv run --frozen --offline --all-packages python tools/v1_poc_systemd_units.py
```

The companion host-identity contract keeps ten non-login service accounts and
14 exact write paths uncreated and UID/GID-unallocated until Ubuntu collision,
container mapping, and ownership proof:

```sh
uv run --frozen --offline --all-packages python tools/v1_poc_host_identities.py
```

The executable credential-interface proof is frozen, but not authorized or
run, by
[`infrastructure/poc/credential_interface_proof_inputs.json`](infrastructure/poc/credential_interface_proof_inputs.json).
It binds the SQL service and both Versity vault services to their exact
artifact/systemd credential inventories, six proof steps, seven canary-
inspection surfaces, manifest-last evidence, rotation/restart requirements,
and the fail-closed product decision gate:

```sh
uv run --frozen --offline --all-packages python -m \
  tools.v1_poc_credential_interface
```

The aggregate admission contract at
[`infrastructure/poc/v1_admission_gate.json`](infrastructure/poc/v1_admission_gate.json)
combines all eight present static gates with the still-unstarted real package,
source, model/embedding, Pinecone, Ubuntu end-to-end, and final acceptance
gates. It deliberately reports `V1_POC_NOT_ADMITTED`; a static pass is not a
V1 readiness claim:

```sh
uv run --frozen --offline --all-packages python -m tools.v1_poc_admission
```

The artifact-admission inventory at
[`infrastructure/poc/artifact_admission.json`](infrastructure/poc/artifact_admission.json)
binds all 16 services to 12 unique artifacts. Two immutable candidates cover
SQL Server and both scheduler services; ten selections or reproducible builds
remain, and no artifact is admitted. The offline consistency gate is:

```sh
uv run --frozen --offline --all-packages python tools/v1_poc_artifacts.py
```

The complete local M7 proof is exposed through the locked workspace command:

```bash
uv run --frozen --all-packages asklegal-local reset --exact-test-state
uv run --frozen --all-packages asklegal-local prove --scenario E2E-001
uv run --frozen --all-packages asklegal-local prove --all
```

`prove --all` executes all 32 accepted scenarios twice in clean path-distinct
roots, rejects any external DNS/socket attempt, and writes only ignored
synthetic state under `var/local-conformance/`. The report statement is
`local synthetic platform proved`; it makes no source, jurisdiction, model,
Azure, Pinecone, Ask.Legal routing, or production-readiness claim.

M2 is complete locally. The framework-free domain now includes all five M2
lifecycle machines, immutable command/effect contracts, explicit quarantine
re-entry, and the typed Management Register boundary with a deterministic fake.
Two exact forward-only migrations build the common register on fresh SQL
Server, where local conformance proves replay, concurrency, stale rejection,
atomic facts and intents, effect fencing, receipts, projections, recovery
rows, ledger verification, and procedure-only application access.

M3 is also complete locally. The private control-plane and public Review APIs
start independently with strict `/api/v1` boundaries, separate audiences and
CORS policies, exact OpenAPI fingerprints, bounded raw JSON, idempotency,
optimistic versions, ETags, snapshot-bound pagination, safe errors, liveness,
readiness, and local identity/register/task/projection adapters. The Review
package includes a replaceable PKCE browser client with memory-only bearer
tokens. The acquisition, legal-processing, and promotion workers have no HTTP
ingress and prove exact configuration, local task hubs, leases, fencing,
cooperative shutdown, drift rejection, and separately disabled effect ports.
No external or production effect is authorized or performed.

M4 is complete locally. Versioned machine contracts now govern connector
requests, Watcher and Scraper outcomes, immutable evidence objects and
packages, exact vault receipts, and the one outcome for each observation. The
synthetic connector proves bounded retry, throttling facts, source-contract
drift, no-change admission, complete pagination, instability restart, partial
capture, and inert hostile input. Filesystem-backed local primary/recovery
vault fakes prove content addressing, conditional create, exact-version reads,
manifest-last visibility, verified recovery copies, corruption incidents,
retention holds, lost acknowledgement, and restart. The acquisition worker
cannot mark a Source Snapshot preserved until it receives the exact complete
recovery receipt; it receives no recovery credential itself. No real source,
Azure vault, model, embedding, serving, deployment, or production operation
is enabled.

The disabled V1 POC boundary additionally locks Boto3 `1.43.49` for explicit-
credential S3 access to separate logical Versity endpoints. Offline fakes prove
conditional immutable writes, lossless provider-version references, exact read-
back, COMPLIANCE retention/legal hold, and manifest-last recovery composition.
All five applications construct only their permitted vault roles without
connecting. Real certificates, buckets, policies, Versity behavior, and Ubuntu
runtime admission remain blocked.

Run the complete proof with an already-cached exact uv 0.12.5 installation:

```sh
.venv/bin/python tools/package_spike.py --uv /path/to/uv-0.12.5
```

Bootstrap every locked workspace member and run the ordinary local suite with
one command:

```sh
python3 -m tools.dev_test \
  --uv /path/to/uv-0.12.5 \
  --node /path/to/node-24.19.0
```

The command rejects any other uv, Node.js, or Python version, performs an exact frozen
all-member sync, disables unrelated host pytest plugins, supplies only the
declared workspace source roots, and then runs the ordinary suite. It does not
start opt-in SQL Server, Durable Task emulator, image-admission, or package
proofs.

## Start here

1. [`AGENTS.md`](AGENTS.md) — mandatory operating instructions.
2. [`.agent/CONTEXT.md`](.agent/CONTEXT.md) — stable domain language.
3. [`.agent/DECISIONS.md`](.agent/DECISIONS.md) — settled decisions.
4. [`.agent/ROADMAP.md`](.agent/ROADMAP.md) — overall progress,
   delivery milestones, proof dependencies, and exit gates.
5. [`.agent/WORKING_STATE.md`](.agent/WORKING_STATE.md) — current
   objective and exact next step.
6. [`docs/adr/0001-use-a-modular-monorepo.md`](docs/adr/0001-use-a-modular-monorepo.md)
   — accepted repository architecture.
7. [`docs/adr/0002-use-replacement-pinecone-indexes.md`](docs/adr/0002-use-replacement-pinecone-indexes.md)
   — accepted serving-target and cutover architecture.
8. [`docs/adr/0003-make-corpus-releases-complete-scoped-snapshots.md`](docs/adr/0003-make-corpus-releases-complete-scoped-snapshots.md)
   — accepted Corpus Release boundary.
9. [`docs/adr/0004-make-desired-state-inventories-complete-and-flattened.md`](docs/adr/0004-make-desired-state-inventories-complete-and-flattened.md)
   — accepted Desired-State Inventory boundary.
10. [`docs/adr/0005-handle-unavailable-release-scopes-explicitly.md`](docs/adr/0005-handle-unavailable-release-scopes-explicitly.md)
   — accepted unavailable-scope behavior.
11. [`docs/adr/0006-make-the-promotion-manifest-the-sole-execution-envelope.md`](docs/adr/0006-make-the-promotion-manifest-the-sole-execution-envelope.md)
    — accepted approval and execution envelope.
12. [`docs/adr/0007-bind-approval-to-one-manifest-and-execution-lineage.md`](docs/adr/0007-bind-approval-to-one-manifest-and-execution-lineage.md)
    — accepted Approval contract.
13. [`docs/adr/0008-adopt-the-five-field-serving-envelope.md`](docs/adr/0008-adopt-the-five-field-serving-envelope.md)
    — accepted serving-record and separate internal traceability boundary.
14. [`docs/adr/0009-separate-serving-state-definition-from-lifecycle.md`](docs/adr/0009-separate-serving-state-definition-from-lifecycle.md)
    — accepted immutable Serving State and append-only lifecycle boundary.
15. [`docs/adr/0010-do-not-use-distillation-source-derived-identity.md`](docs/adr/0010-do-not-use-distillation-source-derived-identity.md)
    — excludes Distillation's source-derived hashes as greenfield identity.
16. [`docs/adr/0011-use-register-issued-layered-identity.md`](docs/adr/0011-use-register-issued-layered-identity.md)
    — accepted register-issued layered identity and immutable Search Records.
17. [`docs/adr/0012-use-evidence-backed-legislation-continuity-rules.md`](docs/adr/0012-use-evidence-backed-legislation-continuity-rules.md)
    — accepted evidence-backed legislation identity-continuity rules.
18. [`docs/adr/0013-deliver-warnings-in-required-serving-metadata.md`](docs/adr/0013-deliver-warnings-in-required-serving-metadata.md)
    — establishes the required LLM-facing metadata channel later standardized
    as `metadata.authority_note` by ADR 0050.
19. [`docs/adr/0014-use-proposition-scoped-case-law-continuity-and-retirement.md`](docs/adr/0014-use-proposition-scoped-case-law-continuity-and-retirement.md)
    — accepted case-law continuity, treatment, authority-note, and retirement rules.
20. [`docs/adr/0015-use-publisher-evidence-backed-reference-work-continuity.md`](docs/adr/0015-use-publisher-evidence-backed-reference-work-continuity.md)
    — accepted Principles continuity and licence-expiry freeze rules.
21. [`docs/adr/0016-keep-the-record-traceability-lookup-outside-the-query-path.md`](docs/adr/0016-keep-the-record-traceability-lookup-outside-the-query-path.md)
    — keeps the internal record-to-source traceability map outside Ask.Legal's
    live query path.
22. [`docs/adr/0017-use-jurisdiction-specific-principles-terminology.md`](docs/adr/0017-use-jurisdiction-specific-principles-terminology.md)
    — names Australian Principles, Singapore Principles, and other
    jurisdiction-specific Principles as separate material families.
23. [`docs/adr/0018-use-versioned-jurisdiction-and-material-source-rulebooks.md`](docs/adr/0018-use-versioned-jurisdiction-and-material-source-rulebooks.md)
    — standardizes the Source Rulebook Contract while keeping every
    jurisdiction-and-material rulebook separate.
24. [`docs/adr/0019-define-hong-kong-legislation-coverage-and-bilingual-records.md`](docs/adr/0019-define-hong-kong-legislation-coverage-and-bilingual-records.md)
    — defines complete Hong Kong legislation coverage and one English-and-
    Traditional-Chinese Search Record per searchable location.
25. [`docs/adr/0020-use-english-only-internal-warnings-for-hong-kong-records.md`](docs/adr/0020-use-english-only-internal-warnings-for-hong-kong-records.md)
    — keeps Hong Kong authority notes as English-only internal LLM instructions.
26. [`docs/adr/0021-use-canonical-bilingual-text-and-structure-aligned-splitting-for-hong-kong-legislation.md`](docs/adr/0021-use-canonical-bilingual-text-and-structure-aligned-splitting-for-hong-kong-legislation.md)
    — fixes Hong Kong legislation's bilingual text layout and legal-structure
    splitting rule.
27. [`docs/adr/0022-require-hkel-xml-and-matching-verified-pdfs-for-hong-kong-legislation.md`](docs/adr/0022-require-hkel-xml-and-matching-verified-pdfs-for-hong-kong-legislation.md)
    — records the original verified-copy gate; ADR 0081 later permits matching
    official HKeL assisted copies across covered scopes.
28. [`docs/adr/0023-defer-reconstructed-hong-kong-legislation-records.md`](docs/adr/0023-defer-reconstructed-hong-kong-legislation-records.md)
    — records the former reconstruction deferral, later superseded by ADR
    0080, while preserving its historical rationale.
29. [`docs/adr/0024-keep-hklii-non-controlling-and-defer-formal-registration.md`](docs/adr/0024-keep-hklii-non-controlling-and-defer-formal-registration.md)
    — establishes HKLII's non-controlling discovery and originating-source
    evidence boundary; ADR 0045 later registers the automated source role.
30. [`docs/adr/0025-use-fact-specific-gazette-event-evidence-for-hong-kong-legislation.md`](docs/adr/0025-use-fact-specific-gazette-event-evidence-for-hong-kong-legislation.md)
    — uses exact Gazette artifacts for specific legal events while keeping the
    applicable HKeL evidence as the consolidated-law boundary.
31. [`docs/adr/0026-use-hkel-past-data-for-history-and-editorial-records-for-official-editorial-events.md`](docs/adr/0026-use-hkel-past-data-for-history-and-editorial-records-for-official-editorial-events.md)
    — separates historical version reconciliation from official editorial-
    amendment evidence without bypassing applicable current HKeL evidence.
32. [`docs/adr/0027-exclude-legco-bills-and-proceedings-from-hong-kong-legislation.md`](docs/adr/0027-exclude-legco-bills-and-proceedings-from-hong-kong-legislation.md)
    — excludes LegCo Bills and proceedings from the automated current-law
    pipeline while allowing optional non-controlling human research.
33. [`docs/adr/0028-pin-hkel-publication-specifications-for-source-interpretation.md`](docs/adr/0028-pin-hkel-publication-specifications-for-source-interpretation.md)
    — pins the official HKeL specifications that define source interpretation
    without treating them as item-specific evidence or serving content.
34. [`docs/adr/0029-allow-official-hkel-assisted-copies-for-constitutional-instruments.md`](docs/adr/0029-allow-official-hkel-assisted-copies-for-constitutional-instruments.md)
    — records the original constitutional assisted-copy exception, later
    broadened across covered Hong Kong Legislation by ADR 0081.
35. [`docs/adr/0030-classify-hkel-instruments-by-legal-nature-and-explicit-disposition.md`](docs/adr/0030-classify-hkel-instruments-by-legal-nature-and-explicit-disposition.md)
    — routes HKeL A-series entries by actual legal nature and requires a
    complete versioned Instrument Disposition Registry.
36. [`docs/adr/0031-use-tiered-source-monitoring-and-change-triggered-ai.md`](docs/adr/0031-use-tiered-source-monitoring-and-change-triggered-ai.md)
    — uses scalable tiered source checks and gates model work behind a real
    deterministic change signal and an explicitly enabled task.
37. [`docs/adr/0032-register-fact-specific-hong-kong-legislation-sources.md`](docs/adr/0032-register-fact-specific-hong-kong-legislation-sources.md)
    — registers Hong Kong legislation sources by exact fact authority, outage
    impact, endpoint family, and monitoring tier while keeping historical
    material on demand.
38. [`docs/adr/0033-define-hong-kong-legislation-current-update-rules-and-conformance-cases.md`](docs/adr/0033-define-hong-kong-legislation-current-update-rules-and-conformance-cases.md)
    — defines stable Hong Kong current-update rules and matching pass, fail,
    boundary, conflict, and regression cases.
39. [`docs/adr/0034-establish-the-first-hong-kong-legislation-current-baseline-without-replaying-history.md`](docs/adr/0034-establish-the-first-hong-kong-legislation-current-baseline-without-replaying-history.md)
    — establishes the complete first Hong Kong current baseline from accepted
    present evidence while opening history only for named uncertainties.
40. [`docs/adr/0035-define-ordinary-provision-hkel-reconciliation-fixtures.md`](docs/adr/0035-define-ordinary-provision-hkel-reconciliation-fixtures.md)
    — fixes ordinary-provision XML/PDF, bilingual-pairing, source-review, and
    canonical-rendering examples with exact pass, block, or Quarantine results.
41. [`docs/adr/0036-define-schedule-table-and-form-hkel-reconciliation-fixtures.md`](docs/adr/0036-define-schedule-table-and-form-hkel-reconciliation-fixtures.md)
    — fixes Legal Location, rendering, bilingual-alignment, mismatch, and safe-
    splitting examples for Schedules, tables, and prescribed forms.
42. [`docs/adr/0037-define-note-image-and-cross-reference-hkel-reconciliation-fixtures.md`](docs/adr/0037-define-note-image-and-cross-reference-hkel-reconciliation-fixtures.md)
    — separates statutory and publisher notes, authority-note consequences, visual
    evidence, and exact source references from internal target resolution.
43. [`docs/adr/0038-define-partial-status-and-bilingual-structure-hkel-fixtures.md`](docs/adr/0038-define-partial-status-and-bilingual-structure-hkel-fixtures.md)
    — fixes partial-status coverage, authority-note placement, bilingual alignment,
    and smallest-safe-boundary outcomes.
44. [`docs/adr/0039-confine-generative-llm-use-to-explicit-legal-processing-tasks.md`](docs/adr/0039-confine-generative-llm-use-to-explicit-legal-processing-tasks.md)
    — originally confined internal generative-LLM use to one proposal-only
    gateway; Decision 7's bounded semantic-decision boundary supersedes that
    authority wording while preserving the sole gateway and admission rules.
45. [`docs/adr/0040-define-recursive-overlong-hkel-record-partitioning.md`](docs/adr/0040-define-recursive-overlong-hkel-record-partitioning.md)
    — defines recursive official-structure partitioning, dependency closure,
    exact final-payload measurement, and source-unit coverage proof for
    overlong bilingual Hong Kong legislation records.
46. [`docs/adr/0041-use-strict-hashed-hkel-fixture-packages.md`](docs/adr/0041-use-strict-hashed-hkel-fixture-packages.md)
    — defines the frozen fixture catalogue, strict package manifest, hashed
    synthetic inputs, exact expected artifacts, and semantic validation rules.
47. [`docs/adr/0042-package-the-hong-kong-legislation-source-rulebook.md`](docs/adr/0042-package-the-hong-kong-legislation-source-rulebook.md)
    — packages Hong Kong Legislation policy, source roles, rules, codes,
    contracts, scope readiness, tests, activation, and build conformance.
48. [`docs/adr/0043-defer-final-generative-llm-task-allocation.md`](docs/adr/0043-defer-final-generative-llm-task-allocation.md)
    — defers the remaining deterministic-versus-generative-LLM task allocation
    while preserving the sole gateway and original proposal-only safety
    boundary; later ADRs and Decision 7 settle the admitted bounded semantic-
    decision exceptions.
49. [`docs/adr/0044-normalize-hong-kong-current-update-results-and-complete-observation-failure-cases.md`](docs/adr/0044-normalize-hong-kong-current-update-results-and-complete-observation-failure-cases.md)
    — separates processing, disposition, coverage, review, and output results
    and adds the missing observation-failure conformance cases.
50. [`docs/adr/0045-register-hklii-as-a-non-controlling-automated-discovery-source.md`](docs/adr/0045-register-hklii-as-a-non-controlling-automated-discovery-source.md)
    — registers HKLII for automated Hong Kong Cases discovery while keeping
    judgment and treatment authority with accepted originating evidence.
51. [`docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md`](docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md)
    — limits ordinary Hong Kong Case coverage to binding courts and keeps
    lower-body judgments outside searchable serving.
52. [`docs/adr/0047-serve-hong-kong-case-propositions-in-original-language-by-default.md`](docs/adr/0047-serve-hong-kong-case-propositions-in-original-language-by-default.md)
    — serves Hong Kong Case Propositions in their original language and keeps
    Judiciary translations as linked evidence unless evaluation proves a
    later serving enrichment is needed.
53. [`docs/adr/0048-account-for-every-official-hong-kong-judgment-listing-entry.md`](docs/adr/0048-account-for-every-official-hong-kong-judgment-listing-entry.md)
    — separates official listings, judicial decisions, and judgment artifacts
    and requires explicit acquisition and completeness accounting.
54. [`docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md`](docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md)
    — establishes the first corpus-wide current-authority baseline without an
    arbitrary case-age cutoff.
55. [`docs/adr/0050-use-one-standardized-authority-note-metadata-field.md`](docs/adr/0050-use-one-standardized-authority-note-metadata-field.md)
    — standardizes one required `metadata.authority_note` field across all
    material families for controlled warnings and budget-based material
    support and neutral explanatory context.
56. [`docs/adr/0052-update-hong-kong-cases-through-bounded-impact-reconciliation.md`](docs/adr/0052-update-hong-kong-cases-through-bounded-impact-reconciliation.md)
    — updates Hong Kong Cases through bounded impact reconciliation and fixes
    HKLII's exact non-controlling discovery role.
57. [`docs/adr/0053-use-staged-hybrid-analysis-for-hong-kong-later-treatment.md`](docs/adr/0053-use-staged-hybrid-analysis-for-hong-kong-later-treatment.md)
    — uses whole-judgment LLM discovery and candidate-level LLM proposals
    between deterministic preparation, validation, and Legal Desk decisions.
58. [`docs/adr/0054-classify-hkex-listing-rules-as-hong-kong-regulatory-materials.md`](docs/adr/0054-classify-hkex-listing-rules-as-hong-kong-regulatory-materials.md)
    — adds the Regulatory category and `type: "regulatory"` for current HKEX
    Main Board and GEM Listing Rules while keeping guidance separate.
59. [`docs/adr/0055-use-immutable-selection-transitions-for-hong-kong-case-treatment.md`](docs/adr/0055-use-immutable-selection-transitions-for-hong-kong-case-treatment.md)
    — defines exact reuse, successor, reselection, retirement, partial
    retirement, uncertainty, and embedding-reuse behavior for Hong Kong case
    treatment without mutable records or cyclic lineage.
60. [`docs/adr/0056-separate-semantic-evaluations-from-deterministic-hong-kong-treatment-fixtures.md`](docs/adr/0056-separate-semantic-evaluations-from-deterministic-hong-kong-treatment-fixtures.md)
    — separates LLM semantic-understanding evaluations from byte-exact legal,
    record, release, and serving contract fixtures.
61. [`docs/adr/0057-use-strict-non-leaking-hong-kong-treatment-conformance-packages.md`](docs/adr/0057-use-strict-non-leaking-hong-kong-treatment-conformance-packages.md)
    — fixes permanent non-answer-bearing IDs, strict semantic and deterministic
    packages, expected-artifact states, catalogues, and coverage completeness.
62. [`docs/adr/0058-store-one-directional-case-treatment-relationship-with-two-internal-views.md`](docs/adr/0058-store-one-directional-case-treatment-relationship-with-two-internal-views.md)
    — stores each proposition-scoped treatment once, derives incoming and
    outgoing internal views, and keeps treatment-graph records out of Pinecone.
63. [`docs/adr/0059-freeze-the-initial-hong-kong-treatment-conformance-catalogue.md`](docs/adr/0059-freeze-the-initial-hong-kong-treatment-conformance-catalogue.md)
    — freezes the audited initial 155-case, 155-cell, and 21-pair Hong Kong
    treatment conformance universe.
64. [`docs/adr/0060-define-the-hong-kong-case-proposition-output-and-evidence-contract.md`](docs/adr/0060-define-the-hong-kong-case-proposition-output-and-evidence-contract.md)
    — defines one evidence-bearing proposition record, its labelled serving
    text, exact judgment support, one-record boundary, and zero-record or
    Quarantine behavior without choosing the extraction method.
65. [`docs/adr/0061-define-hong-kong-case-proposition-split-and-merge-rules.md`](docs/adr/0061-define-hong-kong-case-proposition-split-and-merge-rules.md)
    — splits and merges propositions by independent legal meaning, preserves
    opinion boundaries, quarantines indivisible overlong records, and defines
    correction lineage without token-based fragmentation.
66. [`docs/adr/0062-define-the-hong-kong-case-proposition-coverage-ledger.md`](docs/adr/0062-define-the-hong-kong-case-proposition-coverage-ledger.md)
    — requires an immutable complete source-unit, opinion, dependency,
    candidate, evidence-role, outcome, and zero-proposition accounting proof
    for every exact Hong Kong judgment version.
67. [`docs/adr/0063-separate-semantic-evaluation-from-deterministic-hong-kong-case-proposition-conformance.md`](docs/adr/0063-separate-semantic-evaluation-from-deterministic-hong-kong-case-proposition-conformance.md)
    — separates legal-understanding evaluation from exact mechanical
    conformance, uses adjudicated Reference Proposition Maps, and admits only
    one exact complete extraction workflow.
68. [`docs/adr/0064-freeze-the-initial-hong-kong-case-proposition-extraction-conformance-catalogue.md`](docs/adr/0064-freeze-the-initial-hong-kong-case-proposition-extraction-conformance-catalogue.md)
    — freezes the initial 132-case, 132-cell, and 31-pair Hong Kong Case
    Proposition extraction conformance universe.
69. [`docs/adr/0065-use-two-pass-hybrid-analysis-for-hong-kong-case-proposition-extraction.md`](docs/adr/0065-use-two-pass-hybrid-analysis-for-hong-kong-case-proposition-extraction.md)
    — allocates Hong Kong Case Proposition extraction across deterministic
    admission and validation, primary LLM analysis, independent LLM challenge,
    Legal Desk acceptance, narrow human review, and deterministic finalization.
70. [`docs/adr/0066-define-the-hong-kong-case-proposition-llm-task-contracts.md`](docs/adr/0066-define-the-hong-kong-case-proposition-llm-task-contracts.md)
    — fixes the two stable task families, closed request kinds, evidence-bound
    request and response contracts, long-judgment behavior, independent
    challenge, exact-range quotation boundary, and no-confidence rule.
71. [`docs/adr/0067-admit-and-monitor-complete-hong-kong-case-proposition-workflows.md`](docs/adr/0067-admit-and-monitor-complete-hong-kong-case-proposition-workflows.md)
    — admits only an exact complete Case Proposition workflow and fixes its
    evaluation repetitions, context reserve, retry, cost, monitoring,
    suspension, and revalidation policy.
72. [`docs/adr/0068-package-hong-kong-case-proposition-evaluations-and-admission-profiles.md`](docs/adr/0068-package-hong-kong-case-proposition-evaluations-and-admission-profiles.md)
    — defines the immutable evaluation suite, protected real-judgment and
    Reference Proposition Map views, evaluator results, pre-frozen admission
    profile, and non-circular admission evidence chain.
73. [`docs/adr/0069-account-for-every-hkex-listing-rule-component.md`](docs/adr/0069-account-for-every-hkex-listing-rule-component.md)
    — requires immutable complete Main Board and GEM rule-component inventory
    packages with separate membership, ownership, effective-state,
    disposition, processing, and readiness results.
74. [`docs/adr/0070-use-a-lean-hkex-regulatory-source-register.md`](docs/adr/0070-use-a-lean-hkex-regulatory-source-register.md)
    — registers five ordinary HKEX current-source roles, keeps optional and
    item-specific evidence outside routine release dependencies, and prevents
    source material from entering the downstream LLM automatically.
75. [`docs/adr/0071-decide-hkex-effective-state-per-applicability-branch.md`](docs/adr/0071-decide-hkex-effective-state-per-applicability-branch.md)
    — decides current effect per exact applicability branch, preserves
    concurrent transitions, fails closed on trigger or current-product
    conflicts, and separates legal state from serving disposition.
76. [`docs/adr/0072-serve-hkex-regulatory-materials-in-english-only.md`](docs/adr/0072-serve-hkex-regulatory-materials-in-english-only.md)
    — serves complete prevailing English HKEX rule text, keeps Chinese
    translations outside the ordinary release path, and requires evaluated
    Chinese-query retrieval without fabricating Chinese source text.
77. [`docs/adr/0073-construct-complete-source-faithful-english-hkex-records.md`](docs/adr/0073-construct-complete-source-faithful-english-hkex-records.md)
    — constructs class-specific complete English HKEX records with bounded
    governing context, non-recursive cross-references, official-structure
    overlong partitioning, and exhaustive source-unit coverage proof.
78. [`docs/adr/0074-use-two-linked-conformance-layers-for-hkex-regulatory-materials.md`](docs/adr/0074-use-two-linked-conformance-layers-for-hkex-regulatory-materials.md)
    — separates evidence-to-decision from exact decision-to-artifact
    Regulatory conformance and fixes strict catalogues, coverage-matrix,
    high-risk-pair, reproducibility, and build-attestation mechanics.
79. [`docs/adr/0075-freeze-the-initial-hkex-regulatory-conformance-catalogue.md`](docs/adr/0075-freeze-the-initial-hkex-regulatory-conformance-catalogue.md)
    — freezes the audited initial Regulatory conformance universe at 284
    direct cases, 284 matching primary cells, and 57 high-risk pairs.
80. [`docs/adr/0076-use-change-gated-two-pass-hybrid-analysis-for-hkex-regulatory-materials.md`](docs/adr/0076-use-change-gated-two-pass-hybrid-analysis-for-hkex-regulatory-materials.md)
    — uses deterministic fast paths around change-gated update and record
    analysis-and-challenge proposal tasks, with Legal Desk authority and
    deterministic finalization.
81. [`docs/adr/0077-admit-hkex-multilingual-retrieval-and-downstream-answer-behavior-separately.md`](docs/adr/0077-admit-hkex-multilingual-retrieval-and-downstream-answer-behavior-separately.md)
    — separately admits multilingual retrieval, frozen-context answer behavior,
    and the complete Ask.Legal query path for English-only Regulatory records.
82. [`docs/adr/0078-define-serving-record-and-record-traceability-lookup-encoding.md`](docs/adr/0078-define-serving-record-and-record-traceability-lookup-encoding.md)
    — fixes the strict six-field Serving Record, canonical payload and note
    fingerprints, and complete reusable Release-Scope-sharded traceability
    lookup encoding.
83. [`docs/adr/0079-keep-last-verified-legislation-searchable-during-known-consolidation-gaps.md`](docs/adr/0079-keep-last-verified-legislation-searchable-during-known-consolidation-gaps.md)
    — keeps the latest applicable official HKeL legislation held searchable
    with mandatory warnings as the fallback when an official change is known
    but neither an updated consolidation nor an eligible reconstruction is
    available; ADR 0081 permits verified or assisted supporting copies.
84. [`docs/adr/0080-allow-evidence-bound-searchable-hong-kong-legislation-reconstruction.md`](docs/adr/0080-allow-evidence-bound-searchable-hong-kong-legislation-reconstruction.md)
    — permits exact evidence-bound reconstructed Hong Kong consolidations in
    ordinary search with the approved mandatory warning and ADR 0079 fallback.
85. [`docs/adr/0081-allow-official-hkel-assisted-copies-for-current-and-reconstructed-text.md`](docs/adr/0081-allow-official-hkel-assisted-copies-for-current-and-reconstructed-text.md)
    — accepts the latest applicable official HKeL verified or assisted copies
    for ordinary current records and reconstruction bases.
86. [`docs/adr/0082-use-a-closed-deterministic-hong-kong-reconstruction-operation-registry.md`](docs/adr/0082-use-a-closed-deterministic-hong-kong-reconstruction-operation-registry.md)
    — fixes the closed deterministic amendment-operation allow-list, exact
    preconditions, atomicity, bilingual execution, fallback, and traceability
    rules for Hong Kong reconstruction.
87. [`docs/adr/0083-freeze-the-hong-kong-reconstruction-conformance-catalogue.md`](docs/adr/0083-freeze-the-hong-kong-reconstruction-conformance-catalogue.md)
    — freezes the initial 56 reconstruction cases, 56 primary cells, and 30
    pairs; ADRs 0086 and 0087 expand the current catalogue to 63, 63, and 35.
88. [`docs/adr/0084-define-the-hong-kong-reconstruction-plan-and-execution-report-contracts.md`](docs/adr/0084-define-the-hong-kong-reconstruction-plan-and-execution-report-contracts.md)
    — fixes strict immutable Plan and Execution Report identities, fields,
    operation bindings, atomic results, fingerprints, and traceability.
89. [`docs/adr/0085-define-the-reconstructed-consolidation-artifact-contract.md`](docs/adr/0085-define-the-reconstructed-consolidation-artifact-contract.md)
    — fixes the immutable bilingual reconstruction package, complete derivation
    map, coverage proofs, identity result, and ordinary-renderer boundary.
90. [`docs/adr/0086-reconcile-reconstructed-hong-kong-legislation-with-later-hkel.md`](docs/adr/0086-reconcile-reconstructed-hong-kong-legislation-with-later-hkel.md)
    — fixes scalable HKeL monitoring, common-basis comparison, mismatch
    attribution, bounded suspension, impact handling, and safe restart.
91. [`docs/adr/0087-require-attested-reconstruction-capability-before-processing-or-promotion.md`](docs/adr/0087-require-attested-reconstruction-capability-before-processing-or-promotion.md)
    — separates design, implementation, attestation, candidate-processing
    activation, and exact promotion authorization for reconstruction.
92. [`docs/adr/0088-establish-the-cross-cutting-contract-foundation.md`](docs/adr/0088-establish-the-cross-cutting-contract-foundation.md)
    — establishes the implementation-neutral shared schemas, closed
    catalogues, lifecycle machines, fixtures, exact manifest, and offline
    conformance boundary.
93. [`docs/adr/0089-use-python-for-pipeline-applications.md`](docs/adr/0089-use-python-for-pipeline-applications.md)
    — selects Python 3.14 for all backend pipeline applications and shared
    production packages under a strict typed and contract-conformance profile.
94. [`docs/adr/0090-use-fastapi-and-a-strict-python-boundary-toolchain.md`](docs/adr/0090-use-fastapi-and-a-strict-python-boundary-toolchain.md)
    — selects FastAPI, Pydantic v2, Uvicorn, strict parsing and schema/JCS
    adapters, Pyright, Ruff, uv, and the core Python test tools.
95. [`docs/adr/0091-use-azure-sql-for-the-management-register.md`](docs/adr/0091-use-azure-sql-for-the-management-register.md)
    — selects Azure SQL Database, `mssql-python`, command stored procedures,
    selective append-only ledger tables, and exact forward-only migrations for
    the Management Register.
96. [`docs/adr/0092-host-pipeline-applications-on-azure-container-apps.md`](docs/adr/0092-host-pipeline-applications-on-azure-container-apps.md)
    — selects Azure Container Apps with one workload-profiles environment and
    delegated subnet per production application, internal APIs, and no-ingress
    continuous workers.
97. [`docs/adr/0093-use-managed-durable-task-scheduler-for-workflows.md`](docs/adr/0093-use-managed-durable-task-scheduler-for-workflows.md)
    — selects the standalone Python Durable Task SDK with managed Scheduler,
    isolated task hubs, register-mediated handoffs, and a separate promotion
    scheduler.
98. [`docs/adr/0094-use-azure-blob-for-primary-and-recovery-vaults.md`](docs/adr/0094-use-azure-blob-for-primary-and-recovery-vaults.md)
    — selects separately administered Azure Blob version-level WORM primary
    and recovery vaults plus Azure Confidential Ledger for database digests,
    with the Azure-wide and shared-tenant limitation recorded explicitly.
99. [`docs/adr/0095-use-a-private-azure-container-registry-and-attested-image-admission.md`](docs/adr/0095-use-a-private-azure-container-registry-and-attested-image-admission.md)
    — selects one private Premium Azure Container Registry with repository
    ABAC, digest-only releases, Notation and Artifact Signing, SBOM,
    provenance, vulnerability and licence gates, and exact OCI recovery.
100. [`docs/adr/0096-use-application-gateway-for-the-split-api-edge.md`](docs/adr/0096-use-application-gateway-for-the-split-api-edge.md)
    — selects one Application Gateway WAF_v2 with a public Review listener,
    private control listener, internal Container Apps origins, and separate
    Entra API authorization boundaries.
101. [`docs/adr/0097-use-bicep-and-azure-pipelines-for-infrastructure-delivery.md`](docs/adr/0097-use-bicep-and-azure-pipelines-for-infrastructure-delivery.md)
    — selects repository-owned Bicep, Azure Pipelines, workload federation,
    and separate stateless private pools and deployment identities.
102. [`docs/adr/0098-use-azure-monitor-and-immutable-operational-audit-archives.md`](docs/adr/0098-use-azure-monitor-and-immutable-operational-audit-archives.md)
    — selects per-application Application Insights, separate operations and
    security workspaces, closed telemetry, and immutable primary and recovery
    operational-audit archives.
103. [`docs/adr/0099-close-the-m2-m7-implementation-facing-design.md`](docs/adr/0099-close-the-m2-m7-implementation-facing-design.md)
    — proposes the six M2–M7 protocols and the remaining default-task decision
    needed to close the implementation-facing design.
104. [`docs/design/M2_DOMAIN_AND_REGISTER_PROTOCOL.md`](docs/design/M2_DOMAIN_AND_REGISTER_PROTOCOL.md)
    — fixes commands, effects, aggregate transactions, run/work lifecycles,
    and review/gap/quarantine behavior.
105. [`docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md`](docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md)
    — fixes both APIs, three worker processes, configuration, authorization,
    and proposal-preparation ownership.
106. [`docs/design/M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md`](docs/design/M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md)
    — fixes connector results and the two-vault manifest-last evidence protocol.
107. [`docs/design/M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md`](docs/design/M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md)
    — fixes executable jurisdiction/material packages and the local-only
    synthetic proof boundary.
108. [`docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md`](docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md)
    — fixes review, governance, embeddings, replacement targets, Pinecone
    naming, Ask.Legal routing, and fingerprint-bound coverage delivery.
109. [`docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`](docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md)
    — fixes the 32-scenario offline end-to-end acceptance plan.
110. [`docs/design/M2_M7_BUILD_READINESS_DESIGN_AUDIT.md`](docs/design/M2_M7_BUILD_READINESS_DESIGN_AUDIT.md)
    — records and closes the twelve implementation-facing design gaps.
111. [`docs/design/HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md)
    — contains the exact accepted conceptual reconstruction case, cell, and
    controlled-pair catalogue.
112. [`docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md)
    — contains the accepted exact 284-case HKEX Regulatory decision and
    deterministic coverage-cell catalogue and its 57 high-risk pairs.
113. [`docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md)
    — contains the accepted exact synthetic semantic and deterministic Case
    Proposition extraction coverage-cell and case table.
114. [`docs/design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md)
    — contains the accepted exact initial synthetic semantic and deterministic
    Hong Kong treatment coverage-cell and case table.
115. [`docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md`](docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md)
    — records the final design-level treatment consistency audit, corrections,
    readiness boundary, and remaining decisions.
116. [`docs/design/HONG_KONG_LEGISLATION_DESIGN_AUDIT.md`](docs/design/HONG_KONG_LEGISLATION_DESIGN_AUDIT.md)
    — classifies the audited Hong Kong Legislation design as settled policy,
    implementation work, deferred decision, or cross-cutting dependency.
117. [`docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`](docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md)
   — comprehensive closed design of the intended system.

## System shape

```mermaid
flowchart LR
    S["Official and approved publisher sources"]
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
├── contracts/           # stack-neutral normative machine contracts
├── apps/
│   ├── control-plane/
│   ├── review-api/
│   ├── acquisition-worker/
│   ├── legal-processing-worker/
│   └── promotion-worker/
├── packages/
│   ├── domain/
│   ├── contracts/
│   ├── management-register/
│   ├── management-register-adapter/
│   ├── durable-task-adapter/
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

The tree above describes the accepted target structure. The root `contracts/`
directory is the stack-neutral normative source accepted by ADR 0088.
`packages/contracts/` now contains the proved Python boundary adapters, and
`packages/management-register-adapter/` contains the proved synthetic local
SQL Server adapter and exact migration package. All other implementation
directories remain separately gated; neither implemented package becomes a
second source of normative contract authority.

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

The accepted architecture baseline includes the complete implementation-facing
closure package. Exact real-source inventories, deployed models,
measured thresholds, regions, capacity, retention, recovery, service-level,
security-assignment, and cost values remain mandatory implementation/admission
evidence with no implicit defaults. The design intentionally excludes pilot
scope, staged product versions, rollout planning, estimates, temporary
operating arrangements, and migration sequencing.
