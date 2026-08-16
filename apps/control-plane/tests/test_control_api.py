"""M3 private control-plane HTTP boundary conformance."""

import asyncio
from collections.abc import Mapping
from typing import Never

from asklegal_application_runtime import (
    LocalCommandRegister,
    LocalConfigurationSource,
    LocalIdentityVerifier,
    LocalTaskHub,
    Principal,
    TokenType,
    build_local_configuration,
)
from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue
from asklegal_control_plane.api import ControlDependencies, create_app, local_dependencies
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

_TOKEN = {"Authorization": "Bearer local-human"}
_COMMAND = "cmd_" + "1" * 48
_BODY = {"action": "REGISTER_SOURCE", "target_ref": "source-1", "evidence_ref": None}


class LocalClient:
    """Tiny synchronous wrapper around HTTPX's in-process ASGI transport."""

    def __init__(self, app: FastAPI, *, raise_server_exceptions: bool = True) -> None:
        self._app = app
        self._raise = raise_server_exceptions

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
        content: bytes | None = None,
    ) -> Response:
        async def send() -> Response:
            transport = ASGITransport(app=self._app, raise_app_exceptions=self._raise)
            async with AsyncClient(transport=transport, base_url="https://service.test") as client:
                return await client.request(
                    method, path, headers=headers, json=json, content=content
                )

        return asyncio.run(send())

    def get(self, path: str, *, headers: Mapping[str, str] | None = None) -> Response:
        return self.request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        content: bytes | None = None,
    ) -> Response:
        return self.request("POST", path, headers=headers, json=json, content=content)


def _post(
    client: LocalClient, *, command: str = _COMMAND, version: str = '"v0"', body: object = _BODY
) -> Response:
    return client.post(
        "/api/v1/source-commands",
        headers={
            **_TOKEN,
            "Content-Type": "application/json",
            "Idempotency-Key": command,
            "If-Match": version,
        },
        json=body,
    )


def _dependencies(principal: Principal) -> ControlDependencies:
    configuration = build_local_configuration(
        "CONTROL_PLANE",
        audience="api://asklegal-control",
        client="asklegal-control-client",
        task_hub="control-hub",
    )
    return ControlDependencies(
        configuration,
        LocalConfigurationSource(configuration),
        LocalIdentityVerifier({"test": principal}),
        LocalCommandRegister(),
        LocalTaskHub(),
    )


def test_control_startup_openapi_and_closed_route_surface() -> None:
    """Start independently and expose only the accepted control operation families."""
    app = create_app()
    schema = app.openapi()
    assert (
        fingerprint(schema)
        == "sha256:511e404a13a7f4af67f3624c1f874130da945183fd529bb548cfb913585ca711"
    )
    paths = schema["paths"]
    assert "/api/v1/source-commands" in paths
    assert "/api/v1/proposal-package-commands" in paths
    assert all("approval" not in path and "force" not in path for path in paths)
    with LocalClient(app) as client:
        assert client.get("/internal/live").json() == {"status": "live"}
        assert client.get("/internal/ready").status_code == 200
        assert client.get("/api/v1/sources", headers=_TOKEN).headers["etag"].startswith('"sha256:')


def test_control_identity_origin_and_proxy_boundaries() -> None:
    """Reject wrong audience, role, client, token kind, origin, and forged identity headers."""
    cases = (
        Principal(
            "person",
            "api://wrong",
            "asklegal-control-client",
            frozenset({"PipelineAdministrator"}),
            TokenType.DELEGATED_HUMAN,
        ),
        Principal(
            "person",
            "api://asklegal-control",
            "wrong-client",
            frozenset({"PipelineAdministrator"}),
            TokenType.DELEGATED_HUMAN,
        ),
        Principal(
            "person",
            "api://asklegal-control",
            "asklegal-control-client",
            frozenset(),
            TokenType.DELEGATED_HUMAN,
        ),
        Principal(
            "app",
            "api://asklegal-control",
            "asklegal-control-client",
            frozenset({"PipelineAdministrator"}),
            TokenType.APPLICATION,
        ),
    )
    for principal in cases:
        with LocalClient(create_app(_dependencies(principal))) as client:
            response = client.get("/api/v1/sources", headers={"Authorization": "Bearer test"})
            assert response.status_code == 403
            assert set(response.json()) == {
                "error_code",
                "message",
                "correlation_id",
                "command_id",
                "current_version",
                "current_ref",
                "retry_class",
                "details",
            }

    with LocalClient(create_app()) as client:
        allowed = client.get(
            "/api/v1/sources", headers={**_TOKEN, "Origin": "https://control.local.test"}
        )
        assert allowed.headers["access-control-allow-origin"] == "https://control.local.test"
        assert (
            client.get(
                "/api/v1/sources", headers={**_TOKEN, "Origin": "https://evil.test"}
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/sources", headers={**_TOKEN, "X-Forwarded-User": "admin"}
            ).status_code
            == 403
        )


def test_control_raw_body_media_version_and_idempotency_boundaries() -> None:
    """Reject malformed transport before submission and replay only exact commands."""
    with LocalClient(create_app()) as client:
        assert _post(client).json()["resolution"] == "RESULT_RECORDED"
        assert _post(client).json()["resolution"] == "EXACT_REPLAY"
        assert _post(client, body={**_BODY, "target_ref": "source-2"}).status_code == 409
        assert _post(client, command="bad").status_code == 400
        assert _post(client, command="cmd_" + "2" * 48, version='"v0"').status_code == 412
        assert _post(client, command="cmd_" + "3" * 48, version="*").status_code == 400
        assert (
            _post(client, command="cmd_" + "4" * 48, body={**_BODY, "unknown": True}).status_code
            == 400
        )
        response = client.post(
            "/api/v1/source-commands",
            headers={
                **_TOKEN,
                "Content-Type": "text/plain",
                "Idempotency-Key": "cmd_" + "5" * 48,
                "If-Match": '"v0"',
            },
            content=b"{}",
        )
        assert response.status_code == 415
        response = client.post(
            "/api/v1/source-commands",
            headers={
                **_TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "cmd_" + "6" * 48,
                "If-Match": '"v0"',
            },
            content=b"\xff",
        )
        assert response.status_code == 400


def test_control_body_limit_readiness_drift_and_redaction() -> None:
    """Fail bounded input and drift safely without exposing exception content."""
    deps = local_dependencies()
    with LocalClient(create_app(deps)) as client:
        huge = {
            "action": "REGISTER_SOURCE",
            "target_ref": "source-" + "x" * 20_000,
            "evidence_ref": None,
        }
        assert _post(client, body=huge).status_code == 400
        deps.configuration_source.drift()
        assert client.get("/internal/live").status_code == 200
        assert client.get("/internal/ready").status_code == 503

    class ExplodingRegister(LocalCommandRegister):
        def submit(
            self,
            *,
            command_id: str,
            target: str,
            expected_version: int,
            body: Mapping[str, JsonValue],
        ) -> Never:
            del command_id, target, expected_version, body
            message = "database-password-and-sql-text"
            raise RuntimeError(message)

    configuration = deps.configuration
    exploding = ControlDependencies(
        configuration,
        LocalConfigurationSource(configuration),
        deps.identity,
        ExplodingRegister(),
        deps.task_hub,
    )
    with LocalClient(create_app(exploding), raise_server_exceptions=False) as client:
        response = _post(client)
        assert response.status_code == 500
        assert "database-password" not in response.text
