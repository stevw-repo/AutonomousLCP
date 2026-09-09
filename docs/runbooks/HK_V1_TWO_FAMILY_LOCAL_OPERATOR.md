# Hong Kong V1 two-family local operator runbook

Status: implementation runbook; the checked-in units are not installed or
enabled by this document.

## Scope and success rule

This V1 operates exactly two material families:

- `CASES`: binding-court Case propositions with decision dates on or after
  1997-07-01; and
- `LEGISLATION`: constitutional and other instruments, Ordinances, and
  subsidiary legislation.

HKEX Regulatory Materials and Principles are post-V1. They must not appear in a
timer instruction, current proposal, admission arithmetic, or serving target.

`INCOMPLETE_RETRYABLE` means preserved progress with work still outstanding. It
is not success. `INCOMPLETE_TERMINAL`, a rejected item, a missing required gate,
or an unreadable retained reference also blocks admission. Only the exact Gate
A–G evaluator may emit `V1_ADMITTED`.

## Declared schedules

All slots are in `Asia/Hong_Kong`, are persistent across downtime, use
`AccuracySec=1min`, and have zero randomized delay.

| Local slot | Schedule kind | Purpose |
| --- | --- | --- |
| Daily 02:15 | `OBSERVATION` | Ordinary two-family source observation |
| Sunday 03:15 | `RECONCILIATION` | Full two-family reconciliation |
| Daily 04:30 | `AUDIT_ARCHIVE` | Immutable audit archive |
| Monday 05:15 | `RECOVERY_VERIFY` | Recovery evidence verification |
| Daily 06:00 | `TELEMETRY_RETENTION` | Telemetry retention processing |

Each timer invokes the control-plane enqueue command. The schedule kind and
intended slot produce a stable command and cycle identity. Exact replay returns
the retained result. If the cycle was interrupted, enqueueing the same slot
resumes the same cycle ID and journal head; it must not create a competing
baseline. A second different slot is coalesced or refused while the relevant
cycle lease is active, according to the retained schedule result.

## Before any host change

From the repository root, validate the rendered, still-disabled inputs:

```bash
.venv/bin/python tools/v1_poc_render_units.py --check
.venv/bin/python -m pytest \
  tools/tests/test_hk_v1_live_cycle.py \
  tools/tests/test_hk_v1_live_admission.py \
  tools/tests/test_v1_poc_systemd_units.py \
  apps/control-plane/tests/test_v1_schedules.py \
  packages/observability/tests/test_status.py -q
```

Inspect the exact proposed unit and image diff, named orphan processes,
credential changes, paths, and rollback commands. Installing or enabling
units, stopping/removing processes, rotating credentials, replacing images,
changing SQL, or rebooting the host requires explicit user authority for that
frozen plan. Rendering and tests do not grant it.

## Exact local preparation sequence

Run these commands from the repository root. Replace every angle-bracketed
locator with one exact absolute path or retained identifier. None of the
examples contains or accepts a credential value. Do not put a password, token,
key, connection string, or other secret in an argument, manifest, report, or
shell log.

The modes fall into three different classes:

- no-effect inspection: reads retained input and writes only to standard
  output;
- retained local preparation: writes a named report, plan, or configuration
  beneath an explicit path, but performs no host, provider, Pinecone, routing,
  or source-network effect; and
- authority-gated execution: may change credential bindings, dispatch a cycle,
  or delete an exact archived source. Never run one merely because its
  preflight returned exit `0`.

Current operator boundaries are deliberately uneven:

| Operation | Current boundary | Effect status |
| --- | --- | --- |
| Host facts | `tools.v1_poc_collect_host_facts` | Read-only probes plus one retained local output |
| Host reconcile/apply | `tools.hk_v1_host_reconcile --mode plan`, then `tools.hk_v1_host_apply --execute` | Each exact phase needs a detached authority; rebuild/recollect and deployment are separately planned |
| Acquisition inputs | `tools.hk_v1_prepare_acquisition_config` | Retained local preparation only |
| Cutoff selection | `tools.hk_v1_select_acceptance_cutoffs` | Read-only by default; optional retained output |
| Baseline/update | `tools.hk_v1_live_cycle` | No-effect preflight by default; enqueue is explicit |
| All-family no-change | Automatic successful due-cycle continuation | No standalone manual acceptance CLI |
| Review/Approval | Review API and named-human browser action | Approval is a human authority action |
| Promotion | Automatic retained Approval wakeup | Provider/backup/serving effects require prior authority |
| Credential rotation | Repository-owned batch transaction and dual-network helper | No credential execution command is documented until the final operator composition is complete |
| Recovery | `tools.hk_v1_recovery_proof` | Preflight and retained live plan; execution requires exact authority, helpers, sealed references, and read-back adapters |
| Serving rollback/restoration | `tools.hk_v1_serving_state_transition` | Plan-only by default; exact local Serving-State CAS requires detached authority |
| Archive cleanup | `tools.hk_v1_archive_cleanup` | Plan by default; deletion is separately authorized |
| Gate F/G evidence | `tools.hk_v1_operational_evidence` | Read-only owner-result collection plus retained local composites |
| Final admission | `tools.hk_v1_live_admission` | Read-only evaluation of retained proofs |

### 1. Host facts and reconcile plan

Collecting host facts performs bounded read-only host inspection and writes one
private facts envelope. The acknowledgement is required, but it is not host
mutation authority:

```bash
.venv/bin/python -m tools.v1_poc_collect_host_facts \
  --acknowledge-read-only-host-inspection \
  --output /absolute/path/to/hk-v1/host/observed.json

.venv/bin/python -m tools.v1_poc_host_admission \
  --facts /absolute/path/to/hk-v1/host/observed.json
```

The collector exits `0` only after the facts file is atomically written. A
missing acknowledgement or any collection/output failure is nonzero and leaves
no usable new facts. Host admission exits `0` only when the supplied facts
conform to the checked-in policy; its success line still says `NOT_READY` and
`host mutation authorized=false`. A nonzero admission result means the facts
are incomplete, malformed, or nonconforming, not that they should be repaired
automatically.

