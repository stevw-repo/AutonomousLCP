# M3 Application Interface Protocol

Status: accepted implementation-facing design

Date: 2026-08-16

Closes: `BR-05` and `BR-06`

## 1. Shared HTTP contract

The control-plane and Review APIs expose independent `/api/v1` resources and
independent OpenAPI documents. They have separate Entra audiences, clients,
roles, Application Gateway listeners, CORS policies, database roles, and
Container Apps environments. No endpoint proxies a worker or exposes raw
database access.

Requests use strict JSON media types and bounded raw-byte parsing. Mutating
requests require `Idempotency-Key`, which is the domain `command_id`, and an
`If-Match` aggregate version or immutable fingerprint where concurrency
matters. Success returns the authoritative command result or an immutable read
projection reference.

The stable error envelope contains:

- `error_code`, closed and machine-actionable;
- `message`, safe and non-sensitive;
- `correlation_id` and `command_id` when present;
- `current_version` or current immutable reference when safe;
- `retry_class`: `NEVER`, `SAME_COMMAND_AFTER`, or `QUERY_RESULT`; and
- `details`, a closed per-code object with no stack, SQL, source text, token,
  evidence body, manifest body, or secret.

HTTP status is transport classification. The domain result remains explicit.
Unknown fields, unsupported media types, invalid UTF-8, oversized bodies,
floating references, and wildcard filters fail before command submission.

List reads use opaque continuation tokens bound to one immutable projection
snapshot, filter set, sort order, caller authorization, and expiry. Pages never
mix projection generations. Reads return `ETag` from the exact view version.

## 2. Control-plane API

The private API exposes only these operation families:

| Operation | Authority | Result |
|---|---|---|
| Register, revise, suspend, or inspect a source/endpoint | Named `PipelineAdministrator` | Exact Source Registry command/result |
| Plan, schedule, inspect, or cooperatively cancel a run | Named `PipelineAdministrator` | Pipeline Run command/result |
| Inspect work, observations, gaps, quarantines, capabilities, and coverage | Named `PipelineAdministrator` | Sanitized immutable projections and references |
| Trigger approved bounded reprocessing or reconciliation | Named `PipelineAdministrator` plus the exact entity-specific evidence preconditions | New work item; never mutation of old work |
| Prepare/freeze a proposal package | Named `PipelineAdministrator`; preparation remains effect-free | Exact DSI, Serving State Definition, report, and Promotion Manifest refs |
| Inspect operational reports and recovery readiness | Named `PipelineAdministrator` | Exact report/evidence refs |

It has no Approval, revocation, source-content upload, model, embedding,
Pinecone, backup, routing, or retirement endpoint.

The single human role does not collapse technical authorization. Each command
still requires its exact current aggregate, evidence, capability, and
application-boundary preconditions, and application/workload identities remain
separate.

Manual run requests use the same admission, cutoff, overlap, completeness, and
audit rules as scheduled runs. There is no `force`, `skip`, or arbitrary
workflow endpoint.

## 3. Review API

The public Review API exposes:

- list review-ready proposal packages using snapshot-bound pagination;
- retrieve the exact manifest summary, machine manifest reference, diff,
  evidence inventory, coverage/gap view, recovery proof, validations, cost,
  ordered actions, and report sections;
- retrieve a bounded exact evidence artifact through an authorization-checked,
  audited stream; raw vault coordinates are never returned;
- append a reviewer comment bound to one manifest fingerprint and review
  section;
- approve or reject one exact manifest;
- revoke an unconsumed Approval; and
- inspect immutable decision and lifecycle history.

The exact human role is `PipelineAdministrator`. Multiple named people may
receive it. Approval, rejection, and revocation require a delegated named-human
token and current register authorization; no action-specific step-up freshness
test applies. App-only tokens cannot perform them. The caller cannot edit,
upload, substitute, or partially approve any manifest artifact.

The later Ask.Legal admin portal is a separately registered client of this
same API. Integration changes no endpoint semantics or authority boundary.

## 4. Proposal preparation ownership

The control plane owns the `proposal_package_prepare` capability. It may depend
on the framework-free corpus and promotion packages plus read-only evidence and
register ports. Those pure services validate and compose immutable proposal
artifacts but have no provider or production credentials.

The legal-processing worker freezes candidate releases. The control plane
selects complete releases, builds DSIs, composes the candidate Serving State
Definition, review report, and Promotion Manifest, and records `REVIEW_READY`.
The Review API reads and decides. The promotion worker has
`approved_manifest_read` only and must not expose or import a preparation
command.

Before runtime implementation, the architecture manifest must therefore:

- add `asklegal-corpus`, `asklegal-promotion`, and the required read-only
  evidence boundary to the control plane;
- add `proposal_package_prepare` exclusively to the control plane;
- keep production mutation capabilities exclusively on the promotion worker;
  and
- re-run dependency, import, cycle, capability, package, and image proofs.

## 5. Process and configuration contract

Every application starts only after validating one exact configuration bundle
containing application identity, environment, build, contract set, policy
profiles, register view/procedure set, task hub when applicable, network
destinations, secret references, limits, and logging policy. Unknown settings,
missing required settings, raw secrets in configuration, or a configuration
fingerprint mismatch prevent readiness.

The APIs provide separate internal liveness and readiness probes. Liveness
proves only that the process loop responds. Readiness proves configuration is
valid and required local adapters can perform bounded non-mutating checks. It
reveals no versions, topology, credentials, source state, or legal data.

The three workers have no HTTP ingress. Each:

- uses its own managed identity, task hub, register role, vault role, network
  allow-list, and secret namespace;
- claims work with a lease generation and fencing token;
- stops taking new work on shutdown, renews or relinquishes claims safely,
  completes only bounded atomic work, and records interruption;
- caps concurrency, payload, retry, and shutdown time from an exact profile;
- treats configuration change as a new revision and never mutates the meaning
  of an in-flight work item; and
- logs only correlation IDs, closed results, sizes, counts, and latency.

Startup never runs migrations. A separate deployment identity applies exact
forward-only migrations before a compatible application revision is admitted.

## 6. Local adapters and browser client

M3 supplies local fake identity, register, task-hub, vault, source, model,
embedding, target, backup, and routing ports as needed for startup tests. Fakes
implement the same failure and idempotency contracts; they do not weaken
authorization or return implicit success.

The minimal browser client uses authorization code with PKCE, keeps bearer
tokens out of application-controlled persistent storage, uses only the Review
audience, renders immutable evidence/diff/report views, and has no hidden
control or production operation.

## 7. Required M3 proof

Tests must prove independent startup; exact OpenAPI stability; wrong audience,
role, client, token type, origin, media type, size, version, and idempotency
rejection; stable pagination; forged proxy-header rejection; redaction;
graceful shutdown; stale fencing; configuration drift; worker no-ingress; and
the mechanically enforced proposal-preparation ownership.

This document is design authority only and grants no implementation,
deployment, or external-effect authorization.
