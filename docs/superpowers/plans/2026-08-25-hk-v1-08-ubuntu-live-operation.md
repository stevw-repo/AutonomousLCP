# Continuous Ubuntu V1 Operation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the local Ubuntu host into a supervised, current, credential-rotated, scheduled, observable, recoverable V1 stack.

**Architecture:** Extend the repository-owned topology, systemd-unit, host-fact, and admission tools. Desired state remains declarative and read-only comparison runs first; a separate authorization-gated apply command performs exact container/unit/credential changes. Five persistent timers enqueue durable work, while SQL leases prevent overlap. Local structured telemetry and Review dashboards expose source, workflow, coverage, provider, storage, and promotion failures without an external monitoring service.

**Tech Stack:** Ubuntu 24.04.4 LTS, systemd units/timers/credentials, rootless or least-privilege container runtime as already admitted by the V1 topology, SQL Server, two Durable Task scheduler instances, vault gateways, egress proxies, local telemetry collector, Python 3.14.7 tooling, Pytest.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- The declared target contains five applications, SQL Server, two independent scheduler instances, two vault gateways, three egress proxies, and one telemetry collector.
- `acq-batch`, `cp-test`, and every other unsupervised pipeline container are absent from admitted state.
- Images are selected by immutable identity, not mutable tags.
- Credentials are sealed; obsolete plaintext staging is removed only after new values work and old values are proved unusable.
- Timers are persistent and durable; missed runs catch up, overlapping runs do not duplicate work, and shutdown/restart is safe.
- Exact schedules use Asia/Hong_Kong time: daily observation 02:15, weekly full reconciliation Sunday 03:15, daily audit archive 04:30, weekly recovery verification Monday 05:15, and daily telemetry retention 06:00.
- Host mutation, credential rotation, service replacement, container removal, and reboot require exact authority at Task 7.

## Dependency and exit contract

Depends on Plan 7's disabled-by-default real Review/Promotion composition and Plans 1–6 application images. Produces:

```python
def collect_hk_v1_host_facts() -> HKV1HostFacts: ...


def evaluate_hk_v1_host_admission(
    desired: HKV1HostTopology,
    actual: HKV1HostFacts,
) -> HKV1HostAdmissionReport: ...
```

Plan 9 consumes an admitted host report, active timer identities, backup/restore proof, scheduler-replacement proof, and reboot evidence.

## File structure

- Modify `tools/v1_poc_topology.py`, `v1_poc_systemd_units.py`, `v1_poc_render_units.py`, and tests — live topology and five timers.
- Modify `tools/v1_poc_collect_host_facts.py` and `v1_poc_host_admission.py` — complete read-only host facts and blockers.
- Create `tools/hk_v1_host_reconcile.py` — plan/apply boundary with exact target list and dry-run default.
- Modify `tools/v1_poc_credential_interface.py` — staged rotation/read-back/old-value rejection.
- Implement `packages/observability` structured events and local status aggregation.
- Modify Review API to display operational status and local alerts.
- Create backup/restore and scheduler-replacement proof tools under `tools/`.

---

### Task 1: Make current-host collection complete and privilege-aware

**Files:**
- Modify: `tools/v1_poc_collect_host_facts.py`
- Modify: `tools/v1_poc_host_admission.py`
- Test: `tools/tests/test_v1_poc_collect_host_facts.py`
- Test: `tools/tests/test_v1_poc_host_admission.py`

**Interfaces:**
- Consumes: read-only systemd/container/network/filesystem commands.
- Produces: complete `HKV1HostFacts` or an explicit `HOST_FACTS_INCOMPLETE` result with missing fact classes.

- [ ] **Step 1: Write failing incomplete-permission tests**

```python
def test_network_permission_failure_is_reported_as_incomplete_not_exception() -> None:
    facts = collect_with(scripted_command("nft list ruleset", permission_denied()))
    assert facts.complete is False
    assert "NETWORK_POLICY" in facts.missing_fact_classes


def test_admission_cannot_pass_with_incomplete_facts() -> None:
    report = evaluate_hk_v1_host_admission(desired_topology(), incomplete_host_facts())
    assert report.admitted is False
    assert "HOST_FACTS_INCOMPLETE" in report.blocker_codes
```