Freeze the first reconcile plan after the recovery preflight report exists.
Credential rotation is prepared only after five source-bound candidate
images exist. The recovery attachment must be present and fingerprint-bound
before phase-two apply. A missing or invalid report blocks apply. A canonical
`NOT_READY` report is different: it may accompany local
prototype bootstrap because SQL and Scheduler recovery inputs can depend on the
running stack, but it remains an explicit admission limitation:

```bash
.venv/bin/python -m tools.hk_v1_host_reconcile \
  --mode plan \
  --facts /absolute/path/to/hk-v1/host/observed.json \
  --recovery-preflight-report /absolute/path/to/hk-v1/recovery/preflight.json \
  --output /absolute/path/to/hk-v1/host/reconcile-plan.json
```

Exit `0` means only that the canonical plan was written and readied for human
inspection. It does not mean the plan has no blockers: inspect `blockers`,
`authority_required`, `mutation_authorized`, and the plan fingerprint. Invalid
inputs or output paths fail nonzero. The reconciler itself has no mutation
mode. A separate executor accepts only one of its two closed action sets and an
exact detached authority. The authority schema is
`asklegal.hk-v1-host-apply-authority/v1`; it binds the complete plan
fingerprint, ordered actions, sorted targets, repository root, state root, and
one `AUTHORIZED` decision. The executor never creates this authority.

The first actionable plan builds the five local application images only as
`asklegal/<service>:hk-v1-candidate` and then recollects host facts. It does not
replace a running service and does not publish a `:v1` tag. Only after the user
approves that exact plan and its authority may an operator run:

```bash
.venv/bin/python -m tools.hk_v1_host_apply \
  --execute \
  --plan /absolute/path/to/hk-v1/host/reconcile-plan.json \
  --authority /absolute/path/to/hk-v1/host/build-authority.json \
  --repository-root /absolute/path/to/AskLegal-LegalDBPipeline \
  --state-root /absolute/path/to/hk-v1/host/apply-state
```

Successful completion of this first phase returns exit `3` with
`PHASE_COMPLETE_REPLAN_REQUIRED`, not deployment success. It retains exact
image IDs in `var/hk-v1/host/application-build-results.json` and the canonical
post-build facts. Each result row binds the service, candidate tag, exact
`sha256:` image ID, and installed-tree digest. Re-run the reconciler against
those facts and bind those exact build-result bytes into a new plan:

```bash
.venv/bin/python -m tools.hk_v1_host_reconcile \
  --mode plan \
  --facts /absolute/path/to/AskLegal-LegalDBPipeline/var/hk-v1/host/post-image-build.json \
  --application-build-results /absolute/path/to/AskLegal-LegalDBPipeline/var/hk-v1/host/application-build-results.json \
  --vault-application-rotation-plan /absolute/path/to/hk-v1/credential/vault-application-rotation-plan.json \
  --vault-application-rotation-report /absolute/path/to/hk-v1/credential/vault-application-rotation-report.json \
  --recovery-preflight-report /absolute/path/to/hk-v1/recovery/preflight.json \
  --output /absolute/path/to/hk-v1/host/deployment-plan.json
```

Do not authorize phase two until the exact completed value-free credential
result required by the current host contract is retained.

The second host plan freezes runtime paths, configuration, networks, units,
five candidate-tag-to-build-result digest checks, target/timer enablement,
complete host recollection, and an ordered rollback. Every action image ID must
equal the corresponding retained build-result row. Phase two verifies that the
candidate tag still resolves to that ID, then atomically publishes exactly five
ordered rows to `/etc/asklegal/deployment-images`. The file is a root-owned,
regular `0400` persistent restart input; every application launcher and both
bootstrap helpers resolve their image from it rather than an ambient mutable
tag. It requires a second detached authority for its own fingerprint:

```bash
.venv/bin/python -m tools.hk_v1_host_apply \
  --execute \
  --plan /absolute/path/to/hk-v1/host/deployment-plan.json \
  --authority /absolute/path/to/hk-v1/host/deployment-authority.json \
  --repository-root /absolute/path/to/AskLegal-LegalDBPipeline \
  --state-root /absolute/path/to/hk-v1/host/deployment-state
```

Before invoking phase two, the operator must truthfully establish direct local
console access and export `I_HAVE_CONSOLE_ACCESS=1`; the firewall helper refuses
to infer it. Preserve that variable through any required privilege boundary.
The firewall deadman remains armed until exact post-apply firewall readback is
confirmed.

This returns exit `0` only after all actions and the strengthened post-apply
readbacks complete. They require the exact manifest bytes and ownership, fresh
SQL-register and vault-bootstrap receipts, all declared containers running
with admitted health, the five application containers on their authorized
digests, no unexpected container, all application/systemd rows active, all
five timers active, the target active and enabled, and the exact firewall
policies. Terminal replay revalidates these current facts; it cannot reuse a
stale `COMPLETE` claim. Rollback likewise proves each retained predecessor
image or absence and its retained runtime state before reporting restoration.

Host state always records `v1_admitted=false`. When the bound recovery report
is canonically `NOT_READY`, it additionally records
`admission_limitations=["RECOVERY_PREFLIGHT_NOT_READY"]`; host completion does
not clear that Gate F/final-admission blocker. Exit `2` is blocked, failed, or
rollback-unverified. Reboot remains a later, separately planned and authorized
operation.

### 2. Credential batch, Primary-root rotation, and dual-network helper boundary

The current credential work stages one exact value-free batch that changes the
seven application vault credentials plus both Primary vault root components.
The other sixteen credentials remain byte-identical. Do not reuse the legacy
single-credential `pinecone-poc` examples or treat any plan as proof that a
rotation completed. Create the private plaintext input directory outside Git,
then stage all nine replacements without a vault, IAM, service, or Docker
effect:

Host reconciliation may consume only the exact terminal successful batch
result required by its finalized input contract.

```bash
umask 077
sudo /absolute/path/to/AskLegal-LegalDBPipeline/.venv/bin/python \
  -m tools.hk_v1_stage_vault_credential_rotation \
  --source-root /absolute/path/to/private/current-plaintext-credentials \
  --candidate-root /absolute/path/to/private/candidate-plaintext-credentials \
  --receipt /absolute/path/to/hk-v1/credential/staging-receipt.json \
  --rotation-id <rot_-plus-48-lowercase-hex>
```

