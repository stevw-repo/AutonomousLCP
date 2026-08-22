"""Strict Review API and minimal replaceable browser client."""

# FastAPI retains decorator-registered callbacks; route/OpenAPI tests prove their access.
# pyright: reportUnusedFunction=false

import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from typing import Annotated, Literal, Never, Protocol

from asklegal_application_runtime import (
    ApplicationConfiguration,
    AuthorizationError,
    AuthorizationErrorCode,
    IdentityVerifier,
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalCommandRegister,
    LocalConfigurationSource,
    LocalPaginationStore,
    LocalReviewProjectionStore,
    Principal,
    ProposalDetailProjection,
    ProposalProjection,
    authorize,
    build_local_configuration,
    default_local_identity,
)
from asklegal_contracts import ContractViolation, parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_management_register_ports import (
    ApprovalError,
    ApprovalErrorCode,
    InMemoryApprovalRegister,
    ManifestSnapshot,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from asklegal_review_api.governance import ReviewCommand, ReviewGovernance, ReviewGovernanceService

_COMMAND_ID = re.compile(r"^cmd_[0-9a-f]{48}$")
_FORGED_HEADERS = frozenset(
    {"x-forwarded-user", "x-forwarded-roles", "x-auth-request-user", "x-original-user"}
)
_REVIEW_ORIGIN = "https://review.local.test"


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


class ProposalSummary(BaseModel):
    """Immutable proposal summary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: str
    manifest_fingerprint: str
    status: str
    title: str
    review_version: int


class ProposalPage(BaseModel):
    """One snapshot-bound proposal page."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot: str
    items: tuple[ProposalSummary, ...]
    continuation_token: str | None


class ProposalArtifactSummary(BaseModel):
    """One immutable package member safe for Review display."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role: str
    path: str
    media_type: str
    fingerprint: str
    byte_length: int


class ProposalDecisionSummary(BaseModel):
    """One immutable named-human decision safe for Review display."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approval_id: str
    decision: str
    decision_time: str
    reviewer_identity_id: str
    reviewer_identity_fingerprint: str
    authority_evidence_id: str
    authority_evidence_fingerprint: str
    reason: str
    event_fingerprint: str


class ProposalDetail(BaseModel):
    """Closed exact proposal review projection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal: ProposalSummary
    package_fingerprint: str
    promotion_manifest_id: str
    observation_cutoff: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str, str], ...]
    base_serving_state_id: str
    base_serving_state_fingerprint: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str
    artifacts: tuple[ProposalArtifactSummary, ...]
    decision: ProposalDecisionSummary | None


class CommentRequest(BaseModel):
    """Comment bound to one exact manifest section."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["COMMENT"]
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    review_section: Literal[
        "SUMMARY", "DIFF", "EVIDENCE", "COVERAGE", "RECOVERY", "VALIDATION", "COST", "ACTIONS"
    ]
    comment: str = Field(min_length=1, max_length=2_000)


class DecisionRequest(BaseModel):
    """Approve or reject one complete immutable manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["APPROVE", "REJECT"]
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2_000)


class RevocationRequest(BaseModel):
    """Revoke one exact unconsumed approval."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["REVOKE"]
    approval_ref: str = Field(pattern=r"^apr_[0-9a-f]{48}$")
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2_000)


class CommandResponse(BaseModel):
    """Authoritative review command result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command_id: str
    resolution: str
    result_code: str
    authoritative_version: int
    result_ref: str


class HistoryResponse(BaseModel):
    """Immutable decision and lifecycle history."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: str
    snapshot_ref: str
    events: tuple[str, ...]


class ReviewProjectionStore(Protocol):
    """Exact immutable proposal projection surface consumed by Review routes."""

    def load(self) -> tuple[str, tuple[ProposalProjection, ...]]:
        """Return one internally consistent projection generation."""
        ...

    def get(self, proposal_id: str) -> ProposalProjection | None:
        """Return one exact proposal from a verified generation, if present."""
        ...

    def detail(self, proposal_id: str) -> ProposalDetailProjection | None:
        """Return one fully reread immutable proposal package, if present."""
        ...

    def check(self) -> bool:
        """Perform a bounded non-mutating readiness check."""
        ...

    def record_evidence_read(self, *, subject: str, evidence_id: str) -> None:
        """Record or explicitly refuse one sanitized evidence-read audit fact."""
        ...


@dataclass(frozen=True, slots=True)
class ReviewDependencies:
    """Injected Review adapters with no implicit external success."""

    configuration: ApplicationConfiguration
    configuration_source: LocalConfigurationSource
    identity: IdentityVerifier
    register: LocalCommandRegister
    projections: ReviewProjectionStore
    pagination: LocalPaginationStore
    governance: ReviewGovernance | None = None


