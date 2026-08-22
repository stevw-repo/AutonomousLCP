# M7 End-to-End Conformance Plan

Status: accepted implementation-facing design

Date: 2026-08-16

Closes: `BR-12`

## 1. Proof boundary

M7 proves the complete pipeline offline with the reserved `ZZZ` synthetic
Legal Desk package, local fakes, deterministic clocks/randomness, and no
external credentials or network. It proves platform behavior, not real legal
coverage, provider quality, Azure behavior, Pinecone behavior, or production
admission.

One clean command must build the local state and one command must run any named
scenario:

```text
uv run asklegal-local reset --exact-test-state
uv run asklegal-local prove --scenario <scenario-id>
uv run asklegal-local prove --all
```

The implementation may choose the executable package location, but these CLI
semantics and scenario IDs are stable acceptance interfaces. `reset` may
delete only the exact ignored synthetic test root after checking its marker and
resolved path; it never targets the repository or home directory.
`prove` never resets implicitly. If its exact marked root contains prior or
partial proof output, it returns `SYNTHETIC_STATE_RESET_REQUIRED`; the operator
must invoke the explicit exact-state reset before retrying.

## 2. Reproducibility envelope

Every scenario binds:

- Python/tool/dependency locks and all 19 current workspace member builds;
- contract set, six protocol versions, synthetic rulebook, configuration,
  governance, embedding, target, and clock profiles;
- initial register recovery package and primary/recovery fake-vault state;
- exact input fixture package and expected-result package;
- deterministic UTC clock schedule, UUID/ID allocation stream, jitter stream,
  and task delivery schedule; and
- expected artifacts, register facts/projections, effects, reports, logs, and
  terminal state.

Two path-distinct clean executions must produce byte-identical authoritative
artifacts and equivalent register facts after excluding declared incidental
process/transport values. Every exclusion is named and cannot affect a
fingerprint, decision, effect, or report.

## 3. Golden successful flow

`E2E-001` proves:

1. schedule one complete run and freeze its cutoff/configuration;
2. observe a changed synthetic source;
3. preserve complete bytes in primary and recovery fake vaults;
4. apply the active synthetic rulebook and create evidence-bound candidates;
5. account for every synthetic source item and Release Scope;
6. freeze Corpus Releases, DSI, traceability, coverage, Serving State
   Definition, report, and Promotion Manifest;
7. inspect exact artifacts and approve through the Review API/client;
8. create deterministic fake embeddings and a replacement fake target;
9. verify the complete target, backup, recovery readiness, and routing
   candidate;
10. activate one complete routing generation, run post-cutover queries, and
    report success; and
11. reverse-swap to the predecessor, verify rollback, then recover the approved
    candidate from preserved artifacts without changing its definition.

Expected terminal results include one consumed Approval, one successful
execution lineage, exact effect receipts, no unowned target records, one
active Serving State at each point, and complete record-to-evidence traceability.

## 4. Required scenario matrix

