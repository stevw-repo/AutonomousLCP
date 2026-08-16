# Production Technical Stack Recommendation

Status: **ACCEPTED DESIGN BASELINE — Python fixed by ADR 0089, the application
framework and boundary toolchain fixed by ADR 0090, the Management Register
database and write boundary fixed by ADR 0091, the application host and
network-isolation shape fixed by ADR 0092, durable workflow fixed by ADR 0093,
the Azure-only Evidence Vault, Recovery Vault, and digest boundary fixed by ADR
0094, and the image-registry and software-supply-chain boundary fixed by ADR
0095, and the split Application Gateway and Entra API edge fixed by ADR 0096;
the Bicep and Azure Pipelines delivery boundary is fixed by ADR 0097; the
observability and immutable operational-audit boundary is fixed by ADR 0098.
The stateless Azure OpenAI/Foundry provider boundary is selected by decision 1
to match Ask.Legal Backend. Decision 4 selects separate candidate-slot routing.
Decision 5 selects Pinecone naming. Decision 6 selects fingerprint-bound,
protected, verified-and-cached coverage delivery without signing keys. Decision
7 and accepted ADR 0099 settle the remaining LLM-assisted tasks, bounded
semantic-decision authority, deterministic default, and implementation-facing
closure package**
Updated: 2026-08-16
Scope: design selection only

## Current outcome

ADR 0089 selects **Python 3.14** as the application language for the control
plane, Review Application API, acquisition worker, legal-processing worker,
promotion worker, and shared production packages. The exact supported 3.14
patch is now pinned to **3.14.7** by the first authorized local contract spike.

ADR 0090 selects **FastAPI, Pydantic v2, Uvicorn, Pyright strict, Ruff, uv
workspaces, a repository-owned strict JSON parser, `jsonschema` with
`referencing`, Trail of Bits `rfc8785`, pytest, Hypothesis, HTTPX, and AnyIO**
as the application framework and boundary toolchain. Exact dependency versions
remain lock-time implementation details, not floating production choices.

ADR 0091 selects **Azure SQL Database, T-SQL, and Microsoft's first-party
`mssql-python` driver** for the Management Register. Authoritative mutations
use exact command stored procedures behind least-privilege application roles;
selected immutable facts use append-only ledger tables, current views remain
rebuildable projections, and schema changes use fingerprinted forward-only SQL
migration packages.

ADR 0092 selects **Azure Container Apps** for all five production pipeline
runtime boundaries. Each application uses its own workload-profiles
environment, delegated subnet, runtime managed identity, database role,
secrets, scaling policy, deployment identity, and deployment job. The two APIs
have internal origins behind the ADR 0096 edge, all three workers have ingress
disabled, and the promotion worker is a continuously running durable worker
rather than an override-capable manually started Container Apps Job.

ADR 0093 selects the **generally available standalone Python Durable Task SDK
with managed Azure Durable Task Scheduler**. A general scheduler contains
separate control-plane, acquisition, and legal-processing task hubs; a separate
promotion scheduler contains only the promotion task hub. The Review API has
no scheduler access. Cross-application work moves through exact Management
Register outbox facts rather than shared orchestrations or task hubs.

ADR 0094 selects **Azure Blob Storage version-level WORM for both the primary
Evidence Vault and a separately administered Recovery Vault in a dedicated
Azure subscription, plus Azure Confidential Ledger for Azure SQL database
digests**. The Recovery Vault stays under the existing Entra tenant and uses a
different Azure region pair where data-location rules permit. Both copies use
Microsoft-managed keys plus infrastructure encryption; customer-key artifact
classes remain disabled until key recovery has passed.

ADR 0095 selects **one private Azure Container Registry Premium registry with
Entra repository ABAC and attested image admission**. Separate base, tool,
candidate, and per-application release repositories preserve build and runtime
boundaries. Notation with Azure Artifact Signing, BuildKit provenance, Syft
SPDX SBOMs, Grype vulnerability results, a repository-owned licence policy,
digest-only Container Apps references, locked release graphs, and OCI recovery
packages form the production image boundary.

ADR 0096 selects **one regional Azure Application Gateway WAF_v2 with a public
Review listener and private Control listener**. Both origins remain internal
Container Apps environments. The APIs use separate Entra resource
registrations, audiences, scopes, roles, client allow-lists, and application
authorization. Approval and revocation remain human-only under the single
`PipelineAdministrator` role; ordinary production MFA applies, with no separate
action-specific step-up requirement.

ADR 0097 selects **repository-owned Bicep with Azure Pipelines** while GitHub
remains the reviewed source repository. It selects workload-federated
service connections, fresh Microsoft-hosted agents for offline and Azure
control-plane work, and separate stateless Managed DevOps Pools for private
ACR supply-chain work and private Azure SQL migrations. Infrastructure apply,
role assignment, policy and locks, migration, image admission, and each
application deployment remain separately gated.

ADR 0098 selects **direct Azure Monitor OpenTelemetry instrumentation with
five workspace-based Application Insights resources, one application-
operations workspace, and one restricted security-and-audit workspace**.
Azure Monitor remains a detection and query plane rather than an authority.
Required operational audit records also flow to a dedicated immutable primary
archive, are sealed into exact interval packages, and are copied through the
promotion-owned recovery capability to a separately administered Recovery
Audit Archive. Application Insights, a workspace, an alert, or an Azure
Pipeline run log may never be the only audit evidence.