def local_dependencies() -> ReviewDependencies:
    """Create deterministic local Review dependencies."""
    configuration = build_local_configuration(
        "REVIEW_APPLICATION",
        audience="api://asklegal-review",
        client="asklegal-review-client",
        task_hub=None,
    )
    projections = LocalReviewProjectionStore()
    manifests = {
        proposal.proposal_id: ManifestSnapshot(
            "pmn_" + f"{index:048x}",
            proposal.manifest_fingerprint,
            "srv_" + "a" * 48,
            "2026-08-15T00:00:00Z",
            "2026-08-17T00:00:00Z",
            (("configuration", "1.0.0", "sha256:" + "c" * 64),),
        )
        for index, proposal in enumerate(projections.proposals, start=1)
    }
    approvals = InMemoryApprovalRegister({"person-local-1": frozenset({"PipelineAdministrator"})})
    governance = ReviewGovernanceService(approvals, manifests, local_time="2026-08-16T00:00:00Z")
    return ReviewDependencies(
        configuration=configuration,
        configuration_source=LocalConfigurationSource(configuration),
        identity=default_local_identity(
            configuration.identity_audience, configuration.identity_client
        ),
        register=LocalCommandRegister(),
        projections=projections,
        pagination=LocalPaginationStore(secret=b"local-pagination-key-not-a-production-secret"),
        governance=governance,
    )


