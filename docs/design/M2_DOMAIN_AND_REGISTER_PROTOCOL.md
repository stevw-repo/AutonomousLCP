# M2 Domain and Management Register Protocol

Status: accepted implementation-facing design

Date: 2026-08-16

Closes: `BR-01` through `BR-04`

## 1. Boundary

This protocol fixes the framework-free domain and authoritative persistence
behavior needed by every application. JSON Schemas remain normative at system
boundaries; Python domain types implement these rules without importing
FastAPI, SQL, Durable Task, Azure, or provider libraries.

The Management Register is authoritative for business facts, commands,
lifecycles, effect authority, and receipts. Durable Task owns resumable
coordination history only. Neither an API response, queue delivery, Scheduler
history, projection, log, or remote-provider response may replace a register
fact.

## 2. Common operation contracts

All four objects are immutable strict I-JSON and fingerprinted from RFC 8785
JCS bytes. IDs are register-issued and never content-derived.

### Command Envelope

Required fields:

| Field | Rule |
|---|---|
| `command_id` | One stable idempotency identity, allocated before submission |
| `command_type` and `contract_version` | Closed registered command and exact schema version |
| `target_ref` | Exact aggregate identity; fingerprint included when the command is bound to an immutable definition |
| `expected_version` | Non-negative aggregate version or explicit `ABSENT`; never omitted |
| `actor_ref` and `authority_ref` | Stable caller identity and exact current authorization evidence |
| `causation_ref` | Immediate command/event/work item that caused this command |
| `correlation_id` | One complete pipeline-run correlation identity |
| `execution_lineage_ref` | Required for retries, effects, and promotion; otherwise explicit `NONE` |
| `input_refs` | Sorted exact immutable inputs and fingerprints |
| `policy_profile_refs` | Exact configured policy profiles; no floating default |
| `configuration_ref`, `contract_set_ref`, `build_ref` | Exact non-secret execution definitions |
| `submitted_at` and `expires_at` | UTC times; expiry is mandatory for authority-bearing commands |
| `payload` | Closed command-specific object; never legal/evidence bytes when a reference suffices |

The canonical command fingerprint excludes transport metadata and includes all
fields above. The same `command_id` with the same fingerprint is an exact
replay. The same ID with different bytes is `COMMAND_ID_CONFLICT` and can never
execute.

### Command Result

Every accepted submission produces one durable result retrievable by
`command_id`:

- `APPLIED` — one transaction appended the declared facts;
- `EXACT_REPLAY` — the original result is returned byte-for-byte;
- `REJECTED_STALE_VERSION` — expected aggregate version did not match;
- `REJECTED_INVALID_STATE` — the closed lifecycle forbids the command;
- `REJECTED_INVALID_INPUT` — schema, reference, fingerprint, or invariant failed;
- `REJECTED_UNAUTHORIZED` — current exact authority did not permit it;
- `REJECTED_EXPIRED` — command or bound authority expired;
- `REJECTED_CONFLICT` — another single-winner fact already exists;
- `REJECTED_CAPABILITY` — required capability was absent, suspended, or revoked; or
- `INDETERMINATE` — returned only by an adapter that could not yet resolve a
  transport failure; callers must query the register and must not resubmit a
  different command.

Applied and rejected business results are immutable. Transient transport
errors are not business results.

### Effect Intent

An effect intent is appended in the same transaction as the business fact that
authorizes it. It binds:

- intent ID, closed effect type, owning application, aggregate and command;
- execution lineage and permitted checkpoint;
- exact immutable inputs and effect-command fingerprint;
- required capability and current capability-profile reference;
- destination class, with secret destination coordinates resolved only inside
  the owning adapter;
- retry class, attempt ceiling, deadline, and stop conditions;
- expected remote precondition and exact success postcondition; and
- compensation or `NO_COMPENSATION`, never an improvised rollback.

Creating an intent is not performing an effect. Only the exclusive owner may
claim it.

### Effect Receipt

Every attempt appends a sanitized attempt event. Exactly one terminal receipt
is selected for an intent:

- `SUCCEEDED`, including the exact remote identity/version, request ID,
  response fingerprint, postcondition evidence, and observed time;
- `FAILED_FINAL`, including a closed failure code and evidence;
- `CANCELLED_BEFORE_EFFECT`; or
- `OUTCOME_UNKNOWN`, which blocks dependent work until reconciliation proves
  success or safe retry.

The adapter must query by its stable idempotency key or verify the declared
postcondition before retrying after a lost acknowledgement. Raw remote bodies,
legal text, tokens, and secrets never enter the receipt.