Decision 1 selects **Azure OpenAI models sold by Azure through Microsoft Foundry
for stateless generative proposals and embeddings**, matching Ask.Legal
Backend's provider family. Decision 4 selects a restricted App Service
candidate slot, distinct from development, with validated manual slot swap for
Ask.Legal routing. Decision 5 selects the final Pinecone naming contract.
Decision 6 selects complete immutable, fingerprint-bound coverage delivery
through protected authenticated retrieval and verified per-generation caching,
without a coverage-signing-key lifecycle. Exact deployed model profiles and
measured infrastructure/operational values remain admission evidence with no
implicit default. ADR 0099 and its six implementation-facing protocols are
accepted.

The checked-in Ask.Legal Core deployment standard is GitHub Actions rather
than Azure Pipelines. Its inspected Static Web Apps workflows use deployment-
token secrets and its App Service workflows use publish-profile secrets; no
checked-in workload-federation or infrastructure-as-code standard was found.
Workload federation is therefore an intentional security improvement, while
Azure Pipelines is a platform deviation. The user explicitly accepted that
deviation on 2026-08-16, prioritizing Azure-only simplicity and an Azure-
managed private-runner and approval path.

Enterprise Cloud is not required for GitHub Actions or Entra OIDC. Without it,
Ask.Legal could preserve GitHub Actions by owning fresh ephemeral self-hosted
runners inside the private Azure networks and an independent deployment-
approval control. That is not the existing approach unchanged and carries a
runner-platform operating burden. It must be compared honestly with Azure
Pipelines and Managed DevOps Pools rather than implemented through public ACR
or SQL exceptions, persistent runners, or reusable deployment secrets.

The browser surface remains outside that choice. An initial React and
TypeScript review client may be used while the pipeline is proved; the intended
later experience is integration into the Ask.Legal admin portal through the
same separately permissioned Review Application API.

This intentionally simple Azure-only boundary does not protect against an
Azure-wide failure or compromise of the shared Entra tenant. It does isolate
ordinary application, account, subscription, administrator, policy, and
regional failures. No package version, exact edge setting, capacity setting,
deployment workflow, operational capability, or external operation is
accepted merely because these design choices are accepted.

## Why Python is accepted

The language decision combines system fit with organizational fit:

- Microsoft's standalone Python Durable Task SDK is generally available and
  supports durable orchestrations, activities, sub-orchestrations, timers,
  external events, entities, retry policies, continue-as-new, and
  suspend/resume.
- Ask.Legal already operates a Python 3.14 AI service using Flask, Gunicorn,
  SQLAlchemy/pyodbc, OpenAI, Pinecone, document-processing libraries, pytest,
  and Azure App Service.
- Python has the strongest relevant document, OCR, language, data, and model-
  integration ecosystem.
- Selecting C# would introduce a third backend language and package, build,
  security-patching, debugging, hiring, and on-call ecosystem without a
  requirement that Python cannot currently satisfy.
- The existing Node.js backend is plain JavaScript and its in-process cron
  pattern is not the correct durability boundary for multi-day workflows.
  Microsoft's standalone JavaScript/TypeScript Durable Task SDK also remains
  Preview.

The existing Ask.Legal repositories were inspected only through the user's
explicit read-only comparison request. They remain non-authoritative reference
evidence and create no production dependency or shared authorization.

## Python application boundary

Python 3.14 applies to:

| Application or package family | Python responsibility |
|---|---|
| Control plane | Scheduling API, workflow admission, source registry, coordination, coverage status, and reporting |
| Review Application API | Evidence and manifest inspection, comments, rejection, exact Approval, and revocation operations |
| Acquisition worker | Watchers, scrapers, hostile-input containment, hashing, and immutable evidence capture |
| Legal-processing worker | Parsing, deterministic rules, Legal Desk execution, candidate construction, validation, and the sole gated generative-LLM task runner |
| Promotion worker | Embeddings, recovery checks, replacement targets, verification, cutover, rollback, and exact approved retirement |
| Shared production packages | Domain objects, contracts, source connectors, Legal Desks, corpus, promotion, reporting, and adapter interfaces |

It does not require Python for:

- the initial review browser client or later Ask.Legal admin portal;
- Bicep or other infrastructure definitions;
- SQL migrations;
- shell-neutral developer commands;
- an audited third-party native parser or cryptographic library; or
- the existing dependency-free Node contract validator, which remains an
  independent conformance oracle rather than a production service.

A second application language requires a later ADR. A narrow native or command-
line dependency does not become a second application authority and must remain
behind a typed, validated, sandboxed adapter.

## Required Python engineering profile

The greenfield pipeline must not copy a permissive scripting style. Python's
dynamic runtime is acceptable only with stricter mechanical controls than the
existing Ask.Legal AI service currently demonstrates.

### Static types

- Every production function, method, attribute, collection, and return value
  is fully annotated.
- CI runs one selected strict static type checker and fails on every error.
- `Any`, unparameterized collections, unchecked casts, and ignored errors are
  forbidden in domain and application packages. A provider adapter may contain
  one narrow documented escape only when the external library makes it
  unavoidable.
