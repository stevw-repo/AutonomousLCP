"""Disabled-by-default operator boundary for one authentic current-cycle GLD observation."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import signal
import stat
import sys
from base64 import b64decode, b64encode
from binascii import Error as BinasciiError
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from math import floor
from multiprocessing.connection import Connection
from pathlib import Path
from resource import RLIMIT_AS, setrlimit
from time import monotonic
from typing import Never, Protocol, cast
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import ImmutableVault, RetentionProfile
from asklegal_source_connectors import (
    GldGazetteWindow,
    GldSessionRequest,
    HttpMethod,
    OfficialEndpointContract,
    OfficialTransportResponse,
    ProxiedOfficialHttpTransport,
    load_hk_legislation_source_register,
)
from patchright.sync_api import BrowserContext, Route, sync_playwright
from patchright.sync_api import Error as PatchrightError

from asklegal_acquisition_worker.gld_session import (
    FileProtectedSessionStore,
    GldChallengeSessionContract,
    LocalGldSessionTransport,
    build_patchright_gld_session_transport,
)
from asklegal_acquisition_worker.v1_infrastructure import load_v1_infrastructure

_MODE = "ASKLEGAL_HK_V1_GLD_OPERATOR_MODE"
_AUTHORITY = "ASKLEGAL_HK_V1_GLD_CHALLENGE_AUTHORITY_RECEIPT"
_CHALLENGE = "ASKLEGAL_HK_V1_GLD_CHALLENGE_CONTRACT"
_SESSION_ROOT = "ASKLEGAL_HK_V1_GLD_SESSION_ROOT"
_START_DATE = "ASKLEGAL_HK_V1_GLD_START_DATE"
_DISCOVER_MODE = "DISCOVER_CONTRACT"
_OBSERVE_MODE = "OBSERVE_WINDOW"
_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"
_INVENTORY_ENDPOINT_ID = "sep_00000000000000000000000000000000000000000000003b"
_RETENTION = RetentionProfile("hk-v1-gld-observation", "2099-12-31T00:00:00Z")
_MAX_CONFIG_BYTES = 65_536
_MIN_HTTP_STATUS = 100
_MAX_HTTP_STATUS = 599
_MAX_COOKIE_CANDIDATES = 16
_COOKIE_FIELD_COUNT = 3
_MAX_COOKIE_NAME = 256
_MAX_HOST = 253
_MAX_PATH = 2_048
_MAX_PROBE_CANDIDATES = 64
_DISCOVERY_INVALID = "GLD_CONTRACT_DISCOVERY_OBSERVATION_INVALID"
_SESSION_DIRECTORY_MODE = 0o700
_OPERATION_DEADLINE_SECONDS = 60
_SESSION_DEADLINE_SECONDS = 45
_LISTING_DEADLINE_SECONDS = 15
_SESSION_MAX_ATTEMPTS = 3
_SESSION_MAX_REQUESTS_PER_ATTEMPT = 64
_LISTING_MAX_REQUESTS = 1
_DISCOVERY_CHILD_MEMORY_OVERHEAD_BYTES = 1_073_741_824
_DISCOVERY_CHILD_EXIT_GRACE_SECONDS = 1.0
_DISCOVERY_CHILD_OUTCOME_FIELDS = 2


class GldOperatorError(RuntimeError):
    """One stable, non-secret GLD operator stop code."""


@dataclass(frozen=True, slots=True)
class GldOperatorPreflight:
    """Read-only readiness facts; executable never means listing completeness."""

    mode: str
    observation_enabled: bool
    authority_admitted: bool
    challenge_contract_admitted: bool
    session_store_admitted: bool
    observation_executable: bool
    window_issuance_ready: bool
    blocker_code: str

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact non-secret operator report."""
        return {
            "authority_admitted": self.authority_admitted,
            "blocker_code": self.blocker_code,
            "challenge_contract_admitted": self.challenge_contract_admitted,
            "mode": self.mode,
            "observation_enabled": self.observation_enabled,
            "observation_executable": self.observation_executable,
            "session_store_admitted": self.session_store_admitted,
            "window_issuance_ready": self.window_issuance_ready,
        }


class _SessionPort(Protocol):
    def establish(self, request: GldSessionRequest) -> object: ...

    def invalidate(self, session_id: str) -> None: ...


class _HttpPort(Protocol):
    def request(self, *, endpoint: object, method: HttpMethod, timeout_seconds: int) -> object: ...


class _SessionFactory(Protocol):
    def __call__(
        self,
        request: GldSessionRequest,
        challenge_contract: GldChallengeSessionContract,
        session_root: Path,
        *,
        experiment_deadline_seconds: tuple[int, int, int],
        maximum_requests_per_attempt: int,
    ) -> LocalGldSessionTransport: ...


@dataclass(frozen=True, slots=True)
class GldContractDiscoveryObservation:
    """Sanitized browser facts plus the bounded raw navigation response."""

    status_code: int
    final_url: str
    raw_response: bytes
    truncated: bool
    cookies: tuple[tuple[str, str, str], ...]
    probe_candidates: tuple[str, ...]

    def __post_init__(self) -> None:
        """Keep publisher-controlled metadata bounded, sanitized, and value-free."""
        parsed = urlsplit(self.final_url)
        if (
            type(self.status_code) is not int
            or not _MIN_HTTP_STATUS <= self.status_code <= _MAX_HTTP_STATUS
            or type(self.raw_response) is not bytes
            or type(self.truncated) is not bool
            or parsed.scheme != "https"
            or parsed.hostname != "egazette.gld.gov.hk"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.query
            or parsed.fragment
            or type(self.cookies) is not tuple
            or len(self.cookies) > _MAX_COOKIE_CANDIDATES
            or any(
                type(cookie) is not tuple
                or len(cookie) != _COOKIE_FIELD_COUNT
                or any(type(value) is not str or not value for value in cookie)
                or len(cookie[0]) > _MAX_COOKIE_NAME
                or len(cookie[1]) > _MAX_HOST
                or len(cookie[2]) > _MAX_PATH
                or not cookie[2].startswith("/")
                for cookie in self.cookies
            )
            or type(self.probe_candidates) is not tuple
            or len(self.probe_candidates) > _MAX_PROBE_CANDIDATES
            or any(
                type(path) is not str or not path.startswith("/") or "?" in path or "#" in path
                for path in self.probe_candidates
            )
        ):
            raise ValueError(_DISCOVERY_INVALID)


class _DiscoveryPort(Protocol):
    def discover(  # noqa: PLR0913
        self,
        *,
        host: str,
        start_path: str,
        allowed_paths: tuple[str, ...],
        deadline_seconds: int,
        maximum_requests: int,
        maximum_response_bytes: int,
    ) -> GldContractDiscoveryObservation: ...


class _DiscoveryProcess(Protocol):
    @property
    def pid(self) -> int | None: ...

    def is_alive(self) -> bool: ...

    def join(self, timeout: float | None = None) -> None: ...


class _CdpSession(Protocol):
    def send(self, method: str, params: Mapping[str, object] | None = None) -> object: ...

    def on(self, event: str, callback: Callable[[object], None]) -> None: ...


@dataclass(slots=True)
class _BoundedBodyCapture:
    body: bytes | None = None
    exceeded: bool = False
    failed: bool = False


