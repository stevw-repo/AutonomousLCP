"""M3 Review API, pagination, authorization, and browser-client proofs."""

# Pytest retains fixture functions through decorator registration.
# pyright: reportUnusedFunction=false

import asyncio
import os
import shutil
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_application_runtime import (
    CredentialMaterial,
    LocalIdentityVerifier,
    Principal,
    TokenType,
)
from asklegal_contracts import canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_management_register_ports import ApprovalConsumption, ManifestSnapshot
from asklegal_review_api.api import (
    LocalRetainedApprovalRegister,
    ReviewDependencies,
    create_app,
    local_dependencies,
)
from asklegal_review_api.governance import RegisteredReviewGovernanceService
from asklegal_review_api.registered_proposals import (
    ProposalProjectionError,
    RegisteredLocalReviewProjectionStore,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

_SEALED_CREDENTIAL = b"review-api-focused-test-credential"
_TOKEN = {"Authorization": f"Bearer {_SEALED_CREDENTIAL.decode('ascii')}"}


@pytest.fixture(autouse=True)
def _retained_review_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give each test explicit pipeline artifacts and one retained Approval ledger."""
    fixture_root = Path(__file__).parent / "fixtures" / "hk_v1_review"
    artifact_root = tmp_path / "pipeline-artifacts"
    shutil.copytree(fixture_root, artifact_root)
    authority_path = tmp_path / "review-authority.json"
    authority_path.write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "authority_evidence_fingerprint": "sha256:" + "2" * 64,
                    "authority_evidence_id": "evi_" + "2" * 48,
                    "reviewer_identity_fingerprint": "sha256:" + "1" * 64,
                    "reviewer_identity_id": "act_" + "1" * 48,
                    "roles": ["PipelineAdministrator"],
                    "schema_id": "asklegal.local-review-authority/v1",
                    "subject": "person-local-1",
                }
            )
        )
    )
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_STATE_ROOT", str(tmp_path / "review-state"))
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH", str(authority_path))
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_DECISION_TIME", "2026-08-16T00:00:00Z")
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_COMMAND_EXPIRES_AT", "2026-08-16T00:05:00Z")


_COMMAND = "cmd_" + "a" * 48
_PROPOSAL_ID = "ppk_fad5056d2d75286f47dbaf45fb84447745d0dff12d1aa960"
_PERSIST_FAILURE = "synthetic retained-write failure"
_MANIFEST_FINGERPRINT = "sha256:6109575c9707df0fb10d6c849d8f16b96dd86f5453747ede204e6049dd4ef675"


class LocalClient:
    """Tiny synchronous wrapper around HTTPX's in-process ASGI transport."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def __enter__(self) -> LocalClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
    ) -> Response:
        async def send() -> Response:
            transport = ASGITransport(app=self._app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="https://service.test") as client:
                return await client.request(method, path, headers=headers, json=json)

        return asyncio.run(send())

    def get(self, path: str, *, headers: Mapping[str, str] | None = None) -> Response:
        return self.request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
    ) -> Response:
        return self.request("POST", path, headers=headers, json=json)


def _decision(client: LocalClient, *, body: object, command: str = _COMMAND) -> Response:
    return client.post(
        f"/api/v1/proposal-packages/{_PROPOSAL_ID}/decisions",
        headers={
            **_TOKEN,
            "Content-Type": "application/json",
            "Idempotency-Key": command,
            "If-Match": '"v0"',
        },
        json=body,
    )


def _sealed_dependencies() -> ReviewDependencies:
    return local_dependencies(review_api_credential=CredentialMaterial(_SEALED_CREDENTIAL))


def _sealed_app() -> FastAPI:
    return create_app(_sealed_dependencies())


def _cold_dependencies(tmp_path: Path) -> ReviewDependencies:
    artifact_root = tmp_path / "cold-artifacts"
    artifact_root.mkdir()
    state_root = tmp_path / "cold-state"
    state_root.mkdir()
    return local_dependencies(
        state_root=state_root,
        artifact_root=artifact_root,
        authority_path=Path(os.environ["ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH"]),
        review_api_credential=CredentialMaterial(_SEALED_CREDENTIAL),
    )