| ID | Condition | Exact expected result |
|---|---|---|
| `E2E-002` | Complete supported no-change observation | `RUN_NO_CHANGE`; no scraper/model/embed/promotion intent |
| `E2E-003` | Watcher false positive, full capture unchanged | Preserved capture; `SUPPORTED_NO_CHANGE_AFTER_CAPTURE`; no candidate promotion |
| `E2E-004` | Duplicate command and duplicate Scheduler delivery | Original result/receipt returned; one business fact and one effect |
| `E2E-005` | Process restart before an effect | Same work/lineage resumes from register state |
| `E2E-006` | Lost effect acknowledgement | Reconciliation proves one effect; one terminal receipt |
| `E2E-007` | Same command ID with changed bytes | Permanent `COMMAND_ID_CONFLICT`; no effect |
| `E2E-008` | Stale aggregate version or fencing token | Exact stale rejection; winner unchanged |
| `E2E-009` | Overlapping proposal/promotion for same base | Later run blocked or rebased; never two active states |
| `E2E-010` | Cancellation before irreversible effect | Cooperative terminal cancellation; preserved evidence |
| `E2E-011` | Cancellation after promotion starts | Stop/recovery path; never ordinary cancellation |
| `E2E-012` | Partial, unstable, or missing source capture | No snapshot admission; gap/review path; no processing |
| `E2E-013` | Hostile source instructions/archive/path | Isolated evidence and closed failure; no execution of content |
| `E2E-014` | Unknown source semantics | Source Contract Review; affected scope blocked |
| `E2E-015` | Ambiguous/non-total rulebook | Quarantine or block; no guessed legal result |
| `E2E-016` | Coverage Gap with allowed carry-forward | Explicit warning and optional administrator-set due time; old release selected exactly |
| `E2E-017` | Evidence-backed withholding | Complete Withholding Release; exact reviewed removals only |
| `E2E-018` | Quarantine resolution and recurrence | New reprocessing work/new linked quarantine; old facts immutable |
| `E2E-019` | Manifest changes after review display | Decision rejected as stale; new package required |
| `E2E-020` | Missing administrator permission or app-only decision token | Decision rejected; no Approval fact |
| `E2E-021` | Approval is revoked, administrator permission is removed, or bound manifest becomes invalid | Promotion admission fails before first effect |
| `E2E-022` | Approval reused by another lineage | Single-consumption conflict; original lineage only |
| `E2E-023` | Partial embedding batch or wrong dimension | Candidate target fails; production unchanged |
| `E2E-024` | Unknown or extra fake target record | Verification blocks activation and deletion |
| `E2E-025` | Cost/quota limit reached | Stop at declared checkpoint; no truncation or broadened retry |
| `E2E-026` | Recovery copy/backup/read-back failure | No first production effect or cutover |
| `E2E-027` | Base Serving State/routing drift | Approval invalidated; competing state remains active |
| `E2E-028` | Coverage manifest missing or fingerprint-invalid | Activation blocked; cached-current runtime fallback proved |
| `E2E-029` | Post-cutover query regression | Exact reverse-swap rollback and incident report |
| `E2E-030` | Management Register recovery | Digest verified, projections rebuilt, effects reconciled, new fenced lineage |
| `E2E-031` | Attempted wildcard/broad deletion | Port/schema rejection before effect intent |
| `E2E-032` | Synthetic package used outside local environment | Package admission failure |

Each row has at least one positive fixture and, where a near miss could pass
incorrectly, one paired negative fixture differing by the minimum decisive
fact.

## 5. Expected-result package

Every scenario inventories:

- input artifacts and hashes;
- ordered command/result and lifecycle facts;
- expected aggregate versions and terminal run/work states;
- expected outbox, intent, attempt, and receipt counts;
- committed primary/recovery evidence manifests;
- releases, DSI, traceability, coverage, proposal, Approval, Serving State, and
  report artifacts where applicable;
- fake remote target/backup/routing state before and after;
- sanitized log/trace event codes and forbidden-data assertions; and
- exact exit code and human-readable summary fingerprint.

Unexpected files, facts, effects, warnings, network attempts, open work,
unconsumed outbox rows, or unaccounted source items fail the scenario.

## 6. Fault injection

Faults occur at named boundaries: before/after register commit, before/after
manifest commit, before/after remote request, after remote success before
receipt, during batch N, before/after Approval consumption, before/after
routing activation, and during recovery. Injection is deterministic and
recorded in the scenario profile, never timing-race-dependent.

Concurrency tests use explicit barriers to prove single winners. Property tests
vary retry counts, delivery order, page partition, batch partition, and restart
points while preserving the same expected authoritative result.

## 7. Network and secret denial

The proof runs with network disabled. Fake endpoints are in-process or
loopback-only and use test-only identities. Tests fail on DNS/socket attempts
outside the declared local harness, access to ambient Azure/Pinecone/provider
environment variables, unexpected filesystem roots, or any production trust
root.

Fixtures and reports contain invented legal material only. Secret scanners and
hostile-content assertions are part of the acceptance suite.

## 8. M7 exit decision

M7 is complete only when:

- all 32 scenarios pass from exact locks in two clean path-distinct runs;
- the golden flow is operable through the versioned APIs and minimal client;
- every authoritative artifact is deterministic and traceable;
- restart, duplicate, ambiguity, overlap, recovery, rollback, and deletion
  denial have exact results;
- no external service is required or contacted; and
- a new developer can reproduce the suite from the repository instructions.

The M7 report must say “local synthetic platform proved.” It must not say that
Azure, a real source, a real model, Pinecone, Ask.Legal production routing, or
any jurisdiction package is ready.

This document is design authority only and grants no implementation or
external authorization.
