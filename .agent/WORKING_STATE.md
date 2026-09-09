# AskLegal Legal Database Pipeline — Working State

## 2026-09-10 — Offline interview POC (`/root`, local desktop)

## Current goal

Deliver a fast, truthful interviewer-facing proof of the AskLegal pipeline.
The immediate deliverable is a **local synthetic offline POC**, not the live
Hong Kong deployment. Live publisher access, cloud providers, Pinecone, Vault
credential rotation, systemd deployment, and Gate A–G admission are deferred
and are not blockers for this demonstration.

## Implemented POC

- `./tools/run_interview_demo.sh` is the one-command launcher. It works from
  outside the repository, prepares exact ignored state beneath
  `var/interview-demo`, and serves only `127.0.0.1:8002`.
- The launcher runs the existing deterministic `E2E-001` pipeline proof and
  prints a nine-stage timeline from scheduled synthetic change through evidence,
  legal processing, proposal construction, local Review, fake-target cutover,
  rollback, and recovery.
- The Review browser is styled for the interview, prominently says
  `LOCAL SYNTHETIC OFFLINE POC`, presents the proposal in readable form, and
  retains a human APPROVE or REJECT decision in the local register.
- The same screen exposes a demo-only Pipeline Proof Report with the exact
  `E2E-001` narrative, result, fact/effect counts, fingerprint, evidence
  references, limitations, and raw canonical JSON. The report route is absent
  from the normal non-demo Review application.
- The retained Review decision and the completed E2E proof are deliberately
  adjacent but separate. The UI does not claim that its click drove the already
  completed proof. `var/interview-demo/demo-summary.json` records that boundary.
- The disposable demo root has an exact marker and refuses to remove an
  unmarked directory. The browser token is demo-only, held in memory, and no
  real credential is required.

## How to run

```bash
./tools/run_interview_demo.sh
```

Open the printed URL, enter the printed demo token, inspect the proposal, and
choose Approve or Reject. Press Ctrl+C to stop the localhost server. For a
non-serving check, use `./tools/run_interview_demo.sh --prepare-only`.

## Verified state

- The direct golden proof returned `GOLDEN_FLOW_RECOVERED` with 13 retained
  facts and 8 effects.
- The complete M7 runner passed all 32 synthetic scenarios twice with external
  network denied.
- The demo launcher, Review API/UI, retained-decision restart behavior, and
  focused M7 gate passed `33` tests in 12.76 seconds. Ruff lint/format, scoped
  strict Pyright, JavaScript syntax, Bash syntax, and diff checks passed.
- A real localhost browser run proved the proposal could be approved and that
  its APPROVED status, reason, disabled actions, and local-promotion queue label
  remained visible after a full page reload and reconnect.
- A subsequent real browser run displayed the Pipeline Proof Report with
  `GOLDEN_FLOW_RECOVERED`, 13 facts, 8 effects, and its raw JSON link. The final
  report-focused gate passed 33 tests; scoped static and boundary checks passed.
- No live source, Azure/model/embedding provider, Pinecone, Vault, SQL,
  Scheduler, deployment, credential, or third-party-terms effect is part of
  this POC.

## Deferred work

The repository retains the broader Hong Kong V1 implementation and its prior
evidence. Returning to live integration is a separate future task: inspect the
current host state first, then revisit Primary-vault root/application credential
rotation, source observation and terms, provider evaluation, phase-two host
deployment, recovery, and final admission. Do not resume those operations merely
because their code exists.

## Exact next steps

The POC implementation is committed and pushed to `origin/main` as commit
`11bea99` (`Add offline interview demo`). The independent review closed with
no Critical, Important, or Minor findings; the global Python-boundary gate
passed 421 files / 551 exact reviewed exceptions.

1. Use the one-command launcher for the interview.
2. Treat any later live integration work as a separate scope decision rather
   than a prerequisite for the POC.

No sudo password or API key is needed for these steps. Ignored `var/` state and
all credentials must remain out of Git.