def test_review_authenticates_only_the_exact_sealed_credential() -> None:
    """A source-known placeholder cannot impersonate the retained named reviewer."""
    with LocalClient(_sealed_app()) as client:
        assert client.get("/api/v1/proposal-packages", headers=_TOKEN).status_code == 200
        assert (
            client.get(
                "/api/v1/proposal-packages",
                headers={"Authorization": "Bearer local-human"},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/proposal-packages",
                headers={"Authorization": "Bearer review-api-focused-test-credentiax"},
            ).status_code
            == 403
        )


def test_review_startup_openapi_and_exact_surface() -> None:
    """Start independently with an OpenAPI document distinct from control."""
    app = _sealed_app()
    schema = app.openapi()
    assert (
        fingerprint(schema)
        == "sha256:608931b89c4eb48f9a736524bdb3573136f8875f1635e14ba996c8ff43a1b522"
    )
    paths = schema["paths"]
    assert "/api/v1/proposal-packages" in paths
    assert "/api/v1/evidence/{evidence_id}" in paths
    assert all("source-commands" not in path and "pinecone" not in path for path in paths)
    with LocalClient(app) as client:
        assert client.get("/internal/live").status_code == 200
        assert client.get("/internal/ready").status_code == 200


def test_review_detail_exposes_the_exact_package_inventory_without_storage_coordinates() -> None:
    """Detail fields have distinct meaning and all 11 members are accountable."""
    with LocalClient(_sealed_app()) as client:
        response = client.get(f"/api/v1/proposal-packages/{_PROPOSAL_ID}", headers=_TOKEN)

    assert response.status_code == 200
    detail = response.json()
    assert response.headers["etag"] == '"v0"'
    assert detail["proposal"]["proposal_id"] == _PROPOSAL_ID
    assert detail["proposal"]["manifest_fingerprint"] == _MANIFEST_FINGERPRINT
    assert detail["proposal"]["review_version"] == 0
    assert detail["promotion_manifest_id"].startswith("pmn_")
    assert detail["valid_from"] < detail["valid_until"]
    assert detail["validity_predicates"]
    assert detail["base_serving_state_id"].startswith("srv_")
    assert detail["candidate_serving_state_id"].startswith("srv_")
    assert len(detail["artifacts"]) == 11
    assert [item["role"] for item in detail["artifacts"]] == sorted(
        item["role"] for item in detail["artifacts"]
    )
    assert all(item["media_type"] == "application/json" for item in detail["artifacts"])
    assert all(item["fingerprint"].startswith("sha256:") for item in detail["artifacts"])
    serialized = response.text.lower()
    assert "logical_key" not in serialized
    assert "version_id" not in serialized
    assert "vault" not in serialized


def test_review_detail_shows_every_hk_v1_approval_fact() -> None:
    """Hiding any scope, evaluation, backup, or rollback fact breaks informed Approval."""
    scopes = (
        "HK-CASE-BINDING-POST-1997",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    )
    with LocalClient(_sealed_app()) as client:
        response = client.get(f"/api/v1/proposal-packages/{_PROPOSAL_ID}", headers=_TOKEN)

    assert response.status_code == 200
    visible = response.json()["hk_v1_readiness"]
    assert [item["scope_id"] for item in visible["scope_dispositions"]] == list(scopes)
    assert visible["retryable_count"] == 0
    assert visible["model_evaluation_ref"] == "evaluation/model.json"
    assert visible["retrieval_evaluation_ref"] == "evaluation/retrieval.json"
    assert visible["serving_profile_fingerprint"].startswith("sha256:")
    assert visible["target_namespace"] == "synthetic-v1"
    assert visible["backup_profile_fingerprint"].startswith("sha256:")
    assert [item[0] for item in visible["target_members"]] == [
        "rec_" + "1" * 48,
        "rec_" + "2" * 48,
    ]
    assert visible["zero_record_scope_ids"] == list(scopes[1:2] + scopes[3:])
    assert visible["target_name"] == "asklegal-dev-hkg-20260816-bbbbbbbbbbbb"
    assert visible["native_backup_ref"]
    assert visible["recovery_backup_ref"]
    assert visible["rollback_state_id"].startswith("srv_")
    assert visible["proposal_fingerprint"] == next(
        item[2]
        for item in response.json()["validity_predicates"]
        if item[0] == "HK_V1_TWO_FAMILY_PROPOSAL"
    )