- [ ] **Step 2: Run and observe current collector failure behavior**

Run: `python3 -m pytest tools/tests/test_v1_poc_collect_host_facts.py tools/tests/test_v1_poc_host_admission.py -q`

Expected: new privilege-aware assertions fail until incomplete fact classes are modeled.

- [ ] **Step 3: Implement complete fact categories and sanitization**

Collect OS/kernel, systemd target/unit/timer states, immutable image IDs, container names/health, ports/listeners, network-policy summaries, resource limits/usage, disk mounts/free space, credential metadata without values, backup ages, scheduler identities, telemetry freshness, and application readiness. Add `--output` so the collector writes canonical facts without a shell redirection; retain explicit read-only acknowledgement. Never print environment values or secret bytes.

- [ ] **Step 4: Run collector/admission tests and a read-only local snapshot**

Run: `python3 -m pytest tools/tests/test_v1_poc_collect_host_facts.py tools/tests/test_v1_poc_host_admission.py -q`

Expected: all synthetic tests pass.

Run: `python3 -m tools.v1_poc_collect_host_facts --acknowledge-read-only-host-inspection --output var/hk-v1/host/observed.json`

Expected: no mutation; either complete facts or exact permission blockers.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- tools/v1_poc_collect_host_facts.py tools/v1_poc_host_admission.py tools/tests`

Expected: read-only collector/admission changes. Commit only with exact user authorization.

### Task 2: Freeze current images, supervised topology, and orphan detection

**Files:**
- Modify: `tools/v1_poc_topology.py`
- Modify: `tools/v1_poc_application_images.py`
- Modify: `tools/v1_poc_systemd_units.py`
- Modify: `tools/tests/test_v1_poc_topology.py`
- Modify: `tools/tests/test_v1_poc_application_images.py`
- Modify: `tools/tests/test_v1_poc_systemd_units.py`

**Interfaces:**
- Consumes: reproducible current application image admission results.
- Produces: one exact desired topology and orphan-container blocker set.

- [ ] **Step 1: Write failing immutable-image and orphan tests**

```python
def test_every_application_unit_uses_admitted_image_digest() -> None:
    topology = build_v1_topology(admitted_images())
    assert all("@sha256:" in app.image_reference for app in topology.applications)


def test_unmanaged_pipeline_containers_block_host_admission() -> None:
    report = evaluate_hk_v1_host_admission(desired_topology(), facts_with("acq-batch", "cp-test"))
    assert set(report.orphan_pipeline_containers) == {"acq-batch", "cp-test"}
    assert report.admitted is False
```

- [ ] **Step 2: Run and observe mutable/old host assumptions**

Run: `python3 -m pytest tools/tests/test_v1_poc_topology.py tools/tests/test_v1_poc_application_images.py tools/tests/test_v1_poc_systemd_units.py -q`

Expected: new immutable/current/orphan assertions fail.

- [ ] **Step 3: Update desired topology and generated units**

Bind each application image by admitted digest and include resource limits, read-only filesystem, exact credential names, networks, proxy routes, health probes, restart policy, stop timeout, and dependency ordering. Detect any running pipeline container not declared by exact name/image/unit ownership. Extend the render CLI with an explicit `--output` root used only for deterministic preview trees; installation remains a separate reconcile action.

- [ ] **Step 4: Regenerate units twice and compare**

Run: `python3 -m tools.v1_poc_render_units --output var/hk-v1/units/run-1`

Run again with `--output var/hk-v1/units/run-2`.

Expected: canonical trees are byte-identical.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- tools/v1_poc_topology.py tools/v1_poc_application_images.py tools/v1_poc_systemd_units.py tools/tests`

Expected: exact current desired topology and no host mutation. Commit only with exact user authorization.

### Task 3: Generate five durable, non-overlapping systemd timers

**Files:**
- Modify: `tools/v1_poc_systemd_units.py`
- Modify: `tools/v1_poc_render_units.py`
- Modify: `tools/tests/test_v1_poc_systemd_units.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/local_cli.py`
- Create: `apps/control-plane/tests/test_v1_schedules.py`