def create_app(dependencies: ReviewDependencies | None = None) -> FastAPI:
    """Create the independent Review API and replaceable local browser shell."""
    deps = dependencies or local_dependencies()
    app = FastAPI(
        title="AskLegal Review API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.dependencies = deps
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_REVIEW_ORIGIN],
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
    _install_handlers(app)

    async def reviewer(request: Request) -> Principal:
        return _authenticate(request, deps)

    @app.get("/internal/live", include_in_schema=False)
    async def _live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/internal/ready", include_in_schema=False)
    async def _ready() -> JSONResponse:
        is_ready = (
            deps.configuration_source.is_current(deps.configuration.configuration_fingerprint)
            and deps.register.check()
            and deps.projections.check()
            and (deps.governance is None or deps.governance.check())
        )
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready"}, status_code=200 if is_ready else 503
        )

    @app.get("/review", include_in_schema=False, response_class=HTMLResponse)
    async def _browser_client() -> HTMLResponse:
        html = (
            files("asklegal_review_api.client").joinpath("index.html").read_text(encoding="utf-8")
        )
        return HTMLResponse(html)

    @app.get("/review/app.js", include_in_schema=False)
    async def _browser_javascript() -> Response:
        javascript = (
            files("asklegal_review_api.client").joinpath("app.js").read_text(encoding="utf-8")
        )
        return Response(javascript, media_type="text/javascript")

    @app.get(
        "/api/v1/proposal-packages",
        operation_id="listProposalPackages",
        response_model=ProposalPage,
    )
    async def _list_proposals(
        principal: Annotated[Principal, Depends(reviewer)],
        status: Annotated[Literal["REVIEW_READY"], Query()] = "REVIEW_READY",
        limit: Annotated[int, Query(ge=1, le=100)] = 2,
        continuation: Annotated[str | None, Query(max_length=80)] = None,
    ) -> JSONResponse:
        snapshot, generation = deps.projections.load()
        proposals = tuple(item for item in generation if item.status == status)
        filters = (("status", status),)
        offset = 0
        cursor = None
        if continuation is not None:
            cursor = deps.pagination.resolve(
                continuation,
                snapshot=snapshot,
                filters=filters,
                sort="proposal_id",
                subject=principal.subject,
            )
            offset = cursor.offset
        items = proposals[offset : offset + limit]
        next_offset = offset + len(items)
        next_token = None
        if next_offset < len(proposals):
            next_cursor = (
                deps.pagination.next_cursor(
                    snapshot=snapshot,
                    filters=filters,
                    sort="proposal_id",
                    subject=principal.subject,
                    offset=next_offset,
                )
                if cursor is None
                else deps.pagination.advance(cursor, offset=next_offset)
            )
            next_token = deps.pagination.issue(next_cursor)
        page = ProposalPage(
            snapshot=snapshot,
            items=tuple(_proposal_summary(item) for item in items),
            continuation_token=next_token,
        )
        return JSONResponse(page.model_dump(mode="json"), headers={"ETag": f'"{snapshot}"'})

    @app.get(
        "/api/v1/proposal-packages/{proposal_id}",
        operation_id="getProposalPackage",
        response_model=ProposalDetail,
    )
    async def _get_proposal(
        proposal_id: str, _principal: Annotated[Principal, Depends(reviewer)]
    ) -> JSONResponse:
        projection = deps.projections.detail(proposal_id)
        if projection is None:
            _raise_http("PROPOSAL_NOT_FOUND", status=404)
        detail = ProposalDetail(
            proposal=_proposal_summary(projection.proposal),
            package_fingerprint=projection.package_fingerprint,
            promotion_manifest_id=projection.promotion_manifest_id,
            observation_cutoff=projection.observation_cutoff,
            valid_from=projection.valid_from,
            valid_until=projection.valid_until,
            validity_predicates=projection.validity_predicates,
            base_serving_state_id=projection.base_serving_state_id,
            base_serving_state_fingerprint=projection.base_serving_state_fingerprint,
            candidate_serving_state_id=projection.candidate_serving_state_id,
            candidate_serving_state_fingerprint=(projection.candidate_serving_state_fingerprint),
            artifacts=tuple(
                ProposalArtifactSummary(
                    role=item.role,
                    path=item.path,
                    media_type=item.media_type,
                    fingerprint=item.fingerprint,
                    byte_length=item.byte_length,
                )
                for item in projection.artifacts
            ),
            decision=(
                None
                if projection.decision is None
                else ProposalDecisionSummary(
                    approval_id=projection.decision.approval_id,
                    decision=projection.decision.decision,
                    decision_time=projection.decision.decision_time,
                    reviewer_identity_id=projection.decision.reviewer_identity_id,
                    reviewer_identity_fingerprint=(
                        projection.decision.reviewer_identity_fingerprint
                    ),
                    authority_evidence_id=projection.decision.authority_evidence_id,
                    authority_evidence_fingerprint=(
                        projection.decision.authority_evidence_fingerprint
                    ),
                    reason=projection.decision.reason,
                    event_fingerprint=projection.decision.event_fingerprint,
                )
            ),
        )
        return JSONResponse(
            detail.model_dump(mode="json"),
            headers={"ETag": f'"v{projection.proposal.review_version}"'},
        )

    @app.get("/api/v1/evidence/{evidence_id}", operation_id="streamEvidence")
    async def _evidence(
        evidence_id: str, principal: Annotated[Principal, Depends(reviewer)]
    ) -> Response:
        if re.fullmatch(r"evi_[0-9a-f]{48}", evidence_id) is None:
            _raise_http("EVIDENCE_NOT_FOUND", status=404)
        deps.projections.record_evidence_read(subject=principal.subject, evidence_id=evidence_id)
        return Response(
            b'{"artifact":"synthetic-local-evidence"}',
            media_type="application/json",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post(
        "/api/v1/proposal-packages/{proposal_id}/comments",
        operation_id="appendReviewerComment",
        response_model=CommandResponse,
    )
    async def _comment(
        proposal_id: str,
        request: Request,
        principal: Annotated[Principal, Depends(reviewer)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request, deps, principal, idempotency_key, if_match, proposal_id, CommentRequest
        )

    @app.post(
        "/api/v1/proposal-packages/{proposal_id}/decisions",
        operation_id="decideProposalPackage",
        response_model=CommandResponse,
    )
    async def _decide(
        proposal_id: str,
        request: Request,
        principal: Annotated[Principal, Depends(reviewer)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request, deps, principal, idempotency_key, if_match, proposal_id, DecisionRequest
        )

    @app.post(
        "/api/v1/approvals/{approval_id}/revocations",
        operation_id="revokeApproval",
        response_model=CommandResponse,
    )
    async def _revoke(
        approval_id: str,
        request: Request,
        principal: Annotated[Principal, Depends(reviewer)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request,
            deps,
            principal,
            idempotency_key,
            if_match,
            approval_id,
            RevocationRequest,
        )

    @app.get(
        "/api/v1/proposal-packages/{proposal_id}/history",
        operation_id="getProposalHistory",
        response_model=HistoryResponse,
    )
    async def _history(
        proposal_id: str, _principal: Annotated[Principal, Depends(reviewer)]
    ) -> JSONResponse:
        projection = deps.projections.detail(proposal_id)
        if projection is None:
            _raise_http("PROPOSAL_NOT_FOUND", status=404)
        decision = projection.decision
        result = HistoryResponse(
            proposal_id=proposal_id,
            snapshot_ref=(
                projection.package_fingerprint if decision is None else decision.event_fingerprint
            ),
            events=("REVIEW_READY",) if decision is None else ("REVIEW_READY", decision.decision),
        )
        return JSONResponse(
            result.model_dump(mode="json"), headers={"ETag": f'"{result.snapshot_ref}"'}
        )

    return app


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthorizationError)
    async def _authorization_error(request: Request, error: AuthorizationError) -> JSONResponse:
        return _error_response(request, error.code.value, 403, RetryClass.NEVER)

    @app.exception_handler(LocalAdapterError)
    async def _adapter_error(request: Request, error: LocalAdapterError) -> JSONResponse:
        statuses = {
            LocalAdapterErrorCode.COMMAND_ID_CONFLICT: 409,
            LocalAdapterErrorCode.STALE_VERSION: 412,
            LocalAdapterErrorCode.CONTINUATION_INVALID: 400,
        }
        return _error_response(
            request, error.code.value, statuses.get(error.code, 503), RetryClass.NEVER
        )

    @app.exception_handler(ContractViolation)
    async def _contract_error(request: Request, error: ContractViolation) -> JSONResponse:
        return _error_response(request, error.code.value, 400, RetryClass.NEVER)

    @app.exception_handler(ApprovalError)
    async def _approval_error(request: Request, error: ApprovalError) -> JSONResponse:
        status = (
            403
            if error.code is ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL
            else 404
            if error.code is ApprovalErrorCode.APPROVAL_NOT_FOUND
            else 409
        )
        return _error_response(request, error.code.value, status, RetryClass.NEVER)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, _error: RequestValidationError) -> JSONResponse:
        return _error_response(request, "REQUEST_INVALID", 400, RetryClass.NEVER)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = error.detail if type(error.detail) is str else "REQUEST_INVALID"
        return _error_response(request, code, error.status_code, RetryClass.NEVER)

    @app.exception_handler(Exception)
    async def _internal_error(request: Request, _error: Exception) -> JSONResponse:
        return _error_response(request, "INTERNAL_ERROR", 500, RetryClass.QUERY_RESULT)


def _authenticate(request: Request, dependencies: ReviewDependencies) -> Principal:
    if {name.lower() for name in request.headers} & _FORGED_HEADERS:
        raise AuthorizationError(AuthorizationErrorCode.FORGED_PROXY_HEADER)
    origin = request.headers.get("Origin")
    if origin is not None and origin != _REVIEW_ORIGIN:
        raise AuthorizationError(AuthorizationErrorCode.ORIGIN)
    principal = dependencies.identity.verify(request.headers.get("Authorization"))
    authorize(
        principal,
        audience=dependencies.configuration.identity_audience,
        client=dependencies.configuration.identity_client,
    )
    return principal


def _proposal_summary(proposal: ProposalProjection) -> ProposalSummary:
    return ProposalSummary(
        proposal_id=proposal.proposal_id,
        manifest_fingerprint=proposal.manifest_fingerprint,
        status=proposal.status,
        title=proposal.title,
        review_version=proposal.review_version,
    )


async def _submit(
    request: Request,
    dependencies: ReviewDependencies,
    principal: Principal,
    command_id: str,
    if_match: str,
    target: str,
    model_type: type[CommentRequest | DecisionRequest | RevocationRequest],
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
        model = model_type.model_validate(value, strict=True)
    except ValidationError as error:
        raise RequestValidationError([]) from error
    if isinstance(model, CommentRequest | DecisionRequest):
        proposal = dependencies.projections.get(target)
        if proposal is None:
            _raise_http("PROPOSAL_NOT_FOUND", status=404)
        if model.manifest_fingerprint != proposal.manifest_fingerprint:
            _raise_http("MANIFEST_FINGERPRINT_STALE", status=412)
    if isinstance(model, RevocationRequest) and model.approval_ref != target:
        _raise_http("APPROVAL_REFERENCE_MISMATCH")
    body = model.model_dump(mode="json")
    json_body: dict[str, JsonValue] = dict(body)
    if dependencies.governance is None:
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
    outcome = dependencies.governance.submit(
        ReviewCommand(command_id, target, expected_version, json_body, principal)
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


def _raise_http(code: str, *, status: int = 400) -> Never:
    raise HTTPException(status_code=status, detail=code)


def _error_response(request: Request, code: str, status: int, retry: RetryClass) -> JSONResponse:
    command = request.headers.get("Idempotency-Key")
    if command is None or _COMMAND_ID.fullmatch(command) is None:
        command = None
    envelope = ErrorEnvelope(
        error_code=code,
        message="Request could not be completed.",
        command_id=command,
        retry_class=retry,
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status)