## 3. Aggregate and transaction catalogue

Each aggregate has one write owner. Other applications receive exact commands,
read views, or immutable references.

| Aggregate | Write owner | Principal commands | Transaction appends |
|---|---|---|---|
| Source Registry | Control plane | register/revise/suspend source or endpoint | definition event, impact declaration, outbox |
| Pipeline Run | Control plane | schedule/start/cancel/finish run | run event, work admissions, outbox |
| Observation and Snapshot registration | Acquisition worker | start/complete/fail observation; register snapshot | observation event, evidence refs, coverage consequence, outbox |
| Legal processing | Legal-processing worker | admit/decide/quarantine/freeze candidate | decision, rule trace, candidate refs, gap/review records, outbox |
| Corpus and proposal package | Control plane | select releases, freeze DSI, definition, report, manifest | immutable refs, validation facts, review-ready event |
| Review record | Review API | comment/approve/reject/revoke/resolve assigned review | authenticated human fact, lifecycle event, outbox when applicable |
| Promotion execution | Promotion worker | authorize/start/checkpoint/succeed/fail/rollback | execution event, effect intents/receipts, serving lifecycle event |
| Capability and workflow admission | Named system owner plus Legal Desk where required | attest/activate/suspend/revoke | immutable profile/attestation and lifecycle event |

One command transaction performs only: inbox claim, invariant checks,
authoritative fact/event append, outbox append, projection update, and immutable
result. It performs no network, filesystem, model, source, vault, Pinecone,
backup, or routing effect.

Every aggregate increments a monotonic integer version exactly once per applied
command. Single-winner constraints cover at least source-version activation,
one active capability profile per scope, one current Approval per manifest,
Approval consumption, one active Serving State per environment, outbox claim,
and exact retirement.

## 4. Inbox, outbox, claims, and projections

- Inbox uniqueness is `(owning_application, command_id)` plus command
  fingerprint. A fingerprint mismatch is permanent conflict.
- Outbox rows contain only intent/work references and sanitized routing data.
- A claim is a renewable lease with claimant identity, generation, expiry, and
  monotonically increasing fencing token. An expired claimant cannot complete
  using an old token.
- Dispatch acknowledgement records the exact Scheduler instance or receiving
  command. Lost acknowledgement is reconciled by that stable identity.
- Projections are disposable, versioned, rebuildable from immutable facts, and
  carry a checkpoint and source-event fingerprint. They are never authority.
- Recovery exports contain schema/migration set, append-only facts, command
  results, outbox/inbox state, current policy/capability definitions, projection
  checkpoints, and an external digest. Restore rebuilds projections and proves
  the digest before reopening writes.

## 5. Pipeline Run lifecycle

The run is one observation-cutoff-bound coordination aggregate.

`contracts/transitions/pipeline-run.json` is the normative closed-world
machine. Its exact versioned edges and guard preconditions take precedence over
the readable summary below.

States:

`RUN_PLANNED → RUN_ADMITTED → RUN_ACTIVE → RUN_AWAITING_REVIEW →
RUN_APPROVED → RUN_PROMOTING → RUN_SUCCEEDED`

Terminal alternatives are `RUN_NO_CHANGE`, `RUN_REJECTED`, `RUN_CANCELLED`,
`RUN_BLOCKED`, `RUN_FAILED`, and `RUN_ROLLED_BACK`.

Rules:

- planning binds the complete Source Registry, Release Scope Registry,
  contracts, configuration, build, and observation cutoff;
- admission proves no incompatible active run for the same target/cutoff range;
- cancellation is cooperative and can stop only work that has not crossed an
  irreversible effect checkpoint;
- before promotion, `RUN_BLOCKED` means potentially correctable but terminal
  work requiring a new linked/rebased run, `RUN_CANCELLED` requires a named
  `PipelineAdministrator` and no irreversible checkpoint, `RUN_FAILED`
  requires a non-retryable failure or exhausted permitted attempts, and
  `RUN_REJECTED` is human-rejection-only;
- after `RUN_PROMOTING` starts, ordinary cancellation and terminal blocking are
  forbidden. An unknown effect outcome remains `RUN_PROMOTING` under fencing
  and reconciliation, then resolves only to verified success, verified
  approved rollback, or proved final failure;
- no-change requires complete admitted observations and accounting; absence of
  work is not no-change;
- review is entered only after one complete proposal package is frozen;
- approval does not itself start production; it enables a separately recorded
  promotion admission command; and