class PatchrightGldContractDiscovery:
    """Ephemeral same-host observation used only to freeze a later session contract."""

    def discover(  # noqa: C901, PLR0913
        self,
        *,
        host: str,
        start_path: str,
        allowed_paths: tuple[str, ...],
        deadline_seconds: int,
        maximum_requests: int,
        maximum_response_bytes: int,
    ) -> GldContractDiscoveryObservation:
        """Supervise the whole browser lifetime under one wall and memory boundary."""
        parent, child = multiprocessing.get_context("fork").Pipe(duplex=False)
        process = multiprocessing.get_context("fork").Process(
            target=_run_discovery_child,
            args=(
                child,
                host,
                start_path,
                allowed_paths,
                deadline_seconds,
                maximum_requests,
                maximum_response_bytes,
            ),
        )
        started = monotonic()
        process.start()
        child.close()
        try:
            remaining = deadline_seconds - (monotonic() - started)
            if remaining <= 0 or not parent.poll(remaining):
                _stop_discovery_process(process)
                _stop("GLD_CONTRACT_DISCOVERY_DEADLINE_EXCEEDED")
            try:
                outcome: object = parent.recv()
            except (EOFError, OSError) as error:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED", error)
            remaining = deadline_seconds - (monotonic() - started)
            process.join(max(0.0, remaining))
            if process.is_alive():
                _stop_discovery_process(process)
                _stop("GLD_CONTRACT_DISCOVERY_DEADLINE_EXCEEDED")
            if type(outcome) is not tuple:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED")
            exact_outcome = cast("tuple[object, ...]", outcome)
            if len(exact_outcome) != _DISCOVERY_CHILD_OUTCOME_FIELDS:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED")
            tag = exact_outcome[0]
            payload = exact_outcome[1]
            if tag not in {"OK", "ERROR"}:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED")
            if tag == "ERROR":
                code = payload
                if type(code) is not str or not code.startswith("GLD_"):
                    _stop("GLD_CONTRACT_DISCOVERY_FAILED")
                _stop(code)
            observation = payload
            if (
                type(observation) is not GldContractDiscoveryObservation
                or len(observation.raw_response) > maximum_response_bytes
            ):
                _stop("GLD_CONTRACT_DISCOVERY_RESPONSE_LIMIT_EXCEEDED")
            return observation
        finally:
            parent.close()
            if process.is_alive():
                _stop_discovery_process(process)


def _run_discovery_child(  # noqa: PLR0913, PLR0917
    connection: Connection,
    host: str,
    start_path: str,
    allowed_paths: tuple[str, ...],
    deadline_seconds: int,
    maximum_requests: int,
    maximum_response_bytes: int,
) -> None:
    """Run one direct Patchright attempt in an isolated process group."""
    try:
        os.setsid()
        current_virtual_bytes = int(Path("/proc/self/statm").read_text().split()[0]) * os.sysconf(
            "SC_PAGE_SIZE"
        )
        child_limit = (
            current_virtual_bytes + _DISCOVERY_CHILD_MEMORY_OVERHEAD_BYTES + maximum_response_bytes
        )
        setrlimit(RLIMIT_AS, (child_limit, child_limit))
        observation = _discover_direct(
            host=host,
            start_path=start_path,
            allowed_paths=allowed_paths,
            deadline_seconds=deadline_seconds,
            maximum_requests=maximum_requests,
            maximum_response_bytes=maximum_response_bytes,
        )
        connection.send(("OK", observation))
    except GldOperatorError as error:
        connection.send(("ERROR", str(error)))
    except BaseException:  # noqa: BLE001 - child returns only one stable non-secret code.
        connection.send(("ERROR", "GLD_CONTRACT_DISCOVERY_FAILED"))
    finally:
        connection.close()


def _stop_discovery_process(process: _DiscoveryProcess) -> None:
    """Kill the exact isolated browser process group, including descendants."""
    if process.pid is None:
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    process.join(_DISCOVERY_CHILD_EXIT_GRACE_SECONDS)
    if process.is_alive():
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.join(_DISCOVERY_CHILD_EXIT_GRACE_SECONDS)


def _bounded_cdp_stream(
    session: _CdpSession, handle: str, maximum_response_bytes: int
) -> tuple[bytes, bool]:
    """Read no more than the authorized body plus one sentinel byte from Chromium."""
    body = bytearray()
    target = maximum_response_bytes + 1
    try:
        while len(body) < target:
            remaining = target - len(body)
            result = session.send("IO.read", {"handle": handle, "size": min(65_536, remaining)})
            if type(result) is not dict:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED")
            exact_result = cast("dict[str, object]", result)
            raw_data = exact_result.get("data")
            encoded = exact_result.get("base64Encoded", False)
            eof = exact_result.get("eof")
            if type(raw_data) is not str or type(encoded) is not bool or type(eof) is not bool:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED")
            try:
                chunk = b64decode(raw_data, validate=True) if encoded else raw_data.encode("utf-8")
            except (BinasciiError, UnicodeError) as error:
                _stop("GLD_CONTRACT_DISCOVERY_FAILED", error)
            body.extend(chunk[:remaining])
            if len(chunk) > remaining or len(body) == target:
                return bytes(body[:maximum_response_bytes]), True
            if eof:
                return bytes(body), False
    finally:
        session.send("IO.close", {"handle": handle})
    return bytes(body[:maximum_response_bytes]), len(body) > maximum_response_bytes


def _capture_paused_navigation(  # noqa: C901
    session: _CdpSession,
    event: object,
    maximum_response_bytes: int,
    capture: _BoundedBodyCapture,
) -> None:
    """Consume one response-stage document through the bounded CDP stream surface."""
    try:
        if type(event) is not dict:
            capture.failed = True
            return
        exact_event = cast("dict[str, object]", event)
        request_id = exact_event.get("requestId")
        status = exact_event.get("responseStatusCode")
        headers = exact_event.get("responseHeaders")
        if type(request_id) is not str or type(status) is not int or type(headers) is not list:
            capture.failed = True
            return
        stream_result = session.send("Fetch.takeResponseBodyAsStream", {"requestId": request_id})
        if type(stream_result) is not dict:
            capture.failed = True
            return
        exact_stream = cast("dict[str, object]", stream_result)
        stream_handle = exact_stream.get("stream")
        if type(stream_handle) is not str:
            capture.failed = True
            return
        body, exceeded = _bounded_cdp_stream(session, stream_handle, maximum_response_bytes)
        capture.exceeded = exceeded
        if exceeded:
            session.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"})
            return
        safe_headers: list[dict[str, object]] = []
        for item in cast("list[object]", headers):
            if type(item) is not dict:
                continue
            exact_header = cast("dict[str, object]", item)
            name = exact_header.get("name")
            if type(name) is str and name.lower() not in {
                "content-encoding",
                "content-length",
                "transfer-encoding",
            }:
                safe_headers.append(exact_header)
        session.send(
            "Fetch.fulfillRequest",
            {
                "requestId": request_id,
                "responseCode": status,
                "responseHeaders": safe_headers,
                "body": b64encode(body).decode("ascii"),
            },
        )
        capture.body = body
    except GldOperatorError:
        capture.failed = True
    except TypeError, ValueError:
        capture.failed = True