- Domain packages use closed enums, frozen value objects, discriminated
  unions, protocols, and explicit result types rather than stringly typed
  dictionaries.
- Static typing is an additional check, not a substitute for validation of
  external bytes.

ADR 0090 selects the official Pyright CLI in strict mode. Unknown and implicit
`Any` values are errors. Third-party typing gaps stay inside narrow adapters
with reviewed wrappers or local stubs; they do not relax a whole package. The
official npm distribution is pinned in the development-tool lock rather than
using the community PyPI wrapper as though it were first-party.

### Runtime validation

ADR 0090 selects Pydantic v2 for strict, closed, frozen transport,
configuration, and provider boundary models. Stable domain packages use
framework-free frozen slotted dataclasses, enums, protocols, discriminated
unions, and explicit result types. Repository-owned JSON Schemas remain
normative; Pydantic-generated schemas must not replace or silently reinterpret
the contracts.

The production path for normative JSON must:

1. accept raw UTF-8 bytes into a strict I-JSON pre-parser;
2. reject byte-order marks, duplicate keys, invalid Unicode, invalid number
   forms, non-finite numbers, negative zero, and unsafe integers;
3. validate the exact JSON Schema Draft 2020-12 document and local references;
4. bind the validated value to closed frozen Python types without ignoring
   unknown properties;
5. serialize through RFC 8785 JCS; and
6. calculate and compare the exact lowercase `sha256:` fingerprint.

The strict raw parser is a repository-owned adapter over the standard-library
JSON decoder. It must inspect object pairs and numeric tokens before typed
binding. Draft 2020-12 validation uses `jsonschema.Draft202012Validator` with a
preloaded, network-disabled `referencing.Registry`. JCS uses Trail of Bits
`rfc8785` behind a replaceable internal adapter.

Pydantic's strict mode reduces coercion but is deliberately not treated as
proof of strict I-JSON, Draft 2020-12, or JCS conformance. Normative HTTP routes
read raw bytes and validate them before strict `model_validate` binding; they
do not call Pydantic's JSON parser. The first local spike
must prove every positive, negative, Unicode, numeric, collision, lifecycle,
and reproducibility fixture in both Python and the existing Node validator.

### Determinism and effects

- Durable orchestrator functions contain deterministic coordination only.
- Network, clock, random, filesystem, database, model, source, Pinecone, and
  Azure operations occur in activities or bounded adapters.
- Orchestration payloads contain only small commands, opaque IDs,
  fingerprints, and bounded results; legal content stays in the Evidence Vault
  or approved artifact store.
- External events are deduplicated against exact register-issued IDs and
  fingerprints.
- CPU-heavy parsing or unsafe native libraries run in bounded processes or
  containers rather than blocking API or orchestration workers.
- No distributed transaction spans the Management Register and an external
  provider; transactional outbox/inbox and idempotent adapters control effects.

### Packaging and tests

ADR 0090 selects one uv workspace: each application and shared package is an
installable `pyproject.toml` member, and all Python members resolve through one
committed cross-platform `uv.lock`. Application images install only the member
and dependency groups they need. Python, uv, Pyright, Ruff, and container inputs
are pinned outside or alongside the dependency lock as appropriate. A clean
locked offline-install proof remains mandatory.

Minimum Python checks are:

- Pyright strict type checking;
- Ruff lint and format checks;
- pytest unit, contract, lifecycle, integration, and architecture tests;
- Hypothesis property-based tests for identities, state transitions, retry,
  raw JSON, JCS, and serialization boundaries;
- HTTPX and AnyIO tests across the in-process ASGI boundary;
- import-boundary and dependency-cycle tests;
- dependency vulnerability, licence, provenance, and software-bill-of-
  materials checks;
- two-process byte-identical reproducibility tests; and
- container execution as a non-root user with a read-only root filesystem
  where the application permits it.

Exact versions remain unselected until an authorized local spike creates and
validates the lock without making an external provider call. Tool families and
their responsibilities are settled by ADR 0090.

## Accepted application framework

The control-plane and Review Application HTTP APIs use FastAPI under Uvicorn.
FastAPI provides the typed OpenAPI boundary needed by the initial review client
and later admin portal, while Uvicorn supplies the ASGI server. Flask's existing
Ask.Legal familiarity did not outweigh the additional model, schema, and
OpenAPI wiring it would require for the same result.

This selection is deliberately narrow:

- FastAPI remains in application HTTP adapters and is forbidden in domain and
  contract packages;
- normative JSON routes intercept bounded raw bytes before FastAPI or Pydantic
  parsing or coercion;
- Pydantic models reject unknown fields and coercion but remain subordinate to
  repository-owned schemas;
- generated OpenAPI describes the HTTP API and supports client generation but
  does not become the artifact-contract authority;
- exact error envelopes remain repository-owned contracts;
- reviewer authentication uses the separate Entra resource, client, scope,
  role, Conditional Access, and application-authorization boundary selected by
  ADR 0096; and
- no durable pipeline work may use FastAPI background tasks.

## Infrastructure decisions and recommendations

