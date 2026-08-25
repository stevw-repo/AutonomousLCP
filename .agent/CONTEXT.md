# AskLegal Legal Database Pipeline — Domain Context

This glossary defines the stable language of the autonomous legal-database
pipeline. Architecture and policy decisions belong in `DECISIONS.md` and
`docs/adr/`; current work belongs in `WORKING_STATE.md`.

## Official Hong Kong Legislation source boundary

`packages/source-connectors/src/asklegal_source_connectors/
hk_legislation_source_register.json` is the repository-owned operational
register for the fourteen frozen Hong Kong Legislation source roles. Its
current fingerprint is
`sha256:93944064e78d314670476758ec4cde7cd042caca2f285858dc906bfb108794b4`.
It contains 79 exact endpoint contracts, seven publisher-rights evidence
entries, and the project user's dated report of the AskLegal legal team's
clearance for all fourteen roles. The loader rejects missing roles, unknown
values, identifier or endpoint drift, and a mismatched fingerprint. Every role
also carries its exact ADR 0032 outage consequence: `RELEASE_BLOCKING`,
`AFFECTED_WORK_BLOCKING`, or `NONBLOCKING`.
The current register revision is `2026-08-21.1`, effective 2026-08-21. Adding
the executable outage policy advanced the register schema and all fourteen
source-profile versions to `1.1.0`; the 79 endpoint contracts remain `1.0.0`.

Five roles are technically complete and configured for bounded credential-free
read-only access: the four DATA.GOV.HK current/past inventory/data roles and
the Basic Law portal. Five roles are partially configured: HKeL Editorial
Records, HKeL publication specifications, HKeL verified copies, GLD
e-Gazette, and HKeL Gazette backcapture. One role, HKeL assisted copies, remains
technically blocked; three roles are outside V1 scope. Legal admission is no
longer a blocker, but disabled endpoints remain inaccessible until their exact
rendered, catalogue, physical-holding, or direct-search procedure exists.

`official_http.py` is a deliberately narrow source transport: direct HTTPS,
certificate and hostname verification, no proxy, cookies, redirects, ambient
credentials, uploads, or writes, bounded response sizes, exact expected media
types, and content admission before a capture result. RSS endpoints always
produce discovery-signal results; they cannot produce a legal no-change result.

Technical implementation readiness and source admission are separate facts.
`official_planning.py` accounts for all fourteen roles and all 79 endpoints
without treating legal clearance as technical readiness. `official_binding.py`
binds the six item-specific URL templates without allowing scheme, authority,
credential, query, fragment, or traversal injection. `official_inventory.py`
requires the exact English and Traditional Chinese member set before returning
one complete inventory fingerprint. `official_rendered.py` supplies a bounded
discovery-only rendered-session port. ADR 0100 selects Patchright `1.62.1` in
the acquisition worker as an ephemeral, exact-host discovery adapter. It
returns a sanitized request map, never rendered executable HTML as evidence;
all legal bytes still require inert re-fetch. The NPC application's stable
`/index` route and its `enumData`, `aggregateData`, and `wjConfig` APIs are
enabled as discovery metadata only and cannot prove a complete inventory or no
change. The HKeL Gazette grid, date-window pagination, artifact locators,
session-bound inert PDF fetch, and canonical listing manifest have been exercised
live. The role remains `PARTIALLY_CONFIGURED` because a closed date window is the
implemented completeness unit; it is not a complete whole-register inventory.
The iterator fails explicitly if the publisher's `lastPage` exceeds the
operational page cap or an intermediate page is empty, and the acquisition
activity completes enumeration before retaining any addressed artifact or
listing manifest. The publisher-API transport also enforces its declared
same-host redirect limit.

Every item-specific official endpoint now uses the one shared bounded-locator
contract: exactly one declared path placeholder and one relative locator, with
no missing or extra substitution, authority change, query, fragment, slash
ambiguity, traversal segment, backslash, or template syntax. Publisher-provided
percent escapes are encoded as data. The Gazette activity validates its exact
past-date window and language before constructing the publisher client, reports
register failures with closed codes, and reports every listed artifact as one of
`RETAINED`, `NOT_PUBLISHED`, `SOURCE_UNAVAILABLE`,
`SOURCE_CONTRACT_CHANGED`, or `UNSAFE_RESPONSE`. A completely enumerated listing
with any absent or failed selected-language artifact is `PARTIAL_CAPTURE`, not a
complete capture; an incomplete register walk writes no listing manifest or
addressed artifact. Every terminal HKeL Gazette result now retains one canonical
source-coverage report with exact counts, failure codes, source-policy version,
cutoff, observation-manifest reference when available, disposition, and blocking
flags. The HKeL backcapture role remains `NONBLOCKING`; its gaps are visible but
cannot satisfy or replace the `RELEASE_BLOCKING` GLD e-Gazette observation.

`asklegal_reporting.source_coverage` provides deterministic source-report and
complete due-source-cycle contracts. The cycle rejects source policy/version
drift, reports missing/duplicate/gap source identities, and blocks a missing or
failed `RELEASE_BLOCKING` role. It is not yet assembled across every V1 source
activity or bound into the final Coverage Status Manifest.

The current V1 acquisition service schedules exact direct-HTTP endpoint capture,
sequential multi-endpoint capture, complete-inventory capture, and the special
date-windowed HKeL Gazette capture. The complete-inventory scheduler accepts only
a registered source, exact cutoff, and optional prior member fingerprints; the
worker derives the exact member/version set from the active register. For the
release-blocking current HKeL inventory that set is the English and Traditional
Chinese XML members. It retains admitted members, isolates response-bearing
failures, writes complete attempt accounting last, and emits the source-policy-
bound coverage result. A missing, changed, or unsafe required member therefore
produces an incomplete manifest and blocks release; it cannot become complete or
no-change. The service also registers one closed ADR 0100 rendered-discovery
activity. It accepts only an enabled, fixed, `DISCOVERY_ONLY` browser endpoint
with an exact reviewed Patchright policy and cutoff; callers cannot supply a URL,
host, browser policy, or request path. It retains only the sanitized deterministic
request map and a manifest-last attempt report, both explicitly carrying no
controlling-evidence, completeness, no-change, coverage-satisfaction, or
processing authority. Browser user-info, query strings, fragments, headers,
cookies, and bodies are never retained; exceeding the request ceiling fails
closed. The current reviewed HKeL and NPC endpoints remain disabled or outside
V1, so service registration makes no browser source presently callable. The sole
`CATALOGUE_DISCOVERY` endpoint belongs to the out-of-scope official Gazette
archive. Required HKeL verified-copy, Editorial Record, publication-specification,
and GLD browser products still need inert source-evidence procedures; Patchright
cannot satisfy those gates. Service registration is executable code, not proof
that any procedure is scheduled or running on the current host.

The settled 2026-08-21 V1 direction retains direct GLD e-Gazette as the
originating/current-publication source and earliest official Gazette feed. GLD
is the Gazette publisher; its official Important Notices say selected legal
supplements are *also* available on HKeL “for information”. HKeL Gazette
therefore remains complementary backcapture, recovery, reconciliation, and
gap-detection evidence rather than an upstream replacement. GLD's Cloudflare
Turnstile acceptance path is still a technical admission blocker and must not
be bypassed. The checked-in register's `PARTIALLY_CONFIGURED` GLD role, counts,
and fingerprint above remain executable truth; V1 source readiness requires a
lawful repeatable or explicitly approved bounded manual acquisition procedure
with exact completeness and no-change evidence.

`v1-poc-runtime-proven` and `demo/expo-source-transformation` are disposable
visual branches. They may supply informational discovery leads only. All code,
contracts, fixtures, and tests are independently built and verified on `main`;
nothing is imported or cherry-picked from either branch.

## Collaboration and decision-escalation preference

For remaining design and contract work, do not ask the user
to approve choices whose answer is already dictated by accepted ADRs, exact
evidence boundaries, internal consistency, safety, or an obviously dominant
technical approach. Make those choices, validate them, and keep the canonical
design and continuity files current.

Escalate only a genuine unresolved choice that materially changes legal
meaning, product behavior, acceptable risk, cost, quality, human-review burden,
or another outcome for which no clearly dominant option follows from the
accepted design. Explain the concrete tradeoff and recommendation when
escalating. Routine case enumeration, identifier assignment, schema mechanics,
cross-reference repair, validation, and documentation consistency do not need
separate user approval. This preference authorizes design work only and does
not expand any implementation or operational authorization boundary.

## Completed local M2 boundary

M2 is complete locally against
`docs/design/M2_DOMAIN_AND_REGISTER_PROTOCOL.md`. The framework-free boundary
now includes the five exhaustive lifecycle machines, immutable Command
Envelope/Result and Effect Intent/Receipt objects, and a quarantine-release
re-entry rule that creates a new linked version-one Work Item rather than
reopening an old candidate or Work Item.

`asklegal_management_register_ports.ManagementRegisterStore` is the typed
application boundary. `InMemoryManagementRegister` is the deterministic,
thread-safe behavioral reference. It owns exact command identity and byte
fingerprints, original-result replay, optimistic aggregate versions,
single-winner keys, atomic event and effect-intent append, explicit
configured-or-undecided policy state, renewable leases, monotonic fencing,
attempt facts, one terminal receipt, disposable projection rebuild, and
complete snapshot recovery bound by an external digest. It performs no
external effect.

The SQL prefix is exactly migrations `000001` and `000002`. Migration `000002`
has nine explicit batches and package fingerprint
`f509c4af34e29087e3c71859d473eee0ed9c607b7aa9b6e85eaeee29b5b36b25`.
It adds application-owned command results and aggregate versions, append-only
ledger events/intents/attempts/receipts/policy facts, mutable claim and
projection state, exact resolution, command/effect procedures, recovery
views, and procedure-only roles/users for all five applications. The runner
requires the complete prefix from `000001`, rejects any applied-prefix or
fingerprint drift, and remains forward-only.

The real-engine M2 proof uses the already selected digest-pinned SQL Server
2025 CU7 Developer image on loopback. It passed from a fresh database and the
task-created container and credential file were removed. This is local proof,
not Azure or production admission.

## M2 command and effect contract checkpoint

The second separately authorized M2 checkpoint introduced contract package
1.2.0 and framework-free immutable Python objects for Command Envelope,
Command Result, Effect Intent, and Effect Receipt. M4 advanced the package to
1.3.0, M5 to 1.4.0, and M6 to 1.5.0; the current package root is
`sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`.

A Command Envelope binds a register-issued idempotency identity, closed
command type and contract version, exact aggregate version or `ABSENT`, actor
and authority evidence, causation/correlation/lineage, sorted immutable inputs
and policy profiles, exact configuration/contract-set/build definitions, a
bounded expiry, and a command-specific contract plus immutable payload-object
reference. The domain object is immutable and rejects coercion, malformed
timestamps, floating references, wrong reference types, unsorted/duplicate
inputs, and invalid expiry ordering.

A durable Command Result is the one authoritative applied or rejected business
result. `EXACT_REPLAY`, `COMMAND_ID_CONFLICT`, and `INDETERMINATE` are closed
submission-resolution states, not replacement business results: exact replay
returns the original bytes, conflict creates nothing, and indeterminate callers
query the register using the same command identity.

An Effect Intent records authority before an effect and binds its exclusive
application owner, capability, lineage/checkpoint, immutable inputs,
idempotency key, retry/deadline/stop rules, precondition, postcondition, and
predeclared compensation or `NO_COMPENSATION`. Its closed effect type fixes the
permitted owner/capability/destination class. It contains no destination
coordinates or secrets and performs no effect. Exactly one terminal Effect
Receipt has matching success, final-failure, cancel-before-effect, or
outcome-unknown detail. Unknown outcomes require reconciliation and block
dependent work.

## Review-surface integration direction

The initial review interface may run as a small standalone interface while the
pipeline and Approval workflow are proved. The intended later user experience
is review inside the existing Ask.Legal admin portal. Portal integration is
deliberately deferred until the pipeline works.

The durable boundary is the separately permissioned Review Application API and
its exact evidence, review, rejection, revocation, and Approval contracts—not
the first browser shell. The later admin portal should call that API and may
replace or absorb the initial browser interface without gaining direct write
access to the Management Register, altering frozen packages, or receiving
promotion credentials. Do not couple pipeline correctness to the portal's UI
framework, session store, database, or release cadence before that integration
is designed.

## Production application language

ADR 0089 selects Python 3.14 as the application-language baseline for the
control plane, Review Application API, acquisition worker, legal-processing
worker, promotion worker, and shared production packages. The exact supported
3.14 patch is pinned to **3.14.7** by the explicitly authorized local contract
spike. Any patch change must update the exact locks and repeat the proof.

Python use is governed by a strict profile: complete annotations, CI-failing
static type checks, closed frozen domain types, strict runtime boundary models,
raw-byte I-JSON rejection, independent Draft 2020-12 validation, RFC 8785 JCS
and SHA conformance, deterministic orchestrators, bounded effect adapters,
architecture tests, and reproducible dependency locks. Static types or
Pydantic models never replace the repository-owned normative schemas.

ADR 0089 alone did not select a framework. ADR 0090 subsequently selects the
FastAPI and strict Python boundary toolchain described below, and ADR 0091
selects Azure SQL Database with `mssql-python` for the Management Register.
ADR 0092 selects Azure Container Apps with one workload-profiles environment
and delegated subnet per production application boundary. ADR 0093 selects the
standalone Python Durable Task SDK with managed Durable Task Scheduler.
ADR 0094 selects flat-namespace Azure Blob Storage for separately administered
primary and recovery vaults and Azure Confidential Ledger for Azure SQL
database digests. ADR 0095 selects one private Premium Azure Container
Registry with Entra repository ABAC, separate candidate and release families,
digest-pinned images, Notation and Artifact Signing, SBOM and provenance,
vulnerability and licence admission, locked release graphs, and exact OCI
recovery packages. ADR 0096 selects one Application Gateway WAF_v2 with a
public Review listener, a private control listener, internal Container Apps
origins, and separate Entra resource and application-authorization boundaries.
Exact capacity, remaining security components, retention, recovery objectives,
and operational policies remain separate decisions. The initial review browser
client and later Ask.Legal admin portal may remain React/TypeScript clients of
the separately permissioned Review Application API. Existing Ask.Legal Python
code is reference evidence rather than a code, schema, deployment, or
authorization dependency.

## Python application and contract toolchain

### Temporary build-tool rule

Never run a temporary uv or other tool installer in a mode that edits
`~/.profile`, `~/.bashrc`, `~/.zshrc`, or another shell-startup file. A
temporary directory can disappear while the durable startup reference remains,
breaking later login sessions. Use an exact pinned executable by direct path,
keep its cache explicitly task-local, and remove task-created temporary
artifacts after the proof. A project-local durable tool path requires an
explicit repository decision; `/tmp` is never a durable PATH or startup-file
target.

ADR 0090 selects FastAPI with Pydantic v2 boundary models and Uvicorn for the
control-plane and Review Application HTTP APIs. FastAPI and Pydantic are adapter
tools, not domain or contract authorities: domain and contract packages remain
framework-free, and workers do not use FastAPI as a workflow mechanism.

All normative JSON enters as explicitly bounded raw bytes. A repository-owned
strict parser rejects byte-order marks, duplicate keys, invalid Unicode,
invalid or non-finite numbers, negative zero, and unsafe integers before
`jsonschema.Draft202012Validator` validates against a network-disabled,
preloaded `referencing.Registry`. Only then may a strict, closed, frozen
Pydantic model bind the already parsed value. Trail of Bits `rfc8785` runs
behind a repository adapter and must reproduce the RFC vectors, all repository
fixtures, and the independent Node oracle exactly. Generated OpenAPI describes
HTTP operations and supports admin-portal clients; repository-owned Draft
2020-12 schemas remain normative.

The development baseline is the official Pyright CLI in strict mode, Ruff for
lint and format, uv workspaces with one committed `uv.lock`, pytest,
Hypothesis, HTTPX, and AnyIO's pytest integration. The completed checkpoints
pin their used tools and dependencies exactly. The durability checkpoint adds
the standalone Durable Task SDK and local test backends. The package checkpoint
proves exact uv 0.12.5 offline installation, member isolation, and reproducible
wheel and container inputs. The image-admission checkpoint separately pins its
Linux amd64 OCI toolchain and proves a reproducible synthetic image and
candidate evidence graph without Azure. M3 pins and implements FastAPI,
Pydantic, Uvicorn, HTTPX, and their exact locked dependencies for the two HTTP
applications while keeping workers and the shared application-runtime package
free of HTTP frameworks. Exact Container Apps
profiles and replicas, storage, deployment workflow, provider, service-tier,
retention, and operational values remain open.

## Local Python contract checkpoint

The first implementation authorization is limited to the local synthetic
contract spike under `packages/contracts/`. It pins Python 3.14.7 in
`.python-version` and `uv.lock`, official Pyright 1.1.413 in
`package-lock.json`, and the complete Python dependency graph in `uv.lock`.
The package implements strict size-bounded raw-byte parsing, a preloaded
network-disabled Draft 2020-12 registry, an RFC 8785 adapter, SHA-256, one
strict closed frozen serving-record boundary, and the ordered raw bytes →
schema → typed binding path.

The tests reproduce all 15 existing synthetic fixture results, every exact
manifested artifact size and hash, the independent Node package fingerprint,
and two fresh-process snapshots. Adversarial tests cover BOM, duplicate keys,
invalid UTF-8, unpaired surrogates, non-finite numbers, negative zero, unsafe
integers, trailing input, size limits, external and unknown schemas, a seventh
serving metadata field, coercion, and mutation. This checkpoint authorizes no
application scaffolding, database, Azure, source, model, embedding, Pinecone,
backup, deployment, or other external effect.

## Local Python type-boundary checkpoint

The second explicit implementation authorization completes the local type-
boundary spike. Official Pyright 1.1.413 now checks the repository root in
strict Python 3.14 mode, excluding only dependency environments and ignored
local runtime state under `var/`, so current and future `apps/`, `packages/`,
tests, and repository Python tools cannot be excluded by a manually maintained
member list. Missing stubs and unnecessary type-ignore comments remain errors.

The repository-owned `tools/python_boundary_check.py` independently discovers
Python below every `packages/*` and `apps/*` source and test tree. Stable
finding codes reject explicit `Any`, bare collection annotations, unapproved
casts, unapproved type or lint suppressions, infrastructure imports in
protected packages and applications, boundary libraries in domain packages,
and FastAPI/Starlette/Uvicorn/Flask/Django leakage into contract or domain
packages. Future adapter or infrastructure packages may own external libraries;
the separately gated architecture spike must later prove their exact consumers
and capability direction.

Five runtime-narrowing casts, one jsonschema Pyright suppression, and two
`mssql-python` execute-signature suppressions are the only current exceptions.
Each is bound to one exact path, line, finding code, and durable reason;
duplicate, short-reason, unused, moved, or stale entries fail closed. Fifteen
synthetic tests prove the violation families, automatic future-tree discovery,
closed parameterized annotations, strict Pyright configuration, and complete
consumption of the exception register. This checkpoint adds no
domain kernel, application, database, cloud, source, model, embedding,
Pinecone, deployment, or other external capability.

## Local durability checkpoint

The fourth explicit implementation authorization completes the local
synthetic durability spike under `packages/durable-task-adapter/`. The exact
workspace lock contains Microsoft's standalone `durabletask==1.9.0` and
`durabletask-azuremanaged==1.7.0`. The real-emulator target is pinned to
`mcr.microsoft.com/dts/dts-emulator@sha256:1b49dcf1581168f5c620a4f32083e1291a7dddfa60434acb3eacd8b23355936a`.

The orchestration accepts only an explicit numeric workflow version and opaque
execution, command, build, configuration, contract, and input fingerprints.
Scheduler history is constrained to IDs, fingerprints, closed codes, bounded
counters, and sanitized status under the 64 KiB internal ceiling. The
orchestrator performs no effect; activities resolve external event references
and revalidate current fake-register lineage, capability, approval event,
command ID, and fingerprint immediately before the synthetic effect.

The always-on Microsoft in-memory backend and the separately invoked Docker
emulator both prove that a new worker replays and resumes a waiting instance.
While the first worker is stopped, the proof buffers a stale review event, its
exact duplicate, and a current event. A fresh worker uses a fake Management
Register reconstructed from an immutable snapshot, records the closed
`STALE_FINGERPRINT`, `DUPLICATE_EVENT`, and `ACCEPTED` results, then survives a
simulated lost activity acknowledgement: two effect-activity attempts resolve
to one synthetic effect and one immutable receipt. The emulator additionally
proved that workflow versions must match its numeric
`Major[.Minor[.Patch]]` form; the spike branch is `1.0.0`.

The emulator is memory-only. Stopping it is not a persistence or disaster-
recovery proof. The disposable container was removed after validation; the
digest-pinned image may remain cached. This checkpoint authorizes no Azure
resource, application scaffolding, source or legal data, provider call,
deployment, or production effect.

## Local package checkpoint

The fifth explicit implementation authorization completes the local package
spike. `tools/package_spike_manifest.json` is the closed proof policy for
Python 3.14.7, uv 0.12.5, all 19 current workspace members, each member's allowed
workspace dependency closure, the fixed build epoch, forbidden development
distributions, and the metadata inputs carried toward container construction.
Repository discovery fails if a present or future `packages/*` or `apps/*`
member is absent from that policy.

`tools/package_spike.py` copies only declared build inputs into two
path-distinct, fixed-metadata workspaces and runs `uv build --offline` with
Python downloads disabled. It requires equal wheel names and bytes, safe
archive paths, complete valid wheel RECORD hashes and sizes, and no generated
bytecode. Each member is then synced separately from the unchanged exact lock
into a clean non-editable environment with uv offline mode enforced. An
isolated import probe proves that only the member and its declared workspace
dependency closure are installed and importable, that imports resolve inside
the clean environment, and that pytest, Hypothesis, and Ruff do not leak into
runtime installations.

The proof also creates two deterministic USTAR bundles containing the exact
wheels, `.python-version`, root `pyproject.toml`, `uv.lock`, and a hashed entry
manifest. The bundles are byte-identical and therefore prove reproducible
container *inputs*, not an OCI image, image graph, base image, SBOM,
provenance, signing, vulnerability status, or image admission. Those are
proved separately by the local image-admission checkpoint. After the
architecture spike expanded the workspace, the complete proof passed again
with 18 reproducible wheels and 18 isolated clean installs. The current lock
SHA-256 is
`8acc9a0215fbd26e2903e2d905710e4b1ad5bd38c4429bcc752ce49f89ffb7a9` and
the deterministic container-input bundle SHA-256 is
`4acad3d6f49a419b32946e711ca8d805f864ef37524f0b4f8b4c94ca96adc455`.
This package checkpoint adds no Azure resource, network access, external data,
deployment, or production capability.

## First M2 domain-lifecycle checkpoint

The first separately authorized M2 implementation checkpoint adds a
framework-free immutable lifecycle kernel under `packages/domain/`. It defines
37 closed states and 61 exact transitions across Pipeline Runs, Work Items,
Source Contract Reviews, Coverage Gaps, and Quarantines. Generic frozen
snapshots, events, results, and state machines enforce version-one creation,
exact one-step version increments, stale-version rejection, terminal-state
closure, reachability, and new linked identities for recurrence/re-entry.

Every declared transition and every unlisted state pair is tested. The pure
kernel imports no contract, framework, infrastructure, persistence, or provider
library and performs no I/O or effect. Command/effect contracts, Management
Register ports and persistence, application runtime, and all external
capabilities remain outside this checkpoint.

A 2026-08-16 correctness audit found and the ordered correction closed the
machine-authority, guard, runtime-type, independent-oracle, and developer-test
gaps. Five versioned closed-world machine files, 33 unique lifecycle codes, and
entity-specific schema/inventory links now govern 37 per-machine states and 61
transitions. Runtime-exact validation, independent structural equivalence, and
the exact uv 0.12.5/Node.js 24.19.0/Python 3.14.7 developer command pass. JSON
event names and guard preconditions remain normative for future command
handlers; the pure Python kernel implements state/version behavior only.

Lifecycle-correction decision 1 forbids `RUN_PROMOTING → RUN_BLOCKED` and
`RUN_PROMOTING → RUN_CANCELLED`. An unknown promotion effect outcome remains
`RUN_PROMOTING` while dependent work is fenced and reconciliation runs. Only
verified success, verified approved rollback, or proved final failure may end
that state.

Lifecycle-correction decision 2 classifies every pre-promotion terminal edge.
`RUN_BLOCKED` is potentially correctable but terminal and requires a new linked
or rebased run; `RUN_CANCELLED` requires a named `PipelineAdministrator` before
an irreversible checkpoint; `RUN_FAILED` requires a non-retryable failure or
exhausted permitted attempts; and `RUN_REJECTED` is human-rejection-only.

Lifecycle-correction decision 3 keeps detailed Work Item states but exposes
four operator categories: Completed, Needs follow-up, Stopped, and Retrying.
Every terminal work item stays closed and later continuation is a new linked
item; only `WORK_RETRY_WAIT` preserves the same identity and immutable inputs.

Lifecycle-correction decision 4 permits direct switching between
`MITIGATED_CARRY_FORWARD` and `MITIGATED_WITHHOLDING` for the same unresolved
Coverage Gap when its identity and scope are unchanged. Each switch requires a
new authenticated administrator decision and exact evidence. Only
`RESOLVED_COMPLETE` closes the gap.

Lifecycle-correction decision 5 uses one recurrence/supersession rule for
Source Contract Reviews, Coverage Gaps, and Quarantines. Terminal records never
reopen. A material subject, scope, or definition change supersedes only a
non-terminal record and creates one linked `OPEN` replacement. Recurrence after
terminal closure creates a new linked `OPEN` record without changing the old
record.

Lifecycle-correction decision 6 counts a retry only after processing starts.
Transport redispatch leaves the work item `WORK_DISPATCHED`, reuses the stable
dispatch identity, and consumes no processing attempt. Only a retryable failure
from `WORK_RUNNING` may enter `WORK_RETRY_WAIT`; direct dispatch-to-retry-wait
is forbidden.

## Accepted contract amendment 1.1.0

The 2026-08-16 bounded design reconciliation advances the cross-cutting
contract package to 1.1.0 without reopening the architecture. Approval
Decision 1.1.0 has no independent `valid_until`; Approval Lifecycle 1.1.0 has
no `APPROVAL_EXPIRED` state, and a failed Promotion Manifest validity predicate
invalidates the Approval. Coverage Status Manifest 1.1.0 has no coverage-
signing policy field and requires each scope's last verification time, exact
gap/Quarantine/source-failure references, and one closed warning code matching
its status. Independent positive and negative fixtures enforce both changes.
The resulting contract package-manifest fingerprint is
`sha256:ff8a84ed971b62bb1b27451a61b0d43620c51ec55700ca492b562b4f901df594`.

## Local image-admission checkpoint