def test_review_pagination_is_stable_and_caller_bound() -> None:
    """Tokens keep one snapshot/filter/sort/caller binding and stable page contents."""
    deps = _sealed_dependencies()
    snapshot, _generation = deps.projections.load()
    token = deps.pagination.issue(
        deps.pagination.next_cursor(
            snapshot=snapshot,
            filters=(("status", "ALL"),),
            sort="proposal_id",
            subject="person-local-1",
            offset=0,
        )
    )
    with LocalClient(create_app(deps)) as client:
        first = client.get("/api/v1/proposal-packages", headers=_TOKEN)
        assert first.status_code == 200
        assert first.headers["etag"].startswith('"sha256:')
        second = client.get(f"/api/v1/proposal-packages?continuation={token}", headers=_TOKEN)
        repeated = client.get(f"/api/v1/proposal-packages?continuation={token}", headers=_TOKEN)
        assert second.json() == repeated.json()
        assert second.json()["snapshot"] == first.json()["snapshot"]
        assert (
            client.get(
                f"/api/v1/proposal-packages?status=*&continuation={token}", headers=_TOKEN
            ).status_code
            == 400
        )

    deps = _sealed_dependencies()
    other = Principal(
        "other-person",
        deps.configuration.identity_audience,
        deps.configuration.identity_client,
        frozenset({"PipelineAdministrator"}),
        TokenType.DELEGATED_HUMAN,
    )
    deps = ReviewDependencies(
        deps.configuration,
        deps.configuration_source,
        LocalIdentityVerifier({_SEALED_CREDENTIAL.decode("ascii"): other}),
        deps.register,
        deps.projections,
        deps.pagination,
    )
    with LocalClient(create_app(deps)) as client:
        assert (
            client.get(
                f"/api/v1/proposal-packages?continuation={token}", headers=_TOKEN
            ).status_code
            == 400
        )


def test_review_decision_requires_named_human_and_exact_manifest() -> None:
    """App-only tokens and editable/partial manifest attempts cannot decide."""
    deps = _sealed_dependencies()
    app_principal = Principal(
        "automation",
        deps.configuration.identity_audience,
        deps.configuration.identity_client,
        frozenset({"PipelineAdministrator"}),
        TokenType.APPLICATION,
    )
    app_deps = ReviewDependencies(
        deps.configuration,
        deps.configuration_source,
        LocalIdentityVerifier({_SEALED_CREDENTIAL.decode("ascii"): app_principal}),
        deps.register,
        deps.projections,
        deps.pagination,
    )
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed",
    }
    with LocalClient(create_app(app_deps)) as client:
        response = _decision(client, body=body)
        assert response.status_code == 403
        assert response.json()["error_code"] == "AUTH_WRONG_TOKEN_TYPE"

    with LocalClient(_sealed_app()) as client:
        assert _decision(client, body=body).json()["result_code"] == "APPROVED"
        stale = {
            **body,
            "manifest_fingerprint": "sha256:" + "2" * 64,
        }
        assert _decision(client, body=stale, command="cmd_" + "d" * 48).status_code == 412
        assert (
            _decision(
                client,
                body={**body, "replacement_manifest": "forbidden"},
                command="cmd_" + "b" * 48,
            ).status_code
            == 400
        )
        assert (
            _decision(
                client,
                body={"action": "APPROVE", "manifest_fingerprint": "latest", "reason": "bad"},
                command="cmd_" + "c" * 48,
            ).status_code
            == 400
        )