The Management Register is accepted by ADR 0091, application hosting by ADR
0092, durable workflow by ADR 0093, evidence and recovery storage by ADR 0094,
image registry and admission by ADR 0095, and the API edge and Entra resource
boundary by ADR 0096. Other infrastructure components remain recommendations
until a later decision.

### Durable workflow

**Accepted by ADR 0093: the GA standalone Python Durable Task SDK with managed
Azure Durable Task Scheduler.** The workers remain ordinary Python processes
on Container Apps rather than acquiring an Azure Functions host.

One general Scheduler resource has separate task hubs for control,
acquisition, and legal processing. One isolated Scheduler resource has the
promotion task hub. Identities are user-assigned, RBAC is task-hub scoped,
private endpoints and private DNS provide the data path, and public network
access is disabled after proof. The Review API and other application
identities have no promotion Scheduler path or role.

Cross-application handoff uses the Management Register's transactional outbox.
Each receiving application schedules exact idempotent work into only its own
task hub. The Scheduler owns execution history, deterministic replay, timers,
retries, external-event delivery, and durable waiting. The Management Register
remains authoritative for business state, legal decisions, evidence bindings,
capabilities, Approval, promotion admission, and Serving State.

Scheduler payloads have an initial internal 64 KiB ceiling and contain only
opaque IDs, fingerprints, closed codes, counters, and sanitized status. Legal
content, prompts, model or provider payloads, approvals, comments, secrets,
and raw exception data remain outside Scheduler history. Terminal history is
operational and purgeable, never the audit or disaster-recovery record.

Temporal was the strongest alternative, but Temporal Cloud on Azure is still
invite-only pre-release and self-hosting would add a workflow control plane,
persistence and visibility stores, schema upgrades, and recovery operations.
Dapr Workflow adds sidecars, actor placement, and a strongly consistent state
store; its multi-application mode also requires a shared namespace and state
store. Durable Functions adds an unneeded Functions host. A custom SQL or
queue state machine would make the project implement replay, durable waits,
versioning, and recovery itself.

Do not introduce Redis queues, Celery, Azure Service Bus, Kafka, APScheduler,
or another workflow engine merely for convenience. A measured ingress or
throughput requirement may justify a narrowly owned transport later; none may
become a second source of workflow truth.

### Management Register database

**Accepted by ADR 0091: Azure SQL Database with `mssql-python`.** Azure SQL and
PostgreSQL can both satisfy the relational, transaction, role, networking, and
restore requirements. PostgreSQL has the more mature Python driver, native
async support, and greater portability. Azure SQL wins for this register
because selective append-only ledger tables and externally stored database
digests provide a native tamper-evidence path, `mssql-python` is now a GA
first-party DB-API driver without a separate ODBC-manager dependency, and
Ask.Legal already operates SQL Server from both backend ecosystems.

The accepted boundary is deliberately narrower than “use SQL Server”:

- immutable authoritative objects, events, command claims and results, outbox
  facts, promotion receipts, and migration facts use a small explicit set of
  append-only ledger tables;
- mutable current-state, dispatch, and reporting tables are rebuildable
  projections and never become historical authority;
- applications call schema-qualified T-SQL command procedures through a typed
  `ManagementRegisterStore`; their managed identities have `EXECUTE` on owned
  commands and `SELECT` on owned views, not table DML or DDL;
- each command atomically records its fingerprint-bound inbox claim, domain
  events, outbox intents, projections, and exact result;
- promotion, rollback, Approval consumption, and similar single-winner
  transitions combine exact constraints and compare-and-set with a finite
  transaction-owned application lock and targeted serializable isolation;
- authoritative JSON is stored as validated JCS UTF-8 bytes plus its
  fingerprint and typed constraint columns, not normalized by SQL Server's
  JSON behavior;
- async FastAPI paths call the synchronous driver only through a bounded AnyIO
  worker-thread adapter, with no connection shared across a thread or `await`;
  and
- one small repository-owned migration runner applies closed, ordered,
  fingerprinted, forward-only T-SQL batch packages under a migration lock and
  records the result in an append-only migration ledger.

The exact service tier, availability configuration, pool sizes, backup and
long-term retention, recovery objectives, digest store, and cost model remain
operations decisions. Ledger is not applied database-wide and does not replace
the Evidence Vault, least privilege, backups, restore drills, or independent
digest verification. `mssql-python` must pass a Python 3.14, Pyright, data-type,
transaction, concurrency, failover, and ambiguous-commit spike before a
production capability is admitted.

This is a local-first development choice. Ordinary development needs no Azure
credentials or shared cloud database: synthetic tests and local provider fakes
run against a supported local SQL Server Developer container created from the
exact migrations. Azure is used later, under separate authorization, only to
prove Azure-specific managed identity, networking, limits, failover, backup,
external ledger-digest, monitoring, and hosting behavior before production.

### Hosting

**Accepted by ADR 0092: Azure Container Apps with one workload-profiles
environment and delegated subnet per pipeline application.** The control plane
and Review Application API are continuously available internal FastAPI apps
behind the split ADR 0096 Application Gateway edge. Acquisition, legal
processing, and promotion are continuously running apps with ingress disabled
and durable worker connections.

