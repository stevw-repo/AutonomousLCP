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

import json
import ssl
from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPSConnection
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .model import ProcessingError, SemanticDecision

if TYPE_CHECKING:
    from asklegal_legal_desks import SemanticTaskProfile

    from .model import SemanticTaskRequest

AZURE_OPENAI_PROVIDER = "AZURE_OPENAI"
"""The only provider value this runner will serve."""

_DEFAULT_TIMEOUT_SECONDS = 90
_HTTP_BAD_REQUEST = 400
_MAX_REPLY_BYTES = 1_000_000
_MAX_EVIDENCE_CHARACTERS = 24_000
_DECISION_KEYS = frozenset(
    {"decision_code", "supporting_evidence_refs", "unresolved_facts", "challenge_code"}
)
_CHALLENGE_CODES = frozenset({"NOT_APPLICABLE", "PASS", "FAIL"})

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
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            message = "MODEL_CREDENTIAL_INVALID"
            raise ProcessingError(message)
        missing = {"endpoint", "deployment", "api_version", "api_key"} - set(parsed)
        if missing:
            message = "MODEL_CREDENTIAL_INCOMPLETE"
            raise ProcessingError(message)
        return cls(
            str(parsed["endpoint"]).rstrip("/"),
            str(parsed["deployment"]),
            str(parsed["api_version"]),
            str(parsed["api_key"]),
        )

    def completions_url(self) -> str:
        """Build the exact chat-completions URL for this deployment."""
        return (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )


class ModelCall(Protocol):
    """The transport surface the runner needs, so a test can supply its own."""

    def post_json(self, url: str, headers: dict[str, str], body: object) -> dict[str, object]:
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

    def post_json(self, url: str, headers: dict[str, str], body: object) -> dict[str, object]:
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
                body=json.dumps(body).encode(),
                headers={**headers, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read(_MAX_REPLY_BYTES)
            if response.status >= _HTTP_BAD_REQUEST:
                message = f"MODEL_HTTP_{response.status}"
                raise ProcessingError(message)
        except (OSError, TimeoutError) as error:
            message = "MODEL_TRANSPORT_FAILURE"
            raise ProcessingError(message) from error
        finally:
            connection.close()
        decoded = json.loads(raw) if raw else {}
        if not isinstance(decoded, dict):
            message = "MODEL_REPLY_NOT_OBJECT"
            raise ProcessingError(message)
        return decoded


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
        fields = _strict_fields(_content(reply), request)
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
        )


def _prompt(request: SemanticTaskRequest) -> str:
    evidence = request.evidence_bytes.decode("utf-8", "replace")[:_MAX_EVIDENCE_CHARACTERS]
    references = "\n".join(f"- {reference}" for reference in request.evidence_refs)
    return (
        f"Task: {request.task}\n"
        f"Phase: {request.phase}\n"
        f"Subject: {request.subject_id}\n"
        f"Available evidence references:\n{references}\n\n"
        f"Evidence:\n{evidence}\n"
    )


def _content(reply: dict[str, object]) -> str:
    choices = reply.get("choices")
    if not isinstance(choices, list) or not choices:
        message = "MODEL_NO_CHOICES"
        raise ProcessingError(message)
    first = choices[0]
    if not isinstance(first, dict):
        message = "MODEL_CHOICE_INVALID"
        raise ProcessingError(message)
    message_body = first.get("message")
    if not isinstance(message_body, dict):
        message = "MODEL_MESSAGE_INVALID"
        raise ProcessingError(message)
    content = message_body.get("content")
    if not isinstance(content, str) or not content.strip():
        message = "MODEL_CONTENT_EMPTY"
        raise ProcessingError(message)
    return content


def _strict_fields(
    content: str,
    request: SemanticTaskRequest,
) -> tuple[str, tuple[str, ...], tuple[str, ...], str]:
    try:
        parsed = json.loads(content)
    except ValueError as error:
        message = "MODEL_OUTPUT_NOT_JSON"
        raise ProcessingError(message) from error
    if not isinstance(parsed, dict):
        message = "MODEL_OUTPUT_NOT_OBJECT"
        raise ProcessingError(message)
    if set(parsed) != _DECISION_KEYS:
        message = "MODEL_OUTPUT_FIELDS_UNEXPECTED"
        raise ProcessingError(message)
    decision_code = parsed["decision_code"]
    refs = parsed["supporting_evidence_refs"]
    unresolved = parsed["unresolved_facts"]
    challenge = parsed["challenge_code"]
    if not isinstance(decision_code, str) or not decision_code:
        message = "MODEL_DECISION_CODE_INVALID"
        raise ProcessingError(message)
    if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
        message = "MODEL_EVIDENCE_REFS_INVALID"
        raise ProcessingError(message)
    if not isinstance(unresolved, list) or not all(isinstance(item, str) for item in unresolved):
        message = "MODEL_UNRESOLVED_FACTS_INVALID"
        raise ProcessingError(message)
    if not isinstance(challenge, str) or challenge not in _CHALLENGE_CODES:
        message = "MODEL_CHALLENGE_CODE_INVALID"
        raise ProcessingError(message)
    # A citation the evidence never offered is a fabrication, not a judgment.
    unknown = [item for item in refs if item not in request.evidence_refs]
    if unknown:
        message = "MODEL_CITED_UNSUPPLIED_EVIDENCE"
        raise ProcessingError(message)
    return (decision_code, tuple(refs), tuple(unresolved), challenge)


def _challenge_literal(value: str) -> Literal["NOT_APPLICABLE", "PASS", "FAIL"]:
    if value == "PASS":
        return "PASS"
    if value == "FAIL":
        return "FAIL"
    return "NOT_APPLICABLE"