The local synthetic image-admission spike is governed by the closed Linux
amd64 policy and source ledger in `tools/image_admission_spike_manifest.json`.
The current 2026-08-22 admission pins Buildx 0.36.1, the named
`asklegal-image-admission-v0262` builder, BuildKit v0.26.2 at image digest
`sha256:de10faf919fc71ba4eb1dd7bd6449566d012b0c9436b1c61bfee21d621b009aa`,
Docker 29.7.2, Syft 1.51.0, Grype 0.117.0, ORAS 1.3.3, Notation 1.3.2,
OpenSSL 3.0.13, BusyBox `1:1.36.1-6ubuntu3.1`, and the Grype v6.1.9 database
built at `2026-08-21T06:17:24Z`. The database archive SHA-256 is
`dca26dd65bd0c4ba626af404a2e60d983d9302863eabdd8a7e7d42008fb4da3c`;
the extracted 1.9 GB database SHA-256 is
`3e1958f596f8c3dd150991a06d401e84070f1ea33538d356cc78280748d13f71`.
Checked-in URLs and hashes cover every release asset, extracted executable,
BusyBox, the database archive, and the extracted database.

`tools/image_admission_bootstrap.py` creates a new disposable input tree,
downloads only HTTPS assets absent from an optional verified cache, verifies
every release and binary hash, imports only the selected database archive, and
checks its exact database hash, schema, build time, and valid status. The
tracked synthetic dpkg status record is required so ordinary Syft discovery
includes the BusyBox package rather than silently omitting it.

`tools/image_admission_spike.py` creates two metadata-normalized contexts and
uses network-disabled, no-cache BuildKit builds. The exact image digest is
`sha256:52bd434d68d024291a83e44c5c0c8c360880001f98dfd36954bad501241c462c`.
Two complete proof executions reproduced image graph
`1f6cc922c2e35bb576c786cd4b03929ec4162dc45e3b335e9760294843a0602b`,
normalized SPDX
`e8e5dc8ef028ffdc804f136a712216601eb05cb2dd106254cb706811cb371721`,
normalized provenance
`4af9ed99424bc2e66c3c77c1aa34b425234d7a157bd83f74d6130da053921114`,
normalized vulnerability result
`8f2dc2761283655f211bb25d3f69bfcca0a6e95af343e7bd1dcf60de52011132`,
licence result
`83af83789a2931a2f85f48cca48617d0e421b7d1026c4e645630d14f2269b92b`,
and unsigned candidate graph
`ead94f80d8b176f3f1e8e6c0df759f8eaee2a0c70edaf12030ee0bb883ca6ac3`.

Syft inventories exact synthetic Python and dpkg packages. Grype scans offline,
is bound to the selected fresh database, and rejects its checked-in Log4Shell
fixture. The repository policy blocks stale, future, incomplete, KEV,
Critical, fixed High, unaccepted unfixed High, and unknown-severity states.
The synthetic licence catalogue blocks denied, review-required, unknown, or
unfulfilled obligations. ORAS copies and restores the exact OCI subject and
referrer closure. Runtime validation uses no network, read-only root,
non-root user, no capabilities, no new privileges, bounded resources, and an
exact command.

Notation creates a fresh ephemeral `LOCAL_TEST_ONLY` certificate and key for
each proof, and OpenSSL signs and verifies the canonical payload. Its
trust root is deliberately incapable of production authority, so the signed
graph changes between complete executions; within each execution the recovery
graph exactly equals the signed release graph. The spike proves no production
upstream-tool admission, ACR, Azure Artifact Signing, ABAC, private networking,
image locking, Container Apps policy, managed identity, deployment, or Azure
recovery. Those require separate Azure proofs and authorization.

## Local architecture checkpoint

The seventh explicit implementation authorization completed M1 with minimum
declarative and installable skeletons. M3 evolves that same closed policy to
the runnable local control plane, Review API, acquisition worker, legal-
processing worker, and promotion worker, plus 14 package roles.

`tools/architecture_spike_manifest.json` is the closed policy for all 19
members, 80 permitted direct internal dependency edges, 31 application
capability ports, permitted external distributions, and exclusive effect
owners. `tools/architecture_spike.py` independently discovers every current
and future `apps/*` and `packages/*` member; checks exact project and module
identity, dependencies and uv workspace sources; parses internal imports;
rejects package-to-application dependencies and cycles; verifies literal role
and capability declarations; and enforces exclusive ownership of approval,
revocation, source access, generative and embedding providers, Pinecone,
backup, routing, and recovery effects.

The current policy fingerprint is
`sha256:5253bae3e841072f8f823a1298344404bbec569f7fa3fd7b87db8f18d5ca168c`.
Synthetic tests prove undeclared-member, forbidden-import,
package-to-application, cycle, and capability-drift failures. Ordinary
repository validation requires no external service. This checkpoint proves
static architecture and ownership boundaries; runnable local composition does
not grant an external effect.

## M3 local application-boundary milestone

M3 is complete against `docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md`.
The private control-plane and public Review APIs are independent FastAPI/ASGI
applications with distinct audiences, clients, origins, OpenAPI fingerprints,
strict bounded raw JSON, closed frozen Pydantic models, safe errors,
idempotency, optimistic versions, ETags, health checks, and drift-failing
readiness. Control owns proposal-package preparation and read-only corpus,
promotion, and evidence dependencies; it owns no Approval or production
mutation. Review binds comments and decisions to one exact manifest, rejects
app-only decisions, streams synthetic evidence through an audited boundary,
and provides opaque snapshot/filter/sort/caller/expiry-bound pagination.

The replaceable Review browser shell uses PKCE primitives, only the Review
audience, and module-memory bearer-token storage. It exposes no control or
production operation. The three workers import no HTTP framework and start
with separate application configuration, task-hub names, secret-reference
namespaces, generation-fenced leases, cooperative shutdown, and individually
named disabled source/vault/model/embedding/target/backup/routing/recovery
ports. The shared `asklegal-application-runtime` package is framework-free and
contains only boundary values and local fakes.

The exact M3 OpenAPI fingerprints are
`sha256:511e404a13a7f4af67f3624c1f874130da945183fd529bb548cfb913585ca711`
for control and
`sha256:0e4adbaf3873c2a14e0ab7ba94337d1d12db919ce1681a2a9662d8dd6155ebe7`
for Review. These are local API drift gates, not normative artifact-schema
fingerprints. M3 performs no external source, model, embedding, vault,
Pinecone, backup, routing, recovery, Azure, deployment, or production effect.

## M4 local evidence-and-acquisition milestone

M4 is complete against
`docs/design/M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md`. Contract package 1.3.0
defines the exact Connector Request, Watcher Result, Scraper Result, Vault
Object Receipt, Evidence Object, Evidence Package, and Acquisition Outcome.
Python closed enums are checked against those independent JSON enums.

`asklegal_source_connectors` now owns immutable Registered Source and Source
Endpoint versions, bounded request/retry profiles, deterministic no-network
Watcher and Scraper behavior, complete pagination and inventory proof,
source-contract drift, hostile-response classification, and complete
Registered Source coverage accounting. No-change is admitted only when the
exact endpoint contract says the complete check proves it. Host, path,
redirect, media, authentication, instability, duplicate/missing member,
truncation, length, size, active-content, archive traversal, recursive archive,
and decompression-ratio failures are explicit and never become empty success.

`asklegal_evidence_vault` now owns content-addressed keys, exact immutable
versions, conditional single assignment, verified exact-version reads,
sanitized acquisition context, manifest-last package visibility, retention and
hold facts, independently verified recovery copies, corruption incidents, and
restart/lost-ack behavior. Its filesystem-backed adapters operate only under
explicit local roots and do not claim Azure WORM, identity, networking,
regional separation, or production retention.

`asklegal_acquisition_worker.AcquisitionService` stages every admitted or
isolated attempt into a complete primary package. It cannot record an
observation until an exact recovery receipt binds that same manifest. Only a
stable complete `SNAPSHOT_PRESERVED` result is
`LEGAL_PROCESSING_ELIGIBLE`; no-change, Coverage Gap, Source Contract Review,
and Quarantine outcomes all carry `NONE`. The Management Register fake selects
one immutable outcome per observation and rejects identity reuse with changed
input. Recovery-copy capability remains exclusive to the promotion-worker
boundary rather than being granted to acquisition.

The current locked package proof still covers all 19 wheels. M4's reproducible
container-input bundle is
`sha256:e34d04924daf5daf223957d268e897ae714eccd742366b06aa91b2733d5bbfb6`;
the unchanged uv lock is
`sha256:cf0e9eb5f7c6aa14a7ee79dd55d1468a5a56cb95c5f1daf05a06b807e682ce92`.

## M5 local executable-package and legal-processing milestone

M5 is complete for the platform and reserved local-synthetic package against
`docs/design/M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md`. Contract package
1.4.0 added executable package, Rulebook Activation, Rule Execution Result,
bounded Semantic Task Request/Decision, and candidate-artifact contracts. Its
independent root was superseded by M6 contract package 1.5.0.

`asklegal_legal_desks` owns the canonical-layout loader, exact member and
fingerprint validation, complete source/scope accounting, closed predicate and
disposition catalogues, profile/leakage/environment checks, scope activation,
suspension, and deterministic rule execution. Exactly one terminal rule must
match; zero and multiple matches block as `RULEBOOK_NON_TOTAL` and
`RULEBOOK_AMBIGUOUS`. Passing package tests does not activate it.

The included package is exactly jurisdiction `ZZZ`, environment
`LOCAL_SYNTHETIC`, material `TEST_LEGAL_MATERIAL`, fingerprint
`sha256:51dc8f224361a67ef6c67ea9cf63126069e664221372b9742ab4995fea879f74`
after rebinding its exact contract-package lock to 1.5.0. Its legal/rule bytes
and test-only authority are unchanged.
It contains a complete invented source universe, one non-overlapping scope,
four terminal rules, deterministic/semantic fixtures, protected evaluation
references, exact renderer/profile/attestation inputs, and no real source or
credential. The loader rejects it outside `LOCAL_SYNTHETIC`.

`asklegal_processing` owns the sole provider-neutral stateless semantic gate,
an always-disabled default runner, one deterministic no-network local fake,
exact primary/challenge reconciliation, and deterministic candidate rendering.
The contract and runtime share one closed twelve-stage catalogue and six exact
primary/secondary pairings covering the accepted Case Proposition, later-
treatment, HKEX Regulatory, Gazette-event, and Reconstruction Plan allocations.
Each pass uses its own task, profile, and prompt fingerprint. The fake exercises
`GAZETTE_EVENT_ANALYSIS` with `GAZETTE_EVENT_CHALLENGE`; it does not claim Azure
OpenAI or Hong Kong semantic admission. `LegalProcessingService` consumes only an M4
`SNAPSHOT_PRESERVED`/`LEGAL_PROCESSING_ELIGIBLE` record whose exact two-vault
receipt and preserved artifact references agree, then writes one immutable
idempotent Management Register result.

All Hong Kong Legislation, Cases, HKEX Regulatory, and Principles packages
remain `NOT_READY`. Real source rights/inventories/bytes, named owners,
adjudicated evaluation truth, exact Azure OpenAI deployments, and attestations
cannot be fabricated from platform code and remain exact M9/package-admission
evidence.

## V1 POC operating target

V1 is a strictly internal POC. Development is shifting to the Ubuntu machine:
on 2026-08-18 the user said they will probably do significant parts of
development there from now on, without retiring the Mac. The continuous runtime
is one Ubuntu 24.04 x86-64 PC with 64 GB RAM and local ext4 storage. Ubuntu is initially the only runtime host; the Mac must not be required
for operation. Azure application hosting is post-V1/deferred.

The accepted runtime uses SQL Server 2025 Developer Edition in a pinned official
Microsoft Linux container; two memory-only Durable Task Scheduler emulator
instances (general and promotion) with `systemd` timers; two separately
identified and credentialed Versity Gateway instances for Primary and Recovery
Evidence Vaults; Ubuntu `systemd-creds`; hosted Pinecone Cloud in an isolated
POC project; OpenTelemetry Collector, Prometheus, Grafana OSS, and persistent
forward-secure-sealed journald. Every container requires an exact tested version
and digest. Services are private by default and least-privileged.

The Management Register remains authoritative over orchestration. Scheduler
loss fences the old execution and creates replacement work from reconciled SQL
state and the last safe checkpoint; it is never described as resuming lost
history. Both evidence vaults currently share one filesystem, so the recovery class is
exactly `LOGICALLY_SEPARATE_POC_RECOVERY`, not protection from host or disk
loss. The earlier single-physical-drive premise was corrected on 2026-08-18:
the host has three disks, and both vaults plus the SQL data path are placed
together on its 4.0 TB disk, so the class is unchanged and still honest.
SQL ledger plus immutable Recovery Vault archives are the authoritative audit
trail. Pinecone is a replaceable serving copy built through immutable
replacement indexes; it is not an evidence or register authority.

Controlled outbound official-source and admitted hosted model/embedding calls
remain separately gated. So do credentials, Pinecone plan selection and the
first real Pinecone mutation. These infrastructure decisions authorize design
and repository implementation only, not deployment or any external effect.

The static POC contracts are under `infrastructure/poc/`. `topology.json`
declares 16 disabled services, 10 networks, and 25 credential reference names;
`artifact_admission.json` maps those services to 12 unique, non-admitted
artifacts; and `host_admission_policy.json` defines the read-only Ubuntu facts
boundary. Matching synthetic host facts never grant admission while credential-
interface proof, exact host-package locks, and private-subnet selection remain
open. These files contain no credential values and grant no build, registry,
host-mutation, service-enablement, or external-write authority.

## Hong Kong Legislation readiness checkpoint

On 2026-08-17, the user selected `HK-LEG-ORDINANCES` as the first real-package
workstream and authorized local, network-disabled implementation only. The
frozen package under
`packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/`
contains the accepted 14 stable source roles and all three non-overlapping Hong
Kong Legislation scopes. Ordinances is the current implementation target;
subsidiary legislation is not yet targeted, and constitutional/other
instruments retains the mandatory Instruments & Others review and row-level
disposition-registry blockers.

The second local checkpoint implements the deterministic, offline
`HKLEG-BASE-INV-001` inventory-accounting slice. A strict package-local Draft
2020-12 schema, closed current-inventory source and reason-code catalogues, one
declarative rule, four synthetic fixtures, and four separately hashed expected
decisions prove complete, missing, duplicate-owned, and legal-nature-
misassigned accounting. The rule decides inventory completeness only: its
legal disposition is always `NOT_APPLICABLE`, it emits no record, and its four
declared terminal branches all have exact fixture coverage.

The third local checkpoint implements the preceding deterministic, offline
`HKLEG-BASE-OBS-001` observation-freeze slice. Five exact fixtures cover one
valid frozen cutoff, a missing required Gazette observation, mixed cutoffs,
rulebook/scope/specification lock drift, and a source change detected after the
cutoff. Only the valid branch advances. The composed proof is exactly
`HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001`; later source changes must trigger a
refreeze or a separate ordinary update and cannot be silently merged.

The fourth local checkpoint implements the following deterministic, offline
`HKLEG-BASE-EVID-001` current-evidence gate. Five exact fixtures prove matching
English and Traditional Chinese current XML with either verified or assisted
official HKeL copies, missing-language blocking, conflict quarantine, and the
ban on using historical XML as a current-evidence substitute. The rule records
the copy evidence class but makes no legal-status decision and emits no Search
Record. The complete ordered proof is now `HKLEG-BASE-OBS-001` →
`HKLEG-BASE-INV-001` → `HKLEG-BASE-EVID-001`; only its golden current bilingual
bundle advances to `HKLEG-BASE-STATE-001`.

The fifth local checkpoint implements `HKLEG-BASE-STATE-001`. Seven exact
fixtures distinguish a fully supported present operative state from a missing
required state signal, partial or ambiguous location mapping, accepted-source
conflict, unknown source semantics, an unproved `InEffect`-style operative
signal, and missing written rulebook support. Only the clear branch emits
`present_state: OPERATIVE_CURRENT`; legal disposition remains
`NOT_APPLICABLE`, no Search Record is emitted, and historical assertion scope
remains `PENDING_LIMIT_RULE` until `HKLEG-BASE-LIMIT-001` runs. The complete
ordered proof is now `HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001` →
`HKLEG-BASE-EVID-001` → `HKLEG-BASE-STATE-001`.

The sixth local checkpoint implements `HKLEG-BASE-LIMIT-001`. Five exact
fixtures prove the clean transition from `PENDING_LIMIT_RULE` to
`PRESENT_STATE_ONLY` and separately block unsupported historical event,
effective-date, continuity, and complete-event-chain assertions. The complete
ordered proof now continues from STATE through LIMIT, and only the clean branch
advances to `HKLEG-BASE-ID-001`.

The seventh local checkpoint implements `HKLEG-BASE-ID-001`. A clear present
object requests new opaque register-owned Legal Item, Official Version, Legal
Location, and Search Record identities without choosing the still-unsettled
concrete ID encodings. HKeL coordinates and legacy Distillation or Pinecone IDs
remain aliases or trace facts. Source/legacy identity reuse and unproved
lineage are blocked; duplicate or continuity ambiguity is quarantined for
targeted review.

The eighth local checkpoint implements `HKLEG-BASE-DISP-001`. It keeps all five
accepted primary dispositions distinct, sends only supported presently
operative text toward record construction, preserves non-searchable accounting,
keeps unresolved facts quarantined, exposes an operative-event/current-text gap,
and blocks publication or one source signal as insufficient.

The ninth local checkpoint implements `HKLEG-BASE-REC-001`. It renders the
ADR 0021 English-first and Traditional-Chinese-second canonical text with exact
punctuation, NFC/LF rules, six metadata strings, and the `None` authority-note
sentinel. The candidate conforms to the repository-wide Serving Record schema,
uses a register-issued `rec_` identity, and fingerprints only canonical metadata.
Non-searchable, legacy-ID, incomplete-bilingual, non-canonical, and unapproved-
note paths emit no candidate.

The tenth local checkpoint implements `HKLEG-BASE-REL-001`. It proves complete
initial-release accounting across objects, locations, dispositions, candidates,
Coverage Gaps, Quarantines, investigations, and identity decisions; requires no
accepted predecessor; and produces eligibility for candidate Corpus Release
construction without itself sealing or publishing a release.

The eleventh local checkpoint implements `HKLEG-BASE-REVIEW-001`. Historical
work opens only for a named material uncertainty and binds the exact question,
objects, requested registered source roles, permitted fact, stopping condition,
and responsible Hong Kong Legislation Legal Desk. Clear items, whole-history
requests, unregistered sources, and mismatched fact scopes do not open work.

The twelfth local checkpoint implements `HKLEG-BASE-HIST-001`. Historical
evidence can establish only the exact fact permitted by the targeted Review
task. Current-evidence substitution, similarity-only proof, unavailable or
insufficient evidence, discovery-only sources, and conflicts all fail closed;
an unavailable fact that makes scope completeness impossible exposes a
Coverage Gap, while a conflict quarantines only the affected decision.

The thirteenth local checkpoint implements `HKLEG-BASE-CHANGE-001`. A source
change after the frozen cutoff must preserve the original package and create a
separate Observation. The only permitted responses are abandon-and-refreeze or
finish the internally consistent original baseline and then run an ordinary
update. Silent cutoff mixing and claims of later currency are blocked.

The fourteenth local checkpoint implements the ordinary
`HKLEG-CURRENT-OBS-001` through `HKLEG-CURRENT-OBS-003` gate. Six fixtures
distinguish supported no change, newly opened and deduplicated bounded work,
release-blocking observation failure with a Coverage Gap, item-only dependency
failure, and an urgent affected signal. A signal opens acquisition work but
does not decide legal status; supported no change reuses the existing Corpus
Release instead of creating an empty release.

The fifteenth local checkpoint implements `HKLEG-CURRENT-EVID-001` through
`HKLEG-CURRENT-EVID-004`. Nine fixtures prove complete verified and assisted
bilingual bundles, newer-assisted selection, same-version verified preference,
coverage-dependent and non-current missing evidence, bilingual version and
XML/copy conflicts, unofficial-copy rejection, and structure/identity
quarantine. Evidence class never cures a mismatch or missing artifact.

The sixteenth local checkpoint implements `HKLEG-CURRENT-DIFF-001` and
`HKLEG-CURRENT-DIFF-002`. Seven fixtures distinguish exact unchanged reuse,
unsupported reuse, payload change, multiple structure/location differences,
evidence-bundle-only change, an added object, and a missing predecessor
baseline. The classifier reads only exact accepted-bundle fingerprints and
references. It emits no record and makes no legal-identity, status, repeal, or
continuity inference; exact equality is reuse-eligible only when continuing
support is separately proved.

The seventeenth local checkpoint implements `HKLEG-CURRENT-CAUSE-001` and
`HKLEG-CURRENT-CAUSE-002`. Six fixtures prove exact Gazette cause, exact
Editorial Record cause, fully exact non-serving technical republication,
unexplained-change Quarantine, cause/bundle conflict Quarantine, and bounded
Source Contract Review. A status signal, HKeL appearance, similarity, or AI
result cannot substitute for assigned cause evidence. The gate emits no record
and makes no legal identity or status inference.

The eighteenth local checkpoint implements `HKLEG-CURRENT-EVENT-001`. Eight
fixtures route a proved operative event with no matching current consolidation
to an eligible reconstruction plan, verified or assisted known-stale fallback,
or explicit no-record Coverage Gap; they also prove ordinary-path return,
incomplete-evidence blocking, conflict Quarantine, and unbounded-affected-set
Quarantine. The gate records only a Legal Status Event and Coverage Gap. It
cannot construct text or emit a Search Record.

The nineteenth through twenty-first local checkpoints implement the ordinary
`HKLEG-CURRENT-DISP-001` → `HKLEG-CURRENT-REC-001` →
`HKLEG-CURRENT-REL-001` completion path. Disposition assigns exactly one of the
five accepted states while keeping processing separate. Record handling reuses
an immutable Search Record only when all six serving fields are equal and
continuing legal support is proved; any serving-field change requires a new
Register-issued ID and an attempted same-ID mutation quarantines. Release
accounting exactly reconciles objects, locations, events, selected and retired
records, Coverage Gaps, and Quarantines before candidate-release construction.

The twenty-second local checkpoint implements
`HKLEG-CURRENT-COMMENCEMENT-001`. Twelve fixtures distinguish exact default,
fixed-date, appointed-date, conditional-event, and progressive partial
commencement at the frozen cutoff. Operative facts require an exact operative
provision plus authentic retained event evidence; publication or HKeL
`InEffect` alone cannot establish legal effect. Future and unsatisfied events
remain in the Waiting Room, partial commencement changes only exact newly named
Legal Locations while preserving prior operative locations, and incomplete,
conflicting, or invalid affected-set claims block or quarantine without a
Search Record. The decision binds the operative-provision and event-evidence
fingerprints and produces the exact `event_operative_at_cutoff`, effective date,
operative locations, and pending locations needed by later event routing.

The package builder now regenerates the readiness contract from every actual
`HKLEG-*.json` rule and every declared frozen fixture group before fingerprinting
the package. The previously static readiness file omitted all ordinary-current
slices; package conformance now proves that its inventory exactly equals the
loader-visible rule and fixture sets.

The twenty-third local checkpoint implements `HKLEG-CURRENT-CESSATION-001`.
Fourteen fixtures cover whole and partial repeal, revocation, expiry, and
revival before and after the cutoff. Every decision binds the exact operative
provision, retained event evidence, prior event-history fingerprint, effective
date, pre-event operative/ceased partition, and exact affected Legal Locations.
Operative cessation preserves identities and moves only the affected locations
to ceased state; future events preserve the complete pre-event state. Revival
reuses an identity only with explicit continuity proof and otherwise
quarantines. Successful events append to history; blocked or quarantined facts
preserve the prior history unchanged. The rule emits no Official Version,
successor identity, substitution inference, or Search Record.

The twenty-fourth local checkpoint implements
`HKLEG-CURRENT-TEXT-EVENT-001`. Sixteen fixtures cover whole and exact-location
operative amendments, express official corrections, and HKeL Editorial Record
events with and without matching resulting HKeL bundles, plus future-effective,
incomplete, conflicting, bilingual-operation, resulting-text, and invalid-set
paths. Gazette evidence is fact authority for amendments and express
corrections; HKeL Editorial Records are fact authority only for their exact
editorial operations. Successful events append to the bound prior history.
Future events keep pre-event current text; a missing consolidation creates a
Coverage Gap and routes to the existing event/reconstruction boundary. The
rule never patches prior text, constructs resulting text, creates an Official
Version, infers identity continuity, or emits a Search Record.

The twenty-fifth local checkpoint implements
`HKLEG-CURRENT-PUBLICATION-001`. Thirteen fixtures distinguish ordinary and
Extraordinary Legal Supplement No. 1 Ordinance enactment/publication, Legal
Supplement No. 2 subsidiary-legislation and notice publication, enabling-
authority-bound Main Gazette notice publication, Legal Supplement No. 3
excluded inventory, and other-supplement discovery. They block incomplete or
post-cutoff evidence and quarantine evidence or Gazette-class conflicts.
Extraordinary timing does not change material authority. The rule produces no
commencement, legal effect, identity, continuity, Official Version, or Search
Record; it routes each publication fact to the separate evidence or
fact-specific event boundary.

The twenty-sixth local checkpoint implements the bounded pre-Plan semantic
gate `HKLEG-RECON-PLAN-SEMANTIC-001` selected by ADR 0099 Decision 7. Thirteen
fixtures cover one exact confirmed untrusted candidate plus missing profiles,
missing or invalid decision/challenge results, incomplete evidence bindings,
unsupported operations, model-authored final-text overreach, challenge
objection or unresolved uncertainty, conflicting semantic results, and failed
deterministic prechecks. The gate consumes only exact fingerprint-bound admitted
result claims; it performs no provider call or profile admission. Even its
successful result is only `UNTRUSTED_STRUCTURED_PLAN_CANDIDATE` and must enter
the complete deterministic ADR 0084 Plan validator. It creates no `rpl_` Plan,
executes no ADR 0082 operation, constructs no text, emits no Search Record, and
performs no external effect.

The twenty-seventh local checkpoint implements the full deterministic ADR 0084
Plan validator `HKLEG-RECON-PLAN-001`. Twenty-one fixtures cover two exact valid
Plans and every fail-closed boundary for candidate/contract validity, closed
operation registry, semantic binding, accepted Legal Desk authority, latest
eligible base, complete ordered event chain, applicability, dependency closure,
overlap, source-unit ownership, authentic bilingual streams, operation/event
bindings, atomic groups, undeclared input, and deterministic revalidation. A
valid result binds the existing `rpl_` candidate identity and canonical
fingerprint but executes no ADR 0082 operation, constructs no text or artifact,
emits no record, activates no scope, and performs no external effect.

That Plan-validation checkpoint was package version `0.27.0` with fingerprint
`sha256:f5eabc5748274e0cb1301ab1d10a7251f3c307bfe375808a6d5b5db253e0cbe7`.
It contains 33 offline rules and 216 exact deterministic fixtures.
It still has no real source bytes, complete source-acquisition proof, complete
rule or fixture universe, semantic profile, adjudicated evaluation, named owner
attestation, conformance attestation, activation, or processing authority. All
three scopes therefore remain `NOT_READY`; the loader continues to require
explicit blockers and later-state proof.

