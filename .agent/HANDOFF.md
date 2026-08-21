# Where the project stands — 2026-08-20

Read this first. It is the current short handoff. `WORKING_STATE.md` contains
the detailed history; `ROADMAP.md` contains the durable delivery sequence.

## Repository and host

- Root: `/home/docpro/Desktop/Ask.Legal Database/AskLegal-LegalDBPipeline`
- Host: `docpro-MS-7D99`, Ubuntu 24.04.4 LTS, x86-64.
- Branch: `main` at `f4128dc`, one local commit ahead of `origin/main` and not
  behind after a 2026-08-20 fetch.
- Docker commands in the current login session need `sg docker -c '...'`.
- `uv` and `node` are under `/home/docpro/.local/bin`.

The working tree was already dirty when the V1 audit began. Preserve this
active six-field serving-payload fix:

- `apps/promotion-worker/src/asklegal_promotion_worker/service.py`
- `apps/promotion-worker/src/asklegal_promotion_worker/v1_pipeline.py`
- `packages/promotion/src/asklegal_promotion/{__init__,builder,local,model,remote}.py`
- `packages/promotion/tests/test_remote_adapters.py`
- untracked `apps/promotion-worker/tests/test_v1_serving_payload.py`

## Fresh audit baseline

The complete audit was run on 2026-08-20 without changing implementation or
the live host.

| Check | Verified result |
|---|---|
| Full developer suite | 785 passed, 4 skipped; repeated directly with the same result |
| Locked package spike | Passed for all 19 workspace packages |
| Contract validator | Passed; reproducible package fingerprint `sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e` |
| Ruff lint | Passed |
| Ruff format check | Failed: 17 files would be reformatted; do not auto-format under the current Python 3.12 launcher constraint |
| Strict Pyright | Failed: 902 errors total; 715 errors are in 52 tracked files |
| Boundary checker | Passed: 164 files, 12 registered exceptions |
| Lock validation | `uv lock --check` passed |
| Dependency audit | No npm or OSV findings in the locked dependencies |
| JSON/TOML/shell syntax and Markdown local links | Passed |
| Git object integrity | Passed; only ordinary dangling unreachable objects reported |
| M7 fresh rerun | Not rerunnable without reset: `prove --all` found existing `run-a`; no reset was performed |

Four skipped tests still need their dedicated environments: Durable Task
emulator integration, real SQL Server integration, image-admission spike, and
package spike. The package spike was run separately and passed during the
audit. The other three were not re-proved in their dedicated environments.

## Live host state

- `asklegal.target` is enabled and active.
- Fourteen service containers are running; `asklegal-networks` is exited by
  design. No unit is failed and the five application logs report `READY`.
- No AskLegal timers are installed or active. The system therefore does not
  autonomously start its five declared recurring workflows.
- All five running application containers use image IDs older than the current
  local `:v1` tags. Source, tags, and deployed runtime are three different
  states until the host is deliberately reconciled.
- `acq-batch` and `cp-test` are long-running containers outside systemd using
  stale images and privileged pipeline networks. They can contend for work and
  must be investigated/stopped deliberately; the audit did not remove them.
- `/srv/asklegal` uses about 11 GB of 3.6 TB and its primary/recovery/SQL
  ownership is correct.
- Installed systemd units and launch scripts are byte-identical to the current
  generated repository copies.
- The composite gate still reports `V1_POC_NOT_ADMITTED`: 14 components, 8
  static contracts valid, 14 blockers. Its evidence model is not capable of
  representing the already-created identities, enabled services, or exercised
  providers, so it is a fail-closed static baseline, not a current admission
  ledger.

## V1 release blockers

### P0 — promotion trust and correctness

1. `ControlActivities.start_promotion` converts every model decision directly
   into a serving record and schedules promotion. It does not require a frozen
   release, desired-state inventory, Review decision, exact Approval, coverage
   manifest, backup, routing, or rollback proof. It has already promoted an
   `INSUFFICIENT_EVIDENCE` decision in the live chain.
2. The active six-field fix makes the promotion worker reject the control
   plane's current two-field payload. Deploying only that fix breaks the live
   chain rather than making it safe.
3. The promotion launcher permanently sets
   `PROMOTION_WRITE_AUTHORIZED=true`. Authorization is deployment-wide rather
   than bound to one approved immutable command.
4. The real Pinecone adapter ignores the upsert acknowledgement and verifies
   only that record IDs can be fetched. An older same-ID record can make a
   failed/no-op write look successful; vector and six-field metadata equality
   are not proved.
5. The active payload reconstruction computes a new fingerprint from the
   received payload rather than comparing it to an approved fingerprint. A
   changed payload therefore authenticates itself.
6. A provider error after an upsert is recorded `FAILED_FINAL`, even where the
   outcome is unknown and requires reconciliation before retry or terminal
   failure.