Exit `0` prints only the staging fingerprint and candidate binding. The command
must fail if either Primary root component or any application credential is
reused. Preserve the private candidate directory until the later application
rotation succeeds.

Both the rendered `80-install.sh` path and authority-gated host phase two
install
`/usr/local/libexec/asklegal-vault-primary-root-rotation-network` and
`/usr/local/libexec/asklegal-vault-application-rotation-network` as root-owned
executables with mode `0755`. Host rollback snapshots and restores each
predecessor or exact absence. These helpers supply the bounded Docker network
environment needed by the manifest-bound candidate control-plane image; their
presence is neither credential authority nor proof of a successful rotation.

Rotate the Primary root pair before rotating application IAM. Root preflight
reads exact staging, sealed-root, vault-data, source-tree, and candidate-image
bindings and retains a value-free plan; it does not change credentials, IAM,
services, vault data, or Docker:

```bash
sudo /absolute/path/to/AskLegal-LegalDBPipeline/.venv/bin/python \
  -m tools.hk_v1_vault_primary_root_rotation preflight \
  --staging-receipt /absolute/path/to/hk-v1/credential/staging-receipt.json \
  --sealed-root /etc/asklegal/credentials \
  --vault-data-root /srv/asklegal/vault-primary \
  --application-build-results /absolute/path/to/AskLegal-LegalDBPipeline/var/hk-v1/host/application-build-results.json \
  --application-image-inputs /absolute/path/to/AskLegal-LegalDBPipeline/infrastructure/poc/application_image_inputs.json \
  --workspace-root /absolute/path/to/AskLegal-LegalDBPipeline \
  --plan-output /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-plan.json
```

After inspecting and authorizing that exact `plan_fingerprint`, execute with
the same immutable inputs:

```bash
sudo /absolute/path/to/AskLegal-LegalDBPipeline/.venv/bin/python \
  -m tools.hk_v1_vault_primary_root_rotation execute \
  --staging-receipt /absolute/path/to/hk-v1/credential/staging-receipt.json \
  --sealed-root /etc/asklegal/credentials \
  --vault-data-root /srv/asklegal/vault-primary \
  --application-build-results /absolute/path/to/AskLegal-LegalDBPipeline/var/hk-v1/host/application-build-results.json \
  --application-image-inputs /absolute/path/to/AskLegal-LegalDBPipeline/infrastructure/poc/application_image_inputs.json \
  --workspace-root /absolute/path/to/AskLegal-LegalDBPipeline \
  --plan-output /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-plan.json \
  --state-root /absolute/path/to/private/vault-primary-root-rotation-state \
  --runtime-credential-root /run/asklegal/credentials/vault-primary \
  --report-output /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-report.json \
  --authorized-plan-fingerprint <exact-sha256-plan-fingerprint>
```

Execution stops the five dependent applications, bootstrap, and Primary vault;
switches the two sealed root files; atomically installs the plan-bound
value-free Primary launcher and root-network helper; and restarts against the
same `/srv` vault data. Their exact predecessor bytes or absence are staged in
the transaction state, but the hardened files deliberately remain installed
during credential rollback so the restored old root cannot reappear in Docker
configuration. This step does not depend on the later host phase-two
installation. Success
requires exact data identity, healthy dependants, no root value in Docker
create arguments or `Config.Env`, new-root acceptance, and old-root rejection.
Failure restores the old sealed pair, retains the hardened runtime files, and
proves old-root acceptance plus new-root rejection. Only exit `0` and a strictly parsed
terminal `SUCCEEDED` root report permit the seven-application transaction.

The production entrypoint is
`tools.hk_v1_vault_application_rotation`. Both modes require the exact staging
receipt, successful Primary-root report, private sealed root, current
application-image input manifest, current source-bound application build
results, and repository root. Preflight is read-only with respect to
credentials, IAM, services, vaults, and Docker networks; it retains a canonical
plan and production-adapter readiness result:

```bash
sudo /absolute/path/to/AskLegal-LegalDBPipeline/.venv/bin/python \
  -m tools.hk_v1_vault_application_rotation preflight \
  --staging-receipt /absolute/path/to/hk-v1/credential/staging-receipt.json \
  --primary-root-rotation-plan /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-plan.json \
  --primary-root-rotation-report /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-report.json \
  --sealed-root /absolute/path/to/private/sealed-bindings \
  --plan-output /absolute/path/to/hk-v1/credential/vault-application-rotation-plan.json \
  --preflight-output /absolute/path/to/hk-v1/credential/vault-application-rotation-preflight.json \
  --application-build-results /absolute/path/to/AskLegal-LegalDBPipeline/var/hk-v1/host/application-build-results.json \
  --application-image-inputs /absolute/path/to/AskLegal-LegalDBPipeline/infrastructure/poc/application_image_inputs.json \
  --workspace-root /absolute/path/to/AskLegal-LegalDBPipeline
```

Run preflight as root because predecessor sealed-state inspection is root-only.
It rejects stale source, replaced build-result bytes, a missing candidate tag,
or a control-plane candidate image ID that is not bound to the exact current
build results. Exit `0` means the production adapters are ready; exit `2`
means `VAULT_APPLICATION_ROTATION_PREFLIGHT_NOT_READY`. Neither result grants
execution authority.

After inspecting the retained plan, obtain explicit authority for its exact
`plan_fingerprint`. Execute repeats every immutable input so it cannot switch
to different source, build results, staging, or sealed roots. It additionally
requires private state and runtime-credential roots plus a value-free report
path:

```bash
sudo /absolute/path/to/AskLegal-LegalDBPipeline/.venv/bin/python \
  -m tools.hk_v1_vault_application_rotation execute \
  --staging-receipt /absolute/path/to/hk-v1/credential/staging-receipt.json \
  --primary-root-rotation-plan /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-plan.json \
  --primary-root-rotation-report /absolute/path/to/hk-v1/credential/vault-primary-root-rotation-report.json \
  --sealed-root /absolute/path/to/private/sealed-bindings \
  --plan-output /absolute/path/to/hk-v1/credential/vault-application-rotation-plan.json \
  --application-build-results /absolute/path/to/AskLegal-LegalDBPipeline/var/hk-v1/host/application-build-results.json \
  --application-image-inputs /absolute/path/to/AskLegal-LegalDBPipeline/infrastructure/poc/application_image_inputs.json \
  --workspace-root /absolute/path/to/AskLegal-LegalDBPipeline \
  --state-root /absolute/path/to/private/vault-application-rotation-state \
  --runtime-credential-root /etc/asklegal/credentials \
  --report-output /absolute/path/to/hk-v1/credential/vault-application-rotation-report.json \
  --authorized-plan-fingerprint <exact-sha256-plan-fingerprint>
```