def _discover_direct(  # noqa: C901, PLR0913, PLR0915
    *,
    host: str,
    start_path: str,
    allowed_paths: tuple[str, ...],
    deadline_seconds: int,
    maximum_requests: int,
    maximum_response_bytes: int,
) -> GldContractDiscoveryObservation:
    """Navigate once without clicks, terms acceptance, credentials, or retained secrets."""
    observed_paths: list[str] = []
    request_count = 0
    exceeded = False
    allowed = frozenset(allowed_paths)

    def route_handler(route: Route) -> None:
        nonlocal exceeded, request_count
        request = route.request
        parsed = urlsplit(request.url)
        request_count += 1
        permitted = (
            request.method in {"GET", "HEAD"}
            and parsed.scheme == "https"
            and parsed.hostname == host
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in allowed
            and request.resource_type not in {"eventsource", "websocket"}
        )
        if request_count > maximum_requests:
            exceeded = True
            permitted = False
        elif permitted and parsed.path not in observed_paths:
            observed_paths.append(parsed.path)
        if permitted:
            route.continue_()
        else:
            route.abort()

    try:
        with sync_playwright() as engine:
            browser = engine.chromium.launch(
                headless=True,
                args=("--disable-extensions", "--disable-features=PasswordManagerOnboarding"),
            )
            try:
                context: BrowserContext = browser.new_context(
                    accept_downloads=False,
                    ignore_https_errors=False,
                    java_script_enabled=True,
                    service_workers="block",
                )
                context.route("**/*", route_handler)
                page = context.new_page()
                page.on("popup", lambda popup: popup.close())
                capture = _BoundedBodyCapture()
                cdp = cast("_CdpSession", context.new_cdp_session(page))
                cdp.on(
                    "Fetch.requestPaused",
                    lambda event: _capture_paused_navigation(
                        cdp, event, maximum_response_bytes, capture
                    ),
                )
                cdp.send(
                    "Fetch.enable",
                    {
                        "patterns": [
                            {
                                "urlPattern": f"https://{host}{start_path}",
                                "resourceType": "Document",
                                "requestStage": "Response",
                            }
                        ]
                    },
                )
                try:
                    response = page.goto(
                        f"https://{host}{start_path}",
                        timeout=float(deadline_seconds * 1_000),
                        wait_until="domcontentloaded",
                    )
                except PatchrightError:
                    if capture.exceeded:
                        _stop("GLD_CONTRACT_DISCOVERY_RESPONSE_LIMIT_EXCEEDED")
                    raise
                if response is None:
                    _stop("GLD_CONTRACT_DISCOVERY_FAILED")
                if capture.exceeded:
                    _stop("GLD_CONTRACT_DISCOVERY_RESPONSE_LIMIT_EXCEEDED")
                if capture.failed or capture.body is None:
                    _stop("GLD_CONTRACT_DISCOVERY_FAILED")
                raw = capture.body
                truncated = exceeded
                cookies = tuple(
                    sorted(
                        (
                            str(cookie.get("name", "")),
                            str(cookie.get("domain", "")),
                            str(cookie.get("path", "")),
                        )
                        for cookie in context.cookies()
                        if cookie.get("name") and cookie.get("domain") and cookie.get("path")
                    )
                )[:_MAX_COOKIE_CANDIDATES]
                final = urlsplit(page.url)._replace(query="", fragment="").geturl()
                return GldContractDiscoveryObservation(
                    response.status,
                    final,
                    raw,
                    truncated,
                    cookies,
                    tuple(sorted(observed_paths)),
                )
            finally:
                browser.close()
    except GldOperatorError:
        raise
    except PatchrightError as error:
        _stop("GLD_CONTRACT_DISCOVERY_FAILED", error)


def _stop(code: str, cause: BaseException | None = None) -> Never:
    error = GldOperatorError(code)
    if cause is None:
        raise error
    raise error from cause


def _absolute_regular(environment: Mapping[str, str], key: str) -> Path | None:
    raw = environment.get(key)
    if type(raw) is not str or not raw or raw != raw.strip():
        return None
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        return None
    return path


def _absolute_session_root(environment: Mapping[str, str]) -> Path | None:
    raw = environment.get(_SESSION_ROOT)
    if type(raw) is not str or not raw or raw != raw.strip():
        return None
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink():
        return None
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        return None
    if path.exists() and not path.is_dir():
        return None
    return path


def _document(path: Path) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(path.read_bytes(), max_bytes=_MAX_CONFIG_BYTES)
    except (OSError, TypeError, ValueError) as error:
        _stop("GLD_OPERATOR_CONFIG_INVALID", error)
    if type(value) is not dict:
        _stop("GLD_OPERATOR_CONFIG_INVALID")
    return value


def _exact_allowed_paths(value: JsonValue | None) -> tuple[str, ...] | None:
    """Validate one closed unique route list shared by preflight and execution."""
    if type(value) is not list or not value:
        return None
    paths: list[str] = []
    for candidate in value:
        if type(candidate) is not str or len(candidate) > _MAX_PATH:
            return None
        parsed = urlsplit(candidate)
        if (
            not candidate.startswith("/")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.path != candidate
            or candidate in paths
        ):
            return None
        paths.append(candidate)
    return tuple(paths)


def _fingerprinted(document: dict[str, JsonValue], *, fields: set[str]) -> dict[str, JsonValue]:
    if set(document) != fields | {"fingerprint"}:
        _stop("GLD_OPERATOR_CONFIG_INVALID")
    fingerprint = document["fingerprint"]
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    expected = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    if fingerprint != expected:
        _stop("GLD_OPERATOR_CONFIG_INVALID")
    return body


def _authority(path: Path) -> tuple[dict[str, JsonValue], str]:
    document = _document(path)
    claimed_fingerprint = document.get("fingerprint")
    body = _fingerprinted(
        document,
        fields={
            "schema_id",
            "schema_version",
            "authorization_id",
            "attempt_id",
            "named_authorizer",
            "source_id",
            "authorized_action",
            "rights_basis",
            "authorized_at",
            "expires_at",
            "cycle_id",
            "observation_cutoff",
            "endpoint_id",
            "endpoint_version",
            "register_version",
            "register_fingerprint",
            "admitted_host",
            "allowed_paths",
            "maximum_response_bytes",
            "maximum_requests",
            "deadline_seconds",
            "operation_deadline_seconds",
            "session_deadline_seconds",
            "listing_deadline_seconds",
            "session_max_attempts",
            "session_max_requests_per_attempt",
            "listing_max_requests",
            "challenge_contract_fingerprint",
            "discovery_observation_fingerprint",
            "primary_vault",
            "object_prefix",
            "manifest_prefix",
            "session_root",
        },
    )
    try:
        authorized_at = datetime.fromisoformat(str(body["authorized_at"]))
        expires_at = datetime.fromisoformat(str(body["expires_at"]))
    except ValueError as error:
        _stop("GLD_CHALLENGE_AUTHORITY_INVALID", error)
    if (
        body["schema_id"] != "asklegal.gld-challenge-authority"
        or body["schema_version"] != "1.0.0"
        or body["source_id"] != _SOURCE_ID
        or body["authorized_action"]
        not in {"DISCOVER_GLD_CHALLENGE_CONTRACT", "OBSERVE_GLD_CURRENT_WINDOW"}
        or body["rights_basis"] != "USER_REPORTED_LEGAL_TEAM_CLEARANCE"
        or type(body["authorization_id"]) is not str
        or not body["authorization_id"]
        or type(body["named_authorizer"]) is not str
        or not body["named_authorizer"]
        or authorized_at.tzinfo is None
        or authorized_at.utcoffset() != UTC.utcoffset(authorized_at)
        or expires_at.tzinfo is None
        or expires_at.utcoffset() != UTC.utcoffset(expires_at)
        or expires_at <= authorized_at
    ):
        _stop("GLD_CHALLENGE_AUTHORITY_INVALID")
    if type(claimed_fingerprint) is not str:
        _stop("GLD_CHALLENGE_AUTHORITY_INVALID")
    return body, claimed_fingerprint


