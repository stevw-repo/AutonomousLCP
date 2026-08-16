"""Strict, independently secured control-plane API adapter."""

# FastAPI retains decorator-registered callbacks; route/OpenAPI tests prove their access.
# pyright: reportUnusedFunction=false

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Never

from asklegal_application_runtime import (
    ApplicationConfiguration,
    AuthorizationError,
    AuthorizationErrorCode,
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalCommandRegister,
    LocalConfigurationSource,
    LocalIdentityVerifier,
    LocalTaskHub,
    Principal,
    authorize,
    build_local_configuration,
    default_local_identity,
)
from asklegal_contracts import ContractViolation, parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_COMMAND_ID = re.compile(r"^cmd_[0-9a-f]{48}$")
_CORRELATION_ID = re.compile(r"^run_[0-9a-f]{48}$")
_FORGED_HEADERS = frozenset(
    {"x-forwarded-user", "x-forwarded-roles", "x-auth-request-user", "x-original-user"}
)
_CONTROL_ORIGIN = "https://control.local.test"


class RetryClass(StrEnum):
    """Closed HTTP retry advice."""

    NEVER = "NEVER"
    QUERY_RESULT = "QUERY_RESULT"
    SAME_COMMAND_AFTER = "SAME_COMMAND_AFTER"


class ErrorEnvelope(BaseModel):
    """Stable safe error response."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    error_code: str
    message: str
    correlation_id: str | None = None
    command_id: str | None = None
    current_version: int | None = None
    current_ref: str | None = None
    retry_class: RetryClass
    details: dict[str, str | int] = Field(default_factory=dict)


class ControlCommandRequest(BaseModel):
    """Closed effect-free control command boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal[
        "REGISTER_SOURCE",
        "REVISE_SOURCE",
        "SUSPEND_SOURCE",
        "PLAN_RUN",
        "SCHEDULE_RUN",
        "CANCEL_RUN",
        "REPROCESS",
        "RECONCILE",
        "PREPARE_PROPOSAL_PACKAGE",
    ]
    target_ref: str = Field(min_length=4, max_length=128, pattern=r"^[a-z0-9][a-z0-9:_-]+$")
    evidence_ref: str | None = Field(
        default=None,
        min_length=4,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9:_-]+$",
    )


class CommandResponse(BaseModel):
    """Authoritative command result projection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command_id: str
    resolution: str
    result_code: str
    authoritative_version: int
    result_ref: str


class ProjectionResponse(BaseModel):
    """Sanitized immutable control projection reference."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    projection: str
    snapshot_ref: str
    items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ControlDependencies:
    """Injected application adapters; no adapter is discovered implicitly."""

    configuration: ApplicationConfiguration
    configuration_source: LocalConfigurationSource
    identity: LocalIdentityVerifier
    register: LocalCommandRegister
    task_hub: LocalTaskHub


def local_dependencies() -> ControlDependencies:
    """Create fail-closed deterministic local dependencies."""
    configuration = build_local_configuration(
        "CONTROL_PLANE",
        audience="api://asklegal-control",
        client="asklegal-control-client",
        task_hub="control-local-task-hub",
    )
    return ControlDependencies(
        configuration=configuration,
        configuration_source=LocalConfigurationSource(configuration),
        identity=default_local_identity(
            configuration.identity_audience,
            configuration.identity_client,
        ),
        register=LocalCommandRegister(),
        task_hub=LocalTaskHub(),
    )