- every terminal state references exact reports and unresolved gaps.

Overlapping acquisition for different scopes may run concurrently. Two runs
may not prepare or promote competing desired states for the same environment
and base Serving State. The later run remains `RUN_BLOCKED` or is rebased into
a new immutable run after the earlier one finishes.

## 6. Work Item lifecycle

`contracts/transitions/work-item.json` is the normative closed-world machine.

Every cross-application unit follows:

`WORK_PLANNED → WORK_DISPATCHED → WORK_RUNNING → WORK_SUCCEEDED`

Terminal alternatives: `WORK_NO_CHANGE`, `WORK_BLOCKED`, `WORK_QUARANTINED`,
`WORK_CANCELLED`, and `WORK_FAILED_FINAL`.

`WORK_RETRY_WAIT` is non-terminal and returns to `WORK_DISPATCHED` with the
same work identity and immutable inputs. A changed input creates a new linked
work item. Every attempt binds the workflow version, build, configuration,
contract set, inputs, and fencing token. Scheduler replay cannot change them.

A work attempt counts only after processing enters `WORK_RUNNING`. Delivery
retry keeps the item `WORK_DISPATCHED`, reuses one stable dispatch identity,
and consumes no processing-attempt allowance; direct
`WORK_DISPATCHED → WORK_RETRY_WAIT` is forbidden. Operator views group the
detailed states as Completed (`WORK_SUCCEEDED`, `WORK_NO_CHANGE`), Needs
follow-up (`WORK_BLOCKED`, `WORK_QUARANTINED`), Stopped (`WORK_CANCELLED`,
`WORK_FAILED_FINAL`), and Retrying (`WORK_RETRY_WAIT`). Terminal items never
reopen.

## 7. Review, Coverage Gap, and Quarantine lifecycles

The generic two-state foundation machine is retained only as its historical
base. M2 implements three entity-specific immutable record families.
`contracts/transitions/source-contract-review.json`,
`contracts/transitions/coverage-gap.json`, and
`contracts/transitions/quarantine.json` are their normative closed-world
machines.

### Source Contract Review

`OPEN → RESOLVED_SUPPORTED | RESOLVED_CHANGED | RESOLVED_UNSUPPORTED |
SUPERSEDED`

A resolution names the exact source-contract version and consequence. A later
recurrence creates a new linked review; a closed record is never reopened.

### Coverage Gap

`OPEN → MITIGATED_CARRY_FORWARD | MITIGATED_WITHHOLDING |
RESOLVED_COMPLETE | SUPERSEDED`

Mitigated is not resolved. It remains user-visible until a later complete
release proves the gap closed. Every state names affected scopes, evidence,
severity, assigned administrators, optional due time, and serving consequence.
The same unresolved gap may switch directly between carry-forward and
withholding only when its identity and affected scope are unchanged and a new
authenticated administrator decision with exact evidence exists.

### Quarantine

`OPEN → RELEASED_TO_REPROCESSING | PERMANENTLY_EXCLUDED | SUPERSEDED`

Release never makes the old candidate searchable. It authorizes a new linked
work item to re-enter all deterministic and legal gates. Permanent exclusion
requires an exact Legal Desk decision and complete accounting. Recurrence
creates a new quarantine record.

Notification and optional-due-time events append without changing legal status
or silently releasing work.

Across all three record families, terminal records never reopen. A material
subject, scope, or definition change supersedes only a non-terminal record and
creates one new linked `OPEN` replacement. Recurrence after terminal closure
creates a new linked `OPEN` record without mutating its predecessor.

## 8. Durable Task ownership

Durable orchestrators may schedule activities, wait, retry allowed failures,
and emit register commands. They may not decide legal status, Approval,
capability, desired state, effect success, or serving state. External events
carry only immutable register references. Each activity re-reads current
authority and fencing state immediately before any effect.

On Scheduler loss, recovery fences the old lineage, reconciles every effect
intent and receipt, imports one verified register recovery package, and starts
a new linked lineage at an explicitly safe checkpoint. Scheduler history is
never treated as the recovered audit record.

## 9. Required M2 proof

Implementation may claim this protocol only when tests prove every listed
transition plus exact replay, conflicting replay, stale version, concurrent
winner, expired lease, stale fence, deadlock retry, ambiguous commit, lost
acknowledgement, projection rebuild, digest failure, recovery replay, overlap,
cancel-before-effect, cancel-after-effect, recurrence, and re-entry behavior.

This document is design authority only and grants no implementation or
external-effect authorization.
