---
status: accepted
date: 2026-08-15
refines:
  - "0001"
  - "0006"
  - "0007"
  - "0009"
  - "0088"
  - "0089"
  - "0090"
  - "0091"
  - "0092"
---

# Use managed Durable Task Scheduler for workflows

## Decision

The pipeline uses Microsoft's generally available standalone Python Durable
Task SDK with managed Azure Durable Task Scheduler for durable execution. The
control plane, acquisition worker, legal-processing worker, and promotion
worker remain ordinary Python processes hosted on Azure Container Apps. They
do not run inside the Azure Functions host.

Durable Task Scheduler owns only operational orchestration state: execution
history, deterministic replay, durable timers and waits, retries, activity
dispatch, external-event delivery, and lifecycle operations. The Management
Register remains authoritative for business and legal state, work admission,
capabilities, source and evidence bindings, Approval, promotion admission,
Serving State, and immutable audit facts. Scheduler state can never prove that
an Approval exists or that an external effect is permitted.

This is a production-target decision, not an instruction to develop directly
in Azure. The ordinary development path uses the local Durable Task Scheduler
emulator, synthetic fixtures, local stores, and fake effects. Azure resources,
dependencies, identities, private endpoints, and operational activation remain
separately gated.

## Scheduler and task-hub topology

Production begins with two scheduler resources:

| Scheduler | Task hubs | Network reachability |
|---|---|---|
| General pipeline scheduler | One task hub each for the control plane, acquisition worker, and legal-processing worker | Separate private endpoints or approved private paths from those three application environments |
| Promotion scheduler | One promotion task hub | Private path from the promotion environment only; no control-plane, review, acquisition, or legal-processing application path |

The Review Application API has no task hub and no Scheduler data-plane role.
It records an exact approval, rejection, comment, or revocation command in the
Management Register. A control-plane dispatcher later observes the resulting
register outbox fact and raises only the corresponding opaque event into the
control-plane task hub.

Sharing the general scheduler is a cost and operational optimization, not a
merge of application authority. Each application has its own task hub and a
task-hub-scoped role. Task hubs do not call activities or child orchestrations
in another task hub. The scheduler's public network path is disabled after its
private endpoints and DNS are proved. A private endpoint applies to every task
hub in its scheduler, so network reachability is never treated as authorization.

The promotion scheduler is a separate resource because production mutation is
the highest-risk capability. No other runtime identity or application subnet
can query, signal, pause, terminate, restart, or create promotion
orchestrations. Scheduler or task-hub sharing must never give the control plane
an indirect way to operate promotion code or credentials.

The general scheduler's three task hubs share scheduler capacity and retention
configuration. Load, retention, incident-isolation, or service-level evidence
may require splitting them into separate scheduler resources later. That split
does not change the application contracts or permit a shared task hub. The
selected SKU, capacity units, region, and exact retention days remain measured
operations decisions.

## Identity and command boundary

Each durable application uses its own user-assigned runtime managed identity.
It receives `Durable Task Data Contributor` only on its own task hub because
the same application contains both a narrow dispatcher client and the workers
that process its orchestrations and activities. It receives no Scheduler-level
role and no role on another task hub. A future worker-only deployment may use
the narrower `Durable Task Worker` role.

Cross-application work is handed off only through the Management Register:

1. one application commits an exact fingerprint-bound command and outbox fact;
2. the receiving application's dispatcher claims only its owned pending fact;
3. it starts an orchestration in its own task hub using the register-issued
   execution ID as the idempotent instance identity;
4. it records the exact scheduling result; and
5. duplicate or ambiguous scheduling outcomes are reconciled by the instance
   ID and immutable command result before retry.

No distributed transaction spans Azure SQL and Durable Task Scheduler. A
scheduler call that succeeds while result recording fails is safe to repeat
only because the instance ID, command ID, input fingerprint, inbox claim, and
orchestration-start result are exact and idempotent.

Human users and ordinary operators receive no production dashboard role. The
Azure dashboard requires `Durable Task Data Contributor` and can inspect
payloads, create orchestrations, raise events, and pause, resume, or terminate
instances. Production dashboard access is therefore task-hub-scoped,
time-bound break-glass access with independent authorization and immutable
audit, not the review interface or ordinary monitoring path.

## Determinism and effect rules

Orchestrator functions contain deterministic coordination only. They may use
the SDK's replay-safe orchestration context, schedule activities and child
orchestrations, wait for durable timers or external events, combine tasks, and
continue as new. They must not directly use network, database, filesystem,
clock, randomness, model, source, embedding, Pinecone, backup, or routing APIs.