The twenty-eighth local checkpoint freezes package `0.28.0`, fingerprint
`sha256:fdffbc0cc0ca9fa442640d0a119f6878011054e0da6a13967629c1a2a2d20e0d`.
It adds closed source-neutral canonical language-tree and bilingual-alignment
schemas plus one ordinary textual bilingual renderer declaration. The tree
contract proves canonical pre-order structure, exact parent/child and sibling
relationships, complete ordered source-unit ownership, exact Legal Item and
Legal Location bindings, NFC/LF source text, content and recursive subtree
fingerprints, and closed authentic languages `en` and `zh-Hant`. The alignment
contract covers every final source unit exactly once and permits officially
proved one-to-one, one-to-many, many-to-one, and many-to-many groups without a
similarity-repair path. The renderer produces the exact ADR 0021 English-then-
Traditional-Chinese ordinary textual bytes and fails on unsupported structure.

Current source also executes every ADR 0082 operation transactionally against
those canonical trees. Text replacement and relabelling preserve final source-
unit identity; inserted and replacement fragments carry distinct final units;
delete and move require exact source-unit closure. Final trees, complete ordered
unit inventories, and the bilingual alignment map must match the validated Plan.
OP008 binds the exact renderer declaration and rejects any structural type or
unit kind it cannot represent. Any failure rolls back all provisional outputs.
The executor creates no ADR 0084 Report, ADR 0085 artifact, Search Record, or
external effect. No authentic HKeL XML or XSD exists in the repository or local
`var/` evidence, so this checkpoint makes no real HKeL-format claim.

## V1 POC application-image, runtime-input, and host-fact checkpoint

The disabled V1 artifact inventory now has a second closed contract for the
five repository images. `infrastructure/poc/application_image_inputs.json`
binds Linux amd64, Python 3.14.7, the exact root/package locks, every
application's complete workspace distribution closure, console health check,
service identity, listener ports, and non-root/read-only/no-new-privileges/
no-secret hardening requirements. It admits no image and deliberately leaves
the base digest, third-party wheelhouse, OCI build definition, real runtime
configuration adapters, and Ubuntu build proof unresolved. This prevents the
current local-fake entrypoints from being packaged as if they were V1 runtime
services.

`infrastructure/poc/application_runtime_inputs.json` adds the closed disabled
per-process contract. It binds all five application codes and service
identities to the operational database and exact procedure-only roles, four
scheduler/task-hub assignments, permitted vaults, 25 logical destinations,
topology networks/listeners/outbound profiles, and exactly 19 credential
filenames. It resolves no address and admits no application. Seven blockers
remain: logical destination resolution, systemd credential delivery proof,
real adapter composition, bounded readiness probes, SQL Server certificate
trust, vault-server certificate trust, and Ubuntu runtime proof.

The application-runtime package now owns a process-side
`SystemdCredentialDirectory` loader. It reads only canonical names beneath an
absolute injected `$CREDENTIALS_DIRECTORY`, uses directory-relative no-follow
opens, requires a single-link private `0400` regular file, limits material to
65,536 bytes by default, and exposes only closed path/value-free error codes.
This is a local loader proof, not evidence that systemd or a container image
delivered the files correctly and not a resolution of the separate SQL and
Versity vendor-interface conflict.

The concrete Management Register driver now provides a distinct V1
application factory. It binds `sql-server:1433`, `AskLegalPocOperational`, and
the five exact application principals; requires strict encrypted transport with
hostname-validated server certificates; bounds login time; holds passwords in
a redacted value object; and normalizes connection failures without credential
or topology detail. The old raw-string factory remains only for the opt-in SQL
spike and hides its connection string from representation. This makes trusted
SQL certificate issuance and application-image trust-bundle delivery an
explicit admission blocker rather than accepting `TrustServerCertificate`.

The locked Durable Task emulator SDK now has an exact V1 settings/factory
boundary. Control, acquisition, and legal processing use disjoint hubs on
`dts-general:8080`; promotion alone uses `promotion` on
`dts-promotion:8080`; Review is rejected. The emulator receives no token and
uses private-network plaintext gRPC, requires an explicit concurrency profile,
and preserves only `MEMORY_ONLY` plus `REPLACEMENT_FROM_SAFE_CHECKPOINT`.
All five applications compose their own file credential into the exact SQL
factory and the four applicable scheduler settings without connecting.

The evidence-vault package now also owns the disabled V1 S3-compatible client
boundary. Locked Boto3 `1.43.49` receives only explicit credential-file values,
vault-specific HTTPS endpoints and CA bundles, SigV4 path-style addressing,
and one bounded retry/timeout profile. Exact provider version IDs are encoded
losslessly; conditional create, SHA-256, COMPLIANCE retention, legal hold,
exact-version read-back, replay adoption, manifest-last writing, and
primary-to-recovery copying pass against deterministic S3 fakes. Every
application now composes only its authorized Primary/Recovery vault roles.
Client construction opens no connection. Real Versity behavior, certificates,
bucket/policy setup, credentials, and Ubuntu access remain unproved.

The application-runtime package now defines the complete ordered V1 readiness
dependency set for each application and an asynchronous gate with a hard
per-probe response deadline, safe normalized failure/timeout results, complete
evaluation, and fail-closed aggregate status. The runtime-input contract binds
those exact dependency codes. SQL has a non-mutating bounded encrypted
connection plus exact `SELECT 1` check; each vault has a read-only versioning
and Object Lock check. Official DTS emulator guidance documents gRPC port 8080
connectivity checks but no non-mutating SDK/task-hub health operation, so the
scheduler, telemetry, Review/egress, and real-host probe implementations remain
admission work rather than relying on private SDK internals.

The V1 topology now also reflects the accepted M3 evidence boundary: Control
proposal preparation and Review evidence streaming each receive a separate
read-only Primary Vault credential reference and internal network path. This
corrects the earlier omission but creates no credential or vault access. The
real endpoint resolution, server-certificate trust, bucket policies, and
negative authorization proof remain unresolved admission work.

`tools/v1_poc_collect_host_facts.py` is the corresponding bounded read-only
Ubuntu collector. It emits exactly the facts accepted by the host-admission
policy, reads no credential value, makes no host change, refuses the Mac, and
leaves package-lock and subnet facts empty until their separate admission
steps. Inability to inspect nftables, paths, sealing, or credential modes fails
closed.

`infrastructure/poc/systemd_unit_inputs.json` now turns the accepted unit graph
into a closed disabled contract: one input for every topology service, two
privileged one-shot bootstrap units, five cadence-unresolved timers, exact
dependencies, runtime identities, credential names, write paths, root-owned
management, and a uniform hardening profile. Six explicit blockers prevent
runtime commands, installation, image pull, credential bridging, subnet use,
or enablement. The validator reads repository JSON only; it neither renders nor
touches systemd. All five application compositions now load every one of their
19 declared credential files. Credentials without an admitted provider adapter
remain opaque redacted material rather than receiving an invented format.

`infrastructure/poc/host_identity_inputs.json` closes the remaining static
identity boundary for the ten accepted services that own host paths. Every
account is locked, non-login, group-isolated, uncreated, and has no numeric
UID/GID until collision-free allocation on the Ubuntu host; 14 owned paths are
bound back to topology. The image-defined SQL identity and pathless DTS/egress
container identities are not misrepresented as created host accounts. Four
blockers retain UID/GID allocation, container mapping, ownership read-back, and
real Ubuntu identity proof.

`infrastructure/poc/credential_interface_proof_inputs.json` turns the remaining
SQL/Versity secret-delivery spike into an exact, still-disabled executable-
evidence contract. It binds the credential-gated SQL service and both Versity
vault services to their artifact selection and exact systemd credential names;
requires six delivery, startup, inspection, rotation, restart, and evidence-
then-cleanup steps; scans seven leak surfaces; and requires 12 manifest-last
evidence classes. All three subject results remain `NOT_RUN`. Six explicit
blockers retain Ubuntu access, read-only resolution, pull/run, an exact Versity
digest, synthetic one-use credential creation, and named throwaway-state
mutation/cleanup authority. A failed exact-image proof still requires the
accepted user choice and cannot silently relax the file-only secret rule.

`infrastructure/poc/v1_admission_gate.json` is the authoritative composite V1
POC verdict. It binds 14 ordered components: the eight currently implemented
static contracts plus real Hong Kong package, official source,
model/embedding, Pinecone, Ubuntu end-to-end, and final named-human acceptance
admission. The static contracts may validate while the aggregate remains
exactly `V1_POC_NOT_ADMITTED`, `ready=false`, with all external, host-mutation,
image-pull, credential-creation, service-enablement, and Pinecone-write
authority false. `tools/v1_poc_admission.py` re-executes every static checker
before reporting eight validated static contracts and 14 blockers. It performs
no host or external action and prevents a partial local pass from being
misrepresented as V1 readiness.

## M6 local Review, Approval, corpus, and promotion milestone

M6 is complete locally against
`docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md`. Contract package 1.5.0 has
74 cross-cutting objects and adds frozen Proposal Package Manifest plus exact
Embedding Profile, Request, and Receipt contracts. Its independently reproduced
root is
`sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`.

`asklegal_corpus` deterministically freezes complete per-scope Corpus Releases,
one-release-per-scope Desired-State Inventories, fail-visible Coverage Status
Manifests, and the eleven exact proposal members before committing the root
manifest last. The control-plane preparation service validates the root against
the closed schema registry and proves exact read-back. Serving fingerprints
cover exactly `text`, `country`, `jurisdiction`, `type`, `source`, and
`authority_note` while identity and traceability remain outside that payload.

The Review API's local command path now appends real fingerprint-bound comment,
Approval, rejection, and revocation facts to the M6 register rather than only
returning generic command receipts. The sole human permission remains
`PipelineAdministrator`; the register requires a delegated named human and
reason, rechecks current assignment at consumption, invalidates drift, and
allows one execution lineage only. An exact restart of that same lineage reads
the already-consumed projection rather than consuming again.

`asklegal_promotion` defines exact embedding and replacement-target ports plus
no-network local fakes. The promotion worker validates the immutable manifest,
complete embedding-profile fingerprint, environment, expiry, cost, base state,
validity predicates, coverage fingerprint, target definition, every vector and
metadata record, retrieval gate, provider-native backup, independently verified
recovery copy, routing compare-and-set, and post-cutover generation. Lost
acknowledgements are reconciled by enumerating actual state. Post-cutover
failure reverse-swaps only to the retained
predecessor. Retirement accepts only one manifest-declared exact inactive name;
broad selectors have no port representation.

All M6 effects are synthetic and local. No Azure OpenAI, Pinecone, native
backup, Ask.Legal App Service slot, protected Azure coverage store, Azure
resource, deployment, corpus publication, or production route was accessed or
changed.

## M7 complete local synthetic pipeline milestone

M7 is complete locally against
`docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`. Repository tooling in
`tools/local_conformance.py`, exposed as the second control-plane console entry
point `asklegal-local`, is the only composition layer allowed to import all five
local application boundaries. It is not a sixth deployed application and does
not change the closed architecture graph.

The stable CLI implements exact marked-root reset, one named scenario, and all-
scenario proof semantics. `prove --all` executes the closed `E2E-001` through
`E2E-032` catalogue twice in clean path-distinct directories with DNS/socket
access denied. The frozen profile binds Python, uv/dependency lock, all 19
workspace builds through the package policy, contracts, six protocols,
architecture/image/package policies, deterministic clocks/IDs/jitter, and each
scenario's expected result/fact/effect counts.

The golden flow schedules through the versioned Control API and uses the actual
local acquisition service, primary/recovery vault fakes, ZZZ package lifecycle
and rule engine, candidate renderer, Corpus
Release/DSI/coverage/promotion construction, frozen proposal package, Review
HTTP API and loaded minimal browser client, named-human Approval register, embedding,
replacement target, backup, routing, reverse-swap, and exact same-lineage
recovery. The remaining scenarios prove no-change, false-positive capture,
replay/conflict, restart, lost acknowledgement, stale version/fencing,
overlap, both cancellation boundaries, source failure/hostility/drift,
non-total rules, carry-forward/withholding, quarantine re-entry/recurrence,
stale or unauthorized review, revoked/consumed Approval, vector/inventory/cost/
backup/base/coverage failures, rollback, digest-verified register recovery,
broad-deletion denial, and ZZZ environment containment.

The authoritative report statement is exactly `local synthetic platform
proved`. M7 makes no real-source, Hong Kong legal-readiness, Azure OpenAI,
embedding-quality, Azure, Pinecone, Ask.Legal routing, deployment, or production
claim. M8 remains separately gated.

## M2–M7 build-readiness audit

The 2026-08-16 full design audit found the architecture coherent and twelve
implementation-facing gaps. Accepted ADR 0099 closes them through six accepted
protocols:

1. Domain and Register protocol;
2. Application interfaces;
3. Acquisition and Evidence protocol;
4. executable Legal Desk package;
5. Review and Promotion protocol; and
6. end-to-end conformance plan.

The durable audit is
`docs/design/M2_M7_BUILD_READINESS_DESIGN_AUDIT.md`; the protocol files are
named `M2_DOMAIN_AND_REGISTER_PROTOCOL.md` through
`M7_END_TO_END_CONFORMANCE_PLAN.md` under `docs/design/`. Their material choices
and final package are accepted, so the design prerequisite is complete.
Machine schemas, code, local proof, real-source packages, cloud proof, and
production admission remain separately authorized work.

The audit also clarifies that effect-free proposal-package preparation belongs
to the control-plane coordination boundary through pure corpus/promotion
services. The promotion worker only reads and executes an exact approved
manifest. M7 uses one test-only synthetic Legal Desk package to prove platform
behavior; it makes no Hong Kong or production legal-readiness claim.

Azure OpenAI models sold by Azure through Microsoft Foundry are the selected
stateless generative and embedding service boundary. Exact model deployments,
versions, prompts, dimensions, thresholds, and limits are immutable admission
profiles, never floating architecture defaults. This matches the provider
family verified in Ask.Legal Backend. Its Cloudflare AI endpoint and API-key
authentication are not inherited; private Azure connectivity and Entra
workload identity remain the pipeline security direction.

Decision 2 selects one human `PipelineAdministrator` role, assignable to
multiple named people, for all Review and Control actions. There is no separate
step-up freshness rule, Approval TTL, or absence-cover role; Approval remains
single-use and predicate-bound. Application and workload identities stay
separate.

Decision 3 removes fixed Quarantine/review SLAs. Every item has severity and
named administrator assignment; urgent release-blocking or potentially
misleading current-law issues notify immediately. Due times are optional and
administrator-set. Elapsed time never releases or resolves material.

Decision 4 selects a restricted Ask.Legal App Service `candidate` slot,
distinct from the existing development slot, for validated manual production
swap and reverse-swap rollback. The development slot remains development-only.
Each request pins one routing generation. Production admission must prove the
plan's additional-slot limit and shared capacity.

Decision 5 fixes Pinecone index names as
`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`, normally 38 characters with an
internal 40-character limit. Creation validates allowed characters, the live
45-character API limit, the actual project-ID hostname constraint, and the
full Serving State fingerprint; a shortened-token collision hard-fails.

Decision 6 selects one complete immutable Coverage Status Manifest per routing
generation. The routing generation binds its exact SHA-256 fingerprint and
protected immutable Azure download reference. Ask.Legal retrieves it through
authenticated protected storage, verifies and caches it by routing generation,
blocks activation when it is missing, incomplete, or mismatched, and fails
visibly when neither stored nor verified cached bytes are available. There is
no dedicated coverage-signing identity, signing key, rotation, or signature-
validation lifecycle.

Measured/organization-owned values such as regions, capacity, retention,
recovery objectives, named role assignees, source rights, real endpoint
inventories, and evaluation evidence are admission data. Missing data disables
the capability and does not reopen the general design.

## Management Register technical boundary

ADR 0091 selects one Azure SQL Database as the production Management Register
and Microsoft's first-party `mssql-python` DB-API driver behind a typed
`ManagementRegisterStore`. Exact versions and Azure capacity settings remain
implementation and operations decisions.

Applications cannot mutate authoritative tables directly and no general-
purpose ORM owns the write path. Separate contained Microsoft Entra users and
custom database roles receive only `EXECUTE` on their schema-qualified command
procedures and `SELECT` on owned views. A separate migration identity owns DDL.
The synchronous driver stays inside a bounded adapter; async FastAPI paths run
one complete database operation in a dedicated bounded AnyIO worker thread and
never share a connection across a thread or `await`.

One command is one short transaction. It atomically records the fingerprint-
bound inbox claim, immutable object and lifecycle events, outbox intents,
rebuildable projection changes, and exact result. No external effect occurs
inside that transaction. Critical single-winner transitions combine database
constraints and compare-and-set with finite transaction-owned application
locks and targeted serializable isolation. Ambiguous commit outcomes are
resolved by querying the immutable command result before any retry.

Selected immutable authoritative facts use explicitly declared append-only
ledger tables and externally stored database digests. Ledger is not a database-
wide default and does not replace the Evidence Vault, identity separation,
backups, restore drills, or digest verification. Large artifacts stay outside
the register. Canonical JSON is stored as validated RFC 8785 UTF-8 bytes with
its exact fingerprint and typed constraint columns; SQL Server JSON behavior
is not normative.

Schema changes use closed forward-only migration packages: an exact manifest
lists ordered T-SQL batch bytes and fingerprints, the narrow repository-owned
runner applies the complete package in one transaction under a migration lock,
and the applied package fingerprint is appended to the migration ledger. No
template substitution, implicit file discovery, ORM autogeneration, `GO`
parsing, or automated destructive down migration is permitted.

## Local Management Register checkpoint

The third explicit implementation authorization completes the synthetic local
Management Register spike. It pins `mssql-python==1.12.0` and its complete
transitive graph in `uv.lock`. The real-engine target is SQL Server 2025 CU7
Developer on Ubuntu 22.04 at immutable MCR digest
`sha256:fa0dcf206087759fe6dad4cc02bfa88d97439085e548fbca9039330519c0cf1d`.
SQLite is not used.

`packages/management-register-adapter/` owns the runtime-checked driver wrapper,
typed store, and repository migration runner. Its first migration contains five
explicit T-SQL batches and JCS package fingerprint
`59e606d268bc3910670424dbc8acad823691e358581748f838bd6b9f46256cd0`.
The runner rejects changed or undeclared bytes, `GO`, invalid ordering, stale
package fingerprints, and applied-ID fingerprint drift before execution. It
uses the driver's transaction boundary plus a finite transaction-owned
application lock; an explicit nested `BEGIN TRANSACTION` is forbidden because
`mssql-python` already owns the outer transaction when autocommit is disabled.

The synthetic schema proves append-only ledger facts, ordinary rebuildable
projections, successful execution under exact Review and Promotion users,
direct-DML denial, canonical bytes and hashes, idempotent replay,
concurrent single-winner Approval consumption,
Serving State activation, atomic inbox/event/outbox/result changes, bounded
deadlock-victim retry, and lost-ack resolution through the immutable command
result. Ledger verification locally requires both read-committed snapshot and
snapshot isolation and runs outside a user transaction. External digest
storage remains an Azure-only future proof.

The real-engine checkpoint ran on the prior Ubuntu development host with Docker
29.1.3 enabled; that user was deliberately not a member of the Docker group and
used `sudo docker`. This is historical proof evidence, not a prerequisite fact
about every later workspace host. The validated container and temporary
credential were removed, while the digest-pinned image may remain cached on
that prior host. This checkpoint authorizes no Azure resource, external data,
legal record, application, deployment, or production capability.

## Production hosting and network boundary

ADR 0092 selects Azure Container Apps for the control plane, Review Application
API, acquisition worker, legal-processing worker, and promotion worker. Each
uses a separate workload-profiles environment and delegated subnet because a
Container Apps environment is the platform network secure boundary and the
five applications have different ingress, egress, credential, and blast-radius
requirements.

The two APIs are internal continuously available origins behind the ADR 0096
Application Gateway edge. Only the Review listener is public. The control
listener is private and has no public host or route. The three workers are
continuously running apps with ingress disabled and Durable Task Scheduler
connections. Production initially keeps at least one replica per app; scale to
zero is not assumed for a durable worker with no connected process to receive
streamed work. Exact profiles, replica sizes and limits, region, zones,
firewall, DNS, recovery, service levels, and cost remain measured decisions.

Every app has its own runtime managed identity, database role, secret access,
scaling and health policy, deployment identity, and deployment job. Each
subnet follows an application-specific outbound policy. Private Azure
dependencies use private endpoints and private DNS where supported, and public
network access is disabled after the private path is proved. A shared network
hub may provide private endpoints, DNS, firewall, registry, and observability
without merging application capabilities.

The promotion worker is a no-ingress continuous app, not a manually started
Container Apps Job. The Job start operation permits an execution-template
override, including image and command, and exposes configured Job secrets to
the starter. Promotion instead consumes a small durable command and
independently revalidates the exact Approval, frozen manifest, evidence,
recovery state, fingerprints, target, and expected base state. Correctness
never relies on replica count or deployment overlap.

ADR 0002's downstream Ask.Legal App Service configuration boundary remains
settled and separate. Container Apps hosts the pipeline; it does not move
Ask.Legal itself, alter the App Service slot question, or couple the future
admin portal to the Review API's host.

## Authenticated API edge boundary

ADR 0096 selects one regional Azure Application Gateway WAF_v2 in a dedicated
hub edge subnet. A public HTTPS listener and WAF policy route only to the
Review API. A separate private-IP listener, private DNS name, certificate,
backend pool, probe, routing rule, and WAF policy route only to the control API
through an approved private operator-network path. The public frontend has no
control route, the private listener has no public DNS or fallback, and the
gateway has no route to any worker.

Both API origins remain internal Container Apps environments with private
virtual IPs and public network access disabled. Their app ingress is enabled
at the environment or VNet scope so the hub gateway can reach it; Container
Apps calls this `external` app ingress inside an *internal environment*.
Private DNS, exact backend FQDN and SNI, end-to-end TLS, subnet restrictions,
and trusted-proxy rules prevent direct-origin and forwarded-header bypass.

Application Gateway owns TLS, WAF, coarse rate limits, routing, and origin
isolation, not authentication or business authority. Control and Review use
separate single-tenant Entra resource registrations, audiences, client
allow-lists, scopes, app roles, and API authorization. Each API validates the
token signature, issuer, tenant, audience, lifetime, stable subject, actor
client, delegated scope or expressly admitted application role, and current
operation permission. A passed WAF rule, private network, valid tenant token,
mutable name, or raw group claim is insufficient.

The standalone review browser uses authorization code with PKCE and its own
Review client registration. The later admin portal is admitted as another
client of the same versioned Review API. Approval and revocation reject
app-only tokens and bind the stable human Entra identity. Review and Control
access require the single `PipelineAdministrator` role and MFA before
production admission, with no separate action-specific step-up. Exact
authentication strength, device and session conditions, private operator path,
WAF values, enhanced DDoS choice, capacity, region, recovery, and cost remain
explicit later values with no implied default.

Production WAF policies use a tested current Azure Default Rule Set in
Prevention mode, exact exclusions and size limits, coarse anomaly rate limits,
and sensitive-data log scrubbing. Application policies still enforce exact
identity-aware limits, raw-byte and schema validation, idempotency, concurrency,
and single-winner decisions. One gateway is an accepted shared API-availability
and configuration blast radius, not a shared authorization boundary. No
automatic cross-region edge failover or direct public-origin break-glass path
is claimed.

## Infrastructure-delivery boundary

ADR 0097 is **accepted**. It selects repository-owned Bicep
with GitHub retained as the reviewed source repository and Azure Pipelines as
the operational deployment control plane. Entra workload identity federation
replaces stored Azure credentials. Fresh Microsoft-hosted agents handle
offline and ARM control-plane work; separate stateless Managed DevOps Pools in
delegated subnets handle private ACR supply-chain work and
private Azure SQL migrations.

A **Deployment Change Package** is the immutable operational package
binding exact source and compiled template bytes, tools, target, identity,
what-if output, cost inputs, rollback basis, evidence destination, and one
Operational Deployment Approval. It is not a legal Promotion Manifest or ADR
0007 Approval. Infrastructure apply, role assignment, policy and locks,
migration, image admission, each application's deployment, retirement, and
break-glass remain separate identities and gates. Incremental apply cannot
infer deletion from a resource missing in Bicep.

The decision accepts an additional Azure DevOps control plane to avoid either
operating private GitHub runners or depending on GitHub Enterprise Cloud for
the managed private-network and protected-environment path. The user explicitly
accepted that cost, governance, and visible Ask.Legal-standard deviation on
2026-08-16, prioritizing Azure-only simplicity.

An explicitly authorized 2026-08-15 read-only comparison found that the local
Ask.Legal Core Admin, frontend, Backend, and AI-Service repositories all use
GitHub Actions for checked-in Azure delivery. Static Web Apps workflows consume
stored deployment tokens and App Service workflows consume stored publish
profiles. None of the inspected repositories contains Azure Pipelines YAML,
Bicep, Terraform, `azure/login`, `id-token: write`, or another checked-in
workload-federation path. This comparison is non-authoritative reference
evidence, not imported legacy policy: workload federation is a recommended
security improvement, but Azure Pipelines is a deviation from the visible
delivery standard. Repository files do not prove the GitHub organization plan
or external control-plane configuration.

GitHub Actions and Entra OIDC do not themselves require Enterprise Cloud. On a
lower plan, the project could preserve GitHub Actions by operating fresh
ephemeral self-hosted runners inside the permitted Azure networks for private
ACR and Azure SQL work and by supplying an independent production-approval
control. That is not the existing approach unchanged: standard public GitHub-
hosted runners cannot reach services exposed only through Azure private
endpoints, and required-reviewer environment protection for private
repositories is unavailable below Enterprise Cloud. Public service exceptions,
reusable deployment secrets, persistent runners, or approval by unprotected
workflow convention are not acceptable substitutes.

A focused 2026-08-16 check found only standard `ubuntu-latest` GitHub-hosted
runners and no checked-in larger-runner labels, runner groups, Azure private-
network runner configuration, or other positive Enterprise Cloud signal. The
code-only working inference is therefore “probably Team or lower, or Enterprise
capabilities are unused,” with low confidence. The actual plan remains an
organization billing-and-licensing fact that must be checked by an authorized
owner or billing manager for cost comparison, but it does not reopen the
accepted Azure Pipelines selection.

## Observability and operational-audit boundary

ADR 0098 is **accepted**. It selects direct Azure Monitor
OpenTelemetry instrumentation authenticated by each application's managed
identity, five separate workspace-based Application Insights resources, one
shared application-operations workspace, and one separately restricted
security-and-audit workspace. The five Application Insights resources preserve
application attribution and resource-context access; the two workspaces are
explicit shared availability and configuration blast radii.