### P1 — shipping gates and operational safety

- Strict Pyright is documented as a development boundary but has 715 tracked
  errors, up from the historical 370-error debt, and `tools/dev_test.py` does
  not run Pyright or Ruff. There is no repository CI configuration.
- Model/embedding requests use zero placeholder prompt, package, profile,
  serving-payload, and text fingerprints. The live legal-processing path labels
  arbitrary captured endpoints as `HK_LATER_TREATMENT`; the live promotion
  path estimates tokens with `len(text.split())` despite pinned real tokenizers.
- Plaintext duplicates of SQL, vault, provider, Pinecone, and application
  credentials remain in ignored `var/run/` staging paths. Values were not read.
  Rotate every credential that has existed there, then remove the duplicates
  after confirming the sealed systemd copies; this needs explicit user/root
  action.
- Application telemetry is effectively absent. Prometheus and Grafana are not
  deployed, and only the OTel collector container exists.
- `.claude/settings.local.json` is tracked and grants broad
  `Bash(sg docker *)` permission. It is machine-local policy and should not be
  part of the shared repository without an explicit decision.
- The HKeL Gazette acquisition activity caps every request at 50 pages but does
  not report when the publisher says more pages exist. A sufficiently large date
  window can therefore produce a partial manifest that looks complete.
- The publisher-API `exchange` redirect path is recursive without enforcing the
  transport's declared redirect limit. A same-host redirect loop can run until a
  Python recursion failure instead of returning a bounded source failure.

### P2 — stale records and incomplete readiness

- The source register now contains 79 endpoints, 56 enabled: five configured,
  five partially configured, one blocked, and three out of V1 scope. Older
  references to 78 endpoints and four blocked roles are stale.
- All three executable Hong Kong legal-package scopes remain `NOT_READY`.
- Of 79 endpoint contracts, 63 have a technical procedure and 16 do not. Only
  direct HTTP capture and the special HKeL Gazette workflow are wired into the
  V1 service; the rendered-session, complete-inventory, and Patchright components
  otherwise remain library/test boundaries rather than schedulable activities.
- A focused strict-Pyright run over source connectors and the acquisition worker
  reports 45 errors: 23 in `hkel_gazette.py`, 20 in the V1 acquisition pipeline,
  one in its infrastructure, and one in `official_http.py`.
- The README, V1 topology document, formal admission JSON, and parts of the
  roadmap describe the earlier static-contract phase. They must be reconciled
  before being used as V1 operating instructions.
- `asklegal-local prove --all` is intentionally clean-state-only, but its CLI
  does not explain that reset is required and fails with an unhandled
  `FileExistsError` on a normal second run.
- Seventeen files have formatting drift. Automatic Ruff formatting remains
  unsafe while system launchers must parse under Python 3.12.

## Healthy foundation worth preserving

- The 785-test suite, architecture/boundary checks, package isolation, locked
  builds, schemas/contracts, and dependency hygiene are healthy.
- No tracked secrets, corpus dumps, or large runtime artifacts were found.
- Real source, Azure model/embedding, and Pinecone connectivity were previously
  exercised from their owning workers. That is connectivity evidence, not
  admission or release correctness.
- The Gazette archive holds 7,274 PDFs for 2000–2026 plus a canonical listing
  manifest; pre-2000 OCR remains deliberately unbuilt.

## Recommended dependency order to V1

1. Freeze external writes and stop/investigate the two orphan containers.
2. Repair the promotion trust chain end to end: release → desired state → named
   Review/Approval → exact manifest/fingerprints → acknowledged write → full
   read-back → backup/routing/rollback evidence.
3. Bring the control-plane payload and active six-field promotion fix onto one
   versioned contract and prove rejection, replay, lost-ack, and tamper cases.
4. Re-establish enforced shipping gates: Pyright debt to zero or a narrowly
   registered exception baseline, Ruff policy that preserves Python 3.12
   launcher compatibility, and CI that runs them.
5. Rotate staged credentials, rebuild/reconcile the five images deliberately,
   remove runtime drift, and add health/telemetry and timer-driven operation.
6. Replace the static admission snapshot with evidence that can express actual
   host/provider state, admit the intended legal package/model/embedding/target,
   and run the acceptance, recovery, and rollback proofs.
7. Reconcile README, topology, roadmap, and admission documents, then cut V1.

Accepted V1 risks still need to be named at release: the egress proxy is a
convention rather than an enforced boundary; `asklegal-register` permits broad
east-west access; Review client authentication and shared vault credentials are
relaxed; local image tags are mutable. These were conscious POC relaxations,
not newly discovered defects, but none should be described as production-grade.

No commit, push, deployment, source fetch, model/embedding call, Pinecone
mutation, credential rotation, container stop, or destructive reset was
performed by this audit.