**Interfaces:**
- Consumes: one timer invocation containing schedule kind and scheduled-at timestamp.
- Produces: five timer/service pairs that enqueue durable commands through Control.

- [ ] **Step 1: Write failing exact-calendar and overlap tests**

```python
def test_v1_timers_have_exact_hong_kong_calendars() -> None:
    units = render_v1_units(topology())
    assert units["asklegal-v1-observation.timer"].on_calendar == "*-*-* 02:15:00 Asia/Hong_Kong"
    assert (
        units["asklegal-v1-reconciliation.timer"].on_calendar == "Sun *-*-* 03:15:00 Asia/Hong_Kong"
    )
    assert units["asklegal-v1-audit-archive.timer"].on_calendar == "*-*-* 04:30:00 Asia/Hong_Kong"
    assert (
        units["asklegal-v1-recovery-verify.timer"].on_calendar
        == "Mon *-*-* 05:15:00 Asia/Hong_Kong"
    )
    assert (
        units["asklegal-v1-telemetry-retention.timer"].on_calendar
        == "*-*-* 06:00:00 Asia/Hong_Kong"
    )


def test_duplicate_timer_delivery_replays_one_durable_command() -> None:
    first = enqueue_schedule("OBSERVATION", SCHEDULED_AT)
    second = enqueue_schedule("OBSERVATION", SCHEDULED_AT)
    assert second.command_id == first.command_id
    assert second.replayed is True
```

- [ ] **Step 2: Run and observe the five timers are absent**

Run: `python3 -m pytest tools/tests/test_v1_poc_systemd_units.py apps/control-plane/tests/test_v1_schedules.py -q`

Expected: tests fail until exact timers and durable enqueue commands exist.

- [ ] **Step 3: Implement persistent timer/service pairs**

Set `Persistent=true`, `AccuracySec=1min`, `RandomizedDelaySec=0`, and service `Type=oneshot`. The service calls Control with schedule kind and the systemd-provided invocation identity. Control derives a stable command ID from `(schedule_kind, scheduled_at)` and acquires the correct cycle lease; overlap returns an exact replay/in-progress result.

- [ ] **Step 4: Run unit, schedule, durability, and timezone tests**

Run: `python3 -m pytest tools/tests/test_v1_poc_systemd_units.py apps/control-plane/tests/test_v1_schedules.py packages/durable-task-adapter/tests/test_in_memory_durability.py -q`

Expected: exact calendars, DST behavior, catch-up, duplicate delivery, overlap, and shutdown/restart tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- tools/v1_poc_systemd_units.py tools/v1_poc_render_units.py tools/tests/test_v1_poc_systemd_units.py apps/control-plane`

Expected: five deterministic timers and durable enqueue behavior. Commit only with exact user authorization.

### Task 4: Implement staged credential rotation and old-value rejection

**Files:**
- Modify: `tools/v1_poc_credential_interface.py`
- Modify: `tools/tests/test_v1_poc_credential_interface.py`
- Create: `tools/hk_v1_rotate_credentials.py`
- Create: `tools/tests/test_hk_v1_rotate_credentials.py`

**Interfaces:**
- Consumes: exact credential manifest, generator/provider commands, sealed systemd credential directory, and per-service health/read-back checks.
- Produces: `CredentialRotationReport` with new-value success, old-value rejection, and plaintext-removal evidence.

- [ ] **Step 1: Write failing rollback and plaintext tests**

```python
def test_failed_new_credential_check_restores_old_sealed_binding() -> None:
    result = rotate_credentials(rotation_plan(), checker=failing_new_value_checker())
    assert result.state == "ROLLED_BACK"
    assert result.old_binding_restored is True


def test_rotation_not_complete_while_plaintext_staging_exists() -> None:
    result = evaluate_rotation(staging_path_exists=True, new_works=True, old_fails=True)
    assert result.complete is False
    assert "PLAINTEXT_STAGING_REMAINS" in result.blocker_codes