Azure Monitor is the detection and query plane, not the authority for legal or
business facts, Approval, deployment, promotion, Serving State, or effect
receipts. Required operational audit records also go to a dedicated WORM
Operational Audit Archive. A protected audit-sealing job produces exact
interval packages, and the promotion worker's already accepted recovery-copy
capability copies only those packages into a separately administered Recovery
Audit Archive using conditional create, exact-version read-back, hashes, and a
complete manifest. This preserves ADR 0094's single recovery-writer boundary.

The decision includes a closed telemetry allow-list, legal-text and secret
scrubbing, W3C trace correlation, protected no-sampling classes, bounded
exporter retry, explicit degraded-observability gates, closed diagnostic-
category coverage, and separately owned alerts. Azure DevOps audit export is a
mandatory proof because the native stream currently requires a stored
destination key and the audit service has limited retention and preview
surfaces. The decision authorizes documentation only; no telemetry or archive
resources are authorized.

## Durable workflow technical boundary

ADR 0093 selects Microsoft's generally available standalone Python Durable
Task SDK with managed Azure Durable Task Scheduler. Durable applications stay
ordinary Python Container Apps rather than running in an Azure Functions host.

Production begins with two scheduler resources. A general scheduler contains
separate task hubs for the control plane, acquisition worker, and legal-
processing worker. A separate scheduler contains only the promotion task hub
and is reachable only from the promotion application network. The Review API
has no task hub or Scheduler role. Each durable application uses its own user-
assigned managed identity with `Durable Task Data Contributor` scoped only to
its own task hub; no runtime identity receives Scheduler-wide access.

Cross-application durable handoff occurs through the Management Register's
transactional outbox. The receiving application's dispatcher claims its owned
fact and schedules an idempotent instance into only its own task hub. Task hubs
do not call activities or child orchestrations across application boundaries.
The Scheduler's private endpoints and private DNS supply the network path;
public network access is disabled after proof, and reachability never replaces
RBAC.

The Scheduler owns operational execution history, deterministic replay,
timers, waits, retries, activity dispatch, and external-event delivery. The
Management Register remains authoritative for business and legal state,
capabilities, work admission, evidence bindings, Approval, promotion
admission, Serving State, command results, and effect receipts. There is no
distributed transaction between them.

Orchestrators are deterministic and effect-free. Activities are idempotent,
fingerprint-bound, and revalidate the current register execution lineage and
capability before every effect. Scheduler history contains only opaque IDs,
fingerprints, closed codes, counters, and sanitized status under an initial 64
KiB per-payload ceiling. Legal text, evidence, prompts, model or provider
payloads, approvals, comments, secrets, and raw exceptions stay outside
history.

Every instance has an explicit immutable workflow version and build,
configuration, contract, and input fingerprints in the register. Old replay
branches remain available while work is in flight. Terminal Scheduler history
is purgeable operational data, not the audit, backup, or recovery authority.
The local emulator is in-memory and proves workflow behavior only; managed
identity, private networking, persistence across Scheduler restart, retention,
capacity, and regional recovery require separately authorized Azure proof.

Managed Durable Task Scheduler does not fail in-flight state over to another
region. Safe regional replacement fences the old execution lineage, reconciles
external receipts, selects one exact register checkpoint, and starts a new
recovery lineage. A resumed old orchestration must fail its register capability
and lineage checks. No seamless regional workflow failover is claimed.

## Evidence and recovery technical boundary

ADR 0094 keeps production artifact storage Azure-only. Dedicated flat-
namespace GPv2 Blob accounts form the primary Evidence Vault; separate Blob
accounts in a dedicated recovery subscription under the same Microsoft Entra
tenant form the Recovery Vault. Where data-location rules permit, recovery
uses a different Azure region pair. Both sides use block blobs, versioning,
change feed, soft delete, locked default version-level WORM retention,
exact-version legal holds, infrastructure encryption, private endpoints,
managed-identity RBAC, and public and Shared Key denial.

Only the promotion worker can create and verify recovery copies. It uses one
explicit exact-version, `If-None-Match: *`, read-back, SHA-256, and complete-
manifest protocol; Azure Blob object replication is not an additional baseline
mechanism and no deletion propagates between vaults. Runtime identities cannot
delete versions, weaken retention or holds, or administer storage. Retention
expiry is never deletion authority.

The Recovery Vault isolates ordinary application, account, subscription,
administrator, policy, and regional failures. It is not provider- or tenant-
independent: an Azure-wide failure or compromise of the shared Entra tenant
can affect both copies. The user accepted that limitation to keep one cloud and
one identity and operating model. A later different-tenant or different-
provider copy can reuse the immutable artifact and recovery-manifest contracts.

Microsoft-managed keys plus infrastructure encryption are the baseline on both
copies so one customer key cannot become a shared irreversible loss switch.
Azure SQL ledger digests go to a separately administered private Azure
Confidential Ledger, with verified digest and receipt checkpoints included in
the Recovery Vault. Azure SQL backups and Pinecone-native backups remain
separate recovery mechanisms.

## Container image and software-supply-chain boundary

ADR 0095 selects one shared Premium Azure Container Registry as a platform
service for the five applications. Premium is required for the accepted
private endpoint. The registry uses `RBAC Registry + ABAC Repository
Permissions`, disabled public, anonymous, and admin access, and conditioned
roles over `base/`, `tool/`, `candidate/<application>`, and
`release/<application>` repository families. A role without an ABAC repository
condition is registry-wide and is forbidden for application data-plane use.

Every application has a separate build, pull, verification, and deployment
identity. A build may write only its candidate repository; a runtime may read
only its release repository; the image-admission identity copies without
rebuilding; and the application deployment identity can update only that
Container App after a fresh admission check. Neither candidates nor tags are
deployment authority. Container Apps revisions name only
`release/<application>@sha256:<digest>` references, and a deny-mode policy
rejects other registries, repository families, and tag-only references.

Production images use Notation signatures backed by one centrally administered
Azure Artifact Signing Private Trust profile. The one profile is a shared
software-release trust root rather than a shared runtime capability. Strict
verification binds its expected subject, timestamp trust, registry scope,
release repository, and exact digest. Container Apps does not supply the
selected AKS-style in-platform signature admission, so the separately
permissioned deployment job verifies the signature and immutable Image
Admission Record immediately before every deployment or rollback.

The ACR path is private. Artifact Signing is not claimed to have a private
endpoint: the isolated signing runner has a narrow outbound allowlist for the
selected regional signing, Entra, and timestamp endpoints. Trust roots are
admitted and pinned before a release rather than downloaded during it. The
Private Trust chain, timestamp, revocation, expiry, and long-term offline
verification remain mandatory Azure proofs.

BuildKit provenance, a pinned Syft SPDX JSON SBOM, pinned Grype with an exact
database snapshot, and a repository-owned licence-policy evaluator form the
initial deterministic admission tool boundary. Exact versions are not floated;
they remain disabled until local conformance fixtures prove their provenance,
coverage, output, known-vulnerability, licence, and offline behavior. Unknown
or incomplete scan or licence results block. Exceptions are exact, expiring,
owned records rather than global ignore files.

The ACR release graph is locked but remains a replaceable deployment copy.
Geo-replication protects availability and propagates deletes; it is not a
backup. Complete OCI image-layout packages, signatures, SBOMs, provenance,
trust material, scanner inputs, and Image Admission Records are preserved in
both ADR 0094 vaults. Automatic ACR purge, untagged retention, and soft delete
are not the deletion authority; exact retirement manifests are required.

## Local-first development

Azure SQL is the production target, not the ordinary development environment.
Normal development and automated validation must run without Azure credentials
or a shared cloud database: local Python processes or containers use synthetic
fixtures, local provider fakes, the ignored `var/` storage adapters, and a
supported local SQL Server Developer container created from exact migrations.

Local SQL Server proves the T-SQL dialect, procedures, constraints,
transactions, locks, concurrency, migrations, and ledger behavior that SQLite
or mocked SQL cannot reproduce. Separately authorized non-production Azure
proofs are still required before production for managed identity, private
networking and DNS, Azure limits and failover, backup restoration, external
immutable ledger digests, monitoring, and the selected hosting topology. Cloud
proof supplements the local-first loop; it does not replace it.

## Repository memory boundary

This glossary and the adjacent greenfield continuity files are authoritative
only for `AskLegal-LegalDBPipeline`. No instruction, decision, approval,
priority, status, or next step from a legacy Ask.Legal workspace applies here
unless the user explicitly restates it for this repository. Availability of
another workspace root creates no shared memory or authorization.

## Cross-cutting machine-contract foundation

**Cross-Cutting Contract Package**: The implementation-neutral immutable
package under `contracts/` that defines shared schemas, identity and reference
primitives, closed code catalogues, lifecycle state machines, contract
inventory, synthetic fixtures, exact expected results, and its complete file
manifest. It does not contain jurisdiction-specific legal rules or select the
production stack.
_Avoid_: Application implementation, universal legal rulebook, production authorization

**Foundation Status**: The immutable `contracts/foundation-status.json` fact
record stating which policy decisions are configured or undecided and which
operational capabilities are active or disabled. That historical foundation
checkpoint keeps the complete production stack undecided, every operational
capability disabled, and external effects at `NONE`. ADRs 0089 through 0097
later select the backend language, application boundary toolchain, Management
Register database boundary, application host, durable-workflow service,
evidence-and-recovery storage boundary, image-registry and software-supply-
chain boundary, authenticated API edge, and infrastructure-delivery boundary
without rewriting the checkpoint.
_Avoid_: Deployment status, implied implementation authority

**Immutable Reference**: A closed object containing one registered reference
type, opaque register-issued object ID, and exact `sha256:` fingerprint. A URL,
filename, title, citation, source locator, or floating version cannot replace
it.
_Avoid_: Mutable pointer, latest alias

**Exact Package Inventory**: The sorted complete list of every package member's
contained relative path, role, media type, byte size, and SHA-256 fingerprint.
The root manifest excludes itself; its external JCS fingerprint transitively
binds the package without a cycle.
_Avoid_: Directory discovery, glob, self-referential manifest hash

Shared JSON is strict I-JSON. Canonical bytes use RFC 8785 JCS UTF-8 and
fingerprints use `sha256:<64-lowercase-hex>`. Shared register-issued IDs use a
closed three-character lowercase prefix, underscore, and 48 lowercase
hexadecimal characters. The ID remains identity rather than a digest.

The exact offline validation command is:

```sh
node tools/validate-contracts.mjs
```

The tool makes no network or production call and does not select the future
production runtime. ADRs 0089 through 0097 do
not turn it into a production dependency.

## Source and evidence

**Registered Source**: An approved official or publisher-authorized product
and evidence role with a stable source ID, exact fact authority, outage impact,
monitoring tier, endpoint records, and responsible Legal Desk.
_Avoid_: Website, data source

**Source Endpoint**: One versioned technical or physical location through which
a Registered Source is checked or an artifact is obtained. URLs, languages,
formats, generated download routes, and archive holdings may change without
changing the source ID.
_Avoid_: Registered Source identity, permanent URL

**Fact Authority**: The exact fact that evidence from a Registered Source is
permitted to prove. Authority is not global: one source may prove a legal event
without proving the resulting consolidated text.
_Avoid_: Controlling source for everything, newest source wins

**Source Outage Impact**: The recorded effect of source unavailability:
release-blocking, blocking only affected work that requires the source, or
nonblocking. A detected conflict may block affected work even when an outage
would not.
_Avoid_: Every official-source outage stops everything

**Source Rulebook Contract**: The common required structure that every
jurisdiction-and-material source rulebook must satisfy. It standardizes the
questions, evidence bindings, decision records, versioning, and fail-closed
behavior without making the answers the same across jurisdictions.
_Avoid_: Universal legal-status rules, source list

**Source Rulebook**: One immutable versioned and fingerprinted decision manual
for one jurisdiction-and-material pair. It references Registered Source IDs and
states what evidence those sources may prove, the stable rules a Legal Desk may
apply, and the permitted outcomes.
_Avoid_: Connector configuration, credentials, cross-jurisdiction Principles rulebook

**Source Rulebook Package**: The strict immutable policy package that binds one
Source Rulebook version's coverage, source-role Fact Authorities,
interpretation locks, declarative rules, stable codes, contract locks,
conformance universe, scope readiness, and impact declaration. Activation and
runtime decisions remain outside it.
_Avoid_: Executable application, evidence archive, endpoint configuration

**Release Scope Decision Readiness**: A rulebook-package state declaring
whether one owned Release Scope has every required source role, rule, code,
contract, registry, and test binding needed to support decisions. A not-ready
scope cannot masquerade as complete and does not automatically invalidate an
independent ready scope.
_Avoid_: Source availability, release approval, jurisdiction-wide readiness

**Rulebook Conformance Attestation**: An immutable external proof binding one
exact Source Rulebook Package fingerprint to one exact processing build and its
successful complete conformance results. It proves compatibility, not legal
authority or permission to access sources or promote data.
_Avoid_: Rulebook package, deployment approval, unit-test summary

**Rule Trace**: The ordered list of stable Source Rulebook rule IDs actually
applied to one observation, item, location, or release decision, together with
the evidence, established and unresolved facts, identity effects, and final
outcome. Human explanations, executable rules, fixtures, and decisions use the
same IDs.
_Avoid_: Free-form rationale, execution log, AI chain of thought

**Watcher**: A source-specific monitor that detects a possible addition,
change, disappearance, or legal-status event.
_Avoid_: Scraper, legal checker

**Scraper**: A source-specific retriever that captures the complete changed
content, required attachments, and source metadata.
_Avoid_: Watcher, desk

**Observation**: One recorded result of checking a Registered Source at a
specific time.
_Avoid_: Run, snapshot

**Observation Freshness**: The time since the latest complete successful
Observation for one Registered Source role. It is a release gate defined by the
source's monitoring tier and is separate from the age of the publisher's legal
text or most recent Official Version.
_Avoid_: Source publication date, proof that law changed

**Source Snapshot**: An immutable preserved capture of the source evidence used
for a decision.
_Avoid_: Current page, working copy

**Source Contract Review**: A bounded review opened when a relied-on source
schema, data dictionary, notice, enum, field meaning, verification rule, or
other interpretation specification changes, conflicts, becomes stale, or no
longer validates observed input. It resolves interpretation before affected
new processing resumes; it is not itself a legal-text update.
_Avoid_: Automatic schema acceptance, legal-status event, global pipeline outage

**HKLII Discovery Evidence**: A non-controlling snapshot from Registered Source
`HK-CASE-HKLII-DISCOVERY` showing that HKLII displayed a candidate judgment,
alias, citation, inventory difference, link, or possible treatment relationship
at one time. It may open originating-source acquisition or reconciliation but
cannot prove judgment wording, version, authority, proposition, treatment,
authority note, or retirement.
_Avoid_: Official judgment, case-law Fact Authority, no-change evidence

**Hong Kong Binding-Case Coverage**: The ordinary searchable Hong Kong Case
scope accepted in ADR 0046. It covers written decisions and reasons from the
Court of Final Appeal, Court of Appeal, Court of First Instance, and Competition
Tribunal, plus separately accountable corresponding historical superior-court
and Hong Kong Privy Council material. Standalone lower-body decisions remain
outside this scope even when technically extractable.
_Avoid_: Every Hong Kong judgment, specialist-persuasive material, HKLII index

**Official Judgment Listing Entry**: One source result observed in an official
Judiciary inventory at a fixed cutoff. It must be accounted for but is not
automatically one Judicial Decision, Official Version, or Search Record.
_Avoid_: Judgment Legal Item, Pinecone record, proof of complete acquisition

**Official Judgment Artifact**: One exact originating source file or official
rendered representation that publishes one Official Version of a Judicial
Decision. Source bytes or the exact official capture remain preserved even
when a working conversion is used for parsing.
_Avoid_: Generated conversion, listing entry, Judiciary Translation Artifact

**Judiciary Translation Artifact**: An official Judiciary translation linked
to the exact Hong Kong judgment Official Version, opinion, and passages. It is
preserved evidence for alignment, review, terminology, and cross-language
evaluation but is not another judgment, authority, Official Version, or
default serving-language record under ADR 0047.
_Avoid_: Court-authored original, language duplicate, machine translation

**Evidence Vault**: The durable store of Source Snapshots, official-status
evidence, releases, approvals, reports, and recovery material. ADR 0094 places
the production vault in separately partitioned flat-namespace Azure Blob
accounts with version-level WORM.
_Avoid_: Pinecone, management register

**Recovery Vault**: The separately administered Azure Blob copy of exact
Evidence Vault and Management Register recovery artifacts, kept in a dedicated
Azure subscription and, where permitted, a different Azure region pair. It is
independent of ordinary application and primary-storage administration, but
not independent of Azure or the shared Microsoft Entra tenant.
_Avoid_: Provider-independent backup, tenant-independent backup, deletion-propagating mirror

## Legal material

**Legal Desk**: The named logical decision authority for exactly one
jurisdiction-and-material pair. It applies one immutable active Source Rulebook
to preserved evidence, accepted structured facts, prior register state, and any
permitted evidence-bound proposal; records the exact Rule Trace, established
and unresolved facts, and structured legal and serving consequences; and fails
closed when no rule or sufficient evidence supports a result. It may accept
fully resolved ordinary work automatically. It is not itself a person, LLM,
source connector, renderer, release builder, promotion reviewer, or deployment
service and holds no source, model-provider, Pinecone, Azure, or routing
credentials.
_Avoid_: Virtual lawyer, human review queue, AI agent, source connector, publisher

**Legal Desk Owner**: The accountable authorized legal-domain role responsible
for governing one Legal Desk's coverage, Source Rulebook, stable rules, codes,
reference decisions, and exact human-review triggers. The owner may be a person
or organizational legal function; ordinary runtime Legal Desk decisions do not
require the owner to inspect every item manually.
_Avoid_: Every-run reviewer, promotion approver, model provider

**Legal Desk Decision**: One immutable cutoff-bound result issued under one
exact Legal Desk and Source Rulebook fingerprint. It binds admitted evidence,
prior state, any accepted proposal, established and unresolved facts, ordered
Rule Trace, membership or authority, identity and continuity, legal state,
material disposition, processing and coverage effects, record eligibility and
required authority-note meaning, review route, and decision fingerprint. It is
an input to deterministic rendering and corpus construction, not a Search
Record or permission to publish.
_Avoid_: Model answer, free-form legal opinion, Approval, Pinecone mutation

**Legal Item**: A uniquely tracked legal authority such as an Act, judgment, or
publisher-maintained Principles Title.
_Avoid_: Search record, source file

**Official Version**: One immutable source-supported consolidation,
compilation, correction, edition, rolling publisher update, or other published
version belonging to a Legal Item. For Principles, “official” means publisher-
authorized; it does not make the material primary law.
_Avoid_: Latest file, current record, legal-status event without published text

**Legal Status Event**: An immutable sourced change in legal effect or status,
such as commencement, repeal, expiry, or revival, that does not by itself claim
that a new Official Version was published.
_Avoid_: Fabricated Official Version, inferred current text

**Hong Kong Gazette Event Evidence**: The exact issued Gazette artifact,
operative provision, publication identity, dates, and affected-location mapping
used to prove a specific Hong Kong legislation event. It proves the event, not
the resulting consolidated wording.
_Avoid_: HKeL Official Version, HTML search result, reconstructed consolidation

**Provision**: A stable legal location within legislation from which one or
more search records may be derived.
_Avoid_: Chunk

**Case Proposition**: One material legal answer from one precisely attributed
judicial reasoning path. Its searchable record carries a labelled source-
faithful derived statement, the necessary facts, issue, qualifications,
application and result, and the smallest complete set of exact original-
language judgment passages needed to verify it under ADR 0060. One judgment
may produce zero, one, or many.
_Avoid_: Principle, sentence, whole-case summary, unsupported paraphrase

**Case Proposition Coverage Ledger**: The complete accounting of every
identified opinion, Coverage Unit, context dependency, candidate, accepted
proposition, and evidence role for one exact Official Version under ADR 0062.
It ends in one reproducible completion, Quarantine, blocked, or invalid result.
It prevents silent truncation and unsupported zero-proposition claims, but its
arithmetic does not by itself prove that every semantic judgment was correct.
It is an internal evidence artifact rather than a Search Record.
_Avoid_: Model context window, proposition count, proof from extractor silence

**Coverage Unit**: One ordered, source-mapped structural part of an accepted
original judgment artifact, such as an opinion paragraph, heading, footnote,
table, order, disposition, schedule, appendix, or source-scaffolding part. Each
unit occurs exactly once in primary coverage and ends resolved, quarantined,
or blocked. A resolved unit is proposition evidence, necessary context, or
examined non-propositional material.
_Avoid_: Token chunk, model packet, untracked repeated context

**Reference Proposition Map**: The hidden versioned Hong Kong Cases Legal Desk
answer map for one semantic extraction evaluation judgment under ADR 0063. It
records required and forbidden legal meanings, exact attribution and evidence,
controlling qualifications, permitted equivalent wording and boundaries, and
the correct zero, Quarantine, or blocked result. It is not one preferred
summary string and is never supplied to the evaluated workflow.
_Avoid_: Model answer, production proposition, prose-similarity target

**Case Proposition Workflow Admission**: The decision that one exact complete
combination of parser, structure and segmentation contracts, extraction method,
validators, renderer, Source Rulebook, processing build, evaluation packages,
applicable model, prompt, settings, provider contract, and operational profiles
passed ADR 0067's exact semantic, deterministic, context, retry, cost,
monitoring, and revalidation gates. Admission has immutable `CANDIDATE`,
`EVALUATING`, `ADMITTED`, `SUSPENDED`, `REVOKED`, and `SUPERSEDED` lifecycle
states. It never transfers to a changed component or authorizes production by
itself.
_Avoid_: Approved model name, deployment approval, aggregate benchmark score

**Case Proposition Workflow Admission Profile**: The immutable ADR 0068
candidate definition that binds one exact complete workflow, one Evaluation
Suite Package and evaluator fingerprint, and the exact provider, model
snapshot, prompts, executable schemas, settings, token and output ceilings,
timeouts, backoff, concurrency, currency budgets, ordinary diagnostic
thresholds, provider data-handling values, and non-critical drift thresholds.
The protected sealed inventory and Reference Proposition Maps belong to the
suite, and evaluation results belong to the Run Set; neither is profile
content. A profile instantiates ADR 0067 but cannot weaken its complete-
workflow identity, 20% minimum context reserve, repetitions, exact
deterministic gates, zero-critical-error rule, high-risk gates, bounded
attempts, or suspension rules.
_Avoid_: Mutable deployment settings, model alias, permission to tune until pass

**Case Proposition Evaluation Suite Package**: The immutable ADR 0068 package
that binds the exact synthetic and sealed-real catalogues, coverage and
selection matrices, three permissioned evidence views, hidden Reference
Proposition Maps, adjudications, deterministic fixtures, evaluator, fixed
gates, schemas, inventory, and canonical root fingerprint used to evaluate one
candidate profile. It contains evaluation truth but no candidate output,
admission result, secret, or production authority.
_Avoid_: Test directory, model benchmark report, admission profile

**Sealed Admission Judgment**: One real Hong Kong judgment selected through
ADR 0068's branch-driven matrix whose exact admission membership, Reference
Proposition Map, adjudication, evaluator labels, and case-level results remain
protected from the evaluated task and ordinary workflow developers. “Sealed”
does not claim the public judgment was absent from provider training. Exposure
removes pristine admission and canary eligibility and triggers replacement and
impact review.
_Avoid_: Secret judgment, guaranteed unseen text, development example

**Evaluation Run Set**: The immutable complete case-by-repetition execution and
result package for one exact Case Proposition Evaluation Suite Package and one
exact frozen Workflow Admission Profile under ADR 0068. It preserves every
attempt, output, deterministic artifact, semantic assertion, metric, gate,
invalid or blocked result, and final `ELIGIBLE` or `NOT_ELIGIBLE` conclusion.
Eligibility permits only the later dual attestation and admission decision.
_Avoid_: Aggregate score, mutable dashboard, production Approval

**Case Proposition Extraction Conformance Catalogue**: The frozen initial Hong
Kong extraction coverage universe under ADR 0064: 132 permanent direct cases,
132 matching primary coverage cells, and 31 high-risk positive/near-miss pairs.
Its synthetic cases define required semantic and deterministic boundaries but
do not replace the mandatory sealed real-judgment extension needed for workflow
admission.
_Avoid_: Model benchmark alone, permanent test-count ceiling, treatment catalogue

**Case Proposition Boundary**: The evidence-backed division between distinct
legal answers under ADR 0061. Independently usable answers split; the elements,
exceptions, qualifications, applications, and exact support needed for one
complete answer remain together. The boundary is decided before token or byte
measurement and never arises merely from paragraphs, headings, or model limits.
_Avoid_: Chunk boundary, paragraph boundary, token split, topic similarity

**Indivisible Overlong Case Proposition**: One complete Case Proposition that
still exceeds a pinned serving limit after optional repetition is removed, the
smallest complete exact support is used, and faithful concise derived wording
is revalidated. It enters Quarantine rather than being fragmented into records
that require a query-time join.
_Avoid_: Serving parts, shortened qualification, evidence-only fragment

**Case Dossier**: A non-authoritative grouping object connecting separately
delivered trial, appeal, supplementary, costs, remedy, and procedural decisions
from related litigation. Each delivered judicial decision remains its own
Legal Item.
_Avoid_: Judgment Legal Item, whole-case Search Record

**Later Treatment**: One evidence-backed directional relationship from the
exact decision, version, opinion, and passages of a later judgment to one exact
earlier Case Proposition. It records how the later judgment applies, follows,
distinguishes, doubts, criticises, disapproves, overrules, or otherwise affects
that proposition. Affirmance, variation, reversal, setting aside, and remittal
are recorded separately as appellate-disposition facts rather than being
collapsed into the treatment class. A link to a separately searchable
proposition in the later judgment is useful when one exists but is not
required.
_Avoid_: Prediction, whole-case label, duplicate incoming and outgoing edges

**Incoming Treatment View**: The internal projection keyed by one treated
earlier Case Proposition that shows which later judgments treated it and how.
It is derived from the authoritative Later Treatment relationships and may
drive the earlier proposition's current `authority_note` or selection result.
_Avoid_: Separate relationship copy, raw citation list, Pinecone record

**Outgoing Treatment View**: The internal projection keyed by one treating
later judgment and, when available, its treating Case Proposition that shows
which exact earlier propositions it treated and how. It is derived from the
same Later Treatment relationships and supports impact analysis, corrections,
audit, and reprocessing.
_Avoid_: Whole-case treatment summary vector, outbound authority-note field

**Exceptional Change Review**: Human Hong Kong Cases treatment review reserved
for a controlling decision that changes the structure of binding authority
itself, or expressly replaces a foundational constitutional or jurisdiction-
wide doctrine with independently cross-doctrinal and high corpus impact. A
Court of Final Appeal decision, novelty, bounded overruling, reinstatement, a
new legal test, or a large uniform batch does not qualify by itself.
_Avoid_: Review of every adverse treatment, subjective importance label,
operational anomaly stop

**Principles**: A jurisdiction-specific material family of source-faithful
publisher-derived legal principles, named with its jurisdiction, such as
Australian Principles or Singapore Principles.
_Avoid_: One cross-jurisdiction Reference Works family, Case Propositions