def test_review_rejection_honors_exact_version_and_idempotency() -> None:
    """A named human can reject once and receive the same result on exact replay."""
    body = {
        "action": "REJECT",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "The package needs correction",
    }
    with LocalClient(_sealed_app()) as client:
        first = _decision(client, body=body)
        replay = _decision(client, body=body)
        stale = _decision(client, body=body, command="cmd_" + "f" * 48)

    assert first.status_code == 200
    assert first.json()["result_code"] == "REJECTED"
    assert replay.status_code == 200
    assert replay.json()["resolution"] == "EXACT_REPLAY"
    assert replay.json()["result_ref"] == first.json()["result_ref"]
    assert stale.status_code == 412


def test_review_commands_append_real_governance_facts_and_revoke_exactly() -> None:
    """HTTP decisions and revocations reach the authoritative Approval lifecycle."""
    deps = _sealed_dependencies()
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed complete proposal",
    }
    with LocalClient(create_app(deps)) as client:
        decision = _decision(client, body=body)
        approval_id = decision.json()["result_ref"]
        trigger_path = (
            Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"])
            / "promotion-triggers"
            / f"{approval_id}.json"
        )
        trigger = parse_json_bytes(trigger_path.read_bytes(), max_bytes=10_000)
        assert isinstance(trigger, dict)
        assert trigger["approval_id"] == approval_id
        assert str(trigger["execution_lineage_id"]).startswith("exe_")
        archived_root = (
            Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"]) / "approved-packages" / approval_id
        )
        assert (archived_root / "hk-v1-two-family-proposal.json").read_bytes() == (
            Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
            / "hk-v1-two-family-proposal.json"
        ).read_bytes()
        replay = _decision(client, body=body)
        assert replay.json()["resolution"] == "EXACT_REPLAY"
        restarted = _sealed_dependencies()
        assert isinstance(restarted.register, LocalRetainedApprovalRegister)
        assert restarted.register.get(approval_id).state.value == "APPROVAL_APPROVED"
        proposal_bytes, readiness_bytes = restarted.register.approved_package(approval_id)
        assert proposal_bytes.startswith(b'{"acquisition_manifests"')
        assert b'"target_members"' in readiness_bytes
        trigger_path.unlink()
        repaired = _sealed_dependencies()
        assert isinstance(repaired.register, LocalRetainedApprovalRegister)
        assert trigger_path.is_file()
        revocation = client.post(
            f"/api/v1/approvals/{approval_id}/revocations",
            headers={
                **_TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "cmd_" + "e" * 48,
                "If-Match": '"v1"',
            },
            json={
                "action": "REVOKE",
                "approval_ref": approval_id,
                "manifest_fingerprint": body["manifest_fingerprint"],
                "reason": "Withdraw before execution",
            },
        )
        assert revocation.status_code == 200
        assert revocation.json()["result_code"] == "REVOKED"
    assert isinstance(deps.governance, RegisteredReviewGovernanceService)


def test_default_review_rereads_explicit_pipeline_artifacts() -> None:
    """Packaged demo bytes cannot replace the retained pipeline artifact input."""
    artifact_root = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    artifact_root.joinpath("hk-v1-two-family-proposal.json").write_bytes(b"{}")

    with pytest.raises((RuntimeError, ValueError), match="PROPOSAL_PACKAGE_INVALID"):
        _sealed_dependencies()


def test_review_binds_one_atomically_published_generation(tmp_path: Path) -> None:
    """Review resolves the current pointer once and reads one complete generation."""
    source = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    published = tmp_path / "published"
    generation = published / ".generations" / ("a" * 64)
    shutil.copytree(source, generation)
    (published / "current").symlink_to(Path(".generations") / generation.name)

    dependencies = local_dependencies(
        state_root=tmp_path / "generation-state",
        artifact_root=published,
        authority_path=Path(os.environ["ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH"]),
        review_api_credential=CredentialMaterial(_SEALED_CREDENTIAL),
    )

    assert dependencies.projections.check() is True


