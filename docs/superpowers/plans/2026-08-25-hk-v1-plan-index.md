# Hong Kong Live V1 Plan Set

Status: complete and self-reviewed; awaiting execution-mode selection
Date: 2026-08-25

This index is the execution map for the nine approved implementation plans. It
does not authorize implementation or any external action.

## Plan order

1. [Scope and authority](2026-08-25-hk-v1-01-scope-authority.md)
2. [Autonomous official-source acquisition](2026-08-25-hk-v1-02-autonomous-source-acquisition.md)
3. [Authentic Hong Kong Legislation](2026-08-25-hk-v1-03-authentic-hk-legislation.md)
4. [Post-1-July-1997 Hong Kong Cases](2026-08-25-hk-v1-04-post-1997-hk-cases.md)
5. [Authentic HKEX Main Board and GEM](2026-08-25-hk-v1-05-authentic-hkex.md)
6. [Compact model, retrieval, and Pinecone admission](2026-08-25-hk-v1-06-model-retrieval-pinecone.md)
7. [Local Review, Approval, and real promotion](2026-08-25-hk-v1-07-review-approval-promotion.md)
8. [Continuous Ubuntu operation](2026-08-25-hk-v1-08-ubuntu-live-operation.md)
9. [Complete baseline and live acceptance](2026-08-25-hk-v1-09-live-baseline-acceptance.md)

## Dependency graph

```text
Plan 1: scope/authority
    |
Plan 2: admitted source contracts and complete source cycles
    |
    +-------- Plan 3: Legislation --------+
    +-------- Plan 4: Cases --------------+--> Plan 6: model/retrieval/target admission
    +-------- Plan 5: HKEX ---------------+               |
                                                            +--> Plan 7: Review/promotion
                                                            +--> Plan 8: Ubuntu operation
                                                                     |
                                                                  Plan 9: live acceptance
```

Plans 3–5 have independent files and tests after Plan 2 freezes their source
contracts. Plans 7 and 8 may prepare disabled composition independently after
Plan 6 defines exact profiles, but neither can enable real provider effects.
Plan 9 consumes every earlier exit artifact.

## Specification coverage review

| Specification requirement | Implementing plan/tasks |
|---|---|
| Three-family scope, exclusions, label, common cutoff | Plan 1 Tasks 1–5 |
| Autonomous GLD, HKeL, Judiciary, and HKEX acquisition | Plan 2 Tasks 1–7 |
| Complete source-cycle accounting and no false no-change | Plan 2 Task 6; Plan 9 Task 2 |
| Three bilingual Legislation releases and legal-event handling | Plan 3 Tasks 1–6 |
| Post-1997 official Case accounting, faithful propositions, treatment graph | Plan 4 Tasks 1–7 |
| Separate current Main/GEM releases and component universe | Plan 5 Tasks 1–7 |
| Exact model/tokenizer/embedding/Pinecone profiles | Plan 6 Tasks 1, 2, 5–7 |
| Compact semantic and retrieval evaluation, repeated once | Plan 6 Tasks 3, 4, 6, 7 |
| Local complete Review and named-human whole-proposal decision | Plan 7 Task 1 |
| Approval automatically starts promotion; drift invalidates | Plan 7 Tasks 2, 4, 7 |
| Complete replacement index, read-back, backups, state transition | Plan 7 Tasks 3, 5, 6 |
| No Ask.Legal routing action | Plan 7 Task 3; Plan 9 Tasks 1, 6 |
| Five applications, current images, no orphans, sealed credentials | Plan 8 Tasks 1, 2, 4, 7 |
| Five schedules, non-overlap, catch-up, telemetry, alerts | Plan 8 Tasks 3, 5 |
| SQL/vault recovery, scheduler replacement, reboot | Plan 8 Tasks 6, 7 |
| Formal Gates A–G and `V1_ADMITTED` | Plan 9 Tasks 1–8 |
| Baseline, scheduled changed cycle, later Approval, rollback/restoration | Plan 9 Tasks 3–6 |
| Scheduled no-change and continued healthy next cycle | Plan 9 Task 7 |
| Operator runbook and handoff-ready continuity | Plan 9 Task 8 |

No master-spec requirement is intentionally left without an implementation or
acceptance task. Hong Kong Principles and Ask.Legal integration are explicitly
post-V1 work, not gaps in this plan set.

## Checkpoint discipline

Each task uses the same review cycle:

1. add a focused failing test or an operational preflight assertion;
2. run it and observe the expected failure;
3. implement the smallest complete boundary;
4. run focused tests and inspect the diff;
5. stop at a reviewer checkpoint.

Each plan ends with the complete shipping gate:

```text
python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node
```

No task may report success from an unrun test, skipped required integration,
unread artifact, provider acknowledgement alone, or assumed host state.

## Authorization ledger

Planning approval does not grant these implementation actions:

| Action | First plan checkpoint | Exact authority needed |
|---|---|---|
| External GLD/HKeL/Judiciary/HKEX access | Plan 2 Task 7 | Named hosts, procedures, window, preserved GLD-permission evidence, and terms/consent handling |
| Dependency/lock update | Plan 6 Task 2 | Implementation authority for the exact tokenizer dependency and locks |
| Azure model calls | Plan 6 Task 6 | Named deployments, profile refs, call/token/cost ceiling |
| Pinecone evaluation write | Plan 6 Task 6 | Named project and exact disposable index |
| Pinecone deletion | After Plan 6 Task 6 | Separate exact target deletion authority |
| Live SQL migrations | Plans 7/8 | Exact migration set, database, backup, and rollback plan |
| Real embedding/Pinecone/backup/Serving-State mutation | Plan 9 Task 4 | Exact T1/T2 manifest targets and maximum cost |
| Credential rotation/service replacement/orphan removal | Plan 8 Task 7 | Exact credentials, units, containers, reversible order |
| Host reboot | Plans 8 Task 7 and 9 Task 5 | This exact Ubuntu host and safe checkpoint |
| Rollback/restoration | Plan 9 Task 6 | Exact T2→T1→T2 Serving-State transitions |
| Commit | Every checkpoint | Exact commit authorization |
| Push | Final or user-selected checkpoint | Exact remote, branch, and payload authorization |

Terms or consent presentation is never accepted implicitly. Secrets, authentic
corpora, runtime reports, backups, and provider vectors remain outside Git.

## Definition of plan-set completion

The plan set is ready for execution when:

- all nine files remain linked to the approved master specification;
- the user has reviewed this index and requested execution;
- an execution mode is selected;
- implementation begins at Plan 1, Task 1; and
- every external or destructive gate remains stopped until its exact authority
  appears in current instructions.