**Principle**: One source-faithful publisher paragraph, or one deterministic
serving part of that paragraph, represented as a `type: "principle"` Search
Record.
_Avoid_: Case Proposition, silently rewritten atomic rule

**Hong Kong Regulatory Materials**: The jurisdiction-specific material family
for formal non-legislative regulatory requirements administered by an accepted
Hong Kong regulator or front-line regulatory body. Its initial scope is the
HKEX Main Board and GEM Listing Rules under ADR 0054, represented with
`type: "regulatory"`.
_Avoid_: Policy, Hong Kong Legislation, Hong Kong Principles, general guidance

**HKEX Listing Rule**: One current effective formal requirement or expressly
incorporated rule component from the Main Board or GEM Listing Rules. It is a
non-statutory exchange regulatory rule made under the Securities and Futures
Ordinance and approved by the SFC, not legislation or publisher commentary.
_Avoid_: SFC statutory rule, consultation proposal, FAQ, unincorporated guidance

**Hong Kong English Regulatory Record**: One `type: "regulatory"` Search Record
containing the exact prevailing English HKEX Listing Rule text and English
applicability context for one market, rule location, effective state, and
transition branch under ADRs 0072 and 0073. It uses the smallest complete
official rule-bearing unit that is independently usable with its required
governing context and contains no official or generated Chinese source block.
_Avoid_: Bilingual regulatory record, Chinese-only duplicate, parallel language vector

**HKEX English Source Unit**: One ordered source-supported semantic part of an
accepted prevailing English HKEX product, such as a rule, definition entry,
list item, note, table header or row group, fee branch, Form instruction or
field group, appendix paragraph, or Practice Note unit. Website containers,
PDF pages, line wraps, individual blank fields, and renderer-created parts are
not units merely from presentation.
_Avoid_: Token chunk, page region, Pinecone record, arbitrary sentence

**HKEX English Partition Frontier**: The ordered set of largest complete
official English child units that are individually safe to serve with all
required context after an overlong normal HKEX record recursively descends
through its source structure under ADR 0073.
_Avoid_: Fixed paragraph level, character chunks, sliding-window overlap

**HKEX English Source-Unit Coverage Proof**: One immutable internal ADR 0073
proof mapping every meaning-bearing current English unit to exactly one primary
record owner or explicit blocked or quarantined result, labelling repeated
dependencies, and accounting separately for context-only, presentation-only,
future, historical, and excluded units. Complete accounting does not itself
prove that a Release Scope is serving-ready.
_Avoid_: Record count, parser-success report, Pinecone metadata field

**HKEX Regulatory Conformance Suite Package**: The immutable ADR 0074 package
binding one evidence-to-decision catalogue, one decision-to-artifact
deterministic catalogue, one frozen coverage matrix, strict case packages,
applicable `hk-regulatory` rulebook and contract fingerprints, high-risk pairs,
critical-error rules, reproducibility proof, and complete package fingerprint.
It proves an exact processing build only through a separate conformance
attestation and does not prove real-source currency or authorize serving.
_Avoid_: Retrieval benchmark, production source snapshot, model admission, release approval

**HKEX Regulatory Evidence-to-Decision Case**: One strict synthetic ADR 0074
case that tests whether accepted source-shaped evidence produces the correct
structured Legal Desk result for source authority, membership, ownership,
effective state, disposition, record boundary, dependency, or uncertainty. Its
hidden accepted result never enters a later proposal component's inputs.
_Avoid_: Free-form answer grading, deterministic renderer fixture, real-law decision

**HKEX Regulatory Decision-to-Artifact Fixture**: One strict synthetic ADR 0074
fixture that begins from frozen accepted facts or a Legal Desk Decision and
requires exact canonical records, measurements, partitions, source-unit
coverage, traceability, identity, readiness, failure, and no-side-effect
artifacts. It does not rediscover legal meaning.
_Avoid_: Semantic proposal task, retrieval evaluation, live pipeline run

**HKEX Regulatory Semantic Proposal Tasks**: The four change-gated ADR 0076
generative-LLM task contracts: update analysis, update challenge, record
analysis, and record challenge. They propose exact evidence-bound mappings,
semantic boundaries, dependencies, transitions, and objections only after
deterministic admission and only for baseline, changed, or unresolved work.
They never decide legal state, rewrite source text, render final records, issue
identity, or authorize serving.
_Avoid_: Legal Desk, generic regulatory chatbot, final record generator, scheduled model call

**Regulatory Retrieval and Answer Admission Package**: The immutable ADR 0077
profile binding one exact English Regulatory corpus, multilingual query and
relevance suite, embedding and Pinecone-compatible retrieval workflow,
Ask.Legal Query Contract and application build, downstream answer model and
prompt, three-layer results, slice gates, critical-error rules, monitoring, and
complete fingerprint. It separately proves retrieval, frozen-context answer
behavior, and their end-to-end integration and authorizes none of them merely
by existing.
_Avoid_: Regulatory conformance suite, model marketing claim, production serving approval

**HKEX Optional Chinese Translation Evidence**: An official HKEX Chinese
translation preserved outside ordinary serving and release readiness for
terminology, evaluation, investigation, audit, or possible future design. It
does not replace required English evidence or change a Search Record merely by
changing. It affects current processing only when it exposes a possible defect
in the controlling English identity, version, effective state, wording, or
completeness.
_Avoid_: Current wording authority, release dependency, Pinecone Chinese block

**HKEX Rule Component Instance**: One Main Board-owned or GEM-owned Legal
Location that official evidence proves is part of that exact Listing Rule
rulebook, such as a rule, incorporated note, appendix unit, Practice Note,
Regulatory Form, or Fees Rule. Identical wording or one shared source artifact
does not merge the two board-owned identities.
_Avoid_: Website entry, shared HKEX record, guidance page, PDF page

**HKEX Applicability Branch**: One exact Listing Rule wording plus the
supported cohort, transaction, reporting period, time window, external
condition, or other limitation controlling when it applies. ADR 0071 decides
effective state at this level because one update or Legal Location may contain
several differently timed or concurrently current branches.
_Avoid_: Whole-update state, universalized transition, update number as effect

**HKEX Effective-State Decision**: One immutable cutoff-bound ADR 0071 result
that binds an applicability branch to its component, board, exact update and
current-product evidence, effective facts, transition, lineage, applied rule,
state, reason, and fingerprint. Branch decisions are authoritative; the
component inventory retains a derived summary for complete accounting.
_Avoid_: Publication-date inference, clock-only promotion, serving approval

**HKEX Rule Component Inventory Package**: One immutable cutoff-bound ADR 0069
package that explicitly accounts for every entry in the declared HKEX
rule-component inventory universe; assigns separate membership, board
ownership, derived component effective-state, complete branch decisions,
material-disposition, and processing results; and
reports source-entry, component, current-state, and serving-readiness
completeness for Main Board and GEM separately. The actual component list is a
versioned registry artifact, not an ADR or a Pinecone inventory.
_Avoid_: Website crawl, PDF table of contents, Search Record list, current rulebook alone

**HKEX Core Current-Source Set**: The five ordinary ADR 0070 Registered Source
roles used to bound and construct the current Hong Kong Regulatory Materials
database: rulebook catalogue, consolidated rulebooks, Regulatory Forms, Fees
Rules, and final rule updates. Their reconciled union defines the declared
source-entry universe; no one role proves it alone.
_Avoid_: Every potentially useful HKEX page, downstream LLM context, one controlling source

**HKEX Supplemental Trigger Source**: The exact official Registered Source
temporarily assigned a heightened checking obligation while one pending
conditional Listing Rule amendment depends on its event. The source and its
evidence remain historically preserved after the condition ends; only the
extra monitoring obligation is temporary.
_Avoid_: Generic external-trigger feed, absence of evidence proves no trigger

**HKEX Rulebook Basis Evidence**: Fingerprinted official statements pinned to
one `hk-regulatory` Source Rulebook version to justify source precedence,
language relationship, component inclusion or exclusion, and the standing SFC
approval framework. It is not a separately polled current-rule feed or content
automatically sent to the downstream LLM.
_Avoid_: Ordinary release dependency, current rule text, SFC per-update approval receipt

**Principles Title**: One independently publisher-maintained title or work
tracked as a Legal Item within a jurisdiction's Principles. A platform or
collection containing several titles is a grouping boundary rather than one
legal authority.
_Avoid_: Principles paragraph, publisher website, cross-jurisdiction family

**Legal Location**: One register-tracked place within a Legal Item, such as a
provision, Schedule item, judgment location, or maintained Principles paragraph.
Its internal identity is separate from its visible locator.
_Avoid_: Section number alone, filename, Search Record

**Structured Legal Location**: A Schedule, Schedule Part or item, table, form,
form Part, or other officially identified legislation structure tracked under
its parent Legal Item or Legal Location. Independently locatable official units
may receive child identities; ordinary cells, blanks, visual rows, coordinates,
and renderer-created parts do not receive identity merely from layout.
_Avoid_: PDF region, every cell as a Legal Location, serving-part identity

**Search Record**: One immutable validated, independently searchable
representation of legal material. A Serving State whose approved payload
changes must select a different exact Search Record, including when
`authority_note` changes. A previously unseen payload receives a new ID; an
exact preserved record may be reselected only with proved current support.
_Avoid_: Mutable vector, source snapshot, permanent Legal Item

**Serving Payload Fingerprint**: The lowercase `sha256:<64-hex>` digest of the
RFC 8785 JCS-canonical UTF-8 bytes of one Search Record's exact six-field
`metadata` object. It excludes the register-issued Search Record ID so identity
and content proof remain separate. The Desired-State Inventory's Search Record
`content_fingerprint` has this meaning under ADR 0078.
_Avoid_: Hash of record ID, vector fingerprint, raw serializer output

**Hong Kong Bilingual Legislation Record**: One Hong Kong legislation Search
Record whose single `metadata.text` contains corresponding English and
Traditional Chinese content for the same Legal Location, Official Version, and
operative state. It is embedded and delivered as one record.
_Avoid_: English-only record, Traditional-Chinese-only duplicate, language-field join

**Hong Kong Bilingual Text Layout**: The canonical English-first, Traditional-
Chinese-second representation of one Hong Kong Bilingual Legislation Record.
Both blocks are labelled as authentic text; English-first is a deterministic
format, not an authority ranking. Overlong records split only at matching
official legal boundaries and keep both languages together.
_Avoid_: Monolingual fallback, arbitrary token chunk, observation-date header

**Partition Frontier**: The ordered set of largest complete, source-supported
bilingual legal units that are individually safe to place in an overlong
record part with all required context. Only an oversized branch descends to its
next official aligned level.
_Avoid_: Sentence chunks, one fixed split level, token slices

**Dependency Closure**: The smallest complete source-supported set of governing
headings, lead-ins, headers, local definition scope, qualifications, notes, and
other context needed to understand one record part independently. It is
bilingual for HKeL legislation and prevailing-English-only for HKEX Regulatory
Materials. Required repeated context is labelled and measured; useful but
unnecessary background is not included.
_Avoid_: Sliding-window overlap, omitted lead-in, copied target provision

**Primary Source-Unit Coverage Proof**: An internal proof that every authentic
English and Traditional Chinese source unit occurs exactly once as primary
content and in source order across a record partition. Labelled repeated
dependencies point to their original units without concealing a gap or primary
duplication.
_Avoid_: Text-present check, Pinecone metadata field, unlabelled duplication

**HKeL Dual-Representation Evidence Bundle**: The matching English and
Traditional Chinese HKeL XML, corresponding verified or assisted official HKeL
copies, source metadata, hashes, deterministic mappings, and reconciliation
report for one applicable Official Version. XML constructs the canonical
serving payload; the matching HKeL copies support its official text and
version. Both representations must reconcile before the record can proceed.
_Avoid_: PDF serving payload, XML-only authority proof, fuzzy text match

**HKeL Reconciliation Fixture**: One immutable stable synthetic example that
binds minimal HKeL-shaped XML and applicable PDF evidence, pinned source
interpretation, expected legal-content mapping, canonical bilingual output when
permitted, ordered rule references, and an exact pass, block, or Quarantine
result. It tests the rulebook but proves no real law.
_Avoid_: Production source snapshot, approximate example, AI evaluation prompt

**HKeL Fixture Package**: One immutable synthetic conformance package containing
a strict `fixture.json`, separately hashed declared inputs, and separately
hashed exact expected artifacts. Structural and semantic validation together
prove the fixture; the package is not a Pinecone schema or production evidence.
_Avoid_: One giant escaped JSON file, broad feature tag, real source snapshot

**HKeL Fixture Catalogue**: The frozen strict `catalogue.json` that binds every
required HKeL fixture ID, group, package path, package fingerprint, and common
contract fingerprint. Completeness is exact; an unlisted or missing package is
a failure.
_Avoid_: Test discovery glob, representative sample, mutable test list

**Statutory Note**: A footnote or note that the pinned HKeL specification and
Hong Kong Legislation Source Rulebook classify as part of the legislation or
its prescribed legal structure. Its exact marker, body, attachment, order, and
bilingual relationship are preserved in `metadata.text`.
_Avoid_: Every item visually labelled “note”, HKeL publisher context

**HKeL Publisher Note**: Official HKeL explanatory, editorial, navigation, or
source context that the pinned rules classify as non-legislative. It remains in
evidence and internal traceability, not in `metadata.text`. If it reveals a
material reliance limitation, the Legal Desk must approve a separate controlled
English authority-note warning clause or withhold the record.
_Avoid_: Statutory Note, HKeL Editorial Record, raw publisher prose as warning

**Official Textual Equivalent**: Complete structured text supplied by the
official publisher and explicitly mapped by the pinned specification and
rulebook as a faithful equivalent of a meaningful image. OCR, AI-generated alt
text, reviewer prose, and nearby text are not official textual equivalents.
_Avoid_: Image summary, extracted guess, convenient replacement text

**Cross-Reference Relationship**: An internal evidence-backed link from exact
official referring words to an officially identified target or an explicit
unresolved or out-of-scope target state. It preserves target resolution without
pasting target wording into the referring Search Record or creating a query-
time join.
_Avoid_: Expanded quotation, silent citation correction, LLM lookup dependency

**HKeL Assisted-Copy Evidence Bundle**: The matching English and Traditional
Chinese HKeL XML, corresponding official HKeL assisted copies, source metadata,
hashes, deterministic mappings, source-classification record, and
reconciliation report for any covered Hong Kong Legislation item. XML
constructs the canonical serving payload; the assisted copies provide accepted
Ask.Legal text-and-version evidence without being represented as statutorily
verified. A newer complete assisted version may proceed instead of an older
verified version under ADR 0081.
_Avoid_: Verified-copy claim, non-HKeL webpage, monolingual fallback, PDF-only construction

**HKeL Publication Specification Bundle**: The exact fingerprinted official
XSD, data dictionaries, Important Notices, catalogue descriptions, and explicit
interpretation mapping pinned by one Hong Kong Legislation Source Rulebook
version. It defines how HKeL artifacts are parsed and verified but proves no
item-specific legal event or wording.
_Avoid_: HKeL legal-text bundle, mutable live documentation, serving content

**HKeL Instrument Disposition Registry**: The immutable versioned part of the
Hong Kong Legislation Source Rulebook that accounts for every observed HKeL
Instruments & Others entry and every legal object it represents or proves. It
separates the A-series source filing category from actual legal nature,
Release Scope ownership, serving disposition, evidence relationships,
authority-note consequences, and identity.
_Avoid_: Include-all A-number list, HKeL category as legal classification

**HKeL Past-Data Evidence**: On-demand HKeL inventory, XML, and applicable
verified PDFs for an earlier legislation version, used only for a specific
baseline, investigation, recovery, audit, or evaluation task. It has no
ordinary weekly freshness gate. Exact past wording requires reconciliation
with matching past verified PDFs; similarity or disappearance cannot prove
present law, a legal event, or identity continuity.
_Avoid_: Current-law source, legal event evidence, historical Pinecone record

**HKeL Editorial Record**: An official record with legal status that identifies
editorial amendments, affected legislation, and effective dates. It proves its
stated editorial event but is not the resulting consolidated Official Version
or serving text.
_Avoid_: Gazette instrument, verified consolidated text, reconstructed version

**Excluded LegCo Legislative-History Material**: Legislative Council Bills,
Bills Database records, proceedings, debates, votes, explanatory memoranda, and
committee papers that are outside the automated Hong Kong Legislation
pipeline. They may be consulted manually as non-controlling research but are
not Registered Sources, required evidence, Source Snapshots, or serving input.
_Avoid_: Gazette event evidence, current law, mandatory discovery source

**Reconstructed Consolidation Artifact**: One immutable internal Hong Kong
Legislation result permitted by ADR 0080 when a complete proved chain of
operative amendments can be applied deterministically to the latest applicable
bilingual HKeL base supported by matching verified or assisted official HKeL
copies under ADR 0081. It is not an HKeL Official Version. Its Search Records otherwise follow ordinary legislation serving,
source, citation, quotation, retrieval, and ranking rules with the exact
mandatory reconstruction authority note. ADR 0079 is the fallback when any
reconstruction proof fails. ADR 0085 fixes its strict `rca_` package: complete
authentic-language trees and source units, reconstructed location units,
bilingual and dependency proofs, derivation map, identity-lineage result, and
ordinary-renderer requirements.
_Avoid_: HKeL Official Version, guessed consolidation, model-authored final
text, separate serving material type

**Reconstruction Derivation Map**: The complete ADR 0085 proof assigning every
final source unit and changed structural relation to either byte-identical base
content or one exact admitted operation and its authentic-language amendment
evidence. It has no generated, inferred, translated, manual, corrected-by-
engine, or catch-all origin.
_Avoid_: General provenance note, model rationale, best-effort source link

**Hong Kong Reconstruction Operation Registry**: The immutable, versioned,
fingerprinted ADR 0082 allow-list of exact amendment tree-and-text operations.
It fixes eight stable operation classes, their evidence, selectors,
preconditions, ordering, atomicity, postconditions, failure reasons,
traceability, and required conformance coverage. Anything not defined by the
registry is unsupported and produces no reconstructed result.
_Avoid_: Free-text patch, catch-all operation, fuzzy amendment application,
implementation-private edit

**Reconstruction Plan**: One immutable complete ordered set of registry
operation instances for an exact HKeL base, evidence set, cutoff, applicability
branch, and dependency closure. It must pass deterministic validation before
execution and is never serving text. ADR 0084 fixes its strict JCS JSON
contract and register-issued `rpl_` identity; its `rop_` operation instances
bind exact amendment and effect events, source units, selectors, before and
after states, dependencies, atomic groups, and authentic-language order.
_Avoid_: Model answer, partial amendment list, mutable work queue

**Reconstruction Execution Report**: The immutable machine-checkable account
of every operation's before state, exact match, result, after state, bilingual
and dependency checks, hashes, and final outcome. It proves reproduction and is
linked through traceability rather than placed in Pinecone. ADR 0084 fixes its
strict JCS JSON contract and register-issued `rex_` identity. A failed Report
accounts for applied, failed, and not-run operations and emits an explicit zero
artifact result rather than partial text.
_Avoid_: Free-text reasoning, authority note, source snapshot

**Hong Kong Reconstruction Conformance Suite**: The strict two-layer ADR 0083
suite, expanded by ADRs 0086 and 0087, that freezes 32 evidence-to-plan and 31
plan-to-artifact cases, 63 matching primary coverage cells, and 35 controlled
high-risk pairs. Together with the 121 ordinary Hong Kong Legislation cases, a
reconstruction-enabled profile has 184 direct cases. Every case, cell, and pair
member is mandatory; there is no pass-percentage substitute.
_Avoid_: Sample test set, model evaluation score, real-source currency proof

**Reconstruction Capability Profile**: One immutable exact specification of
the rulebook, registries, contracts, conformance universe, deterministic build,
security boundaries, runtime identity, and candidate-writing capabilities that
must agree before real Hong Kong reconstruction processing may be activated.
ADR 0087 gives it a register-issued `rcp_` identity. The repository currently
has design documents only and therefore remains `DESIGN_ONLY`.
_Avoid_: Accepted ADR, implementation plan, production deployment permission

**Reconstruction Capability Attestation**: Independent immutable proof that
one exact Reconstruction Capability Profile and build passed every mandatory
ordinary and reconstruction case, reproducibility run, containment test, and
architecture boundary. ADR 0087 gives it a register-issued `rct_` identity.
It can support candidate-processing activation but is never human Approval or
permission to promote, access Pinecone, or change Azure.
_Avoid_: Unit-test report, legal opinion, promotion Approval

**Reconstruction Comparison Basis**: The ADR 0086 proof that a reconstructed
artifact and later valid HKeL text represent the same Legal Item, safely
reconciled locations, authentic languages, event horizon, applicability
branch, operative period, and dependency boundary. Additional overlapping
changes make comparison non-isolatable; the pipeline never reverses them to
manufacture a score.
_Avoid_: Latest-versus-old raw diff, reverse reconstruction, similarity score

**Status Coverage Map**: The complete internal assignment of every relevant
Legal Location in one HKeL item to exactly one current-law serving disposition
at a fixed observation cutoff. It records inherited status only when the
Source Rulebook proves the inheritance rule and records every exact child
exception. It is release-accounting evidence, not Pinecone metadata.
_Avoid_: One status flag for a mixed item, authority-note field, inferred inheritance

**Bilingual Alignment Group**: One or more consecutive English source units
and one or more consecutive Traditional Chinese source units that official
identifiers and a pinned rule establish as the same item, version, location,
operative state, and parent relationship. One-to-one, one-to-many,
many-to-one, and many-to-many groups are allowed; translation similarity cannot
create the mapping.
_Avoid_: Translated chunk pair, equal paragraph-count assumption, LLM pairing

**Authority Note**: The required `metadata.authority_note` string carried with
every Search Record and delivered unchanged to the downstream LLM. The exact
value `"None"` means no approved record-level authority note applies at that
Serving State's observation cutoff. A real note uses controlled evidence-backed
warning clauses first, budgeted material support clauses second, and material
neutral context clauses last. It has no fixed support- or explanation-clause
count and is a compact current authority summary, not an exhaustive citation
history or numerical authority score.
_Avoid_: Case-only treatment field, optional lookup-only note, raw citation
list, citation-count score, reviewer notes, null

**Hong Kong Authority Note**: A real `metadata.authority_note` on any Hong Kong
Search Record, written in English only and delivered unchanged as an internal
authority-and-reliance instruction to the downstream LLM. It is not translated
merely because Hong Kong legislation `metadata.text` is bilingual. ADR 0080's
reconstruction note expressly instructs the model to reproduce its warning
portion in an answer that uses the record; the instruction portion itself
remains internal.
_Avoid_: Bilingual authority note, embedded note, translated reconstruction
warning, exposed instruction clause

**Identity Alias**: A source URL, provider identifier, title, citation, visible
locator, or other external label attached to a register-owned identity as
evidence or display data.
_Avoid_: Authoritative internal identity

**Lineage Relationship**: An immutable typed evidence-backed link explaining
how identities relate through correction, replacement, renumbering, split,
merge, reinstatement, or another material-specific event.
_Avoid_: Silent overwrite, inferred similarity

**Search Record Selection Event**: An immutable append-only fact recording
that one frozen Serving State selected, stopped selecting, or reselected an
exact Search Record at its cutoff. It is separate from Search Record lineage,
so reselecting an older exact record never creates a backward lineage edge.
_Avoid_: Search Record mutation, cyclic lineage, current-state flag on a record

**Semantic Treatment Evaluation**: A schema-bound evaluation of whether an
LLM proposes the correct judgment passages, proposition mapping, treatment,
scope, opinion attribution, and uncertainty. It tests semantic understanding,
not byte-exact serving consequences or preferred prose.
_Avoid_: End-to-end promotion test, free-form similarity score, legal decision

**Treatment Contract Fixture**: One strict synthetic deterministic package
that starts from frozen treatment facts and requires exact validation, Rule
Trace, authority note, identity, selection, lineage, embedding, release,
review-routing, and no-side-effect artifacts. It proves contract behavior, not
real law or LLM understanding.
_Avoid_: Model benchmark, real judgment evidence, approximate expected output

**Treatment Coverage Matrix**: The frozen complete list of required Hong Kong
later-treatment conformance cells and their direct semantic or deterministic
cases, high-risk positive and near-miss pairs, checkpoints, and contract
bindings. It—not file discovery or a target count—proves catalogue completeness.
_Avoid_: Test tags, directory scan, aggregate score, arbitrary fixture count

**Hong Kong Treatment Conformance Catalogue**: The accepted initial catalogue
frozen by ADR 0059: 155 permanent direct cases, 155 matching primary coverage
cells, and 21 high-risk positive and near-miss pairs. Its counts arise from the
accepted coverage matrix; future requirements may add versioned cases but may
not reassign or silently change an existing ID or normative result.
_Avoid_: Suggested examples, fixed test quota, model-admission proof

**Treatment Conformance Package**: One immutable hashed semantic evaluation or
deterministic fixture with a strict non-leaking manifest, declared inputs,
expected artifacts, coverage cells, contract bindings, and package inventory.
The model never receives package or expected-answer metadata.
_Avoid_: Prompt folder, unregistered real judgment, self-discovered test

## Processing and model boundaries

**Generative-LLM Task Runner**: The sole legal-processing-worker gateway that
may hold generative-LLM provider credentials and make generative-LLM calls. It
accepts only a stable explicitly enabled task contract and returns a structured
evidence-bound semantic result. After independent challenge and deterministic
validation, that result owns only the exact semantic fields named by the task
contract; the runner has no source, identity, approval, retirement, release, or
serving-effect authority.
_Avoid_: AI worker, general model access, autonomous Legal Desk

**Pipeline LLM Task**: One stable schema-bound use of the Generative-LLM Task
Runner with pinned evidence inputs, prompt, model configuration, output schema,
and evaluation rules. ADR 0053 allocates Hong Kong later-treatment analysis,
ADR 0065 allocates Hong Kong Case Proposition extraction, and ADR 0076 allocates
four change-gated HKEX Regulatory semantic tasks: update analysis, update
challenge, record analysis, and record challenge. The Case Proposition ADR 0066
task contracts may run only as part of an `ADMITTED` exact workflow under ADR
0067, instantiated through ADR 0068's suite, protected-evidence, run-set, and
pre-frozen profile contract; they remain disabled until actual executable
packages and a profile pass. Hong Kong later treatment remains disabled pending
its own exact runtime task contracts and admission.
Decision 7 selects Gazette-event analysis/challenge and Reconstruction Plan
decision/challenge, makes every other unallocated task deterministic for now,
and keeps evaluation deterministic against human-adjudicated reference truth.
_Avoid_: Unnamed AI step, assumed enabled task, legislation status decision