Container Apps won because it provides one direct container model for HTTP
APIs and no-ingress workers, per-app scaling and revisions, and explicit
environment-level network boundaries. App Service remained capable and more
familiar, but strict isolation would require separate plans and worker-specific
WebJob or empty-web-app conventions. Sharing one plan would couple compute,
scaling, and worker pressure; using App Service only for the APIs would add a
second pipeline host without a required capability.

Production does not assume scale to zero: Durable Task Scheduler streams work
to connected workers, so each worker initially keeps at least one replica; the
APIs do likewise for availability. Exact profiles, replica sizes and limits,
zones, region, firewall, DNS, disaster recovery, service levels, and cost remain
measured decisions. All outbound traffic follows per-subnet policy and selected
Azure services use private endpoints and private DNS where supported.

The promotion worker is not a manually started Container Apps Job. The Job
start operation accepts an execution-template override, including image and
command, and a starter can access configured Job secrets. Promotion instead
receives only durable fingerprint-bound work and independently revalidates the
exact Approval and manifest. Correctness never relies on a singleton replica.

ADR 0002 remains unchanged: downstream Ask.Legal stays on its existing App
Service configuration boundary for active Pinecone generation settings.
Selecting Container Apps for the pipeline does not move or redesign that
downstream application.

### API edge and reviewer identity

**Accepted by ADR 0096: one regional Application Gateway WAF_v2 with a public
Review listener and a private control-plane listener.** The public frontend has
no control hostname, listener, path, or backend. The private listener has
private DNS and is reachable only through an approved private operator-network
path. Separate certificates, backend pools, probes, routes, and per-listener
WAF policies preserve the two exposure boundaries. There is no gateway route
to a worker.

Both API origins remain internal Container Apps environments with private
virtual IPs and disabled public network access. Their app ingress is reachable
at the environment or VNet scope so the hub gateway can reach it. Private DNS,
exact backend host and SNI, end-to-end TLS, subnet restrictions, and
trusted-proxy handling prevent a direct-origin or forged-header bypass.

The gateway owns TLS, WAF, coarse rate limiting, routing, and origin isolation;
it does not own authentication or business authorization. Control and Review
are separate single-tenant Entra resource applications. Each FastAPI API
validates issuer, tenant, audience, lifetime, stable subject, actor client,
scope or expressly admitted application role, and the exact application role
and current register authorization for the operation.

The initial browser client uses authorization code with PKCE and a dedicated
Review client registration. The later admin portal is admitted separately to
the same versioned API. Approval and revocation reject app-only tokens and
require a named human with the current `PipelineAdministrator` role. Ordinary
production MFA applies without an action-specific step-up. Exact
authentication strength, device and session policy, private operator path,
WAF rules and limits, capacity, DDoS Network Protection, region, recovery, and
cost remain explicit later values rather than defaults.

Application Gateway was preferred to Front Door Premium because no global or
multi-region public edge is yet required and Front Door does not replace the
private control listener. API Management would add a second proxy behind a WAF
for two first-party APIs whose versioning and authorization already live in the
applications and repository contracts. Direct public Container Apps ingress
would create an edge bypass, while private-only Review access would couple the
first browser and later portal to VPN or proxy integration.

### Evidence and artifacts

**Accepted by ADR 0094: Azure Blob Storage for the primary Evidence Vault and
the separate Recovery Vault.** Both use flat-namespace GPv2 accounts, block
blobs, versioning, change feed, soft delete, locked default version-level WORM
per retention-profile container, exact-version legal holds, infrastructure
encryption, private endpoints, managed identity, and RA-GZRS where the selected
region supports the complete topology.

Recovery accounts live in a dedicated Azure subscription under the existing
Entra tenant and use a different Azure region pair where permitted. Only the
promotion worker can create and verify recovery copies through one explicit
conditional-create, exact-version, read-back, SHA-256, and complete-manifest
protocol. Blob object replication is not an additional copy path, no deletion
propagates between vaults, and no runtime identity can delete versions or
weaken retention.

Azure SQL database ledger digests go to a separate private Azure Confidential
Ledger, not to the ordinary Evidence Vault write boundary. Exact retention
periods, data-location partitions, regions, redundancy exceptions, tiers, copy
and restore objectives, restricted-data encryption profiles, the Management
Register recovery-package format, drill frequency, and measured complete cost
remain open. Local development uses the ignored `var/` adapter and synthetic
fixtures; it cannot attest production immutability, isolation, or regional
recovery.

This Recovery Vault is administratively and regionally isolated, not provider-
or tenant-independent. The accepted Azure-only simplification leaves Azure-
wide and shared-tenant failure as an explicit residual risk.

### Container image supply chain

**Accepted by ADR 0095: one shared Premium Azure Container Registry with
repository ABAC and exact attested image admission.** Premium is required for
the private endpoints already selected under ADR 0092. Public access, the
registry admin user, anonymous pull, catalog access for ordinary identities,
and unconditional application repository roles are disabled.

The registry separates `base/`, `tool/`, `candidate/<application>`, and
`release/<application>`. Each application build identity can read admitted
base and tool inputs and write only its own candidate. A separate image-
admission identity copies the exact OCI graph without rebuilding; a signing
identity signs a passed release digest; a verifier seals its Image Admission
Record; the runtime pull identity reads only the matching release repository;
and the deployment identity updates only the matching Container App.