Activities and adapters perform effects. Every activity assumes at-least-once
delivery and is idempotent, retryable, fingerprint-bound, and safe after
worker termination.
Immediately before an effect, it rechecks the exact register command,
execution lineage, capability, expected state, and any Approval or promotion
lock required by that effect. Scheduler delivery or prior activity success
does not waive those checks.

External events contain an opaque register event ID and exact fingerprint.
The orchestrator or an activity resolves the authoritative fact from the
register and rejects duplicates, stale events, changed fingerprints, or events
for the wrong execution lineage. Review Application input never becomes a
trusted Scheduler event merely because it was delivered successfully.

## History and payload boundary

Scheduler history is operational and inspectable. It must contain only small
opaque IDs, fingerprints, closed reason or result codes, bounded counters, and
sanitized status. It must not contain:

- source or legal text;
- evidence or release bytes;
- prompts, model inputs, model outputs, or provider responses;
- Approval documents or unbounded reviewer comments;
- secrets, credentials, tokens, connection strings, or private URLs;
- raw exception messages or stack traces that can include protected data; or
- a payload presented as the authoritative business record.

The initial design boundary imposes a 64 KiB serialized ceiling on every
orchestration input or output, activity input or output, external event, and
custom-status value, even though the managed service currently allows up to
1 MB. Larger values are stored in the Evidence Vault, artifact store, or
Management Register and referenced by opaque ID plus fingerprint. The exact
contract may set lower limits for individual message types.

Terminal Scheduler history is purged under an explicit policy. Durable Task
Scheduler currently defaults to 30 days, permits at most 90 days, and applies
one retention policy to every task hub in a scheduler. That history is not the
audit, backup, evidence, or disaster-recovery record. Business events,
execution lineage, exact command results, effect receipts, and required
diagnostic evidence are persisted through their authoritative stores before
history can be purged. Preview history export is not a recovery dependency.

## Workflow versioning and deployment

Every orchestration instance is permanently bound to an explicit workflow
definition version. The Management Register records that version together
with the exact application build, configuration, contract, and input
fingerprints. Starting an instance without an explicit admitted version is
forbidden.

Existing version branches are immutable and remain available while any
instance can replay them. A new Container Apps revision may process current or
older versions only when it contains every older deterministic branch and
passes replay tests against preserved histories. A breaking change that cannot
retain those branches requires a separately isolated compatibility worker or a
controlled replacement procedure; it must not strand or silently reinterpret
in-flight work.

Long-running loops use `continue-as-new` before history becomes operationally
large. Deployment tests cover worker termination, revision replacement,
duplicate activity delivery, duplicate and early external events, stale
fingerprints, nondeterministic code changes, old-version replay, and history
growth.

## Failure and disaster recovery

Worker or Container Apps failure is the normal durable-execution case: the
managed Scheduler retains history and re-dispatches work after a compatible
worker reconnects. This behavior does not remove the need for idempotent
activities or register-owned effect receipts.

Durable Task Scheduler does not currently move in-flight orchestration state
to a scheduler in another region. Microsoft's recommended regional design uses
a separate scheduler per region; existing primary-region instances remain
paused and unavailable until that region returns. The design therefore makes
no claim of seamless in-flight regional failover.

A regional recovery may start replacement work only after an independently
authorized procedure:

1. fences the old region and execution lineage in the Management Register;
2. prevents its identities from performing further effects;
3. reconciles every possible external effect from immutable receipts and
   provider state;
4. identifies one exact safe business checkpoint;
5. creates a new recovery execution lineage in the secondary region; and
6. ensures a recovered old orchestration fails its register lineage and
   capability checks if it later resumes.

Promotion recovery additionally revalidates the exact Approval, frozen
manifest, target, Serving State, backup and rollback evidence, and promotion
lock. Scheduler history alone is never copied or interpreted as permission to
repeat a production action. Exact recovery-time and recovery-point objectives,
paired regions, failover triggers, and drill frequency remain policy choices.

## Local and Azure proof boundary

The local emulator is intentionally used for fast deterministic development,
orchestration behavior, activity retry, external-event, version, history, and
worker-termination tests. It stores state in memory and has no managed
identity, RBAC, private endpoint, Azure capacity, retention service, or
regional recovery behavior. Stopping the emulator is therefore not a valid
test of Scheduler persistence or Azure disaster recovery.

Separately authorized non-production Azure proofs must establish:

- Python SDK and Container Apps gRPC connectivity;
- user-assigned managed identity and task-hub-scoped positive and negative
  access;
- the two-scheduler private-endpoint and private-DNS topology with public
  access disabled;
- worker termination, reconnect, checkpoint, retry, and revision behavior;
- dashboard and break-glass restrictions;
- retention and purge behavior;
- capacity, throttling, noisy-neighbor, latency, and complete secure-topology
  cost;
- regional outage and fenced replacement-run procedures; and
- exact observability without protected payload leakage.

No Azure proof authorizes source access, model or embedding calls, production
credentials, promotion, routing, or other external effects.

## Alternatives considered

| Alternative | Assessment |
|---|---|
| Durable Functions with Durable Task Scheduler | Provides the same core durable model, but couples each worker to the Azure Functions host, trigger, binding, scaling, and deployment model. The accepted applications are ordinary Python processes on Container Apps and need no Functions-only trigger. |
| Temporal Cloud | A mature and credible workflow platform with strong Python, versioning, visibility, and high-availability features. Temporal Cloud on Azure is currently invite-only pre-release, so it would add a pre-release, third-party central dependency and an unresolved Azure private-connectivity and commercial boundary. Reconsider if that offering becomes generally available and proves a material requirement the selected service cannot meet. |
| Self-hosted Temporal | Technically capable, but makes Ask.Legal operate and recover Temporal services, persistence and visibility databases, schema upgrades, security, monitoring, and multi-cluster replication. That operational burden is not justified while a managed Azure service meets the accepted requirements. |
| Dapr Workflow | Supports deterministic workflows, durable timers, retries, child workflows, external events, lifecycle operations, and Python. It also introduces Dapr sidecars, actor placement, component configuration, and a strongly consistent transactional actor state store. Its multi-application workflow requires a shared namespace and state store, which conflicts with the accepted capability boundaries; separate app workflows would add that platform without a unique benefit. |
| Service Bus, Celery, Redis, Kafka, or a SQL-backed custom state machine | Useful messaging or job tools, but not a complete substitute for deterministic replay, durable human waits, workflow versioning, fan-out and joins, history management, and safe recovery. Building those semantics here would create a second, security-critical workflow platform. A later measured transport need may add a narrow queue without making it authoritative. |

## Consequences

- Long-running coordination is expressed as typed deterministic Python code
  without coupling workers to Azure Functions.
- The managed service removes a self-operated workflow database and control
  plane, but its billing, quotas, retention, regional behavior, and operational
  availability remain dependencies that must be tested.
- Task-hub RBAC and a separate promotion scheduler preserve application
  authority even though three low-production-capability hubs share a general
  scheduler resource.
- Register-mediated handoff is more explicit than one end-to-end shared
  orchestration, but it prevents a worker identity from processing activities
  belonging to another security boundary.
- The 64 KiB internal payload ceiling and no-sensitive-history rule require
  reference-based data flow through the Register and Evidence Vault.
- A regional Scheduler outage can pause in-flight work. Safe replacement is a
  fenced business-recovery operation, not automatic history failover.
- Exact Scheduler SKU, capacity, retention days, region, recovery objectives,
  and cost remain open until evidence permits them to be selected.

## Current primary references

- [Durable Task SDK overview](https://learn.microsoft.com/en-us/azure/durable-task/sdks/durable-task-overview)
- [Choose the Durable Task hosting model](https://learn.microsoft.com/en-us/azure/durable-task/common/choose-orchestration-framework)
- [Durable Task on Azure Container Apps](https://learn.microsoft.com/en-us/azure/azure-functions/durable/scenario-build-serverless-workflow)
- [Durable Task Scheduler](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler)
- [Managed identity and task-hub RBAC](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-identity)
- [Private endpoints](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-private-endpoints)
- [Orchestration versioning](https://learn.microsoft.com/en-us/azure/durable-task/common/durable-orchestration-versioning)
- [Autopurge retention](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-auto-purge)
- [Dashboard permissions and operations](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-dashboard)
- [Durable Task Scheduler disaster recovery](https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-disaster-recovery-geo-distribution)
- [Temporal Cloud changelog](https://temporal.io/changelog/product-area/cloud)
- [Self-hosting Temporal](https://docs.temporal.io/self-hosted-guide/deployment)
- [Dapr Workflow features](https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-features-concepts/)
- [Dapr multi-application workflows](https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-multi-app)
- [Dapr workflow versioning](https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-versioning/)