**Case Proposition Analysis Task**: The first bounded semantic LLM pass under
ADRs 0065 and 0066, with stable identity
`hk-case-proposition-analysis/v1`. It receives only admitted, source-mapped
judgment evidence and decides material legal answers, unit uses, exact supporting ranges,
qualifications, context, applications, boundaries, attribution, handoffs, and
uncertainty within its admitted schema. A conforming unchallenged result owns
those semantic fields; it cannot prove complete coverage, determine current
authority, or create a serving record.
_Avoid_: One-shot judgment distillation, Legal Desk decision, record publisher

**Case Proposition Challenge Task**: The separate semantic LLM pass under ADR
0065, fixed as `hk-case-proposition-challenge/v1` by ADR 0066, that actively
tests an already validated proposition result for
omissions, unsupported breadth, missing qualifications, wrong attribution,
wrong boundaries, incomplete dependencies, and an unsafe zero or complete
result. It emits exact evidence-linked objections and cannot edit the primary
result or acquire authority beyond its challenge contract.
_Avoid_: Majority vote, duplicate analysis, automatic correction

**Semantic Task Pass**: One complete semantic workflow over one exact judgment,
not necessarily one provider call. Under ADR 0066, a short judgment may fit one
call, while a long judgment may require complete opinion-aware packet calls
plus one judgment-level integration or result-challenge call. Every primary
Coverage Unit remains accounted for, so model context cannot define coverage.
_Avoid_: Exactly one API call, token-window coverage, silent chunking

**Evidence Range ID**: An immutable request-scoped identifier for one exact
original-language span already mapped by deterministic processing to preserved
judgment evidence. Under ADR 0066, an LLM selects these IDs for evidence roles;
deterministic code copies the preserved text into authoritative quotation
fields.
_Avoid_: Model-generated quotation, paragraph number as permanent identity

**Semantic Task Request Kind**: One closed schema branch inside an admitted
Pipeline LLM Task that changes packet shape without expanding semantic
authority. ADR 0066 fixes four analysis kinds and four challenge kinds for
complete judgment, packet, judgment-level integration or result challenge, and
bounded re-analysis or final challenge.
_Avoid_: Free-form mode, new task authority, implementation retry

For Hong Kong later treatment, the LLM is the primary semantic decision
mechanism because judgment language varies. Deterministic processing validates
evidence, structure, identities, authority facts, schemas, coverage, and
permitted claims; it does not infer substantive treatment from keywords or the
absence of keywords. A conforming unchallenged model result owns the admitted
semantic fields; the Legal Desk/human path handles unresolved or exceptional
cases.

For Hong Kong Case Proposition extraction, deterministic processing owns
source admission, complete structure, exact evidence, ledger arithmetic,
semantic-result validation, identity, rendering, and finalization. The **Case
Proposition Analysis Task** decides legal meaning and the independent **Case
Proposition Challenge Task** searches for semantic mistakes or omissions.
Deterministic reconciliation applies only contractible objections and
invariants; it does not recreate the semantic judgment. Human/Legal Desk review is reserved for exact
unresolved ambiguity or an accepted Source Rulebook trigger.

**Embedding Adapter**: The promotion-worker component that sends only
validated selected `metadata.text` to a pinned embedding model. An embedding
model produces retrieval vectors; it is not a generative LLM and cannot make a
legal conclusion.
_Avoid_: LLM task runner, legal classifier, record approver

**Ask.Legal Answer LLM**: The downstream application model that receives
retrieved Pinecone metadata and produces an answer. It is outside this pipeline
and does not authorize any pipeline task to call a generative LLM.
_Avoid_: Pipeline LLM Task, embedding model, Legal Desk

## Corpus and promotion

**Management Register**: The durable ledger of sources, observations, legal
items, states, decisions, work, approvals, and serving history.
_Avoid_: Evidence vault, report

**Initial Current Baseline**: The first accepted complete current-state
accounting for one Release Scope when the pipeline has no preserved previous
accepted current bundle. It may establish clear present state from complete,
consistent accepted current evidence without replaying the full history, but
it makes no unsupported historical event, date, or continuity assertion.
_Avoid_: No-change release, historical reconstruction, legacy-index import

**Hong Kong Cases Current-Authority Baseline**: The first complete greenfield
accounting of every required Hong Kong binding-case court-year scope at one
cutoff, including propositions, material later treatment, authority notes,
current-authority exclusions, zero-record decisions,
Quarantines, and Coverage Gaps.
It has no arbitrary case-age cutoff and imports no legacy identity.
_Avoid_: Judgment dump, recent-cases window, legacy Pinecone migration

**Hong Kong Cases Ordinary Update**: The post-baseline comparison of one new
frozen cutoff with one exact accepted predecessor. It acquires only affected
judgments, follows their complete proposition-and-treatment impact across
court-year scopes, reuses exact unaffected records and releases, and keeps
no-change, accounting, serving, blocked, and quarantined results distinct.
HKLII may generate leads but cannot establish any database effect.
_Avoid_: Whole-corpus reprocessing, HKLII-driven legal update, delta release

**Court-Year Case Release Scope**: The Hong Kong Cases ownership and rebuild
boundary defined by one issuing-court family and the original decision calendar
year. It does not limit cross-scope treatment or legal authority; all required
scopes compose into one Hong Kong Cases target.
_Avoid_: Publication-year batch, treatment boundary, separate legal database

**Release Scope**: A stable, versioned, non-overlapping ownership boundary for
which one responsible desk must account for the complete set of Search Records
at an observation cutoff.
_Avoid_: Folder, arbitrary batch, Pinecone target

**Corpus Release**: A sealed immutable complete snapshot of one Release Scope
at one observation cutoff, containing zero or more validated Search Records and
its completeness, non-searchable disposition, and integrity evidence. It is not
a delta.
_Avoid_: Distillation output, change list, latest dataset

**Desired-State Inventory**: One immutable complete composition for a serving
target. It selects exactly one Corpus Release for every required Release Scope
and materializes the exact expected Search Record IDs, fingerprints, and owners.
_Avoid_: One profile release, release-reference list, deletion list

**Promotion Manifest**: The sole sealed immutable approval and execution
envelope joining the base Serving State, candidate Serving State Definition,
desired states, exact targets, routing, settings, changes, recovery evidence,
validations, ordered actions, rollback, and invalidation conditions under one
fingerprint.
_Avoid_: Report, deployment script, secret bundle, permission to improvise

**Approval**: One immutable authenticated human decision bound to one exact
Promotion Manifest fingerprint and one execution lineage, with a validity
window, objective preconditions, and append-only lifecycle events.
_Avoid_: Permission to improvise, reusable token, general consent

**Serving State Definition**: The sealed immutable fingerprinted description of
one complete candidate search state: environment, routing, indexes,
inventories, query contracts, coverage, verification requirements,
predecessor, and recovery references.
_Avoid_: Activation record, mutable status, index-name setting

**Serving State**: A Serving State Definition whose append-only build and
verification evidence proves it is eligible to serve Ask.Legal.
_Avoid_: Partially updated index, latest index, unverified definition

**Serving State Lifecycle Event**: An immutable append-only fact recording what
happened to one Serving State, such as verification, activation, rollback
activation, failure, protection, or retirement.
_Avoid_: Mutable state-status field, overwritten serving history

**Query Contract**: The versioned, fingerprinted rules that define the serving
record shape and how every Ask.Legal query path reads, filters, and passes those
records to the downstream LLM.
_Avoid_: Incidental application build, undocumented metadata convention

**Record Traceability Lookup**: An immutable fingerprinted internal map keyed
by Search Record ID that points to its legal identities, source evidence,
release ownership, authority-note evidence, and optional review grouping or citation
data. It contains pointers rather than source files and is not read by
Ask.Legal or the downstream LLM during an ordinary query.
_Avoid_: Query database, Evidence Vault, LLM authority-note channel

**Record Traceability Lookup Revision**: One complete immutable strict package
whose canonical manifest binds every serving-record profile and exactly one
declared shard for every Release Scope selected into the target. Its external
root fingerprint transitively binds all shard bytes without a self-reference.
_Avoid_: Mutable lookup table, query-time join, directory scan

**Record Traceability Shard**: One immutable manifest-declared, fingerprinted,
Search-Record-ID-sorted NDJSON entry file for one exact Release Scope and
selected Corpus Release. An unchanged shard may be reused in a later lookup
revision; a traceability-only correction replaces only the affected shard and
root revision.
_Avoid_: Unbounded monolithic lookup, inferred file set, Corpus Release

**Pinecone Index Generation**: One immutable, fully built and verified
Pinecone Index for a jurisdiction, identified by a date-led unique name.
_Avoid_: Live index being edited, latest index

**Routing Configuration**: The complete versioned mapping from every served
jurisdiction to its exact Pinecone Index Generation. Ask.Legal receives the
active index names through Azure App Service application settings.
_Avoid_: Independent uncoordinated index-name changes, latest indexes

**Cutover**: The controlled switch from one verified Serving State to another.
_Avoid_: Upsert, deployment start

## Uncertainty and coverage

**Quarantine**: A preserved state for material that cannot safely proceed
because evidence, identity, legal status, or processing support is incomplete
or conflicting.
_Avoid_: Rejection, deletion, no change

**Coverage Gap**: A known period or area in which the searchable corpus may not
reflect supported current material.
_Avoid_: No search result, quarantine

**Carry-Forward Selection**: An explicit Desired-State Inventory choice to keep
previously approved material searchable with a visible Coverage Gap. Ordinary
carry-forward applies when no affirmative change is proved; ADR 0079 defines a
separate known-stale analytical mode for one exact legislation condition.
_Avoid_: Silent reuse, verified current release

**Known-Stale Analytical Carry-Forward**: The narrow serving mode used when
accepted official evidence proves that legislation changed but the updated
official consolidated text is not yet available and ADR 0080 reconstruction
cannot pass. Every affected location for which valid latest applicable
official HKeL text is held receives a searchable warned analytical fallback,
whether its supporting copy is verified or assisted and whether or not it was
previously selected in Pinecone. The record uses unchanged official text, a
mandatory English authority-note warning, a new warned serving-payload
identity, coverage status, and complete release accounting. It is analytical
material, not current or reconstructed text.
_Avoid_: Current wording, silent stale record, reconstructed consolidation,
historical-search feature

**Withholding Release**: A new complete Corpus Release that omits unsafe or
unsupported records from its searchable set while accounting for every
withheld item, reason, and supporting evidence. Withholding is not a declaration
that the Legal Item ceased to exist.
_Avoid_: Empty placeholder, inferred retirement

**Waiting Room**: Preserved enacted or assented legislation that has not met
the commencement and official-consolidation requirements for search.
_Avoid_: Searchable prospective law

**Frozen Principles Scope**: A jurisdiction-and-source-specific Principles
scope whose exact last approved records remain selected and usable after
licence expiry while every source-specific acquisition and content update is
stopped.
_Avoid_: Withholding, retirement, deletion, verified-current refresh

## Relationships

- A **Registered Source** produces many **Observations**.
- A jurisdiction-and-material **Source Rulebook** satisfies the common **Source
  Rulebook Contract**, references one or more Registered Sources, and binds each
  Legal Desk decision to a stable rule ID, version, fingerprint, and preserved
  evidence.
- Every Hong Kong current-update decision preserves its ordered **Rule Trace**.
  Passing a later rule cannot cure an earlier evidence or reconciliation
  failure, and schema-valid output with the wrong trace fails conformance.
- An **Observation** may trigger one **Scraper** capture and one or more
  **Source Snapshots**.
- Every Hong Kong **Official Judgment Listing Entry** at a fixed cutoff has one
  explicit acquisition outcome. One Judicial Decision may have several
  listings and **Official Judgment Artifacts**, while one valid decision may
  produce zero Case Proposition Search Records. Inventory accounting, evidence
  coverage, and search output remain separate completeness results.
- Every accepted Hong Kong judgment and identified opinion has complete
  **Case Proposition Coverage Ledger** accounting. A qualifying record puts
  both its clearly labelled derived legal statement and its minimum exact
  original-language judgment support in `metadata.text`, because the
  downstream LLM cannot read the internal traceability store during an
  ordinary query. An unresolved possible proposition enters Quarantine rather
  than becoming a guessed record or a valid zero-record decision. Every
  **Coverage Unit** and proposition candidate has an exact outcome, every
  accepted record maps back to the ledger, and a valid no-proposition result
  requires complete source and treatment-screening accounting.
- Every Hong Kong **Case Proposition Boundary** follows independent legal use
  and meaning rather than source layout or size. Same-opinion repetition
  consolidates, opinion roles remain separate except for exact express
  adoption, and an **Indivisible Overlong Case Proposition** enters Quarantine
  rather than being split into incomplete query-dependent fragments.
- Hong Kong Case Proposition extraction uses separate semantic evaluation and
  deterministic contract-conformance suites. A hidden **Reference Proposition
  Map** controls semantic truth; exact fixtures control mechanical truth; and
  **Case Proposition Workflow Admission** binds only the complete fingerprinted
  workflow. ADR 0067 requires all 132 synthetic cases plus the sealed real-
  judgment extension, three ordinary and five high-risk semantic repetitions,
  exact deterministic repetition, no critical error, every high-risk
  distinction in every repetition, and separate dimension and slice gates. ADR
  0068 separates the immutable Evaluation Suite Package, pre-frozen Workflow
  Admission Profile, complete Evaluation Run Set, and final dual-attested
  admission; fixes protected evidence views and branch-driven real-judgment
  selection; and forbids tuning thresholds on sealed results. ADR 0067 also
  fixes a 20% minimum context reserve, bounded attempts, cost reservation,
  weekly canaries, a complete suite at least every 90 days, change-triggered
  revalidation, and automatic suspension. Retrieval quality remains a separate
  later gate.
- The initial Hong Kong **Case Proposition Extraction Conformance Catalogue**
  freezes 132 direct cases, 132 primary coverage cells, and 31 high-risk pairs.
  Future real-judgment admission cases extend rather than rewrite its synthetic
  boundaries.
- Hong Kong Case Proposition extraction follows ADR 0065's two-pass staged
  hybrid. Deterministic processing admits and maps the complete source,
  validates and reconciles proposals, and finalizes accepted records. The
  **Case Proposition Analysis Task** proposes legal meaning; the independent
  **Case Proposition Challenge Task** looks for omissions and unsafe results.
  The Legal Desk accepts complete resolved ordinary work, while only exact
  unresolved ambiguity or a versioned rulebook trigger reaches human review.
- Hong Kong source roles use daily, weekly, monthly or event-triggered, or
  on-demand monitoring tiers. HKeL past material and official archival Gazette
  evidence are on demand only; Editorial Records remain weekly. A deterministic
  unchanged Watcher result creates no LLM, embedding, or large-artifact work.
  A generative LLM may run only through an enabled **Pipeline LLM Task** after
  a real signal survives acquisition, deduplication, and deterministic
  validation.
- A **Legal Desk** applies one immutable jurisdiction-and-material Source
  Rulebook to preserved evidence and prior state and emits an immutable **Legal
  Desk Decision** and Rule Trace. It may accept fully resolved ordinary work
  automatically; its **Legal Desk Owner** governs the rules and exact human-
  review triggers rather than reviewing every item.
- A **Legal Item** has one or more **Official Versions** and may have many
  **Legal Status Events**.
- A **Principles Title** is a Legal Item; its editions or complete rolling
  update states are Official Versions and its publisher paragraphs are Legal
  Locations.
- The Main Board Listing Rules and GEM Listing Rules are separate Legal Items
  and Release Scopes within **Hong Kong Regulatory Materials**. Their complete
  effective consolidated states are Official Versions and their rule-bearing
  units are Legal Locations.
- Every frozen Hong Kong Regulatory Materials cutoff has one **HKEX Rule
  Component Inventory Package**. It accounts for every entry in the exact
  registered inventory universe and keeps membership, board ownership,
  effective state, material disposition, processing outcome, and serving
  readiness separate. Complete accounting may expose a blocked or quarantined
  scope and therefore does not itself make the scope ready to serve.
- The **HKEX Core Current-Source Set** supplies that registered inventory
  universe through five reconciled roles. Optional online-rulebook research,
  general SFC material, guidance, and consultations are not ordinary release
  dependencies or downstream LLM inputs.
- One `FUTURE_CONDITIONAL` rule may depend on an **HKEX Supplemental Trigger
  Source**. Only its heightened monitoring obligation ends after resolution;
  the Registered Source and exact evidence remain immutable history.
- **HKEX Rulebook Basis Evidence** belongs to the versioned Source Rulebook,
  not the Search Record metadata or ordinary Pinecone corpus.
- Every searchable HKEX component produces one **Hong Kong English Regulatory
  Record** under ADRs 0072 and 0073. Its complete official unit, dependency
  closure, canonical projection, overlong partition, and exhaustive source-unit
  accounting are proved by one **HKEX English Source-Unit Coverage Proof**.
  Official Chinese translations are **HKEX Optional Chinese Translation
  Evidence**, not ordinary release dependencies or serving text. Chinese-query
  retrieval must still pass complete multilingual evaluation before the family
  can serve.
- The **HKEX Regulatory Conformance Suite Package** separately proves evidence-
  to-decision correctness and exact decision-to-artifact behavior through one
  frozen branch-driven coverage matrix. Its future complete successful build
  attestation does not prove real-source currency or authorize a release,
  Pinecone, or deployment.
- Each accepted **HKEX Rule Component Instance** belongs to exactly one Main
  Board or GEM Legal Item. One source artifact may prove components in both
  rulebooks, but it does not create one cross-market component or Search
  Record. Nearby guidance remains accounted non-rule material rather than
  entering the component inventory through website placement.
- A **Case Dossier** groups related judicial-decision **Legal Items** without
  merging their identities.
- An **Official Version** may produce zero or more **Search Records**.
- Every searchable Hong Kong legislation location produces one **Hong Kong
  Bilingual Legislation Record**, never parallel language-only records.
- Every Hong Kong Bilingual Legislation Record follows the **Hong Kong
  Bilingual Text Layout**. Operational traceability stays outside
  `metadata.text`, and any serving parts remain aligned to official structure.
- Every applicable HKeL-derived current-law record is supported by an **HKeL
  Dual-Representation Evidence Bundle**. The XML-built text and both authentic-
  language verified or assisted official HKeL copies must reconcile; the files
  and comparison evidence remain outside Pinecone and the ordinary query path.
- An **HKeL Reconciliation Fixture** fixes how a small evidence condition must
  be interpreted. `PASS` clears only the reconciliation gate; missing evidence
  or an invalid deterministic candidate blocks; existing conflicting evidence
  enters Quarantine; and unknown source semantics open Source Contract Review.
- Every partially operative HKeL item has a complete **Status Coverage Map**.
  A mixed-status authority-note warning clause may qualify only an otherwise searchable record; it
  cannot place an uncommenced, repealed, expired, historical, or unknown
  location into current search.
- Every authentic-language unit belongs to exactly one **Bilingual Alignment
  Group**. A mismatch blocks or quarantines the smallest safely separable legal
  branch; governing or unbounded context broadens the affected branch.
- A **Statutory Note** remains exact bilingual legislation and stays attached
  to what it qualifies. An **HKeL Publisher Note** stays outside legal text; a
  material reliance limitation instead requires a separate approved English
  authority note or withholding decision.
- A meaningful image contributes serving text only through an **Official
  Textual Equivalent**. Without one, complete image evidence is preserved but
  the affected location is quarantined rather than described by AI or OCR.
- Exact source cross-reference words remain in `metadata.text`; their
  **Cross-Reference Relationship** is resolved and revised internally without
  expanding, modernizing, or silently correcting the source words.
- The pinned **HKeL Publication Specification Bundle** defines how that source
  evidence is interpreted. A changed or conflicting specification opens
  **Source Contract Review** rather than silently changing a parser, rule, or
  serving record.
- The **HKeL Instrument Disposition Registry** routes every Instruments &
  Others legal object by actual legal nature rather than its A-series filing
  category. It assigns one Release Scope and one primary serving disposition,
  while separately recording evidence relationships and authority-note consequences.
  Unknown or unaccounted entries cannot enter current search.
- A Hong Kong **Legal Status Event** and its exact affected-location mapping
  may exist before a new official consolidation. Under ADRs 0080 through 0087,
  it may contribute to a warned **Reconstructed Consolidation** only when the
  authentic bilingual amendment chain, closed operation registry, exact Plan
  and Execution Report, derivation and coverage proofs, later-HKeL
  reconciliation, and active capability attestation all pass. Otherwise no
  reconstructed result exists and the exact fallback, gap, block, or
  Quarantine path applies.
- **Hong Kong Gazette Event Evidence** may support that event, while the
  matching **HKeL Dual-Representation Evidence Bundle** separately supports
  the searchable consolidated text.
- **HKeL Past-Data Evidence** may supply a missing historical baseline or
  bounded investigation evidence on demand, while an **HKeL Editorial Record**
  proves its official editorial amendment and remains weekly monitored. Neither
  replaces the current **HKeL Dual-Representation Evidence Bundle**.
- **Excluded LegCo Legislative-History Material** creates no automated
  pipeline outcome, source dependency, authority note, or Search Record. Optional
  manual consultation cannot replace accepted Gazette or HKeL evidence.
- A **Legal Item** contains zero or more **Legal Locations**, whose visible
  locators may change without automatically changing their internal identities.
- A **Structured Legal Location** preserves official parentage and identifiers.
  Its deterministic plain-text representation keeps complete table header
  paths, form controls, dependencies, and source order without treating visual
  geometry as identity.
- A changed Search Record has a new ID and an explicit **Lineage Relationship**
  to its predecessor or predecessors.
- A later judicial-decision **Legal Item** may create **Later Treatment** for an
  exact earlier **Case Proposition** without changing the earlier judgment's
  Official Version. A no-proposition later judgment may still create the
  relationship because its decision, opinion, and treating passages are the
  required source anchor.
- Every accepted case-treatment relationship remains once in the internal
  graph. The Management Register derives its **Incoming Treatment View** and
  **Outgoing Treatment View** from the same ID and fingerprint; the views do
  not duplicate the edge, Search Record, or vector.
  The related **Authority Note** renders a budgeted current selection: every
  distinct mandatory warning first, then every material non-repetitive support
  and neutral explanation that fits. Equivalent events are consolidated and
  ranking controls ordering and compression near the pinned budget rather than
  imposing a fixed clause count. Bare citation, consolidated repetition,
  citation counts, and numeric strength scores remain outside the downstream
  LLM note.
- Material source-supported treatment reasoning may appear in the later
  judgment's ordinary Case Proposition `metadata.text`. Pinecone receives no
  separate treatment-relationship record, exhaustive outgoing-treatment list,
  case-specific metadata field, or whole-case treatment vector. Exact citator-
  style enumeration would require a separately approved graph query path.
- Only the **Generative-LLM Task Runner** may execute a **Pipeline LLM Task**.
  An admitted task owns only its named semantic fields after independent
  challenge and deterministic validation. Legal Desk/human review owns
  unresolved and exceptional cases; deterministic code retains source,
  contract, identity, exact-byte, completeness, Approval, and effect authority.
  ADR 0053 accepts whole-judgment discovery and candidate-level
  semantic stages for Hong Kong later treatment. ADR 0065 accepts separate
  proposition-analysis and proposition-challenge stages for Hong Kong Case
  Proposition extraction, and ADR 0067 permits those stages only inside an
  exact `ADMITTED` workflow whose immutable **Case Proposition Workflow
  Admission Profile** passes all gates through ADR 0068's exact Evaluation
  Suite Package and Evaluation Run Set. ADR 0076 accepts four HKEX Regulatory
  semantic stages: update analysis/challenge and record analysis/challenge. No
  real executable task package or production-admitted profile exists for any
  of these accepted allocations. Decision 7 additionally selects Gazette-event
  analysis/challenge and Reconstruction Plan decision/challenge. Offline
  evaluation is deterministic against human-adjudicated reference truth. Every
  other unallocated task defaults to `NO_GENERATIVE_LLM` for now. M5 includes
  one test-only local-fake Gazette task/profile solely for synthetic contract
  proof. `CALL_GENERATIVE_LLM` remains disabled for every real workflow and no
  provider/model call runs today. A later generative allocation requires a new
  ADR and complete task/evaluation/admission package.
- The **Embedding Adapter** is a separate promotion capability, and the
  **Ask.Legal Answer LLM** is a separate downstream application capability.
- Every **Search Record** carries one **Authority Note** string. Changing it,
  including between `"None"` and a real note, changes the serving payload.
- A real **Hong Kong Authority Note** is English only. The downstream LLM
  applies it regardless of query language and may express its effect in the
  answer language.
- Every selected **Search Record** has one matching **Record Traceability
  Lookup** entry validated before promotion. Ask.Legal does not join that
  lookup at query time.
- A **Frozen Principles Scope** keeps its exact last approved Search Records,
  authority-note values, and reusable embeddings in later serving states while
  blocking every update for that Principles source.
- An **Initial Current Baseline** freezes one cutoff, accounts for every item
  in its Release Scope, and may accept a clear present state without proving
  every earlier legal event. A named ambiguity opens targeted historical work;
  unresolved material remains quarantined rather than reconstructed.
- The **Hong Kong Cases Current-Authority Baseline** selects every required
  **Court-Year Case Release Scope** at one cutoff and reconciles material later
  treatment across all scopes. Old age alone does not remove a proposition,
  and a no-proposition decision still participates in treatment screening.
- A **Hong Kong Cases Ordinary Update** starts from that accepted baseline or a
  later accepted predecessor, expands every genuine change through its complete
  treatment impact, and reuses unrelated court-year releases. **HKLII Discovery
  Evidence** may open the work but never proves its legal result.
- A **Corpus Release** belongs to one **Release Scope** and contains zero or
  more **Search Records**.
- A **Desired-State Inventory** selects exactly one Corpus Release for every
  required Release Scope and contains the matching flattened expected-record
  inventory for one serving target.
- A **Promotion Manifest** contains one or more Desired-State Inventories and
  receives at most one current **Approval**.
- A **Routing Configuration** names the exact Pinecone Index Generation for
  every jurisdiction in one Serving State.
- A **Promotion Manifest** binds one candidate **Serving State Definition**.
- Successful build and verification events make its exact definition an
  eligible **Serving State**.
- A successful **Cutover** appends an activation event that makes one verified
  **Serving State** active for its environment.
- **Pinecone** is part of a Serving State but is never the Evidence Vault or
  Management Register.

## Example dialogue

> **Developer:** “The Watcher found that an Act page changed. Can the Scraper
> send the new text to Pinecone?”
>
> **Legal-domain owner:** “No. Preserve a Source Snapshot first. The Legal Desk
> must decide whether it is a supported Official Version. Valid Search Records
> then enter a Corpus Release, the complete Desired-State Inventory, and a
> frozen Promotion Manifest before the human can approve a new Serving State.”

## Flagged ambiguities

- **Current** is material-specific: operative official text for legislation;
  a case proposition together with required later-treatment information for
  cases; and either the latest maintained source-faithful paragraph for a
  jurisdiction's Principles or the exact last approved Principle selected
  under a licence-expiry freeze; and, for Hong Kong Regulatory Materials, the
  exact HKEX rule text and applicability proved effective at the frozen cutoff,
  including any current transitional branch.
- **Principle** refers only to the jurisdiction-specific Principles material
  family. Judicial material uses **Case Proposition**.