def test_running_review_revalidates_replaced_package_without_restart() -> None:
    """An active Review process fails closed for drift or disappearance."""
    deps = _sealed_dependencies()
    artifact = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"]) / (
        "hk-v1-two-family-proposal.json"
    )
    original = artifact.read_bytes()
    artifact.write_bytes(b"{}")
    assert deps.projections.check() is False
    artifact.write_bytes(original)
    assert deps.projections.check() is True
    artifact.unlink()
    assert deps.projections.check() is False
    artifact.write_bytes(original)
    assert deps.projections.check() is True


def test_cold_review_is_ready_and_hot_loads_one_atomic_generation(tmp_path: Path) -> None:
    """An empty Review stays healthy and discovers the later complete generation."""
    deps = _cold_dependencies(tmp_path)
    artifact_root = tmp_path / "cold-artifacts"
    source = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    with LocalClient(create_app(deps)) as client:
        assert client.get("/internal/ready").status_code == 200
        empty = client.get("/api/v1/proposal-packages", headers=_TOKEN)
        assert empty.status_code == 200
        assert empty.json()["items"] == []
        assert (
            client.get(f"/api/v1/proposal-packages/{_PROPOSAL_ID}", headers=_TOKEN).status_code
            == 404
        )

        generation = artifact_root / ".generations" / ("b" * 64)
        shutil.copytree(source, generation)
        (artifact_root / "current").symlink_to(Path(".generations") / generation.name)

        loaded = client.get("/api/v1/proposal-packages", headers=_TOKEN)
        assert loaded.status_code == 200
        assert [item["proposal_id"] for item in loaded.json()["items"]] == [_PROPOSAL_ID]
        detail = client.get(f"/api/v1/proposal-packages/{_PROPOSAL_ID}", headers=_TOKEN)
        assert detail.status_code == 200
        assert detail.headers["etag"] == '"v0"'
        assert detail.json()["proposal"]["manifest_fingerprint"] == _MANIFEST_FINGERPRINT


def test_cold_review_fails_closed_for_partial_or_malformed_package(tmp_path: Path) -> None:
    """A partial live publication and a malformed cold publication never look ready."""
    deps = _cold_dependencies(tmp_path)
    artifact_root = tmp_path / "cold-artifacts"
    source = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    artifact_root.joinpath("hk-v1-two-family-proposal.json").write_bytes(
        source.joinpath("hk-v1-two-family-proposal.json").read_bytes()
    )
    with LocalClient(create_app(deps)) as client:
        assert client.get("/internal/ready").status_code == 503
        assert client.get("/api/v1/proposal-packages", headers=_TOKEN).status_code == 500

    malformed_root = tmp_path / "malformed-artifacts"
    malformed_root.mkdir()
    for name in (
        "hk-v1-two-family-proposal.json",
        "hk-v1-review-readiness.json",
        "hk-v1-review-package.json",
    ):
        malformed_root.joinpath(name).write_bytes(source.joinpath(name).read_bytes())
    malformed_root.joinpath("hk-v1-review-readiness.json").write_bytes(b"{}")
    with pytest.raises(ProposalProjectionError, match="PROPOSAL_PACKAGE_INVALID"):
        local_dependencies(
            state_root=tmp_path / "cold-state",
            artifact_root=malformed_root,
            authority_path=Path(os.environ["ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH"]),
            review_api_credential=CredentialMaterial(_SEALED_CREDENTIAL),
        )


def test_default_review_reads_and_hashes_every_declared_package_member() -> None:
    """A listed member is authority only when Review reads its exact retained bytes."""
    artifact_root = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    artifact_root.joinpath("validation/results.json").write_bytes(b"{}")

    with pytest.raises(RuntimeError, match="PROPOSAL_RECEIPT_FINGERPRINT_MISMATCH"):
        _sealed_dependencies()