Notation with one Azure Artifact Signing Private Trust profile is the central
software-release trust root. BuildKit emits in-toto/SLSA provenance. Pinned
Syft emits SPDX JSON, pinned Grype uses an exact database snapshot no more than
24 hours old, and a repository-owned evaluator applies the licence catalogue.
Unknown or incomplete coverage blocks. Critical and known-exploited findings
block; a fixed High blocks and an unfixed High needs an exact expiring
acceptance. Denied licences block and unknown or review-required licences need
an exact authorized decision.

Container Apps images use only
`release/<application>@sha256:<digest>`. A deny-mode Azure Policy enforces the
registry, repository family, and digest reference. Because Container Apps does
not provide the selected AKS-style in-platform Notation admission, the
deployment job repeats signature, signer, timestamp, graph, current scanner,
licence, exception, and policy checks immediately before every deployment or
rollback.

The ACR path is private. Artifact Signing is not claimed to have Private Link;
the isolated signing runner receives only narrowly allowlisted outbound access
to the selected regional signing, Entra, and timestamp endpoints. Trust roots
are admitted and pinned before release. The Private Trust certificate chain,
timestamp, expiry, revocation, and long-term offline verification require an
Azure proof before production signing is enabled.

The complete signed release graph is locked. ACR zone redundancy and geo-
replication protect availability, not backup or replicated deletion. Exact OCI
image-layout packages and all signing, SBOM, provenance, scanner, policy, and
admission evidence therefore go to both ADR 0094 vaults. Automatic retention,
purge, tag age, and repository prefixes are not deletion authority.

### Review surface

**Leading recommendation: a small React and TypeScript client only while the
pipeline is proved.** The durable boundary is the Review Application API. The
later Ask.Legal admin portal calls versioned inspection, comment, rejection,
Approval, and revocation operations without writing the register directly or
receiving promotion credentials. The initial client can then be removed,
absorbed, or retained as an operator fallback.

### Identity, delivery, and observability

ADR 0097's accepted identity and delivery direction is:

- one managed identity per application;
- Azure Key Vault only for third-party secrets that cannot use workload
  identity;
- Bicep as production infrastructure source of truth;
- Azure Pipelines with Entra workload identity federation and separately
  protected deployment identities;
- fresh Microsoft-hosted agents for offline and ARM control-plane stages;
- two stateless private Managed DevOps Pools, one for the ACR supply chain and
  one for Azure SQL migrations; and
- exact operational change packages, external-to-YAML approvals, incremental
  deployment, read-only drift findings, and separately authorized retirement.

Entra identity, separate API resources, the browser PKCE flow, human-only
Approval, and ordinary production MFA are settled by amended ADR 0096. The
single `PipelineAdministrator` role is fixed by decision 2; exact Conditional
Access values remain admission work. The Bicep, workload-
federation, and deployment selection is settled by ADR 0097; exact pool, role,
check, approver, region, and cost values remain implementation and
governance work. ADR 0098 selects the observability and immutable audit-archive
boundary. Only the
Review Application API can create the exact fingerprint-bound legal Approval
artifact; no Azure Pipelines approval can substitute for it.

## Alternatives considered

| Candidate | Reason not selected as backend application language |
|---|---|
| C# on .NET 10 | Strongest compile-time and Azure-native alternative, but adds a third backend ecosystem while Python provides a GA Durable Task SDK and existing organizational capability |
| TypeScript on Node.js | Good browser and JSON ecosystem, but the standalone Azure Durable Task SDK remains Preview and runtime types are erased |
| JavaScript on Node.js | Existing platform experience, but weaker type guarantees and existing in-process cron is not the required durability model |
| Java | Strong types and GA Durable Task SDK, but adds another unsupported organizational ecosystem without a unique benefit |
| Go | Simple and operationally efficient, but lacks the selected first-party Durable Task path and is weaker for the accepted legal-domain contract surface |
| Rust or C/C++ | Useful for narrow native components, but application complexity and low-level risk solve no demonstrated pipeline bottleneck |

C# is the explicit fallback if a Python spike fails a requirement that a .NET
spike passes or Ask.Legal later adopts .NET as a supported backend standard.

## Required local proof before full application scaffolding

Acceptance of ADRs 0089 through 0099 did not itself authorize these spikes.
The user separately authorized the contract, type-boundary, Management
Register, durability, package, image-admission, and architecture spikes on
2026-08-16; all seven are complete:

1. **Contract spike — COMPLETE** — Python 3.14.7 strict raw parsing, a closed
   Draft 2020-12 registry, strict Pydantic binding, JCS, and SHA reproduce every
   current fixture, exact manifested artifact, Node oracle fingerprint, and
   fresh-process result. Ruff, official Pyright strict, and 25 tests pass from
   exact uv and npm locks.
2. **Type-boundary spike — COMPLETE** — repository-wide official Pyright strict
   reports zero diagnostics; the repository checker automatically discovers
   package and application trees and rejects explicit `Any`, bare collection
   annotations, unapproved casts and suppressions, protected infrastructure
   imports, and contract/domain framework leakage. Five casts and one
   dependency diagnostic are exact explained exceptions, and 15 focused tests
   prove all violation families, discovery, configuration, and stale-exception
   rejection as part of the 40-test suite.
