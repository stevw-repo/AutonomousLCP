"""Dependency-neutral, exact Judiciary transport-attempt policy."""

from __future__ import annotations

import hashlib
import json
from typing import Final, cast
from urllib.parse import urlsplit

_POLICY_100_NAME: Final = "JUDICIARY_TRANSPORT_ATTEMPTS_1.0.0"
_POLICY_110_NAME: Final = "JUDICIARY_TRANSPORT_ATTEMPTS_1.1.0"
_POLICY_120_NAME: Final = "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0"
_MAINTENANCE_STATUS: Final = 200
_MAINTENANCE_BYTE_LENGTH: Final = 255
_MAINTENANCE_SHA256: Final = "39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f"
_RETRYABLE_SERVER_ERROR_STATUSES: Final = frozenset({500, 502, 503, 504})
_PROFILE_100: Final[dict[str, object]] = {
    "maximum_attempts_per_logical_request": 2,
    "minimum_start_interval_seconds": 2.0,
    "name": _POLICY_100_NAME,
    "retry_eligibility": {
        "body_byte_length": 0,
        "final_url": None,
        "media_type": "application/octet-stream",
        "redirect_rejected": False,
        "status": 0,
    },
}
_PROFILE_110: Final[dict[str, object]] = {
    "maximum_attempts_per_logical_request": 2,
    "minimum_start_interval_seconds": 2.0,
    "name": _POLICY_110_NAME,
    "retry_eligibility": {
        "normalized_transport_failure": {
            "body_byte_length": 0,
            "final_url": None,
            "media_type": "application/octet-stream",
            "redirect_rejected": False,
            "status": 0,
        },
        "publisher_maintenance_outage": {
            "body_byte_length": 255,
            "body_sha256": _MAINTENANCE_SHA256,
            "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
            "media_type": "text/plain",
            "redirect_rejected": False,
            "status": 200,
        },
    },
}
_PROFILE_120: Final[dict[str, object]] = {
    "maximum_attempts_per_logical_request": 2,
    "minimum_start_interval_seconds": 2.0,
    "name": _POLICY_120_NAME,
    "retry_eligibility": {
        "normalized_transport_failure": {
            "body_byte_length": 0,
            "final_url": None,
            "media_type": "application/octet-stream",
            "redirect_rejected": False,
            "status": 0,
        },
        "publisher_maintenance_outage": {
            "body_byte_length": 255,
            "body_sha256": _MAINTENANCE_SHA256,
            "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
            "media_type": "text/plain",
            "redirect_rejected": False,
            "status": 200,
        },
        "publisher_server_error": {
            "body_byte_length": "INTEGER_0_TO_REQUEST_MAX_BYTES",
            "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
            "media_type": "ANY_RETAINED_MEDIA_TYPE",
            "redirect_rejected": False,
            "statuses": [500, 502, 503, 504],
        },
    },
}
_PROFILES: Final = {
    _POLICY_100_NAME: _PROFILE_100,
    _POLICY_110_NAME: _PROFILE_110,
    _POLICY_120_NAME: _PROFILE_120,
}