def test_default_review_rejects_self_consistent_readiness_model_drift() -> None:
    """Readiness cannot substitute a model profile different from Task 7."""
    artifact_root = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    readiness_path = artifact_root / "hk-v1-review-readiness.json"
    readiness = parse_json_bytes(readiness_path.read_bytes(), max_bytes=1_000_000)
    assert isinstance(readiness, dict)
    readiness["model_profile_fingerprint"] = "sha256:" + "9" * 64
    unsigned = dict(readiness)
    unsigned.pop("fingerprint")
    unsigned.pop("schema_id")
    readiness["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
    )
    readiness_path.write_bytes(canonicalize(checked_json_value(readiness)))

    with pytest.raises(RuntimeError, match="PROPOSAL_PACKAGE_INVALID"):
        _sealed_dependencies()


def test_default_review_rejects_empty_task7_acquisition_and_batch_evidence() -> None:
    """A self-fingerprinted shell is not a complete Task 7 proposal."""
    artifact_root = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    proposal_path = artifact_root / "hk-v1-two-family-proposal.json"
    proposal = parse_json_bytes(proposal_path.read_bytes(), max_bytes=1_000_000)
    assert isinstance(proposal, dict)
    proposal["acquisition_manifests"] = []
    proposal["prepared_batches"] = []
    unsigned = dict(proposal)
    unsigned.pop("fingerprint")
    proposal["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
    )
    proposal_path.write_bytes(canonicalize(checked_json_value(proposal)))

    with pytest.raises(RuntimeError, match="PROPOSAL_PACKAGE_INVALID"):
        _sealed_dependencies()


def test_restart_rejects_old_approval_after_pipeline_artifact_drift() -> None:
    """A retained Approval cannot be reattached after reviewed bytes drift."""
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed exact frozen package",
    }
    with LocalClient(_sealed_app()) as client:
        assert _decision(client, body=body).status_code == 200

    artifact_root = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
    readiness_path = artifact_root / "hk-v1-review-readiness.json"
    readiness = parse_json_bytes(readiness_path.read_bytes(), max_bytes=1_000_000)
    assert isinstance(readiness, dict)
    limitations = readiness["limitations"]
    assert isinstance(limitations, list)
    readiness["limitations"] = [*limitations, "Changed after Approval."]
    unsigned = dict(readiness)
    unsigned.pop("fingerprint")
    unsigned.pop("schema_id")
    readiness["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
    )
    readiness_path.write_bytes(canonicalize(checked_json_value(readiness)))

    with pytest.raises(RuntimeError, match="PROPOSAL_PACKAGE_INVALID"):
        _sealed_dependencies()


def test_restart_rejects_approval_without_its_retained_package_bytes() -> None:
    """An older or truncated ledger cannot reconstruct Approval from current files."""
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed exact frozen package",
    }
    with LocalClient(_sealed_app()) as client:
        assert _decision(client, body=body).status_code == 200

    state_path = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"]) / ("approval-register.json")
    state = parse_json_bytes(state_path.read_bytes(), max_bytes=5_000_000)
    assert isinstance(state, dict)
    events = state["events"]
    assert isinstance(events, list)
    assert isinstance(events[0], dict)
    events[0].pop("proposal_bytes")
    state_path.write_bytes(canonicalize(checked_json_value(state)))

    with pytest.raises(RuntimeError, match="LOCAL_APPROVAL_LEDGER_INVALID"):
        _sealed_dependencies()


def test_restart_rejects_approval_without_its_exact_state_row() -> None:
    """A truncated state projection cannot resurrect a consumed Approval."""
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed exact frozen package",
    }
    with LocalClient(_sealed_app()) as client:
        response = _decision(client, body=body)
    approval_id = response.json()["result_ref"]

    state_path = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"]) / ("approval-register.json")
    state = parse_json_bytes(state_path.read_bytes(), max_bytes=5_000_000)
    assert isinstance(state, dict)
    approval_states = state["approval_states"]
    assert isinstance(approval_states, dict)
    approval_states.pop(approval_id)
    state_path.write_bytes(canonicalize(checked_json_value(state)))

    with pytest.raises(RuntimeError, match="LOCAL_APPROVAL_LEDGER_INVALID"):
        _sealed_dependencies()