3. **Management Register spike — COMPLETE** — digest-pinned SQL Server 2025 CU7
   Developer and `mssql-python==1.12.0` prove exact migration
   packages, stored-procedure capabilities, JCS byte storage, command
   idempotency, concurrent activation and Approval consumption, transactional
   outbox/inbox, ledger verification, deadlock retry, and ambiguous-commit
   recovery; SQLite remains forbidden as a substitute. The ordinary suite has
   46 passing tests and the separately invoked real-engine proof passes.
4. **Durability spike — COMPLETE** — a Python orchestration survives worker
   termination, buffers duplicate human events, deduplicates through a fake
   register, rejects a stale fingerprint, resumes deterministically, and
   produces one effect across a lost activity acknowledgement.
5. **Package spike — COMPLETE** — clean member-specific environments install
   non-editably from the unchanged exact lock with uv network access disabled,
   import only their declared workspace closure, and two path-distinct builds
   produce byte-identical wheels and container-input bundles. The ordinary
   suite has 59 passing tests with three opt-in integrations skipped; the full
   network-disabled package proof passes separately.
6. **Image-admission spike — COMPLETE** — two network-disabled synthetic clean
   builds produce the same OCI digest and result-determining evidence; pinned
   Syft 1.51.0, Grype 0.117.0 with one exact fresh database, ORAS 1.3.3,
   Notation 1.3.2, Buildx 0.36.1, and the repository policy prove SPDX,
   provenance, vulnerability/licence disposition, exact referrer copy,
   test-only signing, recovery, and locked-down runtime behavior. Stale or
   incomplete scan state, KEV/Critical/High/unknown vulnerability outcomes,
   missing licence obligations, mutable or wrong repository references, and
   broad identities fail closed. Two complete executions reproduced the same
   image, normalized evidence, and unsigned candidate graph without Azure.
7. **Architecture spike — COMPLETE** — one closed manifest covers all 5
   declarative application skeletons and 13 shared packages, 70 allowed direct
   dependency edges, and 30 declared capability ports. Repository and
   synthetic tests fail on undeclared future members, metadata/dependency
   drift, imports outside direct boundaries, application dependencies, cycles,
   declaration drift, and exclusive-capability ownership drift. The expanded
   18-member workspace also passes the complete offline package proof.

All inputs remain synthetic and every external effect remains a local fake.

## Production admission values still to populate and prove

- exact Container Apps workload profiles, replica and connection budgets,
  region, zones, hub-and-spoke details, firewall rules, private DNS, service
  levels, recovery, and secure-topology cost;
- exact Application Gateway region, capacity, listener names, certificates,
  WAF rules, exclusions and limits, enhanced DDoS choice, private operator
  network path, cross-region recovery, retention, and complete edge cost;
- exact ACR regions and geo-replicas, retention, recovery objectives, throughput
  and storage, private build and admission runner, Artifact Signing region,
  admitted tool versions, licence catalogue, logging duration, and complete
  image-supply-chain cost;
- exact Evidence Vault and Recovery Vault retention, data-location partitions,
  Azure regions and redundancy exceptions, tiers, recovery objectives,
  database-recovery package, legal-hold and destruction authority, drill
  frequency, capacity, and complete cost;
- named assignments to the `PipelineAdministrator` role, any configured review
  due times, and proved ordinary Conditional Access/device/session conditions;
- infrastructure modules and deployment jobs;
- exact ADR 0098 telemetry categories, table plans, retention, WORM profiles,
  alerts, owners, recovery objectives, Azure DevOps audit proof, capacity, and
  complete observability cost;
- exact Azure OpenAI/Foundry deployed models, versions, geography, SDK/API,
  prompts, embedding dimensions, budgets, evaluations, and admission profiles;
- the measured App Service candidate-slot and sticky/non-sticky configuration
  proof; and
- registered three-character jurisdiction codes and Pinecone project-ID length
validation for ADR 0099's index-name format.

Accepted ADR 0099 and the M2–M7 protocols define how every value is represented
and how missing evidence fails closed. No schema or code supplies an implicit
value.

## Current primary evidence