Execution is root-only and effectful: it may switch credential files, restart
dependent services, and change both vault IAM sets through the manifest-bound
candidate control-plane image. It is restart-safe and restores the predecessor
binding/IAM state when the candidate cannot be proved. Only exit `0` plus a
strictly parsed terminal `SUCCEEDED` report is completion. Exit `2`, a partial
state, or a plan alone is not proof.

Pass that exact successful plan/report pair to host reconciliation with
`--vault-application-rotation-plan` and
`--vault-application-rotation-report`. The reconciler cross-checks their plan,
rotation, candidate-binding, and staging-receipt identities. Never invoke the
network helper directly, invent the plan-fingerprint authority, substitute a
plan for the terminal report, or place credential material in an argument,
manifest, report, or shell log.

### 3. Recovery preflight, live plan, and gated execution

The default recovery mode only validates detached local evidence and writes a
private report. It does not restore SQL, replace a vault or Scheduler, mutate a
host, or prove Gate F:

```bash
.venv/bin/python -m tools.hk_v1_recovery_proof \
  --operation-id <r_-plus-32-lowercase-hex> \
  --request-fingerprint <sha256:-plus-64-lowercase-hex> \
  --workspace-root /absolute/path/to/disposable-recovery-workspace \
  --sql-snapshot /absolute/path/to/retained/sql-snapshot.json \
  --primary-vault-root /absolute/path/to/retained/primary-vault \
  --recovery-vault-root /absolute/path/to/retained/recovery-vault \
  --scheduler-snapshot-root /absolute/path/to/retained/scheduler \
  --output /absolute/path/to/hk-v1/recovery/preflight.json \
  --mode PREFLIGHT
```

Exit `0` prints `PREFLIGHT_READY`; it proves only that all exact local inputs
are structurally ready. Exit `2` prints `NOT_READY` and retains exact blocker
codes. The library has a separately authorized
`EXECUTE_LOCAL_PROTOTYPE` boundary, but this CLI deliberately composes no
execution request or adapters. Adding `--mode EXECUTE_LOCAL_PROTOTYPE` and
`--authorize-local-execution` therefore returns `NOT_READY` with
`EXECUTION_ADAPTERS_NOT_COMPOSED`; it is not a recovery command or a workaround.

After the recovery owner has retained the canonical live request, the
reference-only credential manifest, and the exact SQL backup-path mapping,
freeze the seven-step live plan without invoking SQL, either vault, or either
Scheduler role:

```bash
umask 077
.venv/bin/python -m tools.hk_v1_recovery_proof \
  --operation-id <r_-plus-32-lowercase-hex> \
  --request-fingerprint <sha256:-plus-64-lowercase-hex> \
  --workspace-root /absolute/path/to/disposable-recovery-workspace \
  --sql-snapshot /absolute/path/to/retained/sql-snapshot.json \
  --primary-vault-root /absolute/path/to/retained/primary-vault \
  --recovery-vault-root /absolute/path/to/retained/recovery-vault \
  --scheduler-snapshot-root /absolute/path/to/retained/scheduler \
  --output /absolute/path/to/hk-v1/recovery/live-plan.json \
  --mode PLAN_LIVE \
  --live-request /absolute/path/to/hk-v1/recovery/live-request.json \
  --live-credential-manifest /absolute/path/to/hk-v1/recovery/credential-references.json \
  --sql-backup-path-manifest /absolute/path/to/hk-v1/recovery/sql-backup-paths.json
```

Exit `0` prints `LIVE_RECOVERY_PLAN_READY`. The plan binds the exact recovery
request, SQL backup mapping, five credential references, deterministic
disposable targets, and all seven ordered steps. It contains no credential
value and grants no execution authority.

Live execution additionally requires a separately reviewed detached authority
for the exact plan fingerprint, an existing private clean-room directory, an
existing private state root, and the following five sealed runtime files named
only by the credential-reference manifest:

- `PRIMARY_VAULT_RECOVERY_READER`
- `RECOVERY_VAULT_RECOVERY_READER`
- `SQL_SERVER_RECOVERY_ADMIN`
- `SCHEDULER_GENERAL_RECOVERY_ADMIN`
- `SCHEDULER_PROMOTION_RECOVERY_ADMIN`

The host must also provide executable fixed-protocol helpers at
`/usr/local/libexec/asklegal-sql-recovery-admin` and
`/usr/local/libexec/asklegal-scheduler-recovery-admin`. The Scheduler helper
must prove old-lineage fencing, effect reconciliation, replacement start, and
denial of old-lineage resumption; a service restart is not an equivalent proof.
Only after those inputs exist and the user authorizes the exact retained plan
may an operator run:

```bash
umask 077
.venv/bin/python -m tools.hk_v1_recovery_proof \
  --operation-id <exact-retained-operation-id> \
  --request-fingerprint <exact-retained-request-fingerprint> \
  --workspace-root /absolute/path/to/disposable-recovery-workspace \
  --sql-snapshot /absolute/path/to/retained/sql-snapshot.json \
  --primary-vault-root /absolute/path/to/retained/primary-vault \
  --recovery-vault-root /absolute/path/to/retained/recovery-vault \
  --scheduler-snapshot-root /absolute/path/to/retained/scheduler \
  --output /absolute/path/to/hk-v1/recovery/live-result.json \
  --mode EXECUTE_LIVE \
  --live-plan /absolute/path/to/hk-v1/recovery/live-plan.json \
  --live-authority /absolute/path/to/hk-v1/recovery/live-authority.json \
  --live-credential-manifest /absolute/path/to/hk-v1/recovery/credential-references.json \
  --sql-backup-path-manifest /absolute/path/to/hk-v1/recovery/sql-backup-paths.json \
  --live-clean-room-root /absolute/path/to/private/recovery-clean-room \
  --live-state-root /absolute/path/to/private/recovery-state
```

