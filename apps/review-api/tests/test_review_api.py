"""M3 Review API, pagination, authorization, and browser-client proofs."""

import asyncio
from collections.abc import Mapping

from asklegal_application_runtime import (
    LocalIdentityVerifier,
    Principal,
    TokenType,
)
from asklegal_contracts import fingerprint
from asklegal_review_api.api import ReviewDependencies, create_app, local_dependencies
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

_TOKEN = {"Authorization": "Bearer local-human"}
_COMMAND = "cmd_" + "a" * 48


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
        "/api/v1/proposal-packages/proposal-1/decisions",
        headers={
            **_TOKEN,
            "Content-Type": "application/json",
            "Idempotency-Key": command,
            "If-Match": '"v0"',
        },
        json=body,
    )


def test_review_startup_openapi_and_exact_surface() -> None:
    """Start independently with an OpenAPI document distinct from control."""
    app = create_app()
    schema = app.openapi()
    assert (
        fingerprint(schema)
        == "sha256:0e4adbaf3873c2a14e0ab7ba94337d1d12db919ce1681a2a9662d8dd6155ebe7"
    )
    paths = schema["paths"]
    assert "/api/v1/proposal-packages" in paths
    assert "/api/v1/evidence/{evidence_id}" in paths
    assert all("source-commands" not in path and "pinecone" not in path for path in paths)
    with LocalClient(app) as client:
        assert client.get("/internal/live").status_code == 200
        assert client.get("/internal/ready").status_code == 200


def test_review_pagination_is_stable_and_caller_bound() -> None:
    """Tokens keep one snapshot/filter/sort/caller binding and stable page contents."""
    with LocalClient(create_app()) as client:
        first = client.get("/api/v1/proposal-packages", headers=_TOKEN)
        assert first.status_code == 200
        assert first.headers["etag"] == '"projection-local-1"'
        token = first.json()["continuation_token"]
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

    deps = local_dependencies()
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
        LocalIdentityVerifier({"local-human": other}),
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
    deps = local_dependencies()
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
        LocalIdentityVerifier({"local-human": app_principal}),
        deps.register,
        deps.projections,
        deps.pagination,
    )
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": "sha256:" + f"{1:064x}",
        "reason": "Reviewed",
    }
    with LocalClient(create_app(app_deps)) as client:
        response = _decision(client, body=body)
        assert response.status_code == 403
        assert response.json()["error_code"] == "AUTH_WRONG_TOKEN_TYPE"

    with LocalClient(create_app()) as client:
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


def test_review_commands_append_real_governance_facts_and_revoke_exactly() -> None:
    """HTTP decisions and revocations reach the authoritative Approval lifecycle."""
    deps = local_dependencies()
    body = {
        "action": "APPROVE",
        "manifest_fingerprint": "sha256:" + f"{1:064x}",
        "reason": "Reviewed complete proposal",
    }
    with LocalClient(create_app(deps)) as client:
        decision = _decision(client, body=body)
        approval_id = decision.json()["result_ref"]
        replay = _decision(client, body=body)
        assert replay.json()["resolution"] == "EXACT_REPLAY"
        revocation = client.post(
            f"/api/v1/approvals/{approval_id}/revocations",
            headers={
                **_TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "cmd_" + "e" * 48,
                "If-Match": '"v0"',
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
    assert deps.governance is not None
    assert deps.governance.approvals.get(approval_id).state.value == "APPROVAL_REVOKED"


def test_review_origin_proxy_evidence_readiness_and_browser_client() -> None:
    """Reject forged context, protect evidence coordinates, and keep tokens memory-only."""
    deps = local_dependencies()
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
        assert "vault" not in evidence.text.lower()
        assert deps.projections.evidence_reads == [("person-local-1", "evi_" + "1" * 48)]
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
        assert "crypto.subtle" in javascript
        assert "api://asklegal-review" in javascript
        assert "localStorage" not in javascript
        assert "sessionStorage" not in javascript
        assert "pinecone" not in javascript.lower()
        assert "control" not in javascript.lower()
        deps.configuration_source.drift()
        assert client.get("/internal/ready").status_code == 503
        assert client.get("/internal/live").status_code == 200