```

- [ ] **Step 2: Run and observe no complete rotation workflow**

Run: `python3 -m pytest tools/tests/test_v1_poc_credential_interface.py tools/tests/test_hk_v1_rotate_credentials.py -q`

Expected: collection fails for the new workflow module or new assertions fail.

- [ ] **Step 3: Implement plan, stage, verify, switch, reject, remove**

```python
def rotate_credentials(
    plan: CredentialRotationPlan,
    store: SealedCredentialStore,
    checker: CredentialHealthChecker,
) -> CredentialRotationReport: ...
```

Generate credentials without writing values to stdout, stage sealed versions, restart only exact dependent units, verify new value, prove old value cannot authenticate, then remove obsolete sealed/plaintext staging. On any pre-removal failure, restore the old binding. Never persist secret values in the report.

- [ ] **Step 4: Run rotation and no-secret-log tests**

Run: `python3 -m pytest tools/tests/test_v1_poc_credential_interface.py tools/tests/test_hk_v1_rotate_credentials.py -q`

Expected: all stage/switch/rollback/old-rejection/plaintext/no-log cases pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- tools/v1_poc_credential_interface.py tools/hk_v1_rotate_credentials.py tools/tests`

Expected: a dry-run-capable exact rotation workflow. Commit only with exact user authorization.

### Task 5: Add local operational telemetry, dashboard, and alerts

**Files:**
- Create: `packages/observability/src/asklegal_observability/events.py`
- Create: `packages/observability/src/asklegal_observability/status.py`
- Modify: `packages/observability/src/asklegal_observability/__init__.py`
- Create: `packages/observability/tests/test_events.py`
- Create: `packages/observability/tests/test_status.py`
- Modify: `apps/review-api/src/asklegal_review_api/api.py`
- Modify: `apps/review-api/src/asklegal_review_api/client/app.js`
- Create: `apps/review-api/tests/test_operational_status.py`

**Interfaces:**
- Consumes: sanitized application audit events and telemetry-collector retained NDJSON.
- Produces: `OperationalStatusSnapshot` and local Review status/alert endpoints.

- [ ] **Step 1: Write failing alert and secret-redaction tests**

```python
def test_source_failure_is_visible_in_operational_status() -> None:
    status = build_operational_status(events(source_failure_event()))
    assert status.healthy is False
    assert status.alerts[0].code == "SOURCE_CYCLE_BLOCKED"


def test_event_rejects_secret_like_fields() -> None:
    with pytest.raises(ObservabilityError, match="SECRET_FIELD_FORBIDDEN"):
        build_event("provider.call", {"api_key": "secret"})
```

- [ ] **Step 2: Run and observe observability package is empty**

Run: `python3 -m pytest packages/observability/tests apps/review-api/tests/test_operational_status.py -q`

Expected: collection fails for missing modules/tests.

- [ ] **Step 3: Implement closed event schema and status aggregation**

Cover source, workflow, coverage, model, provider, storage, review, promotion, backup, rollback, schedule, disk, and resource events. The collector writes bounded rotating local NDJSON and daily summary artifacts. Review exposes a loopback-authenticated dashboard with last success/failure, current blockers, due/overdue schedules, queue depth, storage/resource status, and unresolved alerts.

- [ ] **Step 4: Run observability and Review tests**

Run: `python3 -m pytest packages/observability/tests apps/review-api/tests/test_operational_status.py -q`

Expected: event validation, redaction, retention boundary, stale-status, and alert tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/observability apps/review-api`

Expected: local-only telemetry/status and no external alert service. Commit only with exact user authorization.

### Task 6: Prove SQL/vault restore and independent scheduler replacement

**Files:**
- Create: `tools/hk_v1_recovery_proof.py`
- Create: `tools/tests/test_hk_v1_recovery_proof.py`
- Modify: `tools/v1_poc_host_admission.py`

**Interfaces:**
- Consumes: exact backup refs, disposable restore targets, and two scheduler instance identities.
- Produces: `HKV1RecoveryProof` with SQL restore, vault read-back, and scheduler A/B replacement evidence.

- [ ] **Step 1: Write failing independence tests**

```python
def test_scheduler_replacement_requires_distinct_instance_identity() -> None:
    with pytest.raises(RecoveryProofError, match="SCHEDULER_NOT_INDEPENDENT"):
        prove_scheduler_replacement(instance_a(), same_instance_as_a())