def canonical(value: object) -> bytes:
    """Encode one policy fact in the repository's canonical JSON form."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def execution_policy(name: str = _POLICY_120_NAME) -> dict[str, object]:
    """Return a fresh exact execution-policy profile for report binding."""
    profile = _PROFILES.get(name)
    if profile is None:
        code = "JUDICIARY_EXECUTION_POLICY_INVALID"
        raise ValueError(code)
    value: object = json.loads(canonical(profile))
    if type(value) is not dict:
        code = "JUDICIARY_EXECUTION_POLICY_INVALID"
        raise ValueError(code)
    return cast("dict[str, object]", value)


def execution_policy_fingerprint(name: str = _POLICY_120_NAME) -> str:
    """Return the canonical fingerprint for one closed policy version."""
    return "sha256:" + hashlib.sha256(canonical(execution_policy(name))).hexdigest()


def recognized_execution_policy(policy: object, fingerprint: object) -> str | None:
    """Resolve only an exact closed policy/fingerprint pair."""
    if type(fingerprint) is not str:
        return None
    try:
        candidate = canonical(policy)
    except TypeError, ValueError:
        return None
    if fingerprint != "sha256:" + hashlib.sha256(candidate).hexdigest():
        return None
    for name in _PROFILES:
        if candidate == canonical(execution_policy(name)) and fingerprint == (
            execution_policy_fingerprint(name)
        ):
            return name
    return None


def maintenance_outage(  # noqa: PLR0913 - every exact response fact is explicit.
    *,
    status: int,
    body: bytes,
    media_type: str,
    final_url: str | None,
    redirect_rejected: bool,
    requested_url: str | None,
) -> bool:
    """Recognize only the exact retained publisher-maintenance response tuple."""
    if type(body) is not bytes:
        return False
    return maintenance_outage_facts(
        status=status,
        body_byte_length=len(body),
        body_fingerprint="sha256:" + hashlib.sha256(body).hexdigest(),
        media_type=media_type,
        final_url=final_url,
        redirect_rejected=redirect_rejected,
        requested_url=requested_url,
    )


def maintenance_outage_facts(  # noqa: PLR0913 - every exact retained fact is explicit.
    *,
    status: int,
    body_byte_length: int,
    body_fingerprint: str,
    media_type: str,
    final_url: str | None,
    redirect_rejected: bool,
    requested_url: str | None,
) -> bool:
    """Recognize the exact maintenance tuple from independently read-back facts."""
    if type(requested_url) is not str:
        return False
    try:
        parsed = urlsplit(requested_url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and port in {None, 443}
        and type(status) is int
        and status == _MAINTENANCE_STATUS
        and type(body_byte_length) is int
        and body_byte_length == _MAINTENANCE_BYTE_LENGTH
        and type(body_fingerprint) is str
        and body_fingerprint == "sha256:" + _MAINTENANCE_SHA256
        and type(media_type) is str
        and media_type == "text/plain"
        and type(final_url) is str
        and final_url == requested_url
        and type(redirect_rejected) is bool
        and redirect_rejected is False
    )


def publisher_server_error(  # noqa: PLR0913 - every response fact is explicit.
    *,
    status: int,
    body: bytes,
    media_type: str,
    final_url: str | None,
    redirect_rejected: bool,
    requested_url: str | None,
    max_bytes: int | None,
) -> bool:
    """Recognize one closed publisher server-error tuple from captured bytes."""
    if type(body) is not bytes:
        return False
    return publisher_server_error_facts(
        status=status,
        body_byte_length=len(body),
        media_type=media_type,
        final_url=final_url,
        redirect_rejected=redirect_rejected,
        requested_url=requested_url,
        max_bytes=max_bytes,
    )


def publisher_server_error_facts(  # noqa: PLR0913 - every retained fact is explicit.
    *,
    status: int,
    body_byte_length: int,
    media_type: str,
    final_url: str | None,
    redirect_rejected: bool,
    requested_url: str | None,
    max_bytes: int | None,
) -> bool:
    """Recognize one closed publisher server-error tuple from retained facts."""
    if type(requested_url) is not str:
        return False
    try:
        parsed = urlsplit(requested_url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and port in {None, 443}
        and type(status) is int
        and status in _RETRYABLE_SERVER_ERROR_STATUSES
        and type(body_byte_length) is int
        and body_byte_length >= 0
        and type(max_bytes) is int
        and max_bytes >= 0
        and body_byte_length <= max_bytes
        and type(media_type) is str
        and type(final_url) is str
        and final_url == requested_url
        and type(redirect_rejected) is bool
        and redirect_rejected is False
    )


def retry_eligible(  # noqa: PLR0913 - the closed tuple plus its policy are explicit.
    *,
    status: int,
    body: bytes,
    media_type: str,
    final_url: str | None,
    redirect_rejected: bool,
    requested_url: str | None = None,
    max_bytes: int | None = None,
    policy_name: str = _POLICY_120_NAME,
) -> bool:
    """Admit only a tuple named by the selected closed policy version."""
    normalized_transport_failure = (
        type(status) is int
        and status == 0
        and type(body) is bytes
        and body == b""
        and type(media_type) is str
        and media_type == "application/octet-stream"
        and type(final_url) in {str, type(None)}
        and final_url is None
        and type(redirect_rejected) is bool
        and redirect_rejected is False
    )
    if policy_name == _POLICY_100_NAME:
        return normalized_transport_failure
    if policy_name not in {_POLICY_110_NAME, _POLICY_120_NAME}:
        return False
    eligible = normalized_transport_failure or maintenance_outage(
        status=status,
        body=body,
        media_type=media_type,
        final_url=final_url,
        redirect_rejected=redirect_rejected,
        requested_url=requested_url,
    )
    if policy_name == _POLICY_110_NAME:
        return eligible
    return eligible or publisher_server_error(
        status=status,
        body=body,
        media_type=media_type,
        final_url=final_url,
        redirect_rejected=redirect_rejected,
        requested_url=requested_url,
        max_bytes=max_bytes,
    )