Exit `0` prints `LIVE_RECOVERY_PROVED` only after every step is reconciled or
executed and its read-back receipt is retained. Exit `2` retains `NOT_READY`
when an adapter input or privileged helper is absent. Never put a credential
value in an argument, plan, authority, report, or continuity file.

### 4. GLD challenge-contract discovery and window observation

GLD itself needs no API key. The operator is nevertheless disabled by default
because its Patchright browser performs source-network effects and may expose a
terms, consent, cookie, or challenge surface. Before any source attempt, the
acquisition image must pass the offline runtime check:

```bash
.venv/bin/python -m tools.v1_poc_patchright_runtime --check
.venv/bin/python -m tools.v1_poc_application_images
```

The current repository has the exact pinned Patchright browser bytes at
`var/application-inputs/ms-playwright` and `114` exact Debian 13 Chromium/Xvfb
archives at `var/patchright-debs`. The locked manifest is
`infrastructure/poc/patchright_runtime_system_packages.json`; the runtime check
must report `blocker=NONE`. These inputs have passed real headless and headed
Xvfb launches in a disposable network-disabled copy of the pinned base image.
The application-image check still reports the separate OCI build/proof blocker.
Obtain exact image-build authority before building or attempting GLD; locked
input bytes do not themselves authorize an image or source effect.

The installed operator's no-effect preflight reads its explicit runtime mode,
authority/contract paths, private session root, and vault configuration:

```bash
.venv/bin/python -m tools.hk_v1_gld_operator preflight
```

With the normal `ASKLEGAL_HK_V1_GLD_OPERATOR_MODE=DISABLED`, preflight reports
`GLD_OPERATOR_DISABLED`. Contract discovery requires a named, expiring,
self-fingerprinted authority for exactly one cycle and cutoff, action
`DISCOVER_GLD_CHALLENGE_CONTRACT`, the registered GLD host/start path and exact
allowed routes, request/byte/deadline ceilings, Primary-vault identity and
prefixes, and the private session root. Install only that reviewed receipt at
`/etc/asklegal/config/hk-v1-acquisition/gld-challenge-authority.json`, set mode
`DISCOVER_CONTRACT`, then run the effect only after the user authorizes it:

```bash
.venv/bin/python -m tools.hk_v1_gld_operator execute \
  --cycle-id <exact-cycle-id> \
  --observation-cutoff <YYYY-MM-DDTHH:MM:SSZ>
```

Discovery retains bounded raw response bytes and sanitized route/cookie-name
facts under the exact authority lineage. It does not click, accept terms,
create a challenge contract, claim a complete window, or publish anything. A
human must inspect that exact retained discovery fingerprint. Only then may the
human freeze a challenge contract bound to it and issue a distinct authority
for action `OBSERVE_GLD_CURRENT_WINDOW`. Install both exact files, set mode
`OBSERVE_WINDOW`, and invoke the same cycle/cutoff command. Observation permits
at most the contract-bound session attempts plus one non-redirecting listing
request under one decreasing operation deadline. It still returns an
incomplete observation until the authentic publisher shape has a strict parser.

If any new or changed terms, consent, or cookie choice appears, stop. Read it
and obtain explicit user permission before interacting with it. Do not infer
permission from source readability, prior technical success, or the absence of
an API key.

### 5. Acquisition-configuration preparation

This is an offline retained-local write, not a no-effect preflight. It reads the
already retained source tree and exact GLD window, then atomically publishes
five inputs beneath a new output root. It makes no source-network call:

```bash
.venv/bin/python -m tools.hk_v1_prepare_acquisition_config \
  --source-root /absolute/path/to/retained/source-root \
  --gld-window /absolute/path/to/retained/gld-window-snapshot.json \
  --gld-window-sha256 <sha256:-plus-64-lowercase-hex> \
  --output-root /absolute/path/to/hk-v1/acquisition/config
```

Exit `0` emits the canonical `READY` report. Exit `2` writes one closed error
code to standard error. Preserve the output root: an exact replay verifies its
receipt and all five files without repeating the expensive retained HKeL scan;
drift fails with `ACQUISITION_CONFIG_OUTPUT_DRIFT` instead of overwriting it.

The prepared root contains exactly:
`gld-window-snapshot.json`, `hkel-admission-receipt.json`,
`hkel-archive-observation.json`, `judiciary-advanced-search-form.html`, and
`judiciary-advanced-search-form.sha256`. Preparation does not install them.
Placing that exact root at `/etc/asklegal/config/hk-v1-acquisition`, or changing
the retained source-admission mount, is a host change and needs authority for
the frozen host plan. The live Acquisition service also requires its explicit
read-only source-admission root and writable due-cycle and legislation state
roots. Missing, drifted, or symlinked inputs make service startup `NOT_READY`;
there is no production fallback to test fixtures.

### 6. Cutoff selection and acceptance cycles

The selector requires complete `CASES` and `LEGISLATION` manifests beneath
both `<retained-root>/t1/` and `<retained-root>/t2/`. First inspect the canonical
selection on standard output without writing it:

```bash
.venv/bin/python -m tools.hk_v1_select_acceptance_cutoffs \
  --retained-root /absolute/path/to/hk-v1/acceptance-cutoffs
```

Then freeze it once at a new absolute output path:

```bash
.venv/bin/python -m tools.hk_v1_select_acceptance_cutoffs \
  --retained-root /absolute/path/to/hk-v1/acceptance-cutoffs \
  --output /absolute/path/to/hk-v1/acceptance/cutoffs.json
```

Exit `0` means a complete two-family `t1`/`t2` selection was emitted or
atomically written. With `--output`, standard output is empty. Exit `2` writes
one closed error code such as `COMMON_CUTOFF_INCOMPLETE`,
`AUTHENTIC_CHANGE_NOT_FOUND`, or an output failure. The output path is
immutable: an existing path fails with `ACCEPTANCE_CUTOFF_OUTPUT_CONFLICT`, so
resume from the retained file rather than overwriting or regenerating it.

Preflight each exact cycle. `BASELINE` must use `t1`; `UPDATE` must use `t2`:

```bash
.venv/bin/python -m tools.hk_v1_live_cycle \
  --kind BASELINE \
  --cutoff-file /absolute/path/to/hk-v1/acceptance/cutoffs.json \
  --cutoff-key t1 \
  --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json \
  --mode preflight

.venv/bin/python -m tools.hk_v1_live_cycle \
  --kind UPDATE \
  --cutoff-file /absolute/path/to/hk-v1/acceptance/cutoffs.json \
  --cutoff-key t2 \
  --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json \
  --mode preflight
```

Preflight exit `0` emits `enqueued:false` and
`resolution:"PREFLIGHT_READY"`; it performs no retained-state write or
Scheduler dispatch. Exit `2` writes only `HK_V1_ACCEPTANCE_CYCLE_NOT_READY`.

`--mode enqueue` is the effect switch: it writes the stable request below the
explicit state root and dispatches it to the configured Control-plane
Scheduler. Only after exact user authority for the reviewed preflight may the
operator run the matching command with:

```text
--mode enqueue --state-root /absolute/path/to/hk-v1/control/acceptance-state
```

A successful enqueue exits `0`, emits `enqueued:true`, and returns the retained
and dispatched resolution. Exit `2` means no successful enqueue result was
proved. Reuse the same cutoff file, role, matrix, and state root for restart;
the stable request identity prevents a competing restart lineage.

After the exact Control orchestration reaches `COMPLETED`, export its validated
owner result without dispatching another cycle. Repeat the same kind, cutoff,
and Matrix inputs used for enqueue:

```bash
.venv/bin/python -m tools.hk_v1_live_cycle \
  --kind BASELINE \
  --cutoff-file /absolute/path/to/hk-v1/acceptance/cutoffs.json \
  --cutoff-key t1 \
  --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json \
  --mode result \
  --output /absolute/path/to/hk-v1/acceptance/baseline-result.json
```

Result mode performs one read-only Scheduler lookup, verifies the exact
instance, orchestrator, request identity, cutoff, and canonical result schema,
then atomically creates a mode-`0600` file. It never schedules work. Replaying
the same bytes is accepted; a nonterminal instance or any output/result drift
exits `2` with `HK_V1_ACCEPTANCE_CYCLE_NOT_READY`.

There is presently no separate manual all-family no-change acceptance CLI. The
cutoff selector requires at least one authentic controlling T1-to-T2
manifest/content delta, and `hk_v1_live_cycle` rejects an `UPDATE` whose
`authentic_changed_families` is empty.

Ordinary scheduled `OBSERVATION` and `RECONCILIATION` cycles do have the real
no-change path. After the due cycle proves complete accounting and releases its
block, Control runs the durable `continue_hk_v1_due_acceptance` activity. It
rebuilds a stable `UPDATE` request from the exact retained two-family evidence;
when both child manifests say `NO_CHANGE`, it returns genuine `NO_CHANGE`
before Legal Processing, proposal, Review, or Promotion effects. The operator
initiates or exactly replays that route only through the schedule command
documented under “Restart and missed-run handling,” using the real timer
invocation ID and Hong Kong slot.

Do not manufacture a changed-family claim, reuse a stale T2 selection, or call
a changed update a no-change proof. Gates B and G may use only the retained
result from this automatic scheduled continuation; the absence of a standalone
manual acceptance command is not evidence that no change occurred.

### 7. Review authority, hot proposal discovery, and Approval wakeup

Review requires an explicit, canonical, secret-free authority document at the
configured path. The rendered local service uses
`/var/lib/asklegal/review/review-authority.json`:

```json
{"authority_evidence_fingerprint":"sha256:<64-lowercase-hex>","authority_evidence_id":"evi_<48-lowercase-hex>","reviewer_identity_fingerprint":"sha256:<64-lowercase-hex>","reviewer_identity_id":"act_<48-lowercase-hex>","roles":["PipelineAdministrator"],"schema_id":"asklegal.local-review-authority/v1","subject":"<exact-named-human-subject>"}
```

The identifiers and fingerprints are references, not credential values. The
repository has no command that invents or attests these facts. After the user
identifies the named human and authorizes the exact retained configuration,
place it at the configured path with mode `0600`; changing a retained authority
file is drift and is not an in-place edit procedure.

For a first placement only, after inspecting the exact canonical source file
and receiving authority for that host path, the rendered Review runtime UID is
`3007` and the bounded host command is:

```bash
sudo /usr/bin/install --owner=3007 --group=3007 --mode=0600 \
  /absolute/path/to/reviewed-review-authority.json \
  /var/lib/asklegal/review/review-authority.json
```

Do not use this command to overwrite an existing retained authority file.

The continuously running Review service rereads and revalidates these current
files beneath `/var/lib/asklegal/review-artifacts` on each projection read:

```text
hk-v1-two-family-proposal.json
hk-v1-review-readiness.json
hk-v1-review-package.json
```

It therefore discovers a newly retained valid package without restart and
fails closed while a partial or inconsistent replacement is visible. Evidence
requests return the exact retained evidence-bearing traceability row, never a
synthetic success body. Legal Processing, not Review, owns publication of the
package files.

There is no Approval CLI. The named human reviews the package through the
Review application and submits `APPROVE` or `REJECT` there. On `APPROVED`,
Review first retains the exact package tree under:

```text
/var/lib/asklegal/review/approved-packages/<exact-approval-id>/
```

It then persists the Approval ledger and atomically creates the canonical
wakeup item:

```text
/var/lib/asklegal/review/promotion-triggers/<exact-approval-id>.json
```

The trigger binds the Approval to one stable `exe_...` execution lineage.
Restart or exact replay repairs the narrow ledger-durable/trigger-absent crash
window. Do not create, copy, edit, or delete a promotion trigger manually.

### 8. Promotion

Promotion continuously scans the retained Review trigger directory and
idempotently schedules `promote_approved_hk_v1` using the trigger's stable
execution-lineage ID. At activity execution it rereads the same trigger, the
retained Approval ledger, the retained Review authority, and the
Approval-specific archived package. It does not consume whichever proposal is
merely current in the Review display.

The worker remains `NOT_READY` or fails visibly if any required serving
profile, exact tokenizer resource, current Serving State, effect-intent ledger,
Approval/package/authority binding, credential, backup root, or provider
boundary is absent or drifted. `asklegal-promotion-worker --check` checks the
older local runtime and is not proof that continuous V1 promotion is ready.
There is no manual promotion-trigger CLI and the removed
`ASKLEGAL_PROMOTION_TRIGGER` single-file input must not be recreated.