def test_sql_backup_ack_without_restored_readback_fails() -> None:
    result = prove_sql_restore(backup_ack_only())
    assert result.passed is False
    assert result.failure_code == "SQL_RESTORE_READBACK_FAILED"
```

- [ ] **Step 2: Run and observe proof tool is absent**

Run: `python3 -m pytest tools/tests/test_hk_v1_recovery_proof.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement exact disposable recovery workflows**

Back up current register state, restore to a new explicitly named disposable database, compare required tables/projections/fingerprints, read primary/recovery vault objects, stop scheduler A while B drains/replays durable work, then reverse roles. Cleanup commands must target only generated disposable names and require explicit cleanup authority.

- [ ] **Step 4: Run synthetic and isolated local proofs**

Run: `python3 -m pytest tools/tests/test_hk_v1_recovery_proof.py -q`

Expected: all synthetic failure cases pass.

Run the proof against repository-owned isolated local services only after confirming that exact authority. Expected: restored read-back matches, each scheduler independently substitutes for the other, and no live V1 state is changed.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- tools/hk_v1_recovery_proof.py tools/tests/test_hk_v1_recovery_proof.py tools/v1_poc_host_admission.py`

Expected: exact recovery proof tooling and blockers. Commit only with exact user authorization.

### Task 7: Reconcile the live host and prove reboot recovery

**Files:**
- Create: `tools/hk_v1_host_reconcile.py`
- Create: `tools/tests/test_hk_v1_host_reconcile.py`
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: desired topology, current complete host facts, current admitted images, rotation plan, and exact host-mutation authority.
- Produces: dry-run plan or exact applied reconciliation report plus post-reboot admitted host report.

- [ ] **Step 1: Write the dry-run and exact-target tests**

```python
def test_reconcile_defaults_to_plan_only() -> None:
    result = reconcile_host(arguments(mode="plan"), scripted_host())
    assert result.mutations_performed == ()
    assert set(result.orphans_to_remove) == {"acq-batch", "cp-test"}


def test_apply_refuses_target_not_in_frozen_plan() -> None:
    with pytest.raises(HostReconcileError, match="UNPLANNED_TARGET"):
        reconcile_host(arguments(mode="apply", target="unrelated-container"), scripted_host())
```

- [ ] **Step 2: Implement and run the plan-only command**

Run: `python3 -m tools.hk_v1_host_reconcile --mode plan --facts var/hk-v1/host/observed.json --output var/hk-v1/host/reconcile-plan.json`

Expected: exact unit/image/credential/timer/orphan changes are listed; no mutation occurs.

- [ ] **Step 3: Stop and obtain exact host authority**

Require explicit authority for removing only the named orphan containers, installing/reloading exact unit files, rotating the named credentials, replacing exact application containers, running local migrations, and rebooting this Ubuntu host. Resolve any unplanned current host difference before apply.

- [ ] **Step 4: Apply in reversible order and verify before reboot**

Run: `python3 -m tools.hk_v1_host_reconcile --mode apply --plan var/hk-v1/host/reconcile-plan.json --output var/hk-v1/host/reconcile-result.json`

The CLI recomputes and verifies the approved plan's embedded fingerprint before any mutation. Stage units/credentials, migrate with backup, start current stack, run readiness and source/provider capability checks, prove old credentials fail, then remove only exact obsolete/orphan targets. Run the full host collector and require host admission except the reboot gate.

- [ ] **Step 5: Reboot and prove admitted recovery**

After separately confirming reboot authority, reboot once. Verify target/services/timers, SQL, both schedulers, vaults, proxies, telemetry, Review auth, durable queue recovery, and no orphan. Run:

`python3 -m tools.v1_poc_collect_host_facts --acknowledge-read-only-host-inspection --output var/hk-v1/host/post-reboot.json`

`python3 -m tools.v1_poc_host_admission --facts var/hk-v1/host/post-reboot.json`

Expected: Gate F passes. Record exact mutations, removed targets and recoverability, reboot evidence, and external effects in `.agent/WORKING_STATE.md`. Request explicit commit authority before the Plan 8 checkpoint.
