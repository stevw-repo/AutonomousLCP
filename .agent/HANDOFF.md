# Where the project stands — 2026-08-21

Read this first. It is the current short handoff. `WORKING_STATE.md` contains
the detailed history; `ROADMAP.md` contains the durable delivery sequence.

## Repository and host

- Root: `/home/docpro/Desktop/Ask.Legal Database/AskLegal-LegalDBPipeline`
- Host: `docpro-MS-7D99`, Ubuntu 24.04.4 LTS, x86-64.
- Branch: `main`; the verified pre-checkpoint base was `c4b3ba2`, equal to the
  refreshed `origin/main` ref. The 2026-08-21 checkpoint contains the audit,
  continuity reconciliation, and first six independently built HKV1-2
  acquisition slices described below.
- Docker commands in the current login session need `sg docker -c '...'`.
- `uv` and `node` are under `/home/docpro/.local/bin`.

Commit `c4b3ba2` contains the independently built six-field serving-payload
change. It is now committed on `main`; the running promotion image is older and
does not prove that source. The control-plane two-field payload remains
incompatible with the current promotion source.

`v1-poc-runtime-proven` and `demo/expo-source-transformation` are disposable
visual branches. Inspect them only for informational discovery leads. Never
import or cherry-pick their code. The former is an ancestor of `main`, has no
unique commits, and was 28 commits behind when inspected on 2026-08-21.

## Fresh audit baseline

The complete audit was run on 2026-08-20 without changing implementation or
the live host.

| Check | Verified result |
|---|---|
| Full ordinary pytest suite | 856 passed, 4 skipped after the sixth HKV1-2 slice |
| Locked package spike | Passed for all 19 workspace packages |
| Contract validator | Passed; reproducible package fingerprint `sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e` |
| Ruff lint | Passed |
| Ruff format check | Failed: 13 files would be reformatted; do not broadly auto-format under the current Python 3.12 launcher constraint |
| Strict Pyright | Failed: 856 errors total; 665 are in tracked Python and 191 are in ignored local runtime files under `var/`; the focused acquisition/Gazette/readiness surface is clean |
| Boundary checker | Passed: 173 files, 12 registered exceptions |
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

- Strict Pyright is documented as a development boundary but has 713 tracked
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
- The HKeL Gazette iterator now rejects page-cap exhaustion and an empty
  intermediate page as explicit incomplete results. The worker materializes the
  complete bounded listing before retaining any addressed PDF or listing
  manifest, so these failures cannot create a short successful window.
- The publisher-API `exchange` surface now enforces the transport's declared
  redirect limit and returns `REDIRECT_LIMIT_EXCEEDED` for a same-host loop.
- Item-specific endpoint templates now require the shared exact bounded-locator
  contract, including a required single substitution and rejection of authority,
  query, fragment, traversal, slash, backslash, and template ambiguity.
- Gazette invalid input fails before publisher-client construction. Register
  failures and every listed artifact now have closed durable outcomes; a missing
  selected-language publication or failed artifact makes the window
  `PARTIAL_CAPTURE`, while an incomplete register walk writes no manifest or
  artifact.
- Every terminal HKeL Gazette result now retains a canonical, fingerprinted
  source-coverage report with exact source policy, cutoff, counts, manifest
  reference, failure codes, disposition, and blocking consequence. HKeL
  backcapture gaps remain visible `NONBLOCKING` results and never satisfy the
  separate `RELEASE_BLOCKING` GLD role.
- The source-cycle orchestrator derives the exact due roles from the active
  register, records one immutable terminal report per due role, reads every
  report back by exact vault reference, and writes the complete cycle report
  last. Its exact binding now enters the V1 Coverage Status Manifest and blocks
  release/promotion freeze if accounting is incomplete or a release-blocking
  role has a gap.

### P2 — stale records and incomplete readiness

- The source register now contains 79 endpoints, 56 enabled: five configured,
  five partially configured, one blocked, and three out of V1 scope. Older
  references to 78 endpoints and four blocked roles are stale.
- Direct GLD e-Gazette is retained inside V1 as the originating/current-
  publication source and earliest official Gazette feed. HKeL Gazette is
  complementary backcapture, recovery, reconciliation, and gap-detection
  evidence, not the upstream replacement. GLD remains
  `PARTIALLY_CONFIGURED`: its Cloudflare Turnstile acceptance path must not be
  bypassed, and a lawful repeatable or explicitly approved bounded manual
  procedure still needs completeness and no-change admission evidence.
- All three executable Hong Kong legal-package scopes remain `NOT_READY`.
- Of 79 endpoint contracts, 63 have a technical procedure and 16 do not. Direct
  HTTP, exact complete-inventory, special HKeL Gazette, and reviewed Patchright
  discovery workflows are wired into the V1 service. The sole catalogue endpoint
  belongs to the out-of-scope Gazette archive. Required browser-session legal-
  evidence procedures otherwise remain unwired.
- Complete-inventory scheduling cannot accept a caller-selected subset. It
  derives the exact member/version set from the active register, retains admitted
  members, isolates response-bearing failures, writes attempt accounting last,
  and emits the source-policy-bound coverage result. Current HKeL inventory means
  exactly its English and Traditional Chinese XML pair; any failed member is
  release-blocking. This is deterministic local proof, not a live HKeL capture or
  evidence that a host timer currently schedules the activity.
- Rendered discovery accepts no caller URL or browser-policy override and retains
  only a sanitized request map plus attempt report. Request user-info is removed,
  and request-count overflow now fails closed. Every result says explicitly that
  it proves no evidence, completeness, no-change, coverage satisfaction, or
  processing authority. Current reviewed HKeL/NPC endpoints remain disabled or
  out of V1, so no browser source became callable and no host Chromium admission
  was established.
- The exact focused strict-Pyright run over HKeL Gazette, the acquisition
  pipeline/infrastructure, and the readiness protocol now reports zero errors,
  clearing the previously recorded 40-error slice.
- The README, V1 topology document, formal admission JSON, and parts of the
  roadmap describe the earlier static-contract phase. They must be reconciled
  before being used as V1 operating instructions.
- `asklegal-local prove --all` is intentionally clean-state-only, but its CLI
  does not explain that reset is required and fails with an unhandled
  `FileExistsError` on a normal second run.
- Thirteen files have formatting drift. Broad automatic Ruff formatting remains
  unsafe while system launchers must parse under Python 3.12.

## Healthy foundation worth preserving

- The 856-test suite, architecture/boundary checks, package isolation, locked
  builds, schemas/contracts, and dependency hygiene are healthy.
- No tracked secrets, corpus dumps, or large runtime artifacts were found.
- Real source, Azure model/embedding, and Pinecone connectivity were previously
  exercised from their owning workers. That is connectivity evidence, not
  admission or release correctness.
- The Gazette archive holds 7,274 PDFs for 2000–2026 plus a canonical listing
  manifest; pre-2000 OCR remains deliberately unbuilt.
- The complete local Hong Kong V1 defined by the accepted design contains four
  material families: Legislation, binding-court Cases, HKEX Regulatory
  Materials, and selected licensed Hong Kong Principles. Only the Legislation
  package has implementation checkpoints; it remains `NOT_READY`. Cases,
  Regulatory Materials, and Principles have no executable real package today.

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