def _challenge_contract(path: Path) -> tuple[GldChallengeSessionContract, str]:
    document = _document(path)
    claimed_fingerprint = document.get("fingerprint")
    body = _fingerprinted(
        document,
        fields={
            "schema_id",
            "schema_version",
            "version",
            "navigation_path",
            "required_cookie_name",
            "required_cookie_path",
            "expected_navigation_status",
            "probe_path",
            "expected_probe_status",
            "discovery_observation_fingerprint",
        },
    )
    if (
        body.pop("schema_id") != "asklegal.gld-challenge-contract"
        or body.pop("schema_version") != "1.0.0"
    ):
        _stop("GLD_CHALLENGE_CONTRACT_INVALID")
    try:
        return (
            GldChallengeSessionContract(**body),  # type: ignore[arg-type]
            str(claimed_fingerprint),
        )
    except (TypeError, ValueError) as error:
        _stop("GLD_CHALLENGE_CONTRACT_INVALID", error)


def _preflight(  # noqa: PLR0913
    mode: str,
    blocker_code: str,
    *,
    observation_enabled: bool = False,
    authority_admitted: bool = False,
    challenge_contract_admitted: bool = False,
    session_store_admitted: bool = False,
    observation_executable: bool = False,
) -> GldOperatorPreflight:
    return GldOperatorPreflight(
        mode=mode,
        observation_enabled=observation_enabled,
        authority_admitted=authority_admitted,
        challenge_contract_admitted=challenge_contract_admitted,
        session_store_admitted=session_store_admitted,
        observation_executable=observation_executable,
        window_issuance_ready=False,
        blocker_code=blocker_code,
    )


def preflight_gld_operator(  # noqa: C901, PLR0911, PLR0912
    environment: Mapping[str, str],
    *,
    cycle_id: str | None = None,
    observation_cutoff: str | None = None,
    vault: ImmutableVault | None = None,
) -> GldOperatorPreflight:
    """Inspect local configuration without creating a directory or reaching GLD."""
    mode = environment.get(_MODE, "DISABLED")
    if mode not in {_DISCOVER_MODE, _OBSERVE_MODE}:
        return _preflight(mode, "GLD_OPERATOR_DISABLED")
    authority_path = _absolute_regular(environment, _AUTHORITY)
    if authority_path is None:
        return _preflight(
            mode,
            "GLD_CHALLENGE_AUTHORITY_REQUIRED",
            observation_enabled=True,
        )
    try:
        authority, _authority_fingerprint = _authority(authority_path)
    except GldOperatorError as error:
        return _preflight(mode, str(error), observation_enabled=True)
    start_date = environment.get(_START_DATE)
    try:
        date.fromisoformat(start_date if type(start_date) is str else "")
    except ValueError:
        return _preflight(
            mode,
            "GLD_DATE_WINDOW_REQUIRED",
            observation_enabled=True,
            authority_admitted=True,
        )
    now = datetime.now(tz=UTC)
    authorized_at = datetime.fromisoformat(str(authority["authorized_at"]))
    expires_at = datetime.fromisoformat(str(authority["expires_at"]))
    if not authorized_at <= now < expires_at:
        return _preflight(
            mode,
            "GLD_CHALLENGE_AUTHORITY_NOT_CURRENT",
            observation_enabled=True,
        )
    if cycle_id is None or observation_cutoff is None or vault is None:
        return _preflight(
            mode,
            "GLD_EXECUTION_BINDING_REQUIRED",
            observation_enabled=True,
        )
    try:
        cutoff = datetime.fromisoformat(observation_cutoff)
    except ValueError:
        return _preflight(mode, "GLD_OBSERVATION_CUTOFF_INVALID", observation_enabled=True)
    if not cycle_id or cutoff.tzinfo is None or cutoff.utcoffset() != UTC.utcoffset(cutoff):
        return _preflight(mode, "GLD_OBSERVATION_CUTOFF_INVALID", observation_enabled=True)
    register = load_hk_legislation_source_register()
    endpoint = next(
        item for item in register.endpoints if item.endpoint_id == _INVENTORY_ENDPOINT_ID
    )
    exact_cutoff = cutoff.replace(microsecond=0).isoformat()
    common_expected: dict[str, JsonValue] = {
        "admitted_host": "egazette.gld.gov.hk",
        "cycle_id": cycle_id,
        "deadline_seconds": 60,
        "operation_deadline_seconds": _OPERATION_DEADLINE_SECONDS,
        "endpoint_id": endpoint.endpoint_id,
        "endpoint_version": endpoint.version,
        "maximum_response_bytes": endpoint.max_bytes,
        "observation_cutoff": exact_cutoff,
        "primary_vault": vault.vault_name.value,
        "register_fingerprint": register.fingerprint,
        "register_version": register.register_version,
        "rights_basis": "USER_REPORTED_LEGAL_TEAM_CLEARANCE",
        "schema_id": "asklegal.gld-challenge-authority",
        "schema_version": "1.0.0",
        "source_id": _SOURCE_ID,
    }
    if mode == _DISCOVER_MODE:
        allowed = _exact_allowed_paths(authority.get("allowed_paths"))
        expected = {
            **common_expected,
            "authorized_action": "DISCOVER_GLD_CHALLENGE_CONTRACT",
            "attempt_id": "gld-discover-"
            + sha256(
                canonicalize(
                    checked_json_value({"cycle_id": cycle_id, "observation_cutoff": exact_cutoff})
                )
            ).hexdigest()[:32],
            "challenge_contract_fingerprint": None,
            "discovery_observation_fingerprint": None,
            "manifest_prefix": "poc/report/gld-contract-discovery",
            "maximum_requests": 64,
            "listing_deadline_seconds": None,
            "listing_max_requests": None,
            "object_prefix": "poc/isolation/gld-contract-discovery",
            "session_deadline_seconds": None,
            "session_max_attempts": None,
            "session_max_requests_per_attempt": None,
            "session_root": None,
        }
        if (
            authority.get("authorized_action") != "DISCOVER_GLD_CHALLENGE_CONTRACT"
            or allowed is None
            or "/en/list-of-gazette" not in allowed
            or any(authority.get(key) != value for key, value in expected.items())
        ):
            return _preflight(
                mode,
                "GLD_CHALLENGE_AUTHORITY_BINDING_INVALID",
                observation_enabled=True,
            )
        return _preflight(
            mode,
            "NONE",
            observation_enabled=True,
            authority_admitted=True,
            observation_executable=True,
        )
    challenge_path = _absolute_regular(environment, _CHALLENGE)
    if challenge_path is None:
        return _preflight(
            mode,
            "GLD_CHALLENGE_CONTRACT_REQUIRED",
            observation_enabled=True,
            authority_admitted=True,
        )
    try:
        contract, challenge_fingerprint = _challenge_contract(challenge_path)
    except GldOperatorError as error:
        return _preflight(
            mode,
            str(error),
            observation_enabled=True,
            authority_admitted=True,
        )
    session_root = _absolute_session_root(environment)
    if session_root is None or not session_root.is_dir():
        return _preflight(
            mode,
            "GLD_SESSION_ROOT_REQUIRED",
            observation_enabled=True,
            authority_admitted=True,
            challenge_contract_admitted=True,
        )
    try:
        mode_bits = stat.S_IMODE(session_root.stat(follow_symlinks=False).st_mode)
    except OSError:
        mode_bits = 0
    if mode_bits != _SESSION_DIRECTORY_MODE:
        return _preflight(
            mode,
            "GLD_SESSION_ROOT_NOT_ADMITTED",
            observation_enabled=True,
            challenge_contract_admitted=True,
        )
    discovery_fingerprint = contract.discovery_observation_fingerprint
    allowed_paths = sorted({contract.navigation_path, contract.probe_path, "/en/list-of-gazette"})
    authority_paths = _exact_allowed_paths(authority.get("allowed_paths"))
    expected = {
        **common_expected,
        "allowed_paths": checked_json_value(allowed_paths),
        "authorized_action": "OBSERVE_GLD_CURRENT_WINDOW",
        "attempt_id": "gld-observe-"
        + sha256(
            canonicalize(
                checked_json_value({"cycle_id": cycle_id, "observation_cutoff": exact_cutoff})
            )
        ).hexdigest()[:32],
        "challenge_contract_fingerprint": challenge_fingerprint,
        "discovery_observation_fingerprint": discovery_fingerprint,
        "manifest_prefix": "poc/report/gld-listing-observation",
        "maximum_requests": None,
        "listing_deadline_seconds": _LISTING_DEADLINE_SECONDS,
        "listing_max_requests": _LISTING_MAX_REQUESTS,
        "object_prefix": "poc/isolation/gld-listing",
        "session_deadline_seconds": _SESSION_DEADLINE_SECONDS,
        "session_max_attempts": _SESSION_MAX_ATTEMPTS,
        "session_max_requests_per_attempt": _SESSION_MAX_REQUESTS_PER_ATTEMPT,
        "session_root": str(session_root),
    }
    if (
        authority.get("authorized_action") != "OBSERVE_GLD_CURRENT_WINDOW"
        or type(discovery_fingerprint) is not str
        or authority_paths is None
        or any(authority.get(key) != value for key, value in expected.items())
    ):
        return _preflight(
            mode,
            "GLD_CHALLENGE_AUTHORITY_BINDING_INVALID",
            observation_enabled=True,
            challenge_contract_admitted=True,
            session_store_admitted=True,
        )
    try:
        PatchrightGldWindowProvider(  # noqa: SLF001 - shared exact preflight validator.
            environment, "127.0.0.1", 1, vault
        )._verify_discovery_basis(  # pyright: ignore[reportPrivateUsage]
            cycle_id, discovery_fingerprint
        )
    except GldOperatorError as error:
        return _preflight(
            mode,
            str(error),
            observation_enabled=True,
            authority_admitted=True,
            challenge_contract_admitted=True,
            session_store_admitted=True,
        )
    return _preflight(
        mode,
        "GLD_LISTING_OBSERVATION_CONTRACT_REQUIRED",
        observation_enabled=True,
        authority_admitted=True,
        challenge_contract_admitted=True,
        session_store_admitted=True,
        observation_executable=True,
    )


