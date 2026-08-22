# Where the project stands — 2026-08-22

Read this first, then `.agent/ROADMAP.md` and `.agent/WORKING_STATE.md`.

## Repository checkpoint

- Root: `/home/docpro/Desktop/Ask.Legal Database/AskLegal-LegalDBPipeline`
- Host: `docpro-MS-7D99`, Ubuntu 24.04.4 LTS, x86-64
- Branch: `main`; substantive V1 checkpoint `da90a87` was pushed to
  `origin/main` on 2026-08-22 after the complete shipping gate passed.
- GitHub accepted the push through the configured old remote but reported that
  the repository moved to `https://github.com/stevw-repo/AutonomousLCP.git`.
  The configured remote has not been changed; reconcile it before relying on
  the old URL for a later checkpoint.
- The disposable branches `v1-poc-runtime-proven` and
  `demo/expo-source-transformation` are informational only. Do not import or
  cherry-pick their code.
- Docker commands in this login session require `sg docker -c '...'`.
- Exact local tools: `/home/docpro/.local/bin/uv` 0.12.5,
  `/home/docpro/.local/bin/node` 24.19.0, workspace Python 3.14.7.

## Verified engineering state

The complete shipping command passed on 2026-08-22:

```sh
.venv/bin/python -m tools.dev_test \
  --uv /home/docpro/.local/bin/uv \
  --node /home/docpro/.local/bin/node
```

Verified result:

- strict Pyright: 0 errors, warnings, or information messages;
- Ruff lint: clean;
- Ruff format: all 375 Python files formatted;
- Python boundary: 187 files, the same 12 exact reviewed exceptions;
- architecture: 5 applications, 14 packages, 80 dependency edges, 31
  capability ports;
- contracts: reproducible package fingerprint
  `sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`;
- ordinary suite: 959 passed, 4 skipped.

The four skipped tests are the intended opt-in gates. All four were run
separately and passed:

- package spike: 5 passed, including path-distinct builds and clean locked
  network-disabled installs for all 19 workspace packages;
- SQL Server: 1 passed against a new digest-pinned disposable SQL Server. The
  proof applies migrations `000001` through `000007`, commits real Review-ready
  and decided proposals, proves Review/Promotion projection reads, consumption,
  revocation, invalidation, no-effect execution authorization, replay/lost-ack
  recovery, permission isolation, tamper and changed-lineage rejection, one
  concurrent terminal winner, and denial of direct fact-table access;
- Durable Task: 1 passed against a new digest-pinned disposable emulator;
- image admission: full opt-in proof passed. Two canonical executions reproduced
  image digest
  `sha256:52bd434d68d024291a83e44c5c0c8c360880001f98dfd36954bad501241c462c`
  and all unsigned evidence fingerprints. Ephemeral signed graph hashes differed
  as designed; recovery equalled the signed graph within each execution.

Every disposable SQL, Durable Task, and BuildKit proof container/builder was
removed. Their downloaded digest-pinned images and ignored `/tmp` input caches
may remain.

M7 was explicitly reset and rerun under authorization: all 32 scenarios passed,
with report marker `local synthetic platform proved`. The report content digest
printed by the CLI was
`sha256:9d4f00dfb43ac73634cec69f0311d23b819637830161ce0b51ee7699b712de38`;
the report file SHA-256 is
`9bc2dec2b642444b4fd84728ac8458d918085d9cd6e772e71f50eb0eb80b4dbf`.
A normal second run returned exactly `SYNTHETIC_STATE_RESET_REQUIRED`.

## CI state

`azure-pipelines.yml` now runs the same complete shipping gate on a fresh
unprivileged Ubuntu 24.04 Microsoft-hosted agent. `tools/ci/bootstrap.sh`
downloads and verifies exact uv 0.12.5 and Node 24.19.0 archives, installs
Python 3.14.7 with `--no-bin`, and writes no profile/home executable. A clean
bootstrap run completed on 2026-08-22. The pipeline contains no service
connection, private pool, deployment environment, provider credential, or
production authority.

The CI files are now pushed in checkpoint `da90a87`. The hosted execution has
not yet been observed, so HKV1-1 remains `IN PROGRESS` for that single remote
observation.

## Image-proof corrections

The authorized rerun found and fixed two genuine reproducibility defects:

1. the old gate checked that some BuildKit v0.26.2 node existed but hardcoded
   actual builds to mutable builder `default` (currently v0.32.2);
2. the tracked synthetic image fixture lacked the dpkg status record required
   for Syft to inventory the declared BusyBox package.

The policy now binds named builder `asklegal-image-admission-v0262`, BuildKit
image digest
`sha256:de10faf919fc71ba4eb1dd7bd6449566d012b0c9436b1c61bfee21d621b009aa`,
Docker 29.7.2, and Grype database build `2026-08-21T06:17:24Z` with exact
archive/database hashes. `tools/image_admission_bootstrap.py` is the verified
reproduction path. `tools/image_admission_direct_runner.sh` is a non-elevating,
Docker/Buildx-only adapter for a shell that already has Docker permission.

## Current V1 position

HKV1-0 and HKV1-2 remain acquisition/scope work. Direct GLD e-Gazette is the
earliest originating official Gazette source and remains in V1, but its lawful
Turnstile-gated acquisition procedure is not admitted. HKeL Gazette remains
complementary backcapture, recovery, reconciliation, and gap evidence. The
repository has 79 endpoint contracts, 56 enabled; five source roles are
configured, five partially configured, one technically blocked, and three out
of V1 scope.

HKV1-3 through HKV1-6 remain the largest product gaps:

- all three Hong Kong Legislation scopes remain `NOT_READY`. Frozen package
  `0.27.0` now contains 33 rules and 216 deterministic fixtures. The
  commencement rule covers exact default, fixed, appointed, conditional, and
  progressive partial commencement and produces exact operative/pending
  locations without inferring effect from publication or HKeL `InEffect` alone.
  A second rule covers exact whole/partial and future/operative repeal,
  revocation, expiry, and continuity-proved revival, binding pre/post state and
  append-only event history without creating versions, successors, or records.
  The readiness contract is generated from the complete actual rule/fixture
  inventory rather than the former stale baseline-only list. A third rule
  classifies operative/future amendments, express corrections, and Editorial
  Record events, routes matching bundles to ordinary evidence validation and
  missing consolidation to a Coverage Gap, and never constructs text, an
  Official Version, or a Search Record;
  a fourth rule classifies ordinary/Extraordinary Gazette publication and
  enactment facts across Legal Supplement Nos. 1–3, Main Gazette notices, and
  other supplements without inferring commencement, current law, identity,
  continuity, an Official Version, or a Search Record;
  a fifth bounded pre-Plan semantic rule covers all 13 terminal
  decision/challenge outcomes. Even its successful exact confirmed result is
  only an untrusted structured candidate for the full deterministic ADR 0084
  Plan validator; it creates no Plan identity, executes no operation, authors
  no text, emits no record, and performs no provider or external effect;
  a sixth deterministic rule validates the complete ADR 0084 Plan contract,
  authority, latest base, event chain, dependency/evidence closure, authentic
  bilingual streams, closed operations, event bindings, atomic groups, and
  revalidation across 21 cases. It binds only the existing candidate identity
  and fingerprint and executes no operation or artifact construction;
- no executable real Hong Kong Cases package exists;
- no executable HKEX Regulatory package exists;
- Principles still needs publisher/title/licence selection. If omitted, the
  release cannot honestly be called the complete Hong Kong jurisdiction defined
  by the accepted design.

HKV1-8's next `BEGIN`/Effect Intent slice is intentionally closed until the
Promotion Manifest owns exact per-action effect/capability authority and
HKV1-7 admits the referenced profiles. Proposal packages are
manifest-last and restart-safe; Control registers a fully reread receipt through
the atomic command protocol. Review now re-reads and displays all 11 exact
members, validates the executable Promotion Manifest, and records a schema-valid
named-human approve/reject event with no effect intent. Migration `000004`
projects the optional decision to Review/Promotion. Promotion now reconstructs
the approved candidate after restart by rereading all twelve objects and
validating the exact Approval/manifest/base/predicate/authority bindings.
Migration `000005` adds a Promotion-only atomic single-use consumption command,
exact replay, competing-lineage denial, and explicit denial of the generic
writer; it emits no Effect Intent. Migration `000006` adds named-human Review
revocation and objective Promotion invalidation under the same terminal lock and
winner as consumption. Replay, later-consumption denial, app-specific
permissions, and a concurrent revoke/invalidate race pass on the real engine.
Migration `000007` adds a Promotion-only no-effect execution authorization after
it independently matches the exact consumed proposal, decision, manifest,
`exe_` lineage/fingerprint, worker identity, and validation evidence. Replay and
lost acknowledgement recover exactly; no Effect Intent or handler is created.
Migrations `000003` through `000007` pass the fresh least-privilege proof. A
pinned shared semantic contract now validates all eleven member roles and their
cross-member authority bindings after exact-version reads; Review invokes the
same contract independently. Correctly hashed placeholders, failed gates, and
release/coverage/traceability/recovery/report drift remain invisible. A
pinned-key Entra v2 verifier also
passes local signature/claim/role/token-kind tests but remains unwired pending
exact admitted tenant/client/key/current-authority inputs. Still missing are
current-state/authority service composition, the guarded `BEGIN` plus first
Effect Intent,
backup/cutover, and
rollback through the real local service boundaries.

The next independent safe priority is exact validated-Plan-to-operation
execution plus immutable Reconstruction Report/artifact validation, followed by
fallback-selection contracts. None may activate a real scope or provider.

HKV1-9 also remains incomplete. The last read-only host inspection showed the
declared stack plus orphan `acq-batch` and `cp-test`; application images are
older than current source/tags, timers and useful application telemetry are
absent, and plaintext credential staging duplicates need rotation/removal.
Those host mutations require their own exact authority and are not implied by
the local proof authorization.

## Authorization and side effects

The user authorized continued V1 work plus the repository CI implementation,
deletion/recreation only of the exact marked `var/local-conformance/` state, and
isolated local Docker/host proof services. The migration `000007` proof used a
new disposable database and removed its exact container; its generated
credential existed only in process memory.

No external legal source, Azure model/embedding deployment, Pinecone target,
Ask.Legal route, production system, live host SQL database, credential, or
deployed application was accessed or mutated during this checkpoint. Public
downloads were limited to the exact SHA-verified CI/image-proof tools,
BuildKit image, and Grype database. The authorized checkpoint `da90a87` was
pushed; no external source/provider/deployment action accompanied it. Do not
create another checkpoint commit or push without new exact authorization.

## Exact next work

1. Define the exact admitted capability/profile inputs for the separately
   guarded `EXECUTION_AUTHORIZED -> EXECUTION_RUNNING` `BEGIN` transition and
   first atomic Effect Intent, without inventing unset HKV1-7 values.
2. Compose exact admitted Entra/current-authority/current-state readers once
   their real local inputs exist.
3. Implement the `BEGIN` contract in fail-closed disabled composition, but keep
   every provider handler disabled until HKV1-7 target/profile admission is
   complete.
4. Implement exact Plan-to-operation execution and immutable Reconstruction
   Report/artifact validation behind `HKLEG-RECON-PLAN-001`; keep all real
   scopes inactive and all provider effects disabled.