def create_app(dependencies: ControlDependencies | None = None) -> FastAPI:
    """Create one independent control API with exact injected boundaries."""
    deps = dependencies or local_dependencies()
    app = FastAPI(
        title="AskLegal Control Plane API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.dependencies = deps
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_CONTROL_ORIGIN],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-Correlation-ID",
        ],
        expose_headers=["ETag"],
    )

    @app.exception_handler(AuthorizationError)
    async def _authorization_error(request: Request, error: AuthorizationError) -> JSONResponse:
        return _error_response(request, error.code.value, 403, RetryClass.NEVER)

    @app.exception_handler(LocalAdapterError)
    async def _adapter_error(request: Request, error: LocalAdapterError) -> JSONResponse:
        if error.code is LocalAdapterErrorCode.COMMAND_ID_CONFLICT:
            return _error_response(request, error.code.value, 409, RetryClass.QUERY_RESULT)
        if error.code is LocalAdapterErrorCode.STALE_VERSION:
            return _error_response(request, error.code.value, 412, RetryClass.NEVER)
        return _error_response(request, error.code.value, 503, RetryClass.SAME_COMMAND_AFTER)

    @app.exception_handler(ContractViolation)
    async def _contract_error(request: Request, error: ContractViolation) -> JSONResponse:
        return _error_response(request, error.code.value, 400, RetryClass.NEVER)

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _error_response(request, "REQUEST_INVALID", 400, RetryClass.NEVER)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = error.detail if type(error.detail) is str else "REQUEST_INVALID"
        return _error_response(request, code, error.status_code, RetryClass.NEVER)

    @app.exception_handler(Exception)
    async def _internal_error(request: Request, _error: Exception) -> JSONResponse:
        return _error_response(request, "INTERNAL_ERROR", 500, RetryClass.QUERY_RESULT)

    async def operator(request: Request) -> Principal:
        return _authenticate(request, deps)

    @app.get("/internal/live", include_in_schema=False)
    async def _live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/internal/ready", include_in_schema=False)
    async def _ready() -> JSONResponse:
        is_ready = (
            deps.configuration_source.is_current(deps.configuration.configuration_fingerprint)
            and deps.register.check()
            and deps.task_hub.check()
        )
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready"},
            status_code=200 if is_ready else 503,
        )

    @app.post(
        "/api/v1/source-commands",
        operation_id="submitSourceCommand",
        response_model=CommandResponse,
    )
    async def _source_command(
        request: Request,
        _principal: Annotated[Principal, Depends(operator)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request,
            deps,
            idempotency_key,
            if_match,
            frozenset({"REGISTER_SOURCE", "REVISE_SOURCE", "SUSPEND_SOURCE"}),
        )

    @app.post(
        "/api/v1/run-commands", operation_id="submitRunCommand", response_model=CommandResponse
    )
    async def _run_command(
        request: Request,
        _principal: Annotated[Principal, Depends(operator)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request,
            deps,
            idempotency_key,
            if_match,
            frozenset({"PLAN_RUN", "SCHEDULE_RUN", "CANCEL_RUN"}),
        )

    @app.post(
        "/api/v1/reprocessing-commands",
        operation_id="submitReprocessingCommand",
        response_model=CommandResponse,
    )
    async def _reprocess_command(
        request: Request,
        _principal: Annotated[Principal, Depends(operator)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request,
            deps,
            idempotency_key,
            if_match,
            frozenset({"REPROCESS", "RECONCILE"}),
            require_evidence=True,
        )

    @app.post(
        "/api/v1/proposal-package-commands",
        operation_id="prepareProposalPackage",
        response_model=CommandResponse,
    )
    async def _proposal_command(
        request: Request,
        _principal: Annotated[Principal, Depends(operator)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request,
            deps,
            idempotency_key,
            if_match,
            frozenset({"PREPARE_PROPOSAL_PACKAGE"}),
            require_evidence=True,
        )

    @app.get("/api/v1/sources", operation_id="listSources", response_model=ProjectionResponse)
    async def _sources(
        response: Response,
        _principal: Annotated[Principal, Depends(operator)],
    ) -> ProjectionResponse:
        response.headers["ETag"] = '"sha256:' + "a" * 64 + '"'
        return _projection("sources")

    @app.get("/api/v1/runs", operation_id="listRuns", response_model=ProjectionResponse)
    async def _runs(
        response: Response,
        _principal: Annotated[Principal, Depends(operator)],
    ) -> ProjectionResponse:
        response.headers["ETag"] = '"sha256:' + "a" * 64 + '"'
        return _projection("runs")

    @app.get(
        "/api/v1/operations/{projection}",
        operation_id="inspectOperations",
        response_model=ProjectionResponse,
    )
    async def _operations(
        projection: Literal[
            "work", "observations", "gaps", "quarantines", "capabilities", "coverage"
        ],
        response: Response,
        _principal: Annotated[Principal, Depends(operator)],
    ) -> ProjectionResponse:
        response.headers["ETag"] = '"sha256:' + "a" * 64 + '"'
        return _projection(projection)

    @app.get(
        "/api/v1/reports/{report}", operation_id="inspectReport", response_model=ProjectionResponse
    )
    async def _reports(
        report: Literal["recovery-readiness", "operational"],
        response: Response,
        _principal: Annotated[Principal, Depends(operator)],
    ) -> ProjectionResponse:
        response.headers["ETag"] = '"sha256:' + "a" * 64 + '"'
        return _projection(report)

    return app


def _authenticate(request: Request, dependencies: ControlDependencies) -> Principal:
    if {name.lower() for name in request.headers} & _FORGED_HEADERS:
        raise AuthorizationError(AuthorizationErrorCode.FORGED_PROXY_HEADER)
    origin = request.headers.get("Origin")
    if origin is not None and origin != _CONTROL_ORIGIN:
        raise AuthorizationError(AuthorizationErrorCode.ORIGIN)
    principal = dependencies.identity.verify(request.headers.get("Authorization"))
    authorize(
        principal,
        audience=dependencies.configuration.identity_audience,
        client=dependencies.configuration.identity_client,
    )
    return principal


async def _submit(
    request: Request,
    dependencies: ControlDependencies,
    command_id: str,
    if_match: str,
    allowed_actions: frozenset[str],
    *,
    require_evidence: bool = False,
) -> CommandResponse:
    if _COMMAND_ID.fullmatch(command_id) is None:
        _raise_http("IDEMPOTENCY_KEY_INVALID")
    expected_version = _expected_version(if_match)
    if request.headers.get("Content-Type") != "application/json":
        _raise_http("MEDIA_TYPE_UNSUPPORTED", status=415)
    value = parse_json_bytes(
        await request.body(), max_bytes=dependencies.configuration.limits.max_body_bytes
    )
    try:
        model = ControlCommandRequest.model_validate(value, strict=True)
    except ValidationError as error:
        raise RequestValidationError([]) from error
    if model.action not in allowed_actions or (require_evidence and model.evidence_ref is None):
        _raise_http("COMMAND_PRECONDITION_INVALID")
    body: dict[str, JsonValue] = {
        "action": model.action,
        "evidence_ref": model.evidence_ref,
        "target_ref": model.target_ref,
    }
    outcome = dependencies.register.submit(
        command_id=command_id, target=model.target_ref, expected_version=expected_version, body=body
    )
    return CommandResponse(
        command_id=outcome.command_id,
        resolution=outcome.resolution,
        result_code=outcome.result_code,
        authoritative_version=outcome.authoritative_version,
        result_ref=outcome.result_ref,
    )


def _expected_version(value: str) -> int:
    if not value.startswith('"v') or not value.endswith('"'):
        _raise_http("IF_MATCH_INVALID")
    digits = value[2:-1]
    if not digits.isdigit() or (len(digits) > 1 and digits.startswith("0")):
        _raise_http("IF_MATCH_INVALID")
    return int(digits)


def _projection(name: str) -> ProjectionResponse:
    return ProjectionResponse(projection=name, snapshot_ref="sha256:" + "a" * 64, items=())


def _raise_http(code: str, *, status: int = 400) -> Never:
    raise HTTPException(status_code=status, detail=code)


def _error_response(request: Request, code: str, status: int, retry: RetryClass) -> JSONResponse:
    correlation = request.headers.get("X-Correlation-ID")
    if correlation is None or _CORRELATION_ID.fullmatch(correlation) is None:
        correlation = None
    command = request.headers.get("Idempotency-Key")
    if command is None or _COMMAND_ID.fullmatch(command) is None:
        command = None
    envelope = ErrorEnvelope(
        error_code=code,
        message="Request could not be completed.",
        correlation_id=correlation,
        command_id=command,
        retry_class=retry,
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status)