def _verify_primary_object(
    vault: ImmutableVault, object_key: str, fingerprint: str, byte_length: int
) -> None:
    try:
        reference = vault.resolve_current(object_key)
        body = vault.read_exact(reference) if reference is not None else None
    except Exception as error:  # noqa: BLE001 - Primary is an untrusted evidence port.
        _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID", error)
    if (
        type(body) is not bytes
        or len(body) != byte_length
        or f"sha256:{sha256(body).hexdigest()}" != fingerprint
    ):
        _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID")


class PatchrightGldWindowProvider:
    """Capture a bounded current listing observation, then refuse to invent its parser."""

    def __init__(  # noqa: PLR0913
        self,
        environment: Mapping[str, str],
        proxy_host: str,
        proxy_port: int,
        vault: ImmutableVault,
        *,
        session_factory: _SessionFactory = build_patchright_gld_session_transport,
        http_transport: _HttpPort | None = None,
        discovery: _DiscoveryPort | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        """Bind local authority/configuration to inert source and vault ports."""
        self._environment = dict(environment)
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._vault = vault
        self._session_factory = session_factory
        self._http_transport = http_transport
        self._discovery = discovery or PatchrightGldContractDiscovery()
        self._monotonic_clock = monotonic_clock

    def load_window(self, cycle_id: str, observation_cutoff: str) -> GldGazetteWindow:
        """Perform only an explicitly authorized observation; never issue an unparsed window."""
        if self._environment.get(_MODE) != _OBSERVE_MODE:
            _stop("GLD_OBSERVE_WINDOW_MODE_REQUIRED")
        observation = self.capture_observation(cycle_id, observation_cutoff)
        _stop(f"GLD_LISTING_OBSERVATION_CONTRACT_REQUIRED:{observation['fingerprint']}")

    def capture_observation(  # noqa: C901, PLR0912, PLR0915
        self, cycle_id: str, observation_cutoff: str
    ) -> dict[str, JsonValue]:
        """Capture and retain one bounded inert listing response without claiming completeness."""
        preflight = preflight_gld_operator(
            self._environment,
            cycle_id=cycle_id,
            observation_cutoff=observation_cutoff,
            vault=self._vault,
        )
        if not preflight.observation_executable:
            _stop(preflight.blocker_code)
        try:
            cutoff = datetime.fromisoformat(observation_cutoff)
        except ValueError as error:
            _stop("GLD_OBSERVATION_CUTOFF_INVALID", error)
        if (
            type(cycle_id) is not str
            or not cycle_id
            or cutoff.tzinfo is None
            or cutoff.utcoffset() != UTC.utcoffset(cutoff)
        ):
            _stop("GLD_OBSERVATION_CUTOFF_INVALID")
        register = load_hk_legislation_source_register()
        endpoint = next(
            item for item in register.endpoints if item.endpoint_id == _INVENTORY_ENDPOINT_ID
        )
        source = next(item for item in register.sources if item.source_id == _SOURCE_ID)
        request = GldSessionRequest(
            _SOURCE_ID,
            endpoint.endpoint_id,
            endpoint.version,
            source.version,
            register.register_version,
            register.fingerprint,
            self._environment[_START_DATE],
            cutoff.date().isoformat(),
            "BILINGUAL",
            cutoff.replace(microsecond=0).isoformat(),
        )
        if self._environment.get(_MODE) == _DISCOVER_MODE:
            return self._capture_contract_discovery(cycle_id, request, endpoint)
        challenge_path = _absolute_regular(self._environment, _CHALLENGE)
        session_root = _absolute_session_root(self._environment)
        authority_path = _absolute_regular(self._environment, _AUTHORITY)
        if challenge_path is None or session_root is None or authority_path is None:
            _stop("GLD_OPERATOR_CONFIG_INVALID")
        contract, challenge_fingerprint = _challenge_contract(challenge_path)
        authority, authority_fingerprint = _authority(authority_path)
        raw_allowed_paths = checked_json_value(
            sorted({contract.navigation_path, contract.probe_path, "/en/list-of-gazette"})
        )
        if type(raw_allowed_paths) is not list:
            _stop("GLD_CHALLENGE_CONTRACT_INVALID")
        allowed_paths = raw_allowed_paths
        authority_paths = _exact_allowed_paths(authority.get("allowed_paths"))
        authorized_at = datetime.fromisoformat(str(authority["authorized_at"]))
        expires_at = datetime.fromisoformat(str(authority["expires_at"]))
        expected_authority: dict[str, JsonValue] = {
            "admitted_host": "egazette.gld.gov.hk",
            "allowed_paths": allowed_paths,
            "authorized_action": "OBSERVE_GLD_CURRENT_WINDOW",
            "attempt_id": "gld-observe-"
            + sha256(
                canonicalize(
                    checked_json_value(
                        {"cycle_id": cycle_id, "observation_cutoff": request.observation_cutoff}
                    )
                )
            ).hexdigest()[:32],
            "challenge_contract_fingerprint": challenge_fingerprint,
            "discovery_observation_fingerprint": contract.discovery_observation_fingerprint,
            "cycle_id": cycle_id,
            "endpoint_id": endpoint.endpoint_id,
            "endpoint_version": endpoint.version,
            "manifest_prefix": "poc/report/gld-listing-observation",
            "maximum_requests": None,
            "deadline_seconds": 60,
            "operation_deadline_seconds": _OPERATION_DEADLINE_SECONDS,
            "session_deadline_seconds": _SESSION_DEADLINE_SECONDS,
            "listing_deadline_seconds": _LISTING_DEADLINE_SECONDS,
            "session_max_attempts": _SESSION_MAX_ATTEMPTS,
            "session_max_requests_per_attempt": _SESSION_MAX_REQUESTS_PER_ATTEMPT,
            "listing_max_requests": _LISTING_MAX_REQUESTS,
            "maximum_response_bytes": endpoint.max_bytes,
            "object_prefix": "poc/isolation/gld-listing",
            "observation_cutoff": request.observation_cutoff,
            "primary_vault": self._vault.vault_name.value,
            "register_fingerprint": register.fingerprint,
            "register_version": register.register_version,
            "rights_basis": "USER_REPORTED_LEGAL_TEAM_CLEARANCE",
            "schema_id": "asklegal.gld-challenge-authority",
            "schema_version": "1.0.0",
            "session_root": str(session_root),
            "source_id": _SOURCE_ID,
        }
        if (
            authority_paths is None
            or not authorized_at <= datetime.now(tz=UTC) < expires_at
            or any(authority.get(key) != value for key, value in expected_authority.items())
        ):
            _stop("GLD_CHALLENGE_AUTHORITY_BINDING_INVALID")
        discovery_fingerprint = contract.discovery_observation_fingerprint
        if type(discovery_fingerprint) is not str:
            _stop("GLD_CHALLENGE_AUTHORITY_BINDING_INVALID")
        self._verify_discovery_basis(cycle_id, discovery_fingerprint)
        retained = self._load_retained_observation(
            cycle_id,
            request.observation_cutoff,
            authority_fingerprint,
            challenge_fingerprint,
            discovery_fingerprint,
        )
        if retained is not None:
            return retained
        operation_started = self._monotonic_clock()
        transport: _SessionPort = self._session_factory(
            request,
            contract,
            session_root,
            experiment_deadline_seconds=(15, 15, 15),
            maximum_requests_per_attempt=_SESSION_MAX_REQUESTS_PER_ATTEMPT,
        )
        grant = transport.establish(request)
        session_id = getattr(grant, "session_id", None)
        observed_request_count = getattr(grant, "observed_request_count", None)
        if type(session_id) is not str:
            _stop("GLD_SESSION_GRANT_INVALID")
        if (
            type(observed_request_count) is not int
            or observed_request_count > _SESSION_MAX_REQUESTS_PER_ATTEMPT
        ):
            transport.invalidate(session_id)
            _stop("GLD_SESSION_GRANT_INVALID")
        response: OfficialTransportResponse
        try:
            material = FileProtectedSessionStore(session_root).get(session_id)
            raw_transport = self._http_transport or ProxiedOfficialHttpTransport(
                self._proxy_host,
                self._proxy_port,
                max_redirects=0,
                session_cookies={contract.required_cookie_name: material.session_secret},
            )
            remaining = _OPERATION_DEADLINE_SECONDS - (self._monotonic_clock() - operation_started)
            request_timeout = floor(remaining)
            if request_timeout < 1:
                _stop("GLD_OPERATION_DEADLINE_EXCEEDED")
            response_candidate = raw_transport.request(
                endpoint=endpoint,
                method=HttpMethod.GET,
                timeout_seconds=min(_LISTING_DEADLINE_SECONDS, request_timeout),
            )
            if type(response_candidate) is not OfficialTransportResponse:
                _stop("GLD_LISTING_OBSERVATION_INVALID")
            response = response_candidate
        finally:
            transport.invalidate(session_id)
        if self._monotonic_clock() - operation_started > _OPERATION_DEADLINE_SECONDS:
            _stop("GLD_OPERATION_DEADLINE_EXCEEDED")
        self._retain_observation(
            cycle_id,
            request,
            response,
            authority_fingerprint,
            challenge_fingerprint,
            discovery_fingerprint,
            observed_request_count,
        )
        retained = self._load_retained_observation(
            cycle_id,
            request.observation_cutoff,
            authority_fingerprint,
            challenge_fingerprint,
            discovery_fingerprint,
        )
        if retained is None:
            _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID")
        return retained

    def _verify_discovery_basis(self, cycle_id: str, expected_fingerprint: str) -> None:
        """Re-read the exact retained discovery that the human-frozen contract names."""
        manifest_key = f"poc/report/gld-contract-discovery/{cycle_id}/attempt.json"
        try:
            reference = self._vault.resolve_current(manifest_key)
            if reference is None:
                _stop("GLD_DISCOVERY_BASIS_INVALID")
            content = self._vault.read_exact(reference)
            document = parse_json_bytes(content, max_bytes=_MAX_CONFIG_BYTES)
        except GldOperatorError:
            raise
        except Exception as error:  # noqa: BLE001 - retained basis is hostile evidence.
            _stop("GLD_DISCOVERY_BASIS_INVALID", error)
        if (
            type(document) is not dict
            or canonicalize(document) != content
            or f"sha256:{sha256(content).hexdigest()}" != expected_fingerprint
            or document.get("schema_id") != "asklegal.gld-contract-discovery-observation"
            or document.get("schema_version") != "1.1.0"
            or document.get("cycle_id") != cycle_id
            or document.get("source_id") != _SOURCE_ID
            or document.get("challenge_contract_issued") is not False
            or document.get("terms_accepted") is not False
            or document.get("window_issued") is not False
        ):
            _stop("GLD_DISCOVERY_BASIS_INVALID")
        body_fingerprint = document.get("body_fingerprint")
        byte_length = document.get("byte_length")
        object_key = document.get("object_key")
        if (
            type(body_fingerprint) is not str
            or type(byte_length) is not int
            or type(object_key) is not str
        ):
            _stop("GLD_DISCOVERY_BASIS_INVALID")
        _verify_primary_object(self._vault, object_key, body_fingerprint, byte_length)

    def _capture_contract_discovery(
        self,
        cycle_id: str,
        request: GldSessionRequest,
        endpoint: OfficialEndpointContract,
    ) -> dict[str, JsonValue]:
        """Run the separately authorized contract-discovery mode without session success."""
        authority_path = _absolute_regular(self._environment, _AUTHORITY)
        if authority_path is None:
            _stop("GLD_OPERATOR_CONFIG_INVALID")
        authority, authority_fingerprint = _authority(authority_path)
        allowed = _exact_allowed_paths(authority.get("allowed_paths"))
        if allowed is None or "/en/list-of-gazette" not in allowed:
            _stop("GLD_CHALLENGE_AUTHORITY_BINDING_INVALID")
        maximum_response_bytes = endpoint.max_bytes
        maximum_requests = authority.get("maximum_requests")
        deadline_seconds = authority.get("deadline_seconds")
        expected_authority: dict[str, JsonValue] = {
            "admitted_host": "egazette.gld.gov.hk",
            "authorized_action": "DISCOVER_GLD_CHALLENGE_CONTRACT",
            "attempt_id": "gld-discover-"
            + sha256(
                canonicalize(
                    checked_json_value(
                        {
                            "cycle_id": cycle_id,
                            "observation_cutoff": request.observation_cutoff,
                        }
                    )
                )
            ).hexdigest()[:32],
            "challenge_contract_fingerprint": None,
            "discovery_observation_fingerprint": None,
            "cycle_id": cycle_id,
            "deadline_seconds": 60,
            "endpoint_id": request.endpoint_id,
            "endpoint_version": request.endpoint_version,
            "manifest_prefix": "poc/report/gld-contract-discovery",
            "maximum_requests": 64,
            "operation_deadline_seconds": _OPERATION_DEADLINE_SECONDS,
            "session_deadline_seconds": None,
            "listing_deadline_seconds": None,
            "session_max_attempts": None,
            "session_max_requests_per_attempt": None,
            "listing_max_requests": None,
            "maximum_response_bytes": maximum_response_bytes,
            "object_prefix": "poc/isolation/gld-contract-discovery",
            "observation_cutoff": request.observation_cutoff,
            "primary_vault": self._vault.vault_name.value,
            "register_fingerprint": request.register_fingerprint,
            "register_version": request.register_version,
            "rights_basis": "USER_REPORTED_LEGAL_TEAM_CLEARANCE",
            "schema_id": "asklegal.gld-challenge-authority",
            "schema_version": "1.0.0",
            "session_root": None,
            "source_id": _SOURCE_ID,
        }
        authorized_at = datetime.fromisoformat(str(authority["authorized_at"]))
        expires_at = datetime.fromisoformat(str(authority["expires_at"]))
        if not authorized_at <= datetime.now(tz=UTC) < expires_at or any(
            authority.get(key) != value for key, value in expected_authority.items()
        ):
            _stop("GLD_CHALLENGE_AUTHORITY_BINDING_INVALID")
        authorization_id = authority.get("authorization_id")
        if type(authorization_id) is not str:
            _stop("GLD_CHALLENGE_AUTHORITY_BINDING_INVALID")
        exact_allowed_paths = allowed
        retained = self._load_retained_discovery(
            cycle_id,
            request.observation_cutoff,
            authority_fingerprint,
            authorization_id,
            exact_allowed_paths,
        )
        if retained is not None:
            return retained
        if type(maximum_requests) is not int or type(deadline_seconds) is not int:
            _stop("GLD_CHALLENGE_AUTHORITY_BINDING_INVALID")
        observation = self._discovery.discover(
            host="egazette.gld.gov.hk",
            start_path="/en/list-of-gazette",
            allowed_paths=exact_allowed_paths,
            deadline_seconds=deadline_seconds,
            maximum_requests=maximum_requests,
            maximum_response_bytes=maximum_response_bytes,
        )
        if (
            type(observation) is not GldContractDiscoveryObservation
            or observation.truncated
            or len(observation.raw_response) > maximum_response_bytes
        ):
            _stop("GLD_CONTRACT_DISCOVERY_RESPONSE_LIMIT_EXCEEDED")
        self._retain_discovery(
            cycle_id,
            request,
            observation,
            authority_fingerprint,
            authorization_id,
            exact_allowed_paths,
        )
        retained = self._load_retained_discovery(
            cycle_id,
            request.observation_cutoff,
            authority_fingerprint,
            authorization_id,
            exact_allowed_paths,
        )
        if retained is None:
            _stop("GLD_CONTRACT_DISCOVERY_READBACK_INVALID")
        return retained

    def _retain_discovery(  # noqa: PLR0913, PLR0917
        self,
        cycle_id: str,
        request: GldSessionRequest,
        observation: GldContractDiscoveryObservation,
        authority_fingerprint: str,
        authorization_id: str,
        allowed_paths: tuple[str, ...],
    ) -> None:
        """Retain raw bytes and only sanitized contract-candidate facts."""
        body_fingerprint = f"sha256:{sha256(observation.raw_response).hexdigest()}"
        object_key = "poc/isolation/gld-contract-discovery/" + body_fingerprint.removeprefix(
            "sha256:"
        )
        receipt = self._vault.conditional_create(object_key, observation.raw_response, _RETENTION)
        if (
            not receipt.read_back_verified
            or self._vault.read_exact(receipt.reference) != observation.raw_response
        ):
            _stop("GLD_CONTRACT_DISCOVERY_READBACK_INVALID")
        cookies = checked_json_value(
            [
                {"domain": domain, "name": name, "path": path}
                for name, domain, path in observation.cookies
            ]
        )
        probes = checked_json_value(list(observation.probe_candidates))
        document: dict[str, JsonValue] = {
            "allowed_paths": checked_json_value(list(allowed_paths)),
            "authority_fingerprint": authority_fingerprint,
            "authorization_id": authorization_id,
            "body_fingerprint": body_fingerprint,
            "byte_length": len(observation.raw_response),
            "challenge_contract_issued": False,
            "completeness_supported": False,
            "controlling_evidence": False,
            "cookie_candidates": cookies,
            "cycle_id": cycle_id,
            "endpoint_id": request.endpoint_id,
            "endpoint_version": request.endpoint_version,
            "final_url": observation.final_url,
            "object_key": object_key,
            "observation_cutoff": request.observation_cutoff,
            "probe_candidates": probes,
            "schema_id": "asklegal.gld-contract-discovery-observation",
            "schema_version": "1.1.0",
            "source_id": _SOURCE_ID,
            "status_code": observation.status_code,
            "terms_accepted": False,
            "truncated": observation.truncated,
            "window_issued": False,
        }
        content = canonicalize(checked_json_value(document))
        manifest_key = f"poc/report/gld-contract-discovery/{cycle_id}/attempt.json"
        manifest_receipt = self._vault.conditional_create(manifest_key, content, _RETENTION)
        if (
            not manifest_receipt.read_back_verified
            or self._vault.read_exact(manifest_receipt.reference) != content
        ):
            _stop("GLD_CONTRACT_DISCOVERY_READBACK_INVALID")

    def _load_retained_discovery(
        self,
        cycle_id: str,
        observation_cutoff: str,
        authority_fingerprint: str,
        authorization_id: str,
        allowed_paths: tuple[str, ...],
    ) -> dict[str, JsonValue] | None:
        """Replay an exact retained discovery before starting another browser."""
        manifest_key = f"poc/report/gld-contract-discovery/{cycle_id}/attempt.json"
        try:
            reference = self._vault.resolve_current(manifest_key)
            if reference is None:
                return None
            content = self._vault.read_exact(reference)
            document = parse_json_bytes(content, max_bytes=_MAX_CONFIG_BYTES)
        except Exception as error:  # noqa: BLE001 - retained observation is hostile evidence.
            _stop("GLD_CONTRACT_DISCOVERY_READBACK_INVALID", error)
        if (
            type(document) is not dict
            or set(document)
            != {
                "allowed_paths",
                "authority_fingerprint",
                "authorization_id",
                "body_fingerprint",
                "byte_length",
                "challenge_contract_issued",
                "completeness_supported",
                "controlling_evidence",
                "cookie_candidates",
                "cycle_id",
                "endpoint_id",
                "endpoint_version",
                "final_url",
                "object_key",
                "observation_cutoff",
                "probe_candidates",
                "schema_id",
                "schema_version",
                "source_id",
                "status_code",
                "terms_accepted",
                "truncated",
                "window_issued",
            }
            or document.get("cycle_id") != cycle_id
            or document.get("observation_cutoff") != observation_cutoff
            or document.get("authority_fingerprint") != authority_fingerprint
            or document.get("authorization_id") != authorization_id
            or document.get("allowed_paths") != list(allowed_paths)
            or document.get("schema_id") != "asklegal.gld-contract-discovery-observation"
            or document.get("schema_version") != "1.1.0"
            or document.get("challenge_contract_issued") is not False
            or document.get("window_issued") is not False
            or document.get("terms_accepted") is not False
            or canonicalize(document) != content
        ):
            _stop("GLD_CONTRACT_DISCOVERY_READBACK_INVALID")
        fingerprint = document.get("body_fingerprint")
        length = document.get("byte_length")
        object_key = document.get("object_key")
        if type(fingerprint) is not str or type(length) is not int or type(object_key) is not str:
            _stop("GLD_CONTRACT_DISCOVERY_READBACK_INVALID")
        _verify_primary_object(self._vault, object_key, fingerprint, length)
        return {
            **document,
            "fingerprint": f"sha256:{sha256(content).hexdigest()}",
            "manifest_key": manifest_key,
        }

    def _retain_observation(  # noqa: PLR0913, PLR0917
        self,
        cycle_id: str,
        request: GldSessionRequest,
        response: OfficialTransportResponse,
        authority_fingerprint: str,
        challenge_contract_fingerprint: str,
        discovery_observation_fingerprint: str,
        session_observed_request_count: int,
    ) -> None:
        body_fingerprint = f"sha256:{sha256(response.body).hexdigest()}"
        object_key = f"poc/isolation/gld-listing/{body_fingerprint.removeprefix('sha256:')}"
        object_receipt = self._vault.conditional_create(object_key, response.body, _RETENTION)
        if (
            not object_receipt.read_back_verified
            or self._vault.read_exact(object_receipt.reference) != response.body
        ):
            _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID")
        document: dict[str, JsonValue] = {
            "authority_fingerprint": authority_fingerprint,
            "body_fingerprint": body_fingerprint,
            "byte_length": len(response.body),
            "challenge_contract_fingerprint": challenge_contract_fingerprint,
            "completeness_supported": False,
            "controlling_evidence": False,
            "cycle_id": cycle_id,
            "declared_length": response.declared_length,
            "discovery_observation_fingerprint": discovery_observation_fingerprint,
            "endpoint_id": request.endpoint_id,
            "endpoint_version": request.endpoint_version,
            "final_url": response.final_url,
            "media_type": response.media_type,
            "object_key": object_key,
            "observation_cutoff": request.observation_cutoff,
            "parser_admitted": False,
            "listing_observed_request_count": _LISTING_MAX_REQUESTS,
            "schema_id": "asklegal.gld-listing-observation",
            "schema_version": "1.1.0",
            "source_id": _SOURCE_ID,
            "status_code": response.status_code,
            "session_observed_request_count": session_observed_request_count,
            "truncated": response.truncated,
            "window_issued": False,
        }
        content = canonicalize(checked_json_value(document))
        manifest_key = f"poc/report/gld-listing-observation/{cycle_id}/attempt.json"
        manifest_receipt = self._vault.conditional_create(manifest_key, content, _RETENTION)
        if (
            not manifest_receipt.read_back_verified
            or self._vault.read_exact(manifest_receipt.reference) != content
        ):
            _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID")

    def _load_retained_observation(
        self,
        cycle_id: str,
        observation_cutoff: str,
        authority_fingerprint: str,
        challenge_contract_fingerprint: str,
        discovery_observation_fingerprint: str,
    ) -> dict[str, JsonValue] | None:
        """Return one exact prior attempt before any session or network effect is repeated."""
        manifest_key = f"poc/report/gld-listing-observation/{cycle_id}/attempt.json"
        try:
            reference = self._vault.resolve_current(manifest_key)
            if reference is None:
                return None
            content = self._vault.read_exact(reference)
            document = parse_json_bytes(content, max_bytes=_MAX_CONFIG_BYTES)
        except Exception as error:  # noqa: BLE001 - retained attempt is hostile evidence.
            _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID", error)
        if (
            type(document) is not dict
            or set(document)
            != {
                "authority_fingerprint",
                "body_fingerprint",
                "byte_length",
                "challenge_contract_fingerprint",
                "completeness_supported",
                "controlling_evidence",
                "cycle_id",
                "declared_length",
                "discovery_observation_fingerprint",
                "endpoint_id",
                "endpoint_version",
                "final_url",
                "media_type",
                "object_key",
                "observation_cutoff",
                "parser_admitted",
                "listing_observed_request_count",
                "schema_id",
                "schema_version",
                "source_id",
                "status_code",
                "session_observed_request_count",
                "truncated",
                "window_issued",
            }
            or document.get("cycle_id") != cycle_id
            or document.get("observation_cutoff") != observation_cutoff
            or document.get("authority_fingerprint") != authority_fingerprint
            or document.get("challenge_contract_fingerprint") != challenge_contract_fingerprint
            or document.get("discovery_observation_fingerprint")
            != discovery_observation_fingerprint
            or document.get("schema_id") != "asklegal.gld-listing-observation"
            or document.get("schema_version") != "1.1.0"
            or document.get("listing_observed_request_count") != _LISTING_MAX_REQUESTS
            or type(document.get("session_observed_request_count")) is not int
            or document.get("window_issued") is not False
            or document.get("parser_admitted") is not False
            or canonicalize(document) != content
        ):
            _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID")
        body_fingerprint = document.get("body_fingerprint")
        byte_length = document.get("byte_length")
        object_key = document.get("object_key")
        if (
            type(body_fingerprint) is not str
            or type(byte_length) is not int
            or type(object_key) is not str
        ):
            _stop("GLD_LISTING_OBSERVATION_READBACK_INVALID")
        _verify_primary_object(self._vault, object_key, body_fingerprint, byte_length)
        fingerprint = f"sha256:{sha256(content).hexdigest()}"
        return {**document, "fingerprint": fingerprint, "manifest_key": manifest_key}


def build_gld_window_provider(
    environment: Mapping[str, str],
    proxy_host: str,
    proxy_port: int,
    vault: ImmutableVault,
) -> PatchrightGldWindowProvider | None:
    """Compose the operator only after an explicit local mode switch."""
    if environment.get(_MODE, "DISABLED") != _OBSERVE_MODE:
        return None
    return PatchrightGldWindowProvider(environment, proxy_host, proxy_port, vault)


def build_gld_operator(
    environment: Mapping[str, str],
    proxy_host: str,
    proxy_port: int,
    vault: ImmutableVault,
) -> PatchrightGldWindowProvider | None:
    """Compose either explicit operator mode for the dedicated CLI only."""
    if environment.get(_MODE, "DISABLED") not in {_DISCOVER_MODE, _OBSERVE_MODE}:
        return None
    return PatchrightGldWindowProvider(environment, proxy_host, proxy_port, vault)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    execute = commands.add_parser("execute")
    execute.add_argument("--cycle-id", required=True)
    execute.add_argument("--observation-cutoff", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the installed preflight or one exact, separately authorized attempt."""
    options = _argument_parser().parse_args(arguments)
    environment = dict(os.environ)
    if options.command == "preflight":
        sys.stdout.write(
            json.dumps(preflight_gld_operator(environment).to_json(), sort_keys=True) + "\n"
        )
        return 0
    try:
        infrastructure = load_v1_infrastructure(environment)
        proxy = infrastructure.source_egress_proxy_credential.reveal().decode("utf-8")
        host, raw_port = proxy.removeprefix("http://").rsplit(":", 1)
        provider = build_gld_operator(
            environment,
            host,
            int(raw_port),
            infrastructure.primary_vault,
        )
        if provider is None:
            _stop("GLD_OPERATOR_DISABLED")
        result = provider.capture_observation(options.cycle_id, options.observation_cutoff)
    except Exception as error:  # noqa: BLE001 - only stable local stop text reaches stdout.
        sys.stdout.write(
            json.dumps({"blocker_code": str(error), "result": "BLOCKED"}, sort_keys=True) + "\n"
        )
        return 2
    sys.stdout.write(
        json.dumps({"observation": result, "result": "OBSERVED_INCOMPLETE"}, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