def test_failed_decision_persistence_never_becomes_an_in_memory_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed retained write cannot later be reported as an exact replay."""
    deps = _sealed_dependencies()

    def fail_persist() -> None:
        raise OSError(_PERSIST_FAILURE)

    monkeypatch.setattr(deps.register, "_persist", fail_persist)
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed exact frozen package",
    }
    with LocalClient(create_app(deps)) as client:
        assert _decision(client, body=body).status_code == 500
        assert _decision(client, body=body).status_code == 500


def test_failed_consumption_persistence_leaves_approval_unconsumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consumption becomes visible only after its durable ledger replacement."""
    deps = _sealed_dependencies()
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": _MANIFEST_FINGERPRINT,
        "reason": "Reviewed exact frozen package",
    }
    with LocalClient(create_app(deps)) as client:
        response = _decision(client, body=body)
    approval_id = response.json()["result_ref"]
    detail = deps.projections.detail(_PROPOSAL_ID)
    assert detail is not None
    assert isinstance(deps.register, LocalRetainedApprovalRegister)

    def fail_persist() -> None:
        raise OSError(_PERSIST_FAILURE)

    monkeypatch.setattr(deps.register, "_persist", fail_persist)
    with pytest.raises(OSError, match="retained-write failure"):
        deps.register.consume(
            approval_id,
            "exe_" + "9" * 48,
            ManifestSnapshot(
                detail.promotion_manifest_id,
                detail.proposal.manifest_fingerprint,
                detail.base_serving_state_id,
                detail.valid_from,
                detail.valid_until,
                detail.validity_predicates,
            ),
            ApprovalConsumption(
                detail.base_serving_state_id,
                detail.validity_predicates,
                "2026-08-16T00:01:00Z",
            ),
        )
    assert deps.register.get(approval_id).state.value == "APPROVAL_APPROVED"