- **Stage** previously implied a separate repository. In the greenfield system,
  acquisition, legal processing, release construction, approval, and promotion
  are capability boundaries inside one modular monorepo.
- **Release** does not mean authorization. A **Corpus Release** is an immutable
  artifact; production still requires a valid **Approval** for a complete
  **Promotion Manifest**.
- A zero-record **Corpus Release** is valid only when its complete accounting
  proves that the scope has no supported current Search Records or explicitly
  withholds every item under evidence-backed decisions. A failure or Quarantine
  without those dispositions cannot masquerade as an empty release.
- The accepted serving envelope uses the five legacy base fields plus required
  `authority_note`. This contract does not adopt Distillation's source-path-and-locator
  identity semantics. Greenfield identity is register-owned and will be
  specified independently.
- For legislation, a matching URL, title, citation, visible provision number,
  wording, or document position never proves continuity by itself. Source
  moves preserve proved identities; new official consolidations create new
  Official Versions; repeal-and-substitution, split, merge, and re-enactment
  create the new Legal Item or Legal Location identities required by ADR 0012.
- For case law, one separately delivered judicial decision is one Legal Item;
  the wider litigation belongs in a Case Dossier. An exact proposition
  conclusively overruled by an authoritative court is retired from current
  Pinecone rather than served with a warning clause, while doubted or criticised
  propositions remain eligible only with the authority note required by ADR
  0014 as amended by ADRs 0050 and 0055. A former exact supported record may be
  reselected through a new Search Record Selection Event without backward
  lineage.
- For each jurisdiction's Principles, the Principles Title is the Legal Item,
  the publisher's edition or complete rolling update state is the Official
  Version, and the paragraph is the Legal Location. Licence expiry freezes and
  carries forward only the affected jurisdiction-and-source scope without
  authority-note change, withholding, retirement, or further updates under ADRs
  0015, 0017, and 0050.

## V1 runtime vocabulary — added 2026-08-18

- **V1 service entrypoint** — the continuous `--serve` mode of an application's
  console script. It is not the local `--check` boundary: it loads systemd
  credentials, composes only its own adapters, proves readiness, and serves.
