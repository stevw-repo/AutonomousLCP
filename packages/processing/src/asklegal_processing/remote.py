"""Real Azure OpenAI generative task runner reached through the model egress proxy.

This is the provider side of `SemanticTaskRunner`, the boundary that
`DisabledSemanticTaskRunner` refuses and `DeterministicSemanticTaskRunner` fakes.

The bounded transport here is deliberately self-contained rather than shared with
`asklegal_promotion`. Processing must not depend on promotion, and the neutral
package both share carries data contracts, not HTTP. The duplication is a few
dozen lines and keeps the package boundary honest.

The runner is strict on the way out. The model is asked for exactly the fields the
task contract names, and anything else — extra keys, a missing key, a wrong phase,
an unparseable body — fails closed rather than being repaired into a plausible
legal judgment.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPSConnection
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.parse import urlsplit

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .model import ProcessingError, SemanticDecision, semantic_effect_receipt_id

if TYPE_CHECKING:
    from asklegal_legal_desks import SemanticTaskProfile

    from .model import SemanticTaskRequest

AZURE_OPENAI_PROVIDER = "AZURE_OPENAI"
"""The only provider value this runner will serve."""

_DEFAULT_TIMEOUT_SECONDS = 90
_HTTP_BAD_REQUEST = 400
_MAX_REPLY_BYTES = 1_000_000
_MAX_CREDENTIAL_BYTES = 65_536
SEMANTIC_INPUT_SCHEMA = "asklegal.semantic-task-request/1.0.0"
SEMANTIC_OUTPUT_SCHEMA = "asklegal.semantic-decision/1.0.0"
_DECISION_KEYS = frozenset(
    {"decision_code", "supporting_evidence_refs", "unresolved_facts", "challenge_code"}
)
_CHALLENGE_CODES = frozenset({"NOT_APPLICABLE", "PASS", "FAIL"})
_TASK_DECISION_CODES: dict[str, frozenset[str]] = {
    "HK_CASE_PROPOSITION_ANALYSIS": frozenset(
        {"SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ),
    "HK_CASE_PROPOSITION_CHALLENGE": frozenset(
        {"SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ),
    "HK_LATER_TREATMENT_DISCOVERY": frozenset({"FOUND", "NOT_FOUND", "INSUFFICIENT_EVIDENCE"}),
    "HK_LATER_TREATMENT_CANDIDATE_ANALYSIS": frozenset(
        {"MAINTAINED", "DISTINGUISHED", "OVERRULED", "INSUFFICIENT_EVIDENCE"}
    ),
    "HK_REGULATORY_UPDATE_ANALYSIS": frozenset(
        {"CHANGE_REQUIRED", "NO_CHANGE", "INSUFFICIENT_EVIDENCE"}
    ),
    "HK_REGULATORY_UPDATE_CHALLENGE": frozenset(
        {"CHANGE_REQUIRED", "NO_CHANGE", "INSUFFICIENT_EVIDENCE"}
    ),
    "HK_REGULATORY_RECORD_ANALYSIS": frozenset(
        {"SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ),
    "HK_REGULATORY_RECORD_CHALLENGE": frozenset(
        {"SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ),
    "GAZETTE_EVENT_ANALYSIS": frozenset(
        {"AMENDMENT", "COMMENCEMENT", "CORRECTION", "INSUFFICIENT_EVIDENCE"}
    ),
    "GAZETTE_EVENT_CHALLENGE": frozenset(
        {"AMENDMENT", "COMMENCEMENT", "CORRECTION", "INSUFFICIENT_EVIDENCE"}
    ),
    "RECONSTRUCTION_PLAN_DECISION": frozenset(
        {"SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ),
    "RECONSTRUCTION_PLAN_CHALLENGE": frozenset(
        {"SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ),
}

_INSTRUCTION = (
    "You are a bounded legal-analysis component. Answer only from the supplied "
    "evidence. Reply with one JSON object and nothing else, containing exactly "
    "these four keys: decision_code (string), supporting_evidence_refs (array of "
    "strings drawn only from the supplied evidence references), unresolved_facts "
    "(array of strings), challenge_code (one of NOT_APPLICABLE, PASS, FAIL). "
    "Do not add commentary, markdown, or any other key. If the evidence does not "
    "support a decision, return decision_code INSUFFICIENT_EVIDENCE and list what "
    "is missing in unresolved_facts."
)


def semantic_prompt_fingerprint() -> str:
    """Return the exact repository-owned system-prompt identity."""
    return f"sha256:{sha256(_INSTRUCTION.encode()).hexdigest()}"


@dataclass(frozen=True, slots=True)
class AzureDeployment:
    """Exact coordinates of one Azure OpenAI chat deployment."""

    endpoint: str
    deployment: str
    api_version: str
    api_key: str

    @classmethod
    def from_credential_json(cls, raw: bytes) -> AzureDeployment:
        """Parse the four-field credential this repository stages for Azure."""
        parsed = _object(
            _parse_json(raw, "MODEL_CREDENTIAL_INVALID", max_bytes=_MAX_CREDENTIAL_BYTES),
            "MODEL_CREDENTIAL_INVALID",
        )
        if set(parsed) != {"endpoint", "deployment", "api_version", "api_key"}:
            message = "MODEL_CREDENTIAL_FIELDS_INVALID"
            raise ProcessingError(message)
        return cls(
            _text(parsed, "endpoint", "MODEL_CREDENTIAL_ENDPOINT_INVALID").rstrip("/"),
            _text(parsed, "deployment", "MODEL_CREDENTIAL_DEPLOYMENT_INVALID"),
            _text(parsed, "api_version", "MODEL_CREDENTIAL_VERSION_INVALID"),
            _text(parsed, "api_key", "MODEL_CREDENTIAL_KEY_INVALID"),
        )

    def completions_url(self) -> str:
        """Build the exact chat-completions URL for this deployment."""
        return (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )


class ModelCall(Protocol):
    """The transport surface the runner needs, so a test can supply its own."""

    def post_json(self, url: str, headers: dict[str, str], body: JsonValue) -> dict[str, JsonValue]:
        """Send one request and return its decoded reply."""
        ...


class BoundedModelTransport:
    """Bounded JSON transport that reaches the model through one egress proxy.

    The connection is opened to the proxy and tunnelled with CONNECT, so TLS is
    still terminated at the provider. The proxy is a constructor argument, never an
    environment variable, so a worker cannot fall back to direct egress when the
    variable is unset.
    """

    def __init__(
        self,
        proxy_host: str,
        proxy_port: int,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a transport pinned to one proxy with default trust."""
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._timeout = timeout_seconds
        self._context = ssl.create_default_context()

    def post_json(self, url: str, headers: dict[str, str], body: JsonValue) -> dict[str, JsonValue]:
        """Send one bounded POST through the proxy and return its JSON object."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname is None:
            message = "MODEL_ENDPOINT_NOT_HTTPS"
            raise ProcessingError(message)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        connection = HTTPSConnection(
            self._proxy_host,
            port=self._proxy_port,
            timeout=self._timeout,
            context=self._context,
        )
        try:
            connection.set_tunnel(parsed.hostname, parsed.port or 443)
            connection.request(
                "POST",
                target,
                body=canonicalize(body),
                headers={**headers, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read(_MAX_REPLY_BYTES + 1)
            if len(raw) > _MAX_REPLY_BYTES:
                message = "MODEL_REPLY_TOO_LARGE"
                raise ProcessingError(message)
            if response.status >= _HTTP_BAD_REQUEST:
                message = f"MODEL_HTTP_{response.status}"
                raise ProcessingError(message)
        except (OSError, TimeoutError) as error:
            message = "MODEL_TRANSPORT_FAILURE"
            raise ProcessingError(message) from error
        finally:
            connection.close()
        if not raw:
            return {}
        return _object(_parse_json(raw, "MODEL_REPLY_NOT_JSON"), "MODEL_REPLY_NOT_OBJECT")


class AzureSemanticTaskRunner:
    """Real `SemanticTaskRunner` backed by one Azure OpenAI chat deployment."""

    def __init__(
        self,
        deployment: AzureDeployment,
        transport: ModelCall,
        *,
        max_output_tokens: int = 1024,
    ) -> None:
        """Bind the runner to one deployment and one proxied transport."""
        self._deployment = deployment
        self._transport = transport
        self._max_output_tokens = max_output_tokens
        self.invocations: list[str] = []

    def invoke(
        self,
        profile: SemanticTaskProfile,
        request: SemanticTaskRequest,
    ) -> SemanticDecision:
        """Return one strict bounded decision, or fail closed."""
        if profile.provider != AZURE_OPENAI_PROVIDER:
            message = "SEMANTIC_PROVIDER_NOT_ADMITTED"
            raise ProcessingError(message)
        if profile.deployment_name != self._deployment.deployment:
            message = "SEMANTIC_DEPLOYMENT_MISMATCH"
            raise ProcessingError(message)
        validate_semantic_task_contract(profile, request)
        reply = self._transport.post_json(
            self._deployment.completions_url(),
            {"api-key": self._deployment.api_key},
            {
                "messages": [
                    {"role": "system", "content": _INSTRUCTION},
                    {"role": "user", "content": _prompt(request)},
                ],
                "max_completion_tokens": self._max_output_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        fields = _strict_fields(_content(reply), profile, request)
        provider_request_id = _provider_request_id(reply)
        value = {
            "challenge_code": fields[3],
            "decision_code": fields[0],
            "phase": request.phase,
            "request_id": request.request_id,
            "supporting_evidence_refs": list(fields[1]),
            "task": request.task,
            "unresolved_facts": list(fields[2]),
        }
        output_fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"
        self.invocations.append(request.request_id)
        return SemanticDecision(
            request.request_id,
            request.task,
            request.phase,
            fields[0],
            fields[1],
            fields[2],
            _challenge_literal(fields[3]),
            output_fingerprint,
            AZURE_OPENAI_PROVIDER,
            provider_request_id,
            semantic_effect_receipt_id(request.request_id, provider_request_id, output_fingerprint),
        )

    def invoke_exact_json(
        self,
        profile: SemanticTaskProfile,
        request: SemanticTaskRequest,
        *,
        output_schema: str,
    ) -> bytes:
        """Return canonical task-specific JSON after exact profile and request admission."""
        if profile.provider != AZURE_OPENAI_PROVIDER:
            message = "SEMANTIC_PROVIDER_NOT_ADMITTED"
            raise ProcessingError(message)
        if profile.deployment_name != self._deployment.deployment:
            message = "SEMANTIC_DEPLOYMENT_MISMATCH"
            raise ProcessingError(message)
        if profile.output_schema != output_schema:
            message = "SEMANTIC_TASK_SCHEMA_AUTHORITY_INVALID"
            raise ProcessingError(message)
        _validate_request_envelope(profile, request)
        reply = self._transport.post_json(
            self._deployment.completions_url(),
            {"api-key": self._deployment.api_key},
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            _INSTRUCTION
                            + " Return only the exact JSON object required by output schema "
                            + output_schema
                            + "."
                        ),
                    },
                    {"role": "user", "content": _prompt(request)},
                ],
                "max_completion_tokens": self._max_output_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        parsed = _object(
            _parse_json(_content(reply).encode(), "MODEL_OUTPUT_NOT_JSON"),
            "MODEL_OUTPUT_NOT_OBJECT",
        )
        self.invocations.append(request.request_id)
        return canonicalize(checked_json_value(parsed))


def semantic_provider_input_text(request: SemanticTaskRequest) -> str:
    """Return the exact two-message text counted by V1 before provider use."""
    return f"{_INSTRUCTION}\n{_prompt(request)}"


def _prompt(request: SemanticTaskRequest) -> str:
    try:
        evidence = request.evidence_bytes.decode("utf-8", "strict")
    except UnicodeDecodeError:
        message = "SEMANTIC_EVIDENCE_NOT_UTF8"
        raise ProcessingError(message) from None
    references = "\n".join(f"- {reference}" for reference in request.evidence_refs)
    return (
        f"Task: {request.task}\n"
        f"Phase: {request.phase}\n"
        f"Subject: {request.subject_id}\n"
        f"Available evidence references:\n{references}\n\n"
        f"Evidence:\n{evidence}\n"
    )


def _content(reply: dict[str, JsonValue]) -> str:
    choices = reply.get("choices")
    if not isinstance(choices, list) or not choices:
        message = "MODEL_NO_CHOICES"
        raise ProcessingError(message)
    first = _object(choices[0], "MODEL_CHOICE_INVALID")
    message_body = _object(first.get("message"), "MODEL_MESSAGE_INVALID")
    content = message_body.get("content")
    if not isinstance(content, str) or not content.strip():
        message = "MODEL_CONTENT_EMPTY"
        raise ProcessingError(message)
    return content


def _provider_request_id(reply: dict[str, JsonValue]) -> str:
    value = reply.get("id")
    if type(value) is not str or not value or value == "unreported":
        message = "MODEL_PROVIDER_REQUEST_ID_MISSING"
        raise ProcessingError(message)
    return value


def _strict_fields(
    content: str,
    profile: SemanticTaskProfile,
    request: SemanticTaskRequest,
) -> tuple[str, tuple[str, ...], tuple[str, ...], str]:
    parsed = _object(
        _parse_json(content.encode(), "MODEL_OUTPUT_NOT_JSON"),
        "MODEL_OUTPUT_NOT_OBJECT",
    )
    if frozenset(parsed) != _DECISION_KEYS:
        message = "MODEL_OUTPUT_FIELDS_UNEXPECTED"
        raise ProcessingError(message)
    decision_code = parsed["decision_code"]
    refs = parsed["supporting_evidence_refs"]
    unresolved = parsed["unresolved_facts"]
    challenge = parsed["challenge_code"]
    decision = _exact_text(decision_code, "MODEL_DECISION_CODE_INVALID")
    allowed = _TASK_DECISION_CODES.get(profile.task)
    if allowed is not None and decision not in allowed:
        message = "MODEL_DECISION_CODE_INVALID"
        raise ProcessingError(message)
    evidence_refs = _text_tuple(refs, "MODEL_EVIDENCE_REFS_INVALID")
    unresolved_facts = _text_tuple(unresolved, "MODEL_UNRESOLVED_FACTS_INVALID")
    if type(challenge) is not str or challenge not in _CHALLENGE_CODES:
        message = "MODEL_CHALLENGE_CODE_INVALID"
        raise ProcessingError(message)
    # A citation the evidence never offered is a fabrication, not a judgment.
    unknown = [item for item in evidence_refs if item not in request.evidence_refs]
    if unknown:
        message = "MODEL_CITED_UNSUPPLIED_EVIDENCE"
        raise ProcessingError(message)
    return (decision, evidence_refs, unresolved_facts, challenge)


def validate_semantic_task_contract(
    profile: SemanticTaskProfile,
    request: SemanticTaskRequest,
) -> None:
    """Validate the repository-owned task contract before any provider effect."""
    if profile.task not in _TASK_DECISION_CODES:
        return
    expected_phase = "CHALLENGE" if profile.task.endswith("_CHALLENGE") else "DECISION"
    if request.task != profile.task or request.profile_id != profile.profile_id:
        message = "SEMANTIC_TASK_PROFILE_MISMATCH"
        raise ProcessingError(message)
    if request.phase != expected_phase:
        message = "SEMANTIC_TASK_PHASE_INVALID"
        raise ProcessingError(message)
    if (
        profile.input_schema != SEMANTIC_INPUT_SCHEMA
        or profile.output_schema != SEMANTIC_OUTPUT_SCHEMA
        or profile.prompt_fingerprint != semantic_prompt_fingerprint()
    ):
        message = "SEMANTIC_TASK_SCHEMA_AUTHORITY_INVALID"
        raise ProcessingError(message)
    if (
        type(request.evidence_bytes) is not bytes
        or not request.evidence_bytes
        or len(request.evidence_bytes) > profile.evidence_budget_bytes
        or type(request.evidence_refs) is not tuple
        or not request.evidence_refs
        or any(type(item) is not str or not item for item in request.evidence_refs)
        or len(set(request.evidence_refs)) != len(request.evidence_refs)
    ):
        message = "SEMANTIC_EVIDENCE_LIMIT_INVALID"
        raise ProcessingError(message)
    _prompt(request)


def _validate_request_envelope(profile: SemanticTaskProfile, request: SemanticTaskRequest) -> None:
    """Validate the common evidence-bound request without assuming one output shape."""
    expected_phase = "CHALLENGE" if profile.task.endswith("_CHALLENGE") else "DECISION"
    if request.task != profile.task or request.profile_id != profile.profile_id:
        message = "SEMANTIC_TASK_PROFILE_MISMATCH"
        raise ProcessingError(message)
    if request.phase != expected_phase:
        message = "SEMANTIC_TASK_PHASE_INVALID"
        raise ProcessingError(message)
    if (
        type(request.evidence_bytes) is not bytes
        or not request.evidence_bytes
        or len(request.evidence_bytes) > profile.evidence_budget_bytes
        or type(request.evidence_refs) is not tuple
        or not request.evidence_refs
        or any(type(item) is not str or not item for item in request.evidence_refs)
        or len(set(request.evidence_refs)) != len(request.evidence_refs)
    ):
        message = "SEMANTIC_EVIDENCE_LIMIT_INVALID"
        raise ProcessingError(message)
    _prompt(request)


def _parse_json(
    raw: bytes,
    error_code: str,
    *,
    max_bytes: int = _MAX_REPLY_BYTES,
) -> JsonValue:
    try:
        return parse_json_bytes(raw, max_bytes=max_bytes)
    except ContractViolation:
        raise ProcessingError(error_code) from None


def _object(value: JsonValue, error_code: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ProcessingError(error_code)
    return value


def _text(document: dict[str, JsonValue], field: str, error_code: str) -> str:
    return _exact_text(document.get(field), error_code)


def _exact_text(value: JsonValue, error_code: str) -> str:
    if type(value) is not str or not value:
        raise ProcessingError(error_code)
    return value


def _text_tuple(value: JsonValue, error_code: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProcessingError(error_code)
    result: list[str] = []
    for item in value:
        if type(item) is not str:
            raise ProcessingError(error_code)
        result.append(item)
    return tuple(result)


def _challenge_literal(value: str) -> Literal["NOT_APPLICABLE", "PASS", "FAIL"]:
    if value == "PASS":
        return "PASS"
    if value == "FAIL":
        return "FAIL"
    return "NOT_APPLICABLE"