Starting or enabling the Promotion service when a valid retained Approval and
effect intents are present can reach embedding, backup, Pinecone, and routing
effects. Do so only under exact user authority for that frozen Approval and
the admitted profiles, credentials, target, budget, and effect intents. Review
never receives those credentials and performs none of those effects.

After that authority is recorded, the bounded service action is:

```bash
sudo /usr/bin/systemctl start asklegal-promotion-worker.service
```

This command is not a dry run. Prefer the already supervised service when it is
running; its trigger scan is continuous and restart-safe. A failed stable
Promotion orchestration remains fail-visible for investigation—do not delete
its trigger or invent a second execution-lineage ID to force another attempt.

### 9. Rollback and restoration

Promotion contains exact internal rollback checkpoints for a failed
in-progress promotion, and credential rotation restores the predecessor
binding when its authorized execution cannot prove the candidate. Those are
bounded compensations inside their owning operation; they are not general
operator rollback commands.

The standalone local Serving-State tool plans the exact T2→T1→T2 operation
from the canonical current Serving State and retained T1/T2 Promotion
readbacks. Planning validates the declared predecessor, candidate, activation
receipt, targets, backups, and readback fingerprints. It does not change the
Serving State or call a source, provider, index, or routing boundary:

```bash
umask 077
.venv/bin/python -m tools.hk_v1_serving_state_transition \
  --serving-state /var/lib/asklegal/promotion/current-serving-state \
  --t1-readback /absolute/path/to/t1-promotion-readback.json \
  --t2-readback /absolute/path/to/t2-promotion-readback.json \
  --receipt-root /absolute/path/to/var/hk-v1/acceptance/rollback \
  --output /absolute/path/to/var/hk-v1/acceptance/plans/serving-transition.json
```

The detached authority is not generated by the tool. Create it only after the
user authorizes mutation of the exact plan. It must be canonical schema
`asklegal.hk-v1-serving-state-transition-authority/v1`, version `1.0.0`, with
an `auth_<48-lowercase-hex>` authority ID, the exact operation ID, plan
fingerprint, Serving-State path, T1 and T2 state IDs, ordered operations
`["ROLLBACK_T2_TO_T1","RESTORE_T1_TO_T2"]`, decision `AUTHORIZED`, and its
own SHA-256 fingerprint.

After that exact authority exists, this command mutates only the local
Serving-State compare-and-set projection:

```bash
umask 077
.venv/bin/python -m tools.hk_v1_serving_state_transition \
  --execute \
  --plan /absolute/path/to/var/hk-v1/acceptance/plans/serving-transition.json \
  --authority /absolute/path/to/serving-transition-authority.json \
  --output /absolute/path/to/var/hk-v1/acceptance/rollback/final-report.json
```

The tool atomically retains stable rollback and restoration receipts plus
Gate-G-shaped `rollback-readback.json` and `restoration-readback.json` under
the plan's receipt root. Exact replay returns the same report; state or
evidence drift stops before another mutation. It never deletes an index or
changes Ask.Legal routing.

The recovery CLI now has an exact `PLAN_LIVE` and authority-gated
`EXECUTE_LIVE` path. It deliberately remains `NOT_READY` unless the two fixed
privileged helpers, five sealed credential references, exact SQL backup
mapping, clean-room root, state root, retained plan, and detached authority are
all available. `EXECUTE_LOCAL_PROTOTYPE`, file copying, direct state-file
editing, manual trigger creation, or a container restart is not a substitute
for the live SQL/vault/Scheduler read-back contract.

### 10. Archive-before-cleanup plan and gated execution

The default archive command inventories only explicitly repeated candidate and
protected paths. It emits recursive size, SHA-256, mode, and modification-time
metadata; it does not copy or delete anything. Every protection category is
required, and each option may be repeated for additional exact paths:

```bash
umask 077
.venv/bin/python -m tools.hk_v1_archive_cleanup \
  --destination /absolute/path/to/distinct-approved-archive \
  --candidate /absolute/path/to/exact-old-cycle \
  --latest-journal /absolute/path/to/latest-journal \
  --current-baseline /absolute/path/to/current-baseline \
  --fixture /absolute/path/to/fixtures \
  --approval-state /absolute/path/to/review-approval-state \
  --promotion-evidence /absolute/path/to/promotion-evidence \
  > /absolute/path/to/hk-v1/archive/archive-plan.json
```

Plan exit `0` means the canonical inventory was emitted. Exit `2` emits only
`ARCHIVE_CLEANUP_NOT_READY`; do not authorize a partial or empty redirected
file. The destination, candidates, complete inventory, and protection set are
all fingerprint-bound.

Execution requires a separately reviewed, exact authority file for that plan
fingerprint and destination. It copies every candidate, recursively reads all
copies back, and only then deletes the exact authorized source paths:

```bash
.venv/bin/python -m tools.hk_v1_archive_cleanup \
  --execute \
  --plan-file /absolute/path/to/hk-v1/archive/archive-plan.json \
  --authority /absolute/path/to/exact-archive-authority.json
```

Exit `0` means all exact copies were verified and all exact authorized sources
were deleted, with a retained terminal state. Exit `2` emits
`ARCHIVE_CLEANUP_NOT_READY`; source drift, authority drift, read-back failure,
or path/symlink drift blocks deletion. Replay the same plan and authority after
an interruption so completed checkpoints are verified and reused. A new plan,
changed destination, or broader deletion requires new exact authority.

## Reading progress

Read the replay-derived local state without starting or rerunning either family:

```bash
/usr/bin/docker exec asklegal-acquisition-worker asklegal-acquisition-worker \
  --show-hk-v1-progress \
  --state-root /var/lib/asklegal/acquisition/due-cycle \
  --cases-cycle-id <retained-cases-cycle-id> \
  --legislation-cycle-id <retained-legislation-cycle-id> \
  --cases-result <exact-cases-manifest-path> \
  --legislation-result <exact-legislation-manifest-path>
```