- [Python 3.14.7 release](https://www.python.org/downloads/release/python-3147/)
- [Durable Task SDK status and features](https://learn.microsoft.com/en-us/azure/durable-task/sdks/)
- [Durable Task Scheduler](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler)
- [Durable Task Scheduler identity and task-hub RBAC](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-identity)
- [Durable Task Scheduler private endpoints](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-private-endpoints)
- [Durable Task orchestration versioning](https://learn.microsoft.com/en-us/azure/durable-task/common/durable-orchestration-versioning)
- [Durable Task Scheduler retention](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-auto-purge)
- [Durable Task Scheduler regional recovery](https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-disaster-recovery-geo-distribution)
- [Temporal Cloud changelog](https://temporal.io/changelog/product-area/cloud)
- [Dapr Workflow](https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-overview/)
- [Pydantic strict mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/)
- [FastAPI request bodies, Pydantic, and OpenAPI](https://fastapi.tiangolo.com/tutorial/body/)
- [FastAPI custom raw request-body handling](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/)
- [FastAPI and Uvicorn deployment](https://fastapi.tiangolo.com/deployment/manually/)
- [Flask async and background-task limits](https://flask.palletsprojects.com/en/stable/async-await/)
- [Pyright configuration and strict mode](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)
- [Ruff linter and formatter](https://docs.astral.sh/ruff/)
- [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [jsonschema Draft 2020-12 and in-memory references](https://python-jsonschema.readthedocs.io/en/stable/referencing/)
- [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [Trail of Bits `rfc8785`](https://trailofbits.github.io/rfc8785.py/)
- [Published `rfc8785` package status](https://pypi.org/project/rfc8785/)
- [pytest parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [Hypothesis property-based testing](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html)
- [Azure SQL ledger overview](https://learn.microsoft.com/en-us/azure/azure-sql/database/ledger-landing?view=azuresql)
- [Azure SQL append-only ledger tables](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-append-only-ledger-tables?view=sql-server-ver17)
- [`mssql-python` production baseline](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/python-sql-driver-mssql-python?view=sql-server-ver17)
- [`mssql-python` transaction management](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/transaction-management?view=sql-server-ver17)
- [`mssql-python` pooling](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/connection-pooling?view=sql-server-ver17)
- [`mssql-python` retry and ambiguous outcomes](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/retry-logic?view=sql-server-ver17)
- [Azure SQL transaction isolation](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql?view=sql-server-ver17)
- [Azure SQL application locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql?view=sql-server-ver17)
- [Azure SQL automated backups and long-term retention](https://learn.microsoft.com/en-us/azure/azure-sql/database/automated-backups-overview?view=azuresql)
- [Azure Blob immutable storage](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview)
- [Azure Blob version-level WORM](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-version-level-worm-policies)
- [Azure Blob object replication](https://learn.microsoft.com/en-us/azure/storage/blobs/object-replication-overview)
- [Azure Storage redundancy](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy)
- [Azure RBAC role-assignment scope](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments)
- [Azure Confidential Ledger](https://learn.microsoft.com/en-us/azure/confidential-ledger/overview)
- [ACR service tiers](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-skus)
- [ACR private endpoints](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-endpoints)
- [ACR repository ABAC](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-abac-repository-permissions)
- [ACR OCI signing](https://learn.microsoft.com/en-us/azure/container-registry/overview-sign-verify-artifacts)
- [Notation with Azure Artifact Signing](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tutorial-sign-verify-notation-artifact-signing)
- [ACR geo-replication](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-geo-replication)
- [BuildKit attestations](https://docs.docker.com/build/metadata/attestations/)
- [Syft SBOM generation](https://oss.anchore.com/docs/guides/sbom/)
- [Grype vulnerability database](https://oss.anchore.com/docs/guides/vulnerability/database/)
- [Container Apps environments](https://learn.microsoft.com/en-us/azure/container-apps/environment)
- [Container Apps networking](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Application Gateway listeners and public/private frontends](https://learn.microsoft.com/en-us/azure/application-gateway/configuration-listeners)
- [Application Gateway v2](https://learn.microsoft.com/en-us/azure/application-gateway/overview-v2)
- [Per-listener Application Gateway WAF policies](https://learn.microsoft.com/en-us/azure/web-application-firewall/ag/per-site-policies)
- [Application Gateway WAF rate limiting](https://learn.microsoft.com/en-us/azure/web-application-firewall/ag/rate-limiting-overview)
- [Microsoft Entra access-token validation](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)
- [Microsoft Entra claims validation](https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation)
- [Microsoft Entra authorization code flow with PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Conditional Access authentication context](https://learn.microsoft.com/en-us/entra/identity-platform/developer-guide-conditional-access-authentication-context)
- [Container Apps user-defined routes](https://learn.microsoft.com/en-us/azure/container-apps/user-defined-routes)
- [Container Apps managed identities](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Container Apps scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Container Apps Jobs and execution overrides](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Durable Task Scheduler private endpoints](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-private-endpoints)
- [App Service plan isolation and billing](https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans)
- [App Service WebJobs](https://learn.microsoft.com/en-us/azure/app-service/webjobs-create)
- [GitHub Actions and Azure OpenID Connect](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)
- [Bicep build and what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if)
- [Azure Pipelines workload identity federation](https://learn.microsoft.com/en-us/azure/devops/pipelines/release/configure-workload-identity?view=azure-devops)
- [Azure Pipelines approvals and checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops)
- [Managed DevOps Pools overview](https://learn.microsoft.com/en-us/azure/devops/managed-devops-pools/overview?view=azure-devops)
- [Managed DevOps Pools architecture](https://learn.microsoft.com/en-us/azure/devops/managed-devops-pools/architecture-overview?view=azure-devops)

## Authorization boundary

Accepted ADRs 0089 through 0099 and this recommendation authorize
documentation only. They do not authorize
scaffolding, migration-runner or
infrastructure implementation, dependency or database installation, external
source access, model or
embedding calls, corpus publication, Azure resource creation, database,
evidence, digest, or backup mutation, Pinecone access, deployment, routing
changes, commits, pushes, or any other external effect. Every operational
capability remains disabled.