def test_review_origin_proxy_evidence_readiness_and_browser_client() -> None:
    """Reject forged context, protect evidence coordinates, and keep tokens memory-only."""
    deps = _sealed_dependencies()
    with LocalClient(create_app(deps)) as client:
        assert (
            client.get(
                "/api/v1/proposal-packages", headers={**_TOKEN, "Origin": "https://evil.test"}
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/proposal-packages", headers={**_TOKEN, "X-Original-User": "admin"}
            ).status_code
            == 403
        )
        evidence = client.get("/api/v1/evidence/evi_" + "1" * 48, headers=_TOKEN)
        assert evidence.status_code == 200
        repeated_evidence = client.get("/api/v1/evidence/evi_" + "1" * 48, headers=_TOKEN)
        assert repeated_evidence.content == evidence.content
        assert (
            evidence.content
            == (
                Path(os.environ["ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"])
                / "record-traceability/entries/"
                "rts_111111111111111111111111111111111111111111111111.ndjson"
            ).read_bytes()
        )
        assert "vault" not in evidence.text.lower()
        assert isinstance(deps.projections, RegisteredLocalReviewProjectionStore)
        assert deps.projections.evidence_reads == [
            ("person-local-1", "evi_" + "1" * 48),
            ("person-local-1", "evi_" + "1" * 48),
        ]
        restarted = _sealed_dependencies()
        assert isinstance(restarted.projections, RegisteredLocalReviewProjectionStore)
        assert restarted.projections.evidence_reads == [
            ("person-local-1", "evi_" + "1" * 48),
            ("person-local-1", "evi_" + "1" * 48),
        ]
        audit_path = (
            Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"]) / "evidence-read-ledger.json"
        )
        audit = parse_json_bytes(audit_path.read_bytes(), max_bytes=5_000_000)
        assert isinstance(audit, dict)
        assert audit["schema_id"] == "asklegal.local-review-evidence-read-ledger/v1"
        entries = audit["entries"]
        assert isinstance(entries, list)
        assert [entry["sequence"] for entry in entries if isinstance(entry, dict)] == [1, 2]
        preflight = client.request(
            "OPTIONS",
            "/api/v1/proposal-packages",
            headers={
                "Origin": "https://review.local.test",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "https://review.local.test"
        javascript = client.get("/review/app.js").text
        html = client.get("/review").text
        assert client.get("/demo/change-report.json").status_code == 404
        assert client.get("/demo/config.json").status_code == 404
        assert "review-token" in html
        assert all(
            expected in html
            for expected in (
                "LOCAL SYNTHETIC OFFLINE POC",
                "No live Hong Kong source",
                'id="pipeline-stages"',
                'id="proposal-summary"',
                'id="raw-proposal"',
                'id="change-report"',
                "Human review",
            )
        )
        assert "crypto.getRandomValues" in javascript
        assert all(
            expected in javascript
            for expected in (
                "renderProposalDetail",
                "updatePipelineStages",
                "target_members",
                "scope_dispositions",
                'fetch("/demo/change-report.json"',
                "Search impact: The earlier proposition remains searchable",
                "Evidence basis:",
                "This does not affect production.",
            )
        )
        assert "/decisions" in javascript
        assert 'submitDecision("APPROVE")' in javascript
        assert 'submitDecision("REJECT")' in javascript
        assert '"Idempotency-Key"' in javascript
        assert '"If-Match"' in javascript
        assert "pendingDecision.command" in javascript
        assert "JSON.stringify(detail, null, 2)" in javascript
        assert 'tokenInput.value = ""' in javascript
        assert "localStorage" not in javascript
        assert "sessionStorage" not in javascript
        assert "innerHTML" not in javascript
        assert "pinecone" not in javascript.lower()
        assert "control" not in javascript.lower()
        deps.configuration_source.drift()
        assert client.get("/internal/ready").status_code == 503
        assert client.get("/internal/live").status_code == 200


def test_review_startup_cleans_only_owned_stale_approval_archive_temps() -> None:
    """Restart removes marked archive staging directories and preserves lookalikes."""
    state_root = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"])
    archive_root = state_root / "approved-packages"
    archive_root.mkdir(parents=True)
    approval_id = "apr_" + "a" * 48
    owned = archive_root / f".{approval_id}.owned123"
    owned.mkdir()
    owned.joinpath(".asklegal-review-approval-archive.tmp").write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "approval_id": approval_id,
                    "schema_id": "asklegal.local-review-approval-archive-temp/v1",
                }
            )
        )
    )
    owned.joinpath("partial.json").write_text("partial")
    lookalike = archive_root / f".{approval_id}.unowned123"
    lookalike.mkdir()
    lookalike.joinpath("partial.json").write_text("must remain")
    external = state_root / "external-owned-lookalike"
    external.mkdir()
    linked = archive_root / f".{approval_id}.linked123"
    linked.symlink_to(external, target_is_directory=True)

    _sealed_dependencies()

    assert not owned.exists()
    assert lookalike.joinpath("partial.json").read_text() == "must remain"
    assert linked.is_symlink()
    assert external.is_dir()


def test_review_rejects_tampered_retained_evidence_audit() -> None:
    """A rewritten audit chain cannot be accepted as a valid restart."""
    deps = _sealed_dependencies()
    with LocalClient(create_app(deps)) as client:
        assert client.get("/api/v1/evidence/evi_" + "1" * 48, headers=_TOKEN).status_code == 200
    audit_path = Path(os.environ["ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"]) / "evidence-read-ledger.json"
    audit_path.write_bytes(audit_path.read_bytes() + b" ")

    with pytest.raises(ProposalProjectionError, match="PROPOSAL_PROJECTION_SNAPSHOT_INVALID"):
        _sealed_dependencies()