Omit a family result path while that family is still running. The projection
cannot report `COMPLETE` unless both supplied result manifests are canonical,
replay-head-bound `COMPLETE` or `NO_CHANGE` results. Missing, unreadable,
corrupt, or incoherent retained state exits nonzero and prints only
`HK_V1_PROGRESS_UNAVAILABLE` to standard error. `NOT_STARTED` means both exact
cycle journals exist but contain no discovered work.

For both `CASES` and `LEGISLATION`, the operator projection exposes:

- discovered, verified, retryable, rejected, terminal, active, and queued
  counts;
- retained byte count;
- the exact journal-head fingerprint; and
- the sealed family result and result fingerprint, when present; and
- the timestamp of the last retained progress.

Arithmetic is exact: terminal equals verified plus rejected, and discovered
equals terminal plus retryable plus active plus queued. A stale or mismatched
journal head is an integrity failure, not zero progress. Do not infer completion
from a percentage, elapsed time, empty page, remote acknowledgement, or process
exit code.

## Restart and missed-run handling

1. Do not delete or rename the current schedule ledger, acquisition journal,
   evidence objects, or predecessor state.
2. Identify the schedule kind and intended Hong Kong slot from the retained
   enqueue result and timer journal.
3. Re-enqueue that exact slot. A deterministic manual replay requires both the
   exact retained scheduled-at value and the original retained 32-hex delivery
   ID as `--invocation-id`; obtain both from the retained enqueue result and
   timer journal. Never invent a new ID or substitute the current time:

   ```bash
   /usr/bin/docker exec asklegal-control-plane asklegal-control-plane \
     --enqueue-schedule <OBSERVATION-or-RECONCILIATION> \
     --scheduled-at <exact-retained-scheduled-at-value> \
     --invocation-id <exact-retained-32-hex-delivery-id>
   ```

   The systemd services provide `${INVOCATION_ID}` automatically for ordinary
   timer delivery; an operator supplies it explicitly only for a manual exact
   replay.
4. Confirm that the returned command ID, cycle ID, and journal head match the
   retained lineage before permitting further work.
5. If the result is `INCOMPLETE_RETRYABLE`, leave successful items retained and
   allow only the remaining eligible work to resume.
6. If the result is terminal, integrity-failed, authorization-failed, or
   source-contract-changed, stop that affected lineage and investigate. Do not
   relabel it as no-change.

## Review, Approval, and promotion

The Review application reads the explicit canonical local proposal, readiness,
and executable package bytes. The human must inspect the four scope
dispositions, limitations, exact target members and zero scopes, model and
embedding profiles, target and namespace, backups, rollback facts, and proposal
fingerprint. Approval is named, fingerprint-bound, retained, and single-use.

Any changed package, evidence, profile, target, backup, scope, member, or
predicate invalidates the old Approval. Promotion may begin only from the same
retained approved package and exact effect intents. Azure calls, Pinecone
writes, backups, and Serving-State changes require the separately admitted
profiles, credentials, budgets, and explicit live-effect authority. Pinecone
deletion is a different authority and is not part of ordinary V1 operation.

## Admission and incident response

The live report keeps these boundaries separate:

- Gate A: exact two-family Coverage Matrix and source authority;
- Gate B: complete official-source, retry, restart, no-change, incomplete, and
  contract-drift evidence;
- Gate C: all four legal-package scopes and release accounting;
- Gate D: exact model, embedding, tokenizer, and two evaluation runs;
- Gate E: Review, Approval/invalidation, promotion/failure stop, replacement
  target, read-back, backup, and rollback;
- Gate F: supervision, schedules, observability, recovery, and restart; and
- Gate G: the complete live baseline, changed/no-change cycles, reboot,
  rollback/restoration, and next-cycle health.

Keep the previous verified Serving State current when any pre-activation gate
fails. Preserve the evidence and exact blocker code. For uncertain provider or
target acknowledgement, reconcile by read-back before retrying. Never repeat a
write merely because the acknowledgement was lost.

Produce the owner-bound operational composites only after their exact inputs
exist. `schedule-live` reads all five completed Control schedule instances and
their retained maintenance results. `gate-f` then binds that schedule result to
the complete host snapshot, operational status, host-apply state, credential
rotation reports, live recovery result, restart evidence, and actual Serving
State. `gate-g` binds the exported baseline/update/no-change results to the two
promotions, reboot snapshots, rollback/restoration readbacks, post-reboot
scheduled cycles, and next-health proof:

```bash
.venv/bin/python -m tools.hk_v1_operational_evidence schedule-live --help
.venv/bin/python -m tools.hk_v1_operational_evidence gate-f --help
.venv/bin/python -m tools.hk_v1_operational_evidence gate-g --help
```

These commands only read owner artifacts and create exact local files. They do
not schedule, reboot, call a source/provider, mutate Serving State, or repair a
failed proof. Retry attempts are accepted only when the retained schedule state,
deterministic attempt number, Scheduler instance, and maintenance result all
bind to the same lineage.

Evaluate only a canonical retained admission manifest whose evidence locators
resolve below one explicit local evidence root:

```bash
.venv/bin/python -m tools.hk_v1_live_admission \
  --manifest /absolute/path/to/admission.json \
  --evidence-root /absolute/path/to/retained-evidence
```

Exit `0` means `V1_ADMITTED`; exit `1` is a valid but blocked
`NOT_ADMITTED` report, including retained-evidence read-back blockers. Exit `2`
means the manifest or invocation input itself is missing, unreadable,
malformed, or noncanonical. The evaluator reads and hash-checks every envelope,
owning-boundary receipt, and underlying proof. The Approval proof must be the
retained Task 8 Approval ledger in consumed, non-revoked state; a generic
hash-wrapped file cannot satisfy it.

## Current authorization boundary

Repository edits, local deterministic tests, read-only dry-run inspection, and
rendering disabled units are allowed. Stop and request exact user authority
before:

- accepting new or changed publisher terms or bypassing a source challenge;
- live Azure model or embedding calls;
- Pinecone create, upsert, backup, or Serving-State mutation;
- a named human Approval of a frozen proposal;
- applying the host reconcile plan, rotating credentials, or rebooting;
- rollback or restoration of a named Serving State; or
- copying to a secondary disk and deleting exact archived source paths.

Commit, push, publication, deployment, Ask.Legal routing, and broad deletion
are not implied by this runbook.
