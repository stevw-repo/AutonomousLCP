"""M3 framework-free configuration, local-adapter, and worker proofs."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from asklegal_application_runtime import (
    ApplicationConfiguration,
    ConfigurationError,
    ConfigurationErrorCode,
    DisabledEffectPort,
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalCommandRegister,
    LocalPaginationStore,
    LocalTaskHub,
    WorkerResultCode,
    WorkerRuntime,
    WorkLease,
    build_local_configuration,
)
from asklegal_contracts import canonicalize, fingerprint
from asklegal_contracts.json_types import JsonValue


def _unsigned_configuration() -> dict[str, JsonValue]:
    return {
        "application_code": "TEST_WORKER",
        "build_ref": "bld_" + "1" * 48,
        "contract_set_ref": "cst_" + "2" * 48,
        "environment": "LOCAL_TEST",
        "identity": {"audience": "api://test", "client": "test-client"},
        "limits": {
            "lease_seconds": 30,
            "max_body_bytes": 1024,
            "max_concurrency": 1,
            "max_retries": 2,
            "shutdown_seconds": 5,
        },
        "logging_policy": "SAFE_METADATA_ONLY",
        "network_destinations": [],
        "policy_profile_refs": ["pol_" + "3" * 48],
        "register_procedures": ["resolve_command_v1"],
        "register_views": ["application_readiness_v1"],
        "revision": "r1",
        "schema_version": 1,
        "secret_references": ["secretref:test/local"],
        "task_hub": "test-hub",
    }


def _configuration_bytes(unsigned: dict[str, JsonValue]) -> bytes:
    return canonicalize({**unsigned, "configuration_fingerprint": fingerprint(unsigned)})


def test_configuration_is_closed_fingerprinted_and_contains_only_secret_refs() -> None:
    """Reject drift, unknown settings, and raw secret material before readiness."""
    unsigned = _unsigned_configuration()
    assert ApplicationConfiguration.from_bytes(_configuration_bytes(unsigned)).revision == "r1"

    unknown = {**unsigned, "unexpected": "value"}
    with pytest.raises(ConfigurationError) as error:
        ApplicationConfiguration.from_bytes(_configuration_bytes(unknown))
    assert error.value.code is ConfigurationErrorCode.INVALID

    raw_secret: dict[str, JsonValue] = {
        **unsigned,
        "secret_references": ["plaintext-secret"],
    }
    with pytest.raises(ConfigurationError) as error:
        ApplicationConfiguration.from_bytes(_configuration_bytes(raw_secret))
    assert error.value.code is ConfigurationErrorCode.RAW_SECRET

    complete = {**unsigned, "configuration_fingerprint": "sha256:" + "0" * 64}
    with pytest.raises(ConfigurationError) as error:
        ApplicationConfiguration.from_bytes(canonicalize(complete))
    assert error.value.code is ConfigurationErrorCode.FINGERPRINT_MISMATCH


def test_local_command_register_has_exact_replay_and_conflict() -> None:
    """Prove idempotency is exact and stale aggregate versions cannot apply."""
    register = LocalCommandRegister()
    body: dict[str, JsonValue] = {"action": "TEST"}
    command_id = "cmd_" + "1" * 48
    first = register.submit(command_id=command_id, target="target-1", expected_version=0, body=body)
    replay = register.submit(
        command_id=command_id, target="target-1", expected_version=0, body=body
    )
    assert first.result_ref == replay.result_ref
    assert replay.resolution == "EXACT_REPLAY"
    with pytest.raises(LocalAdapterError) as error:
        register.submit(command_id=command_id, target="target-2", expected_version=0, body=body)
    assert error.value.code is LocalAdapterErrorCode.COMMAND_ID_CONFLICT
    with pytest.raises(LocalAdapterError) as error:
        register.submit(
            command_id="cmd_" + "2" * 48, target="target-1", expected_version=0, body=body
        )
    assert error.value.code is LocalAdapterErrorCode.STALE_VERSION


def test_worker_stale_fencing_and_cooperative_shutdown() -> None:
    """A superseded or interrupted lease cannot complete as current work."""
    configuration = build_local_configuration(
        "TEST_WORKER", audience="api://test", client="test", task_hub="test-hub"
    )
    task_hub = LocalTaskHub(("work-1",))
    runtime = WorkerRuntime(configuration, task_hub, DisabledEffectPort("test"))

    def supersede(lease: WorkLease) -> None:
        """Supersede the current lease generation during bounded work."""
        task_hub.reissue(lease.work_id)

    result = runtime.run_once(supersede)
    assert result is WorkerResultCode.STALE_FENCE

    task_hub = LocalTaskHub(("work-2",))
    runtime = WorkerRuntime(configuration, task_hub, DisabledEffectPort("test"))

    def interrupt(_lease: WorkLease) -> None:
        """Request cooperative shutdown during bounded work."""
        runtime.shutdown()

    result = runtime.run_once(interrupt)
    assert result is WorkerResultCode.INTERRUPTED
    assert task_hub.interruptions == ["work-2:1"]
    assert runtime.accepting_work is False


def test_disabled_effect_port_never_implies_success() -> None:
    """M3 startup fakes fail closed for every unauthorized effect."""
    port = DisabledEffectPort("provider")
    with pytest.raises(LocalAdapterError) as error:
        port.invoke({"ref": "synthetic"})
    assert error.value.code is LocalAdapterErrorCode.DISABLED


def test_pagination_tokens_expire_and_reject_changed_bindings() -> None:
    """Opaque cursors cannot cross their caller, snapshot, filter, sort, or expiry."""
    now = [datetime(2026, 8, 16, tzinfo=UTC)]
    store = LocalPaginationStore(secret=b"synthetic-test-key", clock=lambda: now[0])
    cursor = store.next_cursor(
        snapshot="snapshot-1",
        filters=(("status", "REVIEW_READY"),),
        sort="proposal_id",
        subject="person-1",
        offset=2,
    )
    token = store.issue(cursor)
    assert (
        store.resolve(
            token,
            snapshot="snapshot-1",
            filters=(("status", "REVIEW_READY"),),
            sort="proposal_id",
            subject="person-1",
        ).offset
        == 2
    )
    with pytest.raises(LocalAdapterError):
        store.resolve(
            token,
            snapshot="snapshot-1",
            filters=(("status", "REJECTED"),),
            sort="proposal_id",
            subject="person-1",
        )
    now[0] += timedelta(minutes=16)
    with pytest.raises(LocalAdapterError) as error:
        store.resolve(
            token,
            snapshot="snapshot-1",
            filters=(("status", "REVIEW_READY"),),
            sort="proposal_id",
            subject="person-1",
        )
    assert error.value.code is LocalAdapterErrorCode.CONTINUATION_INVALID


def test_configuration_revision_is_immutable() -> None:
    """Changing configuration produces a replacement revision, not mutation."""
    configuration = build_local_configuration(
        "TEST_WORKER", audience="api://test", client="test", task_hub="test-hub"
    )
    replacement = replace(configuration, revision="r2")
    assert configuration.revision == "local-r1"
    assert replacement.revision == "r2"