- **Bounded readiness probe** — one non-mutating dependency check with a hard
  deadline. An *adapter* probe asks the real service a harmless question (SQL
  `SELECT 1`; a vault's versioning and Object Lock state). A *transport* probe
  only opens and closes a connection, and proves reachability, not health.
- **Container-only reservation** — a numeric UID/GID held so nothing else can
  take it, for a service that owns no host path and therefore gets no host
  account. Distinct from an allocated host account and from an image-defined
  identity such as SQL Server's 10001.
- **Installed-tree content digest** — the reproducibility measure for the
  application images: a digest over every file's path, mode, size, and bytes
  under `/opt/asklegal`. Docker image ids are deliberately not claimed to be
  reproducible, because Docker stamps a creation time into the image config.

## V1 official-source cycle vocabulary — added 2026-08-21

- **Official monitoring tier** — the source-role-owned daily-current-law,
  weekly-supporting, monthly-crosscheck, or on-demand cadence. The cycle planner
  derives due work from the active source register and cannot admit an
  `OUT_OF_SCOPE_V1` role.
- **Source coverage cycle** — one cutoff-bound set of all due official source
  roles. Every due role must have exactly one immutable terminal source report,
  including an explicit gap report when its procedure is not implemented.
  Omission is not no-change.
- **Source coverage cycle binding** — the exact Primary Vault name, logical key,
  version, fingerprint, byte length, cutoff, accounting result, release-blocking
  result, and missing/duplicate/gap IDs carried into the V1 Coverage Status
  Manifest. V1 release and promotion freeze fail closed when the binding is
  absent, incomplete, or release-blocking.
- **Official observation profile** — the source-role-owned local timeout,
  attempt ceiling, deterministic backoff, minimum interval, serial concurrency
  ceiling, closed retryable HTTP statuses, and registered outage consequence.
  It is enforced by the acquisition worker and is a conservative local V1
  policy, not evidence of publisher capacity.

## V1 promotion-effect freeze — added 2026-08-21

The current source has no executable external promotion entrypoint. Source
observation ends after acquisition and legal analysis. The promotion worker
registers no scheduler activity, provider effect, SQL handoff consumer, or target
write, and the retired deployment-wide `PROMOTION_WRITE_AUTHORIZED` flag is
always refused. The retained serving-record mapper requires an existing exact
`serving_payload_fingerprint` and compares it to the six received fields; it does
not recompute a changed payload into a new authoritative claim. This is a safety
freeze, not a completed Review/Approval/promotion path, and it is not present in
the older deployed images until an explicitly authorized rebuild/deployment.

## Stored proposal package — added 2026-08-21

A **Stored Proposal Package** is the portable receipt produced only after all 11
frozen proposal members are conditionally created and read back in the Primary
Vault and the schema-valid proposal manifest is committed last. It binds the
package and Promotion Manifest identities/fingerprints and, for every member and
the root, the exact vault, logical key, immutable provider version, fingerprint,
and byte length. A fresh process must reconstruct and verify the entire package
from those exact versions. The receipt is not Review, Approval, publication, or
effect authority.

## Registered proposal projection — added 2026-08-21

A **Registered Proposal Projection** is the read-only Management Register view
created only after Control re-reads all 12 exact proposal objects, revalidates
the complete package, and atomically records the canonical portable receipt as
`PROPOSAL_REVIEW_READY`. Review never treats a package ID, current vault key, or
database row as sufficient: its V1 reader compares the SQL row SHA-256, requires
canonical JSON, binds the register/package/Promotion Manifest identities, checks
the exact ordered 11-role inventory, and validates every Primary Vault logical
key, immutable version, size, and fingerprint before producing `REVIEW_READY`.
An empty register is a valid empty generation; duplicate, out-of-order,
noncanonical, corrupted, or later-version rows fail closed. The authored SQL
migration is not applied by source implementation work. Registration grants no
Approval or external-effect authority.

## Remote mutation outcome — added 2026-08-21

An **Outcome Unknown** is a remote mutation for which no exact successful
acknowledgement was received, including a transport/provider failure after the
request was issued or a malformed, missing, or wrong-count upsert reply. It is
not terminal success or ordinary retry authority. Promotion must enumerate the
remote target and compare the complete attempted batch—identity, exact vector,
and fingerprinted six-field serving payload. Only exact equality adopts the
mutation; any other state is `LOST_ACK_UNRECONCILED` and blocks cutover.

## Executable Promotion Manifest bytes — added 2026-08-21

The proposal role `PROMOTION_MANIFEST` contains the canonical serialized body
whose SHA-256 is the runtime Promotion Manifest fingerprint; it is never a
second wrapper carrying only an ID or fingerprint. The manifest ID derives from
that byte fingerprint. Before `PROPOSAL_REVIEW_READY`, Control re-reads the
complete exact-version package, parses this member, recovers its base/candidate
Serving States, validity window, and invalidation predicates, and requires those
facts to match the proposal root. A shared package reader gives Control, Review,
and Promotion the same twelve-object key/version/length/fingerprint checks.

## Registered Review decision — added 2026-08-22

A **Registered Review Decision** is a schema-valid
`asklegal.approval-decision` 1.1.0 document recorded by the Review application
only after it re-reads the complete exact proposal package, rechecks the
manifest fingerprint, verifies a delegated named-human
`PipelineAdministrator`, and resolves current identity/authority evidence. It
is an immutable no-effect event, not yet a consumable promotion Approval.
Control's proposal-registration aggregate version and Review's decision
aggregate version are separate application-owned sequences: the first Review
decision expects Review version 0 and creates Review version 1. Migration
`000004` projects the proposal receipt and optional decision to only the Review
and Promotion SQL roles. Review reconstructs and validates the canonical
decision after restart and fails closed on drift or tamper.

Approval validity-condition references are exact triples:
`(contract_id, version, fingerprint)`. The version is mandatory under Approval
schema 1.1.0 and may never be invented during decision construction.

## Pinned Entra access-token verification — added 2026-08-22

`EntraAccessTokenVerifier` is the framework-free resource-server adapter for
an already admitted single-tenant Entra v2 profile. It accepts only locally
pinned RSA public keys and RS256; it performs no issuer discovery, JWKS fetch,
or caller-selected key lookup. It checks exact issuer, tenant, audience,
allowed client, delegated scope, token lifetime, stable object identity, roles,
and token kind before returning a reduced `Principal`. App-only tokens can be
classified but ordinary Review authorization still rejects them. Production V1
composition remains disabled until the exact tenant/client/scope/key profile and
current Management Register authority evidence exist.

## Registered Approval consumption — added 2026-08-22

Promotion reconstructs a **Registered Approval Candidate** only from the
least-privilege SQL proposal/decision projection plus a fresh exact-version
reread of the proposal root and all eleven retained members. It validates the
canonical Approval 1.1.0 decision, executable Promotion Manifest, base Serving
State, validity predicates, reviewer identity, and historical authority
evidence before any consumption attempt.

Migration `000005` owns the single-use boundary in the Promotion application.
Its specialized procedure validates the exact proposal, decision fingerprint,
Approval, manifest, command, lifecycle event, and execution lineage; records one
`APPROVAL_CONSUMED` event atomically; and resolves an exact lost acknowledgement
as replay. A different lineage loses. The Promotion SQL role is expressly
denied the generic command procedure, so callers cannot bypass the guard. This
event creates no Effect Intent and grants no embedding, target, backup, routing,
retirement, provider, or deployment authority.

## Registered Approval terminal lifecycle — added 2026-08-22

Migration `000006` adds two specialized no-effect commands. Review may revoke
one exact approved, unconsumed Approval only after a current delegated named
human and authority-evidence recheck. Promotion may invalidate it only for one
closed objective reason such as a closed manifest window, changed base Serving
State, changed validity predicate, or removed reviewer authority. Both append a
schema-valid Approval 1.1.0 lifecycle event with no execution lineage.

Revocation, invalidation, and consumption acquire the same per-Approval SQL
application lock and compete for the same global terminal winner. Exactly one
can commit; exact replay resolves to the original immutable result. Review can
execute only revocation and Promotion only invalidation/consumption. These
terminal events still create no Effect Intent or provider authority.

## Registered execution authorization — added 2026-08-22

Migration `000007` adds the Promotion-only durable
`EXECUTION_PLANNED -> EXECUTION_AUTHORIZED` transition after one exact Approval
consumption. The specialized procedure independently proves the same proposal,
decision, manifest, `exe_` lineage and lineage fingerprint, Promotion worker
identity, and validation evidence from the immutable consumption command/event.
It validates the canonical authorization fingerprint and complete execution
event before committing execution aggregate version 1.

Authorization resolves exact replay and lost acknowledgement, rejects an
unconsumed Approval or changed lineage binding, and creates no Effect Intent,
claim, attempt, receipt, provider call, backup, target write, or routing
authority. The later `BEGIN` transition must separately recheck admitted
capability/profile facts and create the first Effect Intent atomically; no
provider handler is enabled by `000007`.

## V1 proposal-member semantic contract — added 2026-08-22

`validate_v1_proposal_members` is the shared framework-free contract for the
eleven canonical proposal members. It validates the exact role set and the
role-specific content for changes, releases, desired state, coverage, cost,
traceability, recovery, serving state, validation, Review reporting, and the
executable Promotion Manifest. It also proves their cutoff, scope, release,
record, evidence, fingerprint, candidate/base state, count, and gate results
agree as one package.

The shared exact-version package reader invokes this contract after all twelve
Primary Vault objects pass their byte/identity inventory checks, so Control and
Promotion cannot use a correctly hashed but meaningless member. Review invokes
the same contract independently from its own exact-version reads rather than
trusting another application's parsed result. Semantic validation creates no
Approval, Effect Intent, provider capability, or external authority.

## Hong Kong reconstruction execution, artifact, and Report package — added 2026-08-24

The thirtieth local Hong Kong Legislation checkpoint freezes package `0.30.0`,
fingerprint
`sha256:f7b2c61401095aada82528333edc56ae31dd83d0d6990f954ccaf056dc25edef`.
It contains 36 offline rules and 231 deterministic fixtures. The readiness
contract remains generated from that actual inventory and all three real scopes
remain `NOT_READY`.

`HKLEG-RECON-EXEC-001` consumes only one exact deterministically validated Plan,
two independently verified canonical base trees, the complete declared source-
artifact payload inventory, one complete final bilingual alignment map, and the
exact frozen renderer declaration. Its path-free request schema closes text,
canonical-fragment, source-unit-removal, and move-authority payload shapes before
implementation parsing. Its result schema permits only provisional canonical
trees/alignment or a complete no-output block; it cannot issue `rex_` or `rca_`
identities, a Search Record, provider request, or external effect.

The frozen 13-case execution catalogue covers every ADR 0082 operation and exact
atomic rollback for a before-state failure, final-tree mismatch, final source-
unit-inventory mismatch, incomplete bilingual alignment, and an OP008 structure
outside the renderer contract. Package proof revalidates every schema and byte
lock, reconstructs the request, executes it, validates the result, and compares
exact canonical bytes.

`HKLEG-RECON-ARTIFACT-001` constructs and independently re-reads the complete
eleven-member ADR 0085 package. Every final source unit and structural node has
exact unchanged-base or operation ownership. Surviving locations become the
ordinary renderer input; locations removed by a valid delete or replacement
remain explicitly accounted as ended in both the dependency proof and identity
result. Replacement execution results account for both removed and inserted
source units. All eight operation classes build complete artifacts.

`HKLEG-RECON-REPORT-001` creates the immutable canonical ADR 0084 `rex_` Report.
PASS requires the exact re-read artifact and retains the active Coverage Gap;
BLOCK accounts for every Plan operation and emits no artifact or record. FALLBACK
requires its own separately validated reference. The two frozen combined fixtures
cover exact PASS artifact/Report construction and exact no-output BLOCK reporting.

Two consecutive package rebuilds are byte-identical. The full legal-desk package
passes 107 tests. The complete repository shipping gate passes with strict
Pyright 0, Ruff clean across 381 Python files, the same 12 exact reviewed Python
boundary exceptions across 193 files, 5 applications, 14 packages, 80 dependency
edges, 31 capability ports, all contract/package/reproducibility gates, and 1005
passed with 4 intentional opt-in skips in 134.07 seconds. This remains source-
neutral synthetic conformance, not authentic HKeL XML/PDF admission.

## Hong Kong known-stale fallback and later-HKeL reconciliation — added 2026-08-24

Package `0.32.0`, fingerprint
`sha256:dfe7a1a88b77ac30947dcbcd52c636c19f16ba6716ab8fdf8aa3d859c66c5d6a`,
contains 38 offline rules and 255 deterministic fixtures. All three real scopes
remain `NOT_READY`.

`HKLEG-KNOWN-STALE-FALLBACK-001` implements ADR 0079/0081 selection only. The
latest applicable accepted exact bilingual HKeL version is selected with its
byte-exact source-text fingerprints and mandatory warning scope. Verified copy
evidence wins only for the same exact version; a newer valid assisted version
wins over an older verified version. An invalid latest version cannot silently
revive an older version. Missing eligible text yields no record and retains the
Coverage Gap. The gate creates neither an Official Version nor a Search Record.

`HKLEG-RECON-RECONCILE-001` implements ADR 0086's append-only monitoring and
comparison consequences. Invalid HKeL never replaces or becomes comparison
truth. Valid ordinary HKeL proceeds toward replacement regardless of deferred
comparison or material mismatch. Exact comparison accounts for every
reconstructed location; mismatch attribution binds a bounded component or the
complete rulebook/build impact scope; suspension selects validated fallback or
no record; revalidation is append-only. No decision mutates the reconstruction
artifact or performs an external effect.

The 109-test legal-desk suite passes. The complete shipping gate passes strict
Pyright 0, Ruff clean across 383 files, the same 12 reviewed Python-boundary
exceptions across 195 files, all architecture/contract/package/reproducibility
checks, and 1007 passed with 4 intentional skips in 141.77 seconds. This remains
source-neutral synthetic conformance, not authentic HKeL XML/PDF admission.

## Executable ADR 0078 Record Traceability Lookup — added 2026-08-24

The shared corpus package now implements `freeze_record_traceability_lookup`.
It consumes one exact Desired-State Inventory, one exact traceability entry per
selected Search Record, the complete used serving-profile set, register-issued
per-scope shard identities, and exact manifest/entry schema fingerprints.

Construction validates exact record/payload/scope/release agreement; non-empty
Official Version, Legal Location, and typed evidence sets; authority-note bytes
against their structured evidence fingerprint; canonical duplicate-free arrays;
and exact used profile coverage. It emits one JCS-canonical, Search-Record-sorted
NDJSON shard per selected Release Scope with LF after every entry, including an
exact zero-byte shard for a proved-empty scope. The canonical root manifest
binds every scope, release, shard ID/path/count/fingerprint, used profile, schema,
and total count. No file, vault, proposal, provider, or serving target is
mutated.

The proposal trust chain now uses the exact ADR 0078 root manifest as its fixed
`RECORD_TRACEABILITY` member. The portable registered receipt carries one exact
Primary Vault reference for every declared shard. Control writes all shards
before the lookup root and writes the proposal root last; its restart path
rereads every exact version. Review independently parses the receipt and rereads
all roots, members, and shards. Promotion independently repeats the full read
before reconstructing an Approval candidate. Missing, undeclared, corrupt,
wrong-fingerprint, wrong-count, wrong-scope/release, duplicate, noncanonical,
and zero-entry framing drift fail closed. The Desired-State proposal member now
carries each record's exact scope, release, and six-field serving-payload
fingerprint instead of record IDs alone, so transitive lookup validation binds
the actual desired payload inventory.

The M7 synthetic proposal path was also upgraded from its stale summary shapes
to the same exact semantic member and lookup contracts; all 32 path-independent
scenarios pass again. The complete repository shipping gate passes strict
Pyright 0, Ruff clean across 384 Python files, 196 Python-boundary files with
the unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1025 passed with 4 intentional skips in 141.89
seconds.

## Source-neutral recursive bilingual partition package — added 2026-08-24

Hong Kong Legislation package `0.40.0`, fingerprint
`sha256:a94c7b1223b015786df3678cdb106a3e5bd435495bba48aa2692c49d248bbadf`,
contains 39 offline rules and 277 deterministic fixtures. All three real scopes
remain `NOT_READY`.

`HKLEG-RECON-ORP-001` begins only after canonical authentic-language trees and
their accepted bilingual alignment exist. One strict request binds the exact
Legal Location, both tree fingerprints, the alignment fingerprint, declared
official bilingual partition nodes, and an exact serving profile. Measurement
uses the complete final `metadata.text` and independently JCS-serializes all six
serving fields, including `authority_note`. The production model, tokenizer,
numeric ceilings, source parsing, Search Record identity, and provider effects
are outside this boundary.

The recursive engine keeps a whole location when it fits, otherwise descends
only through declared matching official children. It chooses the fewest safe
contiguous parts and then fills earlier parts with the greatest possible number
of frontier units, using actual `X of N` bilingual labels. Required bilingual
parent context is repeated and measured; optional background is not. Exact
primary English and Traditional Chinese source-unit coverage, order, uniqueness,
scope ownership, and child-subtree ownership are checked before a result passes.
An indivisible over-limit branch quarantines with a required Coverage Gap;
unknown published meaning blocks. No arbitrary text boundary is available.

Twenty-two byte-locked source-neutral cases cover every ADR 0040 case, 001–022.
Each fixture is schema-validated, fingerprinted,
executed twice, and compared against exact canonical expected bytes. Missing or
reordered primary coverage now blocks as `SOURCE_UNIT_COVERAGE_DEFECT`; a
one-language-only proposed boundary quarantines as `BILINGUAL_ALIGNMENT_MISMATCH`
with a Coverage Gap. Case 016 separately proves that the absence of a smaller
official child can never be repaired by a sentence, punctuation, token, or
character cut. Case 012 proves a statutory note marker and complete bilingual
body remain in the same primary partition branch as the affected paragraph.
Case 019 separately blocks a requested Legal Location that does not match the
location owned by either authentic-language tree, even when all source units
are present and fit. Case 002 uses an explicit batch boundary that independently
processes two distinct Legal Locations, preserves input order, exposes no
aggregate serving part, and rejects duplicate locations. Case 011 adds an
accepted source-neutral table grammar: complete header paths
label cells, complete rows are indivisible, and every split part repeats the
bilingual headers. It does not claim Schedule, Form, or authentic HKeL-format
support. Case 022 binds an unsafe new Official Version to one explicit
evidence-backed ADR 0005 carry-forward, complete Withholding Release, or no-
jurisdiction-rebuild choice. Ordinary carry-forward is rejected when affirmative
record change is proved; both target-building choices require Approval; no-
rebuild retains the previous verified target. Every result carries the decision
reason, evidence, audit history, Coverage Gap, dates, author, exact references,
and decision predicates while creating no release, desired state, Search Record,
retirement, or external effect. Authentic HKeL XML/XSD/PDF handling, Schedules,
Forms, assets,
legislation-specific traceability entries, and a real admitted tokenizer.

The complete shipping gate after the initial `0.33.0` package passed strict
Pyright 0, Ruff
clean across 386 Python files, 198 Python-boundary files with the unchanged 12
reviewed exceptions, all architecture/contract/package/reproducibility gates,
and 1037 tests with 4 intentional opt-in skips in 148.20 seconds.
The `0.34.0` rerun remains green with the same gate counts and 1037 passed/4
intentional skips in 150.00 seconds; all 121 legal-desk tests pass independently.
The `0.35.0` rerun remains green with the same gate counts and 1037 passed/4
intentional skips in 148.07 seconds. The `0.36.0` checkpoint passes all 122
legal-desk tests and the complete gate with 1038 passed/4 intentional skips in
148.30 seconds; three package builds have identical manifest bytes. The
`0.37.0` checkpoint passes all 123 legal-desk tests and the complete gate with
1039 passed/4 intentional skips in 148.65 seconds; its three package builds are
also byte-identical. The `0.38.0` checkpoint passes all 124 legal-desk tests and
the complete gate with 1040 passed/4 intentional skips in 148.72 seconds; its
three package builds are byte-identical. The `0.39.0` checkpoint passes all 126
legal-desk tests and the complete gate with 1042 passed/4 intentional skips in
149.57 seconds; its three package builds are byte-identical.
The `0.40.0` checkpoint passes all 127 legal-desk tests and the complete gate
with 1043 passed/4 intentional skips in 152.22 seconds; three package builds
have identical manifest fingerprint and raw display bytes.

## Promotion action authority contract — verified 2026-08-24

The executable Promotion Manifest no longer carries opaque `action_ids` or a
global `capability_enabled` switch. Action contract `1.0.0` contains one ordered
closed object per future effect. Each action binds its sequence and identity,
effect type, `PROMOTION_WORKER` ownership, permitted checkpoint, sorted exact
immutable inputs, effect-command fingerprint, exact capability-profile
reference, capability/effect/destination binding, stable idempotency key,
retry class, attempt ceiling, deadline, the complete closed stop-condition set,
remote precondition contract, success-postcondition contract, and explicit
declared compensation or `NO_COMPENSATION`.

The promotion package validates typed action objects before freeze and again on
read-back. The shared Control/Promotion proposal validator and Review's
independent parser validate the same canonical bytes and reject unknown fields,
sequence/identity duplication, wrong effect bindings, stale top-level profile/
desired-state/candidate-state input fingerprints, missing stops, broadened
`NEVER` retry, malformed contracts, and improvised compensation. Current
capability state is deliberately not an approved boolean. The separately
implemented `BEGIN` boundary described below resolves the exact manifest profile
against current admitted capability evidence.

Cross-cutting `promotion_manifest` schema `1.1.0` owns this action contract and
removes its global capability state. The rebuilt contract package fingerprint is
`sha256:7a3f9f279c9dbea50796df013bfa420f2be97e56f067d8763e5286528b7f99d2`.
Hong Kong Legislation package `0.41.0` is a dependency-contract revision of the
unchanged `0.40.0` legal behavior and has fingerprint
`sha256:f5bad65a948de6c4a5e27f4e474dcd7607fb36e70d5afaf104dfa4354fe1f9e7`.
At this action-authority-only checkpoint, the complete gate passed Pyright 0,
Ruff clean/387 formatted, Python boundary
199 files/12 reviewed exceptions, all architecture and reproducibility gates,
and 1053 passed/4 intentional skips in 151.87 seconds. At that checkpoint no
Effect Intent, provider handler, external call, deployment, or target mutation
was enabled.

## Atomic registered execution BEGIN — verified 2026-08-24

The Promotion worker has one fail-closed `RegisteredExecutionBeginService`.
After a complete approved-candidate reread, it selects only action sequence 1
from action contract `1.0.0`, resolves that action's exact capability-profile
reference against current capability evidence, and refuses missing, inactive,
stale, wrong-owner, wrong-capability, changed-profile, or non-evidence results.
The BEGIN command contains the canonical approved action bytes and fingerprint,
exact capability-evidence reference, authorized execution lineage, manifest,
Approval, and Promotion-worker identity. It derives rather than accepts the
event and Effect Intent authority fields.

Migration `000008_registered_execution_begin`, package fingerprint
`34cc6c91d14155c719dfbc9af701adaa37b9ff48d3f62ae874ba32f01c4c4f0b`,
independently closes the command/event/intent shapes, recomputes all byte and
action fingerprints, matches the exact version-1 authorization command/event,
and calls the common command protocol with expected aggregate version 1. One
transaction records version 2, event `PROMOTION_EXECUTION_BEGAN`, and exactly
one first Effect Intent. Exact replay and lost acknowledgement return the
original result; a competing BEGIN records only a rejected command and no
second event or intent.

A fresh digest-pinned SQL Server 2025 Developer proof applied migrations
`000001` through `000008` twice and passed the atomicity, replay, competition,
tamper, binding, and least-privilege checks. The complete shipping gate passes
Pyright 0, Ruff clean/389 formatted, Python boundary 201 files/12 reviewed
exceptions, all architecture and reproducibility gates, and 1060 passed/4
intentional skips in 157.07 seconds. No handler is registered, the created
intent is not claimed, and no provider, target, backup, routing, deployment, or
live-host effect is enabled.

## Authentic HKeL format evidence audit — verified 2026-08-24

A read-only inventory of the complete current workspace, including ignored
local state, found zero `.xml`, `.xsd`, or `.pdf` candidate artifacts outside
tool dependencies. A read-only inspection of `v1-poc-runtime-proven` likewise
found no authentic HKeL XML, XSD, verified/assisted copy, or publication-
specification bytes; that disposable branch contains only documentation,
synthetic fixtures, and claims about those representations. The current source
register names and enables relevant HKeL endpoints, but endpoint contracts are
not source-format evidence. Authentic XML/XSD interpretation and XML/copy
reconciliation therefore remain unimplementable without first preserving the
exact official specification and example bytes. No code may infer tag meanings
from ADR prose or synthetic canonical trees.

## Disabled Promotion first-intent handler — verified 2026-08-24

`apps/promotion-worker/src/asklegal_promotion_worker/registered_effect_handler.py`
implements only the first approved action through injected ports. It validates
the claimed intent fingerprint and closed canonical schema, compares every
action-derived field with current action and capability evidence, renews the
claim immediately before the fake, appends one sanitized started attempt, and
records a strict terminal receipt. A stored prior attempt invokes reconciliation
instead of repeating the effect. Stale or changed authority cancels before an
attempt; absent current authority produces no invented receipt.

`EffectHandoffStore` now reads a claim through
`register.read_claimed_effect_v1`, renews the exact fence, appends attempts, and
consumes and validates the receipt procedure's authoritative result row. Direct
fact-table readback is not required by an application role. Migration `000009`
has two batches because SQL Server treats grants after `CREATE PROCEDURE` in the
same batch as procedure-body text. Its package fingerprint is
`53c719b243174afb6e089a8e37465be4017b96e0b1a54944721c1d8c6e3bfc2c`.

A fresh disposable SQL Server proof applies migrations `000001` through
`000009` twice and passes owner-scoped claim readback, current fencing, renewal,
stale-fence rejection, attempt and receipt persistence, replay, and wrong-owner
denial. The complete repository gate passes Pyright 0, Ruff clean/391 formatted,
203 boundary files with 12 reviewed exceptions, and 1069 passed/4 intentional
skips. No real handler composition or external effect is enabled.

## Hong Kong Cases listing-accounting kernel — verified 2026-08-24

`packages/legal-desks/src/asklegal_legal_desks/hk_case_listing.py` is the first
HKV1-4 implementation. Its included court-family codes are `CFA`, `CA`, `CFI`,
`CT`, `HKSUPERIOR`, and `HKPC`; ownership is exactly
`HK-CASE-{COURT_FAMILY}-{DECISION_YEAR}`. Excluded bodies and excluded artifact
classes remain visible as `OUT_OF_SCOPE` entries and create no scope.

The three official inventory source IDs accepted for completeness are
`HK-CASE-JUDICIARY-LRS-INVENTORY`, `HK-CASE-JUDICIARY-LIBRARY`, and
`HK-CASE-PRIVY-COUNCIL`. `HK-CASE-HKLII-DISCOVERY` is defined but rejected as a
due completeness source. The six acquisition outcomes are `ACQUIRED`,
`DUPLICATE_OR_ALIAS`, `TRANSLATION_ARTIFACT`, `OUT_OF_SCOPE`,
`BLOCKED_UNAVAILABLE`, and `QUARANTINED`. Decision processing separately records
propositions, valid no-material-proposition, processing Quarantine, or
unavailable scope.

The closed source universe contains seven roles: current LRS inventory,
Judiciary original judgments, item-specific court registry fallback, Judiciary
Library history, Privy Council Hong Kong appeal history, optional Judiciary
translations, and HKLII discovery. The six-family registry binds the four
ordinary current families to LRS and the two historical families to their
historical inventory sources while deliberately carrying no unevidenced year
boundary.

The scope-freeze boundary accepts only one complete sorted range set covering
all six families. Every range carries boundary evidence; ordinary current
families must end at the frozen cutoff year and historical families cannot end
after 1997. Only then does it generate the exact inclusive court-year scope
registry.

Seventeen synthetic tests prove complete and zero-record cycles, duplicate and
translation linkage, excluded bodies, unavailable evidence, missing processing,
incomplete due sources, HKLII rejection, post-cutoff isolation, court-year scope
ownership, and invalid duplicate rejection.

Frozen Hong Kong Cases package `0.11.0` remains an honest `NOT_READY` package. It
contains the seven source roles, six scope-family templates, listing-accounting
fixture, seven exact blockers, and three executable deterministic rules. The
source-neutral ADR 0062 Case Proposition Coverage Ledger contract `1.0.0` has 20
permanent ADR
0064 structure/ledger cases validate exact opinion/unit inventory, primary
coverage and order, dependencies and adoption, unit resolutions/uses, candidate
accounting, zero-proposition, Quarantine, blocked, and invalid results. The
ledger emits no Search Record and authorizes no semantic analysis or release.
The second executable rule implements all 16 deterministic ADR 0064 candidate,
evidence, renderer, and output cases. It validates exact candidate outcomes,
complete evidence roles, UTF-8 byte ranges and verbatim quotations, record-to-
proposition-to-ledger ownership, omission-only optional rendering, exact six-
field payloads, zero/one/many inventories, and pinned synthetic token/byte
limits. It validates proposed synthetic records but allocates or creates none.
The final 18-case correction/package/security/workflow-identity rule validates
unchanged reuse, official and processing-correction lineage, partial-impact
isolation, the complete explicit 132-case/132-cell/31-pair catalogue,
evaluation-packet non-leakage, registered sealed-artifact integrity, two-run
reproduction, forbidden capability denial, and exact assembled-workflow
identity. `ELIGIBLE_FOR_WORKFLOW_ADMISSION` creates no admission and grants no
provider, release, deployment, or serving authority. All 54 deterministic ADR
0064 cases are now executable. A separate strict ADR 0065/0066 preflight binds
the two semantic task families and all eight request kinds to exact workflow,
complete opinion/unit manifest, ordered assignment, original-language bytes and
ranges, dependency closure, prior-stage material, allowed IDs, evidence roles,
and no-tool/no-hidden-reference constraints. Its eight supplementary package
fixtures authorize zero provider calls. The separate semantic-materiality
evaluator now executes all 18 frozen `SEM-MAT` cases from small synthetic model-
facing inputs, evaluator-only Reference Proposition Maps, and adjudicated
observations without receiving case identity. Six complete high-risk pairs
reject swapped observations; P019 remains pending the future `SEM-RSK-016`
near-miss. The separate semantic-content evaluator executes all 18 frozen
`SEM-CNT` cases through the same model/reference/observation separation. It
compares required and forbidden meanings, qualifications, exceptions,
definitions, burdens, thresholds, minimum context, application, result, exact
quotation bytes, ordered non-contiguous range sets, preserved structure,
dependencies, unit use, ambiguity/locator consequence, resolution, and
selection without preferred-prose equality or case-ID switching. Pairs
P006-P008 reject swapped observations. The semantic-boundary evaluator now
executes all 22 frozen `SEM-BND` cases through the same separated trust boundary.
It checks cumulative tests versus independent grounds, repetition versus
distinct branches, issue scope, exact opinion inventories and paths, joint and
agreement-only opinions, concurrence, dissent, obiter, plurality, express
adoption, evidence ranges, unit accounting, selection, and quarantine. Pairs
P009-P015 reject swapped observations. Unsupported plurality reasoning remains
separately attributed and quarantined rather than being manufactured into a
majority holding.
The semantic-risk evaluator now executes those final 20 cases. It checks exact
court and original-language authority, auxiliary-only translation use, mixed-
language and historical formats, complete segments and dependencies, supported
parser structure, serving-limit split versus quarantine, genuine uncertainty,
hostile source text as evidence rather than instruction, and immutable
corrected-reasons re-evaluation. Pairs P016-P018 reject swapped observations and
`SEM-RSK-016` completes cross-checkpoint pair P019 against the proven zero in
`SEM-MAT-017`. All 78 frozen semantic cases now execute.
The first later-treatment checkpoint additionally executes all 13 frozen
whole-judgment discovery cases and pair P001. It preserves complete lead,
opinion, segment, context, correction, unresolved-identity, zero-proposition,
and original Chinese/mixed-language facts while deciding no legal effect and
granting no provider or downstream authority.
Concrete scopes, semantic profiles, evaluations, attestations, and activation
remain empty. Package fingerprint is
`sha256:545b9bb4ebb9dbfba16dc7bd3d54e1b83e698991331d4ffe30fe2c3ab82f77d9`.
It also contract-locks source-access register fingerprint
`sha256:c1c22ab94bb7ebdc95b6597c74856c430572a3887900deb1d57645fa186c33e4`.
The current cross-cutting contract fingerprint is
`sha256:92b5193ca9fa45d2260ee2012cd350818136f4d12b1d93e763a67b827d15c455`.

Hong Kong Cases source-access register `2026-08-24.1` contains the same seven
roles in sorted order. Every role binds its exact fact authority, completeness
authority, outage impact, unresolved publisher-rights state, and technical
blockers. All roles are `BLOCKED`; the endpoint inventory is empty. Its access
boundary is exactly `LOCAL_CONTRACT_ONLY_NO_SOURCE_ACCESS` and expressly forbids
real source access, publication, model/embedding calls, Pinecone mutation,
routing, and deployment. The shared endpoint contract accepts stable
`HK-CASE-*` identities, but no real Cases endpoint has been admitted.

The current complete repository gate passes Pyright 0, Ruff clean/454 formatted,
255 boundary files with 12 reviewed exceptions, and 1524 passed/4 intentional
skips in 181.91 seconds. The direct discovery/package suite passes 85 tests and
two consecutive rebuilt 559-file package trees have identical digest
`86ff3164e5e60679205d515f4b5d0a6857bfbfa44b7bb204a0cd17898063b559`.
All 54 proposition deterministic cases, 78 proposition semantic evaluator
cases, and 13/155 treatment cases are executable. No provider workflow, sealed
evaluation, concrete court-year scope, treatment graph, or real-source coverage
is claimed.

## Hong Kong Regulatory Materials inventory foundation

`hk_regulatory_inventory.py` freezes the accepted Main Board and GEM semantic
ownership scopes plus ADR 0070's five ordinary HKEX source roles. One cycle
keeps source-role observation completeness, source-entry membership, component
ownership/structure, atomic applicability-branch state, derived component state,
material disposition, and processing result separate. The catalogue role must
always cover both scopes; another source failure may remain board-bounded only
through explicit non-overlapping observations.

The four entry membership results are `RULE_COMPONENT`, `EVIDENCE_ONLY`,
`EXCLUDED_NON_RULE`, and `UNRESOLVED_MEMBERSHIP`. A rule component has exactly
one board owner, complete bidirectional entry links, supported parent structure
and order, and one or more retained branch decisions. Component summary follows
ADR 0071: one ordinary current branch remains `CURRENT`; limited or concurrent
current branches are `TRANSITIONAL_CURRENT`; a still-current predecessor is not
made transitional by a pending future branch; mixed or unknown facts become
`UNKNOWN`. State, disposition, and `PASS`/`BLOCK`/`QUARANTINE` cannot be repaired
into a plausible combination.

`hk_regulatory_effective_state.py` implements strict source-neutral ADR 0071
contract `1.0.0`. One request binds the exact branch, component, board, Legal
Location, cutoff, update/current-product evidence ranges, finality and permitted
approval inference, fixed-date or registered-source conditional facts,
transition/applicability, predecessor/successor, uncertainty, ADR 0005 outage
choice, rule, and evidence fingerprint. Only final publication with accepted
approval basis can proceed. At or after a date or proved trigger, the controlling
English product must match; no clock-only promotion or reconstructed wording is
possible. All-of and any-of negative evidence differ exactly, stale trigger
evidence becomes `UNKNOWN`, partial successors remain transitional, complete
successors supersede, official no-successor withdrawal withdraws, and
disappearance alone quarantines. Every result explicitly denies Search Record
and serving authority.

`hk_regulatory_continuity.py` implements component-continuity contract `1.0.0`.
It compares issued predecessor component/Legal Location identities with
decision-local current candidates without treating URLs, titles, numbers,
locators, filenames, or text similarity as identity. Proved rename, renumber,
structural move, correction, and URL-alias move preserve identity. Replacement,
split, merge, and board transfer require new register-issued identities with
typed forward lineage; the evaluator does not issue them. Official withdrawal
preserves historical identity, disappearance quarantines without retirement,
and proved reappearance reselects the prior ID. Fifteen frozen cases cover the
complete source-neutral event set and similarity-only rejection.

`hk_regulatory_english.py` implements strict source-neutral ADR 0073 contract
`1.0.0`. One ordered prevailing-English tree belongs to one exact applicability
branch and contains independent normal record roots; partitioning can never pack
different roots. Primary source units remain in exact order and have exactly one
root owner. Official child record units have one parent and partition their
parent's primary inventory exactly. Dependency closure is transitive, source-
ordered, excludes presentation-only material and unneeded background, and
preserves cross-reference locators without copying target text. Unknown normal
boundaries quarantine even when their bytes fit.

The canonical renderer emits the fixed ADR 0073 blocks in UTF-8 NFC with LF and
no trailing whitespace. It accounts for definitions, ordinary rules,
appendices/Practice Notes, table headers and rows, complete fee
category/amount/basis/timing sets, and Regulatory Form instructions and the
closed four-marker vocabulary. An injected exact tokenizer and the canonical
six-field payload are measured independently. Overlong material descends only
through supported official children, chooses the fewest contiguous parts and
earliest-full tie break, measures actual `X of N` labels, and quarantines an
indivisible or fixed-metadata-overlong unit. Future branches go to the Waiting
Room, superseded/withdrawn branches to history, and unknown branches to
Quarantine. The immutable coverage result separately classifies all primary,
context-only, and presentation-only units and always denies Search Record and
serving authority.

`hk_regulatory_record_identity.py` implements the source-neutral ADR 0011/0016/
0055/0073/0078 bridge from one exact current English serving part to a complete
traceability seed and one immutable identity consequence. Exact selected bytes
are preserved; exact older bytes are reselected without backward lineage;
unseen initial or payload-changing bytes require a Management Register-issued
initial or forward-successor ID. The Legal Desk never issues an ID, creates a
Search Record, mutates selection, or grants serving authority. Missing legal
support, non-current construction, false change claims, missing preserved
payloads, cross-scope identity, duplicates, and malformed evidence fail closed.

`hk_regulatory_conformance.py` validates the complete ADR 0075 universe identity
before any executable case result can count. The generated catalogue binds the
exact accepted design fingerprint, all 284 contiguous permanent case IDs, 284
matching primary coverage-cell IDs, eight exact checkpoint counts, and both
roles of all 57 permanent high-risk pairs. Unknown fields, missing/reordered/
misbound identities, count drift, incomplete/duplicate pairs, design drift, or
any claim that case packages, conformance, activation, or effects are ready
fails closed.

`hk_regulatory_conformance_package.py` implements the complete 38-case ADR 0075
package-integrity checkpoint on the strict ADR 0074 decision-to-artifact
envelope. Each fixture declares exact contracts, cell/pair identity, virtual
files and bytes, paths, hashes, media types, input/expected states, the complete
284-cell/57-pair synthetic matrix, reproducibility runs, proposal isolation,
forbidden capabilities, authority claims, and attestation bindings. The runner
derives results from those orthogonal facts and never selects a result from the
case ID. Negative cases pass only when the exact defect is rejected. Package
validity and build compatibility grant no source, provider, release, serving,
deployment, or external-effect authority.

`hk_regulatory_conformance_source.py` implements the complete 62-case ADR 0075
Source Fact Authority, membership, ownership, and language-evidence checkpoint
on the strict ADR 0074 evidence-to-decision envelope. Complete/fresh/reconciled
source-union claims enumerate the exact five-role universe rather than asserting
summary booleans. Each case binds its exact permanent cell and optional P001–
P015 role, two exact contracts, a fingerprinted proposal-safe evidence packet,
and a complete structured reference decision. The runner dispatches only on the
declared assertion dimension and derives the full decision from ordinary facts;
case ID never selects an answer. Conformance compares every structured field,
not only outcome/reason. Required English remains controlling, optional Chinese
cannot repair it, and every result denies Search Record, embedding, release,
serving, deployment, and external-effect authority.

`hk_regulatory_conformance_state.py` implements all 51 permanent ADR 0075
Applicability-branch effective-state and transition cases on the same strict
ADR 0074 evidence-to-decision boundary. The wrapper reuses ADR 0071 for atomic
branch truth and adds only the permanent dimensions that kernel does not own:
non-membership, complete component summaries, multi-branch preservation,
record responsibility, effective-fact ordering, full ADR 0005 source-failure
consequences, downstream-gate denial, and rejection of prose-based UNKNOWN
repair. Cases with two pair memberships preserve both. The evaluator dispatches
on a closed assertion dimension, never case ID, and complete structured equality
is required.

Frozen `_hk_regulatory_package` `0.9.0` binds both ownership scopes, all five
roles, eleven readiness blockers, the inventory fixture, four exact rule/
request/result contract sets, and the 22-case effective-state, 15-case
continuity, eight-case English construction, and eight-case record identity/
traceability fixture/result pairs plus the complete frozen conformance-universe
catalogue/schema/rule. It additionally freezes 38 individually fingerprinted
package-integrity case packages, 38 exact reports, three closed schemas, one
explicit catalogue, and rule `HKREG-PACKAGE-INTEGRITY-001`, plus 62 individually
fingerprinted source-decision case packages, 62 exact reports, three closed
schemas, one explicit catalogue, and rule `HKREG-SOURCE-DECISION-001`, plus 51
individually fingerprinted state-decision case packages, 51 exact reports,
three closed schemas, one explicit catalogue, and rule
`HKREG-STATE-DECISION-001`. Its 356-
file manifest fingerprint is
`sha256:50fb7bf5531f87cff30062c5dafeb016e6a1f3307469b7b2031e14aa57b54f36`.
Its generic terminal rules, admitted model/tokenizer profiles, evaluations,
attestations, endpoint, authentic source bytes, complete component inventory,
the remaining 133 executable case packages/results, register allocations,
release accounting, and activation authority remain empty.

The complete repository gate passes Pyright 0, Ruff clean/421 formatted, 225
boundary files with 12 reviewed exceptions, and 1263 passed/4 intentional skips
in 161.46 seconds. The package-integrity, source-decision, and state-decision checkpoints are
executable; they are not the complete conformance suite. No real HKEX coverage,
Search Record, register allocation, selection event, or serving result is
claimed.

`hk_regulatory_conformance_boundary.py` subsequently implements all 30
permanent ADR 0075 Record Boundary, governing-dependency, definition,
source-structure, cross-reference, and hard-limit cases. The fact-derived
evaluator never switches on case ID. Cross-reference results preserve exact
referring words, referring and target board identities, locator, optional
official heading, and resolution without copying target text. Exact excluded-
background and quarantined-unit identities are explicit result dimensions.
Pairs P025 through P031 each retain their exact positive and near-miss members.

Frozen `_hk_regulatory_package` `0.10.0` adds 30 cases, 30 exact reports, three
strict schemas, one catalogue, and rule `HKREG-BOUNDARY-DECISION-001`. It has
421 files and fingerprint
`sha256:d68b583f60f01b179e096b76f99a23be483e0c0575256d6ddaf13e284bc2a80e`.
181 of 284 permanent cases are executable and 103 remain. Two consecutive
generated package trees are byte-identical. The complete repository gate passes
Pyright 0, Ruff clean/423 formatted, 227 boundary files with the unchanged 12
reviewed exceptions, and 1278 passed/4 intentional skips in 161.24 seconds.
This remains source-neutral synthetic conformance and grants no authentic-
source, Search Record, release, serving, deployment, or effect authority.

`hk_regulatory_conformance_rendering.py` implements all 35 permanent ADR 0075
Canonical English rendering, table, fee, Regulatory Form, English-only serving,
measurement, source-ambiguity, and controlled authority-note cases. It keeps
the accepted ADR 0073 renderer as the canonical baseline: permanent governing-
context case 007 is byte-equal to the existing renderer's accepted output. The
strict decision-to-artifact wrapper binds a synthetic tokenizer/profile and
both exact final measurements, preserves complete source element sets, rejects
incomplete table/fee/Form projections and Chinese serving paths, keeps
`authority_note` outside text/embedding input, and records exact identity
consequences without allocating a Search Record. Pairs P032–P037 and P057 are
complete.

Frozen `_hk_regulatory_package` `0.11.0` adds 35 cases, 35 exact reports, three
strict schemas, one catalogue, and rule `HKREG-RENDERING-DECISION-001`. It has
496 files and fingerprint
`sha256:9e6d03f18b999db768807d951a6f30fc0c3e841edbd4159d98604bfc3858c186`.
216 of 284 permanent cases are executable and 68 remain. Two consecutive
generated package trees are byte-identical. The complete repository gate passes
Pyright 0, Ruff clean/425 formatted, 229 boundary files with the unchanged 12
reviewed exceptions, and 1298 passed/4 intentional skips in 162.53 seconds.
This remains source-neutral synthetic conformance and grants no authentic-
source, admitted tokenizer/model, Search Record, release, serving, deployment,
or effect authority.

`hk_regulatory_conformance_partition.py` implements all 24 permanent ADR 0075
Exact-limit measurement and official-structure partitioning cases by executing
the accepted ADR 0073 partitioner, not a parallel algorithm. Its strict ADR
0074 envelope binds the complete measurement-field inventory, one or two exact
construction requests, the synthetic codepoint counter/profile, and any
proposed cut basis. It preserves exact unsplit and final measurements, final
part labels, record/source-unit groups, dependency closure, payload
fingerprints, branch isolation, quarantine identities, and Coverage Gap IDs.
Cross-normal-unit packing, unrelated fill, PDF-page, sentence/punctuation,
whitespace/token/preferred-size, character/visual/window, and context-removal
proposals terminate before construction. Pairs P038–P040 are complete.

Frozen `_hk_regulatory_package` `0.12.0` adds 24 cases, 24 exact reports, three
strict schemas, one catalogue, and rule `HKREG-PARTITION-DECISION-001`. It has
549 files and fingerprint
`sha256:23d46c57eb30c7f1e59ca0a34e406e69e64f10542bdac814c2e8c0767609497e`.
240 of 284 permanent cases are executable and 44 remain. Two consecutive
generated package trees are byte-identical. The complete repository gate passes
Pyright 0, Ruff clean/427 formatted, 231 boundary files with the unchanged 12
reviewed exceptions, and 1326 passed/4 intentional skips in 165.78 seconds.
This remains source-neutral synthetic conformance and grants no authentic-
source, admitted tokenizer/model, Search Record, release, serving, deployment,
or effect authority.

### Complete source-unit coverage and board-readiness checkpoint

`hk_regulatory_conformance_coverage.py` implements all 20 permanent ADR 0075
English source-unit coverage and per-board readiness cases. It consumes the
accepted ADR 0073 `HKEXEnglishCoverageProof` rather than introducing another
renderer, partitioner, or coverage algorithm. Exact primary ownership,
governing-context dependencies, presentation-only accounting, source order,
board isolation, noncurrent disposition, candidate counts, and later-gate
readiness are explicit result dimensions. Missing, duplicate, orphaned,
wrong-board, fidelity-drifted, or shared-gap units fail closed. Proxy totals
cannot substitute for source-unit accounting, while a genuinely empty complete
board is a valid zero-output result. Pairs P041 through P045 are complete.

Frozen `_hk_regulatory_package` `0.13.0` adds 20 cases, 20 exact reports, three
strict schemas, one catalogue, and rule `HKREG-COVERAGE-DECISION-001`. It has
594 files and fingerprint
`sha256:4cb5d7f6d32de6b8f811cbb72e3eaf05abaaf0d0d316b6143b995a3fe46f6f2e`.
260 of 284 permanent cases are executable and 24 remain. Two consecutive
generated package trees are byte-identical. The complete repository gate passes
Pyright 0, Ruff clean/429 formatted, 233 boundary files with the unchanged 12
reviewed exceptions, and 1352 passed/4 intentional skips in 163.51 seconds.
This remains source-neutral synthetic conformance and grants no authentic-
source, admitted tokenizer/model, Search Record, release, serving, deployment,
or effect authority.

### Complete Search Record identity, lineage, and traceability checkpoint

`hk_regulatory_conformance_identity.py` implements all 24 permanent ADR 0075
identity, lineage, lookup, reuse, and update-consequence cases. It reuses the
accepted immutable record-identity and component-continuity decisions. Exact
payload reuse/reselection, each six-field successor condition, presentation-
only and traceability-only changes, board-separated identical source wording,
one-to-one/split/merge lineage, official continuity, and similarity-only
quarantine are derived from ordinary facts rather than case ID. Duplicate,
colliding, cyclic, backward, wrong-owner, incomplete, orphaned, or fingerprint-
drifted identity data fails closed. The evaluator allocates no register ID and
grants no Search Record selection, release, embedding, serving, or effect
authority. Pairs P046 through P049 are complete.

Frozen `_hk_regulatory_package` `0.14.0` adds 24 cases, 24 exact reports, three
strict schemas, one catalogue, and rule `HKREG-IDENTITY-DECISION-001`. It has
647 files and fingerprint
`sha256:9fffbb23d5db0902c0b6f2deb5d1f8152bd459fbf7bae9c641bcf081499e92fb`.
All 284 permanent cases and all 57 high-risk pairs are executable across the
complete eight-checkpoint source-neutral case universe. Each checkpoint remains
explicitly `full_conformance_suite_complete=false`; the universe records only
`executable_case_packages_complete=true`, while `conformance_ready=false` and
activation remains forbidden. Two consecutive generated package trees are
byte-identical. The complete repository gate passes Pyright 0, Ruff clean/431
formatted, 235 boundary files with the unchanged 12 reviewed exceptions, and
1367 passed/4 intentional skips in 163.33 seconds. Authentic-source evaluation,
protected reference truth, exact admitted tokenizer/model profiles, named
attestations, both real scope admissions, releases, serving, deployment, and
effects remain unadmitted.

### External HKEX build-conformance attestation

The source-neutral HKEX package now has a separate external ADR 0074 Rulebook
Conformance Attestation under
`packages/legal-desks/conformance/hk-regulatory/`. It deliberately remains
outside `_hk_regulatory_package`: the proof depends on both package and build,
and embedding it in the package would create a fingerprint cycle.

Attestation `rba_3934c1b573cb9a346ce131715d23db85981986644d96e389` binds exact package
`0.14.0`, all 284 result artifacts, 39 legal-desk processing-source members,
`uv.lock`, the isolated runner, contract set, and the successful architecture
report. Two fresh processes reproduce result-set fingerprint
`sha256:ef3072108871b2dd1fb945c06d144e00fa3a90be84a229488afbbc2f56ec32f8`
and result-tree fingerprint
`sha256:4a75c5643d662156c541a0a2d63cc46fdb9f0633c4c3c069858d77919f31f8b1`.
Its only capability claim is `BUILD_COMPATIBILITY`; all source, real-evidence,
release, Approval, Pinecone, deployment, activation, and external-effect
authority is false.

### Hong Kong Cases whole-judgment treatment discovery

Source-neutral Cases package `0.11.0` implements the complete first ADR 0059
later-treatment checkpoint: 13 semantic whole-judgment discovery cases and
high-risk pair P001. The evaluator preserves complete opinion/segment ledgers,
formal and implicit leads, resolved/unmatched/ambiguous identity state, exact
passages and context, separate opinion attribution, zero-proposition outgoing
treatment, correction inventory, and original Chinese/mixed-language evidence.
It treats silence and missing context as non-authoritative, decides no legal
effect, and grants no provider call, relationship, Search Record, release,
activation, or external effect. The package fingerprint at this checkpoint is
`sha256:545b9bb4ebb9dbfba16dc7bd3d54e1b83e698991331d4ffe30fe2c3ab82f77d9`.
