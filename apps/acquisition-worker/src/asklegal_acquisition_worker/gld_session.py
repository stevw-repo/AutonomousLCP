"""Inert local-only GLD browser-session establishment and protected storage."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from json import dumps, loads
from math import isfinite
from multiprocessing import get_context
from multiprocessing.synchronize import Event
from os import environ, getpid, killpg, setsid
from pathlib import Path
from select import select
from shutil import rmtree, which
from subprocess import DEVNULL, PIPE, Popen
from tempfile import TemporaryDirectory, gettempdir, mkdtemp
from time import monotonic, sleep
from typing import Protocol
from unicodedata import category
from urllib.parse import SplitResult, urlsplit
from uuid import uuid4

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_source_connectors import (
    GldSessionGrant,
    GldSessionPort,
    GldSessionRequest,
    gld_registered_host,
    load_hk_legislation_source_register,
)
from patchright.sync_api import BrowserContext, Route, sync_playwright
from patchright.sync_api import Error as PatchrightError

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_SESSION_ID = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
_MAX_EXPERIMENT_DEADLINE_SECONDS = 60
_MAX_TOTAL_DEADLINE_SECONDS = 180
_MAX_SESSION_TTL_SECONDS = 3_600
_MAX_SESSION_SECRET_CHARACTERS = 16_384
_MAX_SESSION_SECRET_UTF8_BYTES = 32_768
_MAX_OBSERVED_COOKIES = 16
_MAX_OBSERVED_REQUEST_COUNT = 10_000
_MAX_REQUESTS_PER_ATTEMPT = 1_000
_SESSION_DIRECTORY_MODE = 0o700
_SESSION_FILE_MODE = 0o600
_MAX_CHILD_IPC_BYTES = 65_536
_ATTEMPT_ROOT_PREFIX = "asklegal-gld-child-"
_TERMINAL_HOLD_SECONDS = 2.0
_CHILD_ATTEMPT_ROOT: ContextVar[str | None] = ContextVar("gld_child_attempt_root", default=None)
_HTTP_SUCCESS_MIN = 200
_HTTP_SUCCESS_MAX = 299
_UNSAFE_SESSION_SECRET_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp"})
_CODE_CHALLENGE_CONTRACT_CHANGED = "GLD_CHALLENGE_CONTRACT_CHANGED"
_CODE_CHALLENGE_UNRESOLVED = "GLD_CHALLENGE_UNRESOLVED"
_CODE_SESSION_DEADLINE_INVALID = "GLD_SESSION_DEADLINE_INVALID"
_CODE_SESSION_HOST_MISMATCH = "GLD_SESSION_HOST_MISMATCH"
_CODE_SESSION_INVALIDATION_FAILED = "GLD_SESSION_INVALIDATION_FAILED"
_CODE_SESSION_NAVIGATION_INVALID = "GLD_SESSION_NAVIGATION_INVALID"
_CODE_SESSION_POLICY_REQUEST_MISMATCH = "GLD_SESSION_POLICY_REQUEST_MISMATCH"
_CODE_SESSION_RUNNER_FAILED = "GLD_SESSION_RUNNER_FAILED"
_CODE_SESSION_STORE_FAILED = "GLD_SESSION_STORE_FAILED"
_CODE_SESSION_ROLLBACK_UNPROVED = "GLD_SESSION_ROLLBACK_UNPROVED"
_CODE_SESSION_TTL_EXPIRED = "GLD_SESSION_TTL_EXPIRED"
_CODE_SESSION_DEADLINE_EXCEEDED = "GLD_SESSION_DEADLINE_EXCEEDED"
_CODE_SESSION_CLEANUP_FAILED = "GLD_SESSION_CLEANUP_FAILED"
_MESSAGE_EXACT_REQUEST = "request must be an exact GldSessionRequest"
_MESSAGE_EXACT_POLICY = "policy must be an exact RenderedBrowserPolicy"
_MESSAGE_EXACT_SESSION_ID = "session_id must be an exact string"
_MESSAGE_RUNNER = "browser must implement GldBrowserRunner"
_MESSAGE_STORE = "store must implement ProtectedSessionStore"
_MESSAGE_CLOCK = "clock must be callable"
_MESSAGE_SESSION_ID_FACTORY = "session_id_factory must be callable"
_EXPERIMENT_ORDER = (
    "EPHEMERAL_CLEAN_HEADLESS",
    "HEADED_ISOLATED_DISPLAY",
    "ORIGIN_SCOPED_PERSISTENT",
)
_FAILURE_CODES = frozenset(
    {
        _CODE_CHALLENGE_CONTRACT_CHANGED,
        _CODE_CHALLENGE_UNRESOLVED,
        _CODE_SESSION_DEADLINE_INVALID,
        _CODE_SESSION_HOST_MISMATCH,
        _CODE_SESSION_INVALIDATION_FAILED,
        _CODE_SESSION_NAVIGATION_INVALID,
        _CODE_SESSION_POLICY_REQUEST_MISMATCH,
        _CODE_SESSION_RUNNER_FAILED,
        _CODE_SESSION_STORE_FAILED,
        _CODE_SESSION_ROLLBACK_UNPROVED,
        _CODE_SESSION_TTL_EXPIRED,
        _CODE_SESSION_DEADLINE_EXCEEDED,
        _CODE_SESSION_CLEANUP_FAILED,
    }
)


class GldSessionError(RuntimeError):
    """One closed, non-secret failure result from the local GLD session seam."""

    def __init__(self, code: str) -> None:
        """Accept only one closed failure code, never a browser exception detail."""
        if type(code) is not str or code not in _FAILURE_CODES:
            invalid_code = "GLD_SESSION_FAILURE_CODE_INVALID"
            raise ValueError(invalid_code)
        super().__init__(code)


class GldSessionFailureClass(StrEnum):
    """The two journal-facing outcomes for a sanitized GLD session failure."""

    CONTRACT = "CONTRACT"
    RETRYABLE = "RETRYABLE"


def classify_gld_session_failure(error: object) -> GldSessionFailureClass:
    """Classify one closed GLD error without exposing browser or session material."""
    invalid = "GLD_SESSION_FAILURE_INVALID"
    if type(error) is not GldSessionError or len(error.args) != 1 or type(error.args[0]) is not str:
        raise ValueError(invalid)
    code = error.args[0]
    if code not in _FAILURE_CODES:
        raise ValueError(invalid)
    if code in {
        _CODE_CHALLENGE_CONTRACT_CHANGED,
        _CODE_SESSION_DEADLINE_INVALID,
        _CODE_SESSION_HOST_MISMATCH,
        _CODE_SESSION_NAVIGATION_INVALID,
        _CODE_SESSION_POLICY_REQUEST_MISMATCH,
    }:
        return GldSessionFailureClass.CONTRACT
    return GldSessionFailureClass.RETRYABLE


def _normalized_failure(code: str, _error: Exception) -> GldSessionError:
    """Discard a possibly secret-bearing operational exception behind one fixed code."""
    _error.args = ()
    _error.__cause__ = None
    _error.__context__ = None
    _error.__traceback__ = None
    return GldSessionError(code)


class GldBrowserExperiment(StrEnum):
    """The only unattended local GLD browser compartments, in fixed order."""

    EPHEMERAL_CLEAN_HEADLESS = "EPHEMERAL_CLEAN_HEADLESS"
    HEADED_ISOLATED_DISPLAY = "HEADED_ISOLATED_DISPLAY"
    ORIGIN_SCOPED_PERSISTENT = "ORIGIN_SCOPED_PERSISTENT"


@dataclass(frozen=True, slots=True)
class GldBrowserCookie:
    """One exact origin-scoped cookie candidate from an isolated browser context."""

    name: str
    value: str
    domain: str
    path: str

    def __post_init__(self) -> None:
        """Reject malformed or subclass-controlled publisher state facts."""
        if (
            type(self.name) is not str
            or type(self.value) is not str
            or type(self.domain) is not str
            or type(self.path) is not str
            or not self.name
            or not self.value
            or not _valid_host(self.domain.removeprefix("."))
            or not _valid_path(self.path)
        ):
            cookie_invalid = "GLD_BROWSER_COOKIE_INVALID"
            raise ValueError(cookie_invalid)


@dataclass(frozen=True, slots=True)
class GldBrowserObservation:
    """Bound browser-navigation and inventory-probe facts, never raw browser state."""

    navigation_status: int
    navigation_url: str
    cookies: tuple[GldBrowserCookie, ...]
    probe_status: int
    probe_url: str
    observed_request_count: int = 0

    def __post_init__(self) -> None:
        """Require exact bounded observation facts before contract selection."""
        if (
            type(self.navigation_status) is not int
            or type(self.probe_status) is not int
            or type(self.navigation_url) is not str
            or type(self.probe_url) is not str
            or type(self.cookies) is not tuple
            or any(type(cookie) is not GldBrowserCookie for cookie in self.cookies)
            or len(self.cookies) > _MAX_OBSERVED_COOKIES
            or type(self.observed_request_count) is not int
            or not 0 <= self.observed_request_count <= _MAX_OBSERVED_REQUEST_COUNT
        ):
            observation_invalid = "GLD_BROWSER_OBSERVATION_INVALID"
            raise ValueError(observation_invalid)


@dataclass(frozen=True, slots=True)
class GldChallengeSessionContract:
    """An injected versioned success contract; no current GLD shape is presumed here."""

    version: str
    navigation_path: str
    required_cookie_name: str
    required_cookie_path: str
    expected_navigation_status: int
    probe_path: str
    expected_probe_status: int
    discovery_observation_fingerprint: str | None = None

    def __post_init__(self) -> None:
        """Keep session-success facts closed, exact, bounded, and origin-relative."""
        if (
            type(self.version) is not str
            or not self.version
            or type(self.required_cookie_name) is not str
            or not self.required_cookie_name
            or not _valid_path(self.navigation_path)
            or not _valid_path(self.required_cookie_path)
            or not _valid_path(self.probe_path)
            or type(self.expected_navigation_status) is not int
            or type(self.expected_probe_status) is not int
            or not _HTTP_SUCCESS_MIN <= self.expected_navigation_status <= _HTTP_SUCCESS_MAX
            or not _HTTP_SUCCESS_MIN <= self.expected_probe_status <= _HTTP_SUCCESS_MAX
            or (
                self.discovery_observation_fingerprint is not None
                and (
                    type(self.discovery_observation_fingerprint) is not str
                    or _FINGERPRINT.fullmatch(self.discovery_observation_fingerprint) is None
                )
            )
        ):
            contract_invalid = "GLD_CHALLENGE_CONTRACT_INVALID"
            raise ValueError(contract_invalid)

    def route_is_allowed(self, method: str, url: str) -> bool:
        """Allow only exact contract GET routes with no caller-controlled query or fragment."""
        if type(method) is not str or type(url) is not str or method != "GET":
            return False
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in {self.navigation_path, self.probe_path}
        )

    def select_material(
        self, observation: GldBrowserObservation, admitted_host: str
    ) -> BrowserSessionMaterial:
        """Return the required cookie only after exact navigation and probe success."""
        if type(observation) is not GldBrowserObservation or not _valid_host(admitted_host):
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        expected_navigation = f"https://{admitted_host}{self.navigation_path}"
        expected_probe = f"https://{admitted_host}{self.probe_path}"
        selected = tuple(
            cookie
            for cookie in observation.cookies
            if (
                cookie.name == self.required_cookie_name
                and cookie.domain.removeprefix(".") == admitted_host
                and cookie.path == self.required_cookie_path
            )
        )
        if (
            observation.navigation_status != self.expected_navigation_status
            or observation.navigation_url != expected_navigation
            or observation.probe_status != self.expected_probe_status
            or observation.probe_url != expected_probe
            or len(selected) != 1
        ):
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        return BrowserSessionMaterial(
            f"https://{admitted_host}",
            selected[0].value,
            observed_request_count=observation.observed_request_count,
        )

    def fingerprint_projection(self) -> dict[str, object]:
        """Expose every admitted session-state and exact-route selection fact."""
        return {
            "expected_navigation_status": self.expected_navigation_status,
            "expected_probe_status": self.expected_probe_status,
            "discovery_observation_fingerprint": self.discovery_observation_fingerprint,
            "navigation_path": self.navigation_path,
            "probe_path": self.probe_path,
            "required_cookie_name": self.required_cookie_name,
            "required_cookie_path": self.required_cookie_path,
            "version": self.version,
        }


def _no_cleanup() -> None:
    """Provide a default inert material cleanup action for test-only materials."""


@dataclass(frozen=True, slots=True, repr=False)
class BrowserSessionMaterial:
    """Minimum secret-bearing local state, deliberately excluded from repr output."""

    origin: str
    session_secret: str
    _cleanup: Callable[[], None] = field(default=_no_cleanup, repr=False, compare=False)
    observed_request_count: int = 0

    def __post_init__(self) -> None:
        """Reject an invalid origin, non-exact secret text, or cleanup seam."""
        if type(self.origin) is not str or not _valid_origin(self.origin):
            material_invalid = "GLD_SESSION_MATERIAL_INVALID"
            raise ValueError(material_invalid)
        if type(self.session_secret) is not str or not _valid_session_secret(self.session_secret):
            material_invalid = "GLD_SESSION_MATERIAL_INVALID"
            raise ValueError(material_invalid)
        if (
            type(self.observed_request_count) is not int
            or not 0 <= self.observed_request_count <= _MAX_OBSERVED_REQUEST_COUNT
        ):
            material_invalid = "GLD_SESSION_MATERIAL_INVALID"
            raise ValueError(material_invalid)
        if not callable(self._cleanup):
            material_invalid = "GLD_SESSION_MATERIAL_INVALID"
            raise TypeError(material_invalid)

    def cleanup(self) -> None:
        """Discard local browser scratch material without exposing the secret."""
        self._cleanup()

    def __repr__(self) -> str:
        """Prevent accidental session-secret or browser-state logging."""
        return "BrowserSessionMaterial(<redacted>)"


@dataclass(frozen=True, slots=True)
class RenderedBrowserPolicy:
    """Exact frozen GLD browser policy, bound to one registered session request."""

    request: GldSessionRequest
    challenge_contract: GldChallengeSessionContract | None
    admitted_host: str
    experiment_order: tuple[GldBrowserExperiment, ...]
    experiment_deadline_seconds: tuple[int, ...]
    session_ttl_seconds: int
    maximum_requests_per_attempt: int
    policy_fingerprint: str

    @classmethod
    def for_request(
        cls,
        request: GldSessionRequest,
        *,
        challenge_contract: GldChallengeSessionContract | None,
        experiment_deadline_seconds: tuple[int, int, int] = (20, 20, 20),
        session_ttl_seconds: int = 300,
        maximum_requests_per_attempt: int = 64,
    ) -> RenderedBrowserPolicy:
        """Freeze the sole local policy from the exact registered GLD request."""
        if type(request) is not GldSessionRequest:
            raise TypeError(_MESSAGE_EXACT_REQUEST)
        host = gld_registered_host(request)
        experiments = tuple(GldBrowserExperiment(name) for name in _EXPERIMENT_ORDER)
        fingerprint = _policy_fingerprint(
            request,
            challenge_contract,
            host,
            experiments,
            experiment_deadline_seconds,
            session_ttl_seconds,
            maximum_requests_per_attempt,
        )
        return cls(
            request,
            challenge_contract,
            host,
            experiments,
            experiment_deadline_seconds,
            session_ttl_seconds,
            maximum_requests_per_attempt,
            fingerprint,
        )

    def __post_init__(self) -> None:
        """Bind every policy fact to the exact inert registered GLD request."""
        if type(self.request) is not GldSessionRequest:
            raise TypeError(_MESSAGE_EXACT_REQUEST)
        if (
            self.challenge_contract is not None
            and type(self.challenge_contract) is not GldChallengeSessionContract
        ):
            contract_invalid = "GLD_CHALLENGE_CONTRACT_INVALID"
            raise TypeError(contract_invalid)
        expected_host = gld_registered_host(self.request)
        if type(self.admitted_host) is not str or self.admitted_host != expected_host:
            policy_host_invalid = "GLD_POLICY_HOST_INVALID"
            raise ValueError(policy_host_invalid)
        expected_experiments = tuple(GldBrowserExperiment(name) for name in _EXPERIMENT_ORDER)
        if (
            type(self.experiment_order) is not tuple
            or self.experiment_order != expected_experiments
            or any(
                type(experiment) is not GldBrowserExperiment for experiment in self.experiment_order
            )
        ):
            policy_experiments_invalid = "GLD_POLICY_EXPERIMENTS_INVALID"
            raise ValueError(policy_experiments_invalid)
        if (
            type(self.experiment_deadline_seconds) is not tuple
            or len(self.experiment_deadline_seconds) != len(self.experiment_order)
            or any(
                type(deadline) is not int or not 1 <= deadline <= _MAX_EXPERIMENT_DEADLINE_SECONDS
                for deadline in self.experiment_deadline_seconds
            )
            or sum(self.experiment_deadline_seconds) > _MAX_TOTAL_DEADLINE_SECONDS
        ):
            policy_deadlines_invalid = "GLD_POLICY_DEADLINES_INVALID"
            raise ValueError(policy_deadlines_invalid)
        if (
            type(self.session_ttl_seconds) is not int
            or not 1 <= self.session_ttl_seconds <= _MAX_SESSION_TTL_SECONDS
        ):
            policy_ttl_invalid = "GLD_POLICY_TTL_INVALID"
            raise ValueError(policy_ttl_invalid)
        if (
            type(self.maximum_requests_per_attempt) is not int
            or not 1 <= self.maximum_requests_per_attempt <= _MAX_REQUESTS_PER_ATTEMPT
        ):
            policy_requests_invalid = "GLD_POLICY_REQUEST_BUDGET_INVALID"
            raise ValueError(policy_requests_invalid)
        expected_fingerprint = _policy_fingerprint(
            self.request,
            self.challenge_contract,
            self.admitted_host,
            self.experiment_order,
            self.experiment_deadline_seconds,
            self.session_ttl_seconds,
            self.maximum_requests_per_attempt,
        )
        if (
            type(self.policy_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.policy_fingerprint) is None
            or self.policy_fingerprint != expected_fingerprint
        ):
            policy_fingerprint_invalid = "GLD_POLICY_FINGERPRINT_INVALID"
            raise ValueError(policy_fingerprint_invalid)


@dataclass(frozen=True, slots=True)
class PatchrightGldAttemptPolicy:
    """One sealed Patchright compartment; no browser escape hatch is configurable."""

    experiment: GldBrowserExperiment
    allowed_hosts: tuple[str, ...]
    challenge_contract: GldChallengeSessionContract
    deadline_seconds: int
    headless: bool
    maximum_requests: int = 64
    accept_downloads: bool = False
    allow_popups: bool = False
    allow_extensions: bool = False
    allow_browser_credentials: bool = False
    allow_cross_host_requests: bool = False

    def __post_init__(self) -> None:
        """Reject any caller attempt to expand a browser-compartment capability."""
        if type(self.experiment) is not GldBrowserExperiment:
            attempt_policy_invalid = "GLD_ATTEMPT_POLICY_INVALID"
            raise TypeError(attempt_policy_invalid)
        if (
            type(self.allowed_hosts) is not tuple
            or len(self.allowed_hosts) != 1
            or type(self.allowed_hosts[0]) is not str
            or not _valid_host(self.allowed_hosts[0])
            or type(self.challenge_contract) is not GldChallengeSessionContract
            or type(self.deadline_seconds) is not int
            or not 1 <= self.deadline_seconds <= _MAX_EXPERIMENT_DEADLINE_SECONDS
            or type(self.headless) is not bool
            or type(self.maximum_requests) is not int
            or not 1 <= self.maximum_requests <= _MAX_REQUESTS_PER_ATTEMPT
            or self.accept_downloads is not False
            or self.allow_popups is not False
            or self.allow_extensions is not False
            or self.allow_browser_credentials is not False
            or self.allow_cross_host_requests is not False
        ):
            attempt_policy_invalid = "GLD_ATTEMPT_POLICY_INVALID"
            raise ValueError(attempt_policy_invalid)

    def request_is_allowed(self, method: str, url: str, resource_type: str) -> bool:
        """Apply the exact same-host GET-only request boundary before continuation."""
        if type(method) is not str or type(url) is not str or type(resource_type) is not str:
            return False
        parsed = urlsplit(url)
        return (
            method == "GET"
            and parsed.scheme == "https"
            and parsed.hostname == self.allowed_hosts[0]
            and _safe_port(parsed) in {None, 443}
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and resource_type not in {"eventsource", "websocket"}
            and self.challenge_contract.route_is_allowed(method, url)
        )


@dataclass(frozen=True, slots=True)
class _GldChildRequest:
    """Minimum non-secret request transferred to one owned local browser child."""

    experiment: GldBrowserExperiment
    start_url: str
    policy: PatchrightGldAttemptPolicy
    attempt_root: str

    def __post_init__(self) -> None:
        """Ensure the child cannot be directed outside the frozen parent policy."""
        if (
            type(self.experiment) is not GldBrowserExperiment
            or type(self.start_url) is not str
            or type(self.policy) is not PatchrightGldAttemptPolicy
            or self.experiment is not self.policy.experiment
            or type(self.attempt_root) is not str
            or not Path(self.attempt_root).name.startswith(_ATTEMPT_ROOT_PREFIX)
            or not self.policy.request_is_allowed("GET", self.start_url, "document")
        ):
            child_request_invalid = "GLD_CHILD_REQUEST_INVALID"
            raise ValueError(child_request_invalid)


class _ConcreteAttemptSupervisor(Protocol):
    """Parent-owned bounded local-child boundary for concrete Patchright work."""

    def establish(self, request: _GldChildRequest) -> object:
        """Return one bounded child material result or raise only a closed error."""
        ...


class _ChildProcess(Protocol):
    """Minimal killable local process control surface used by the supervisor."""

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...

    def is_alive(self) -> bool: ...


class GldBrowserRunner(Protocol):
    """A browser seam that accepts only the adapter-derived navigation facts."""

    def establish(
        self, *, start_url: str, allowed_hosts: tuple[str, ...], deadline_seconds: int
    ) -> BrowserSessionMaterial:
        """Create one local GLD session material value or raise a closed error."""
        ...


class ProtectedSessionStore(Protocol):
    """Acquisition-owned storage for minimal local session material only."""

    def put(self, session_id: str, material: BrowserSessionMaterial, expires_at: str) -> bool:
        """Atomically create only one material value and prove the committed result."""
        ...

    def get(self, session_id: str) -> BrowserSessionMaterial:
        """Read one protected material value only for exact invalidation."""
        ...

    def delete(self, session_id: str) -> bool:
        """Remove one protected material value and return true only when deletion is proved."""
        ...


class FileProtectedSessionStore:
    """Restart-safe acquisition-only store protected by local file permissions."""

    def __init__(self, root: Path) -> None:
        """Create or verify one absolute, non-symlinked mode-0700 store root."""
        if type(root) is not type(Path()) or not root.is_absolute() or root.is_symlink():
            raise ValueError(_CODE_SESSION_STORE_FAILED)
        try:
            root.mkdir(mode=_SESSION_DIRECTORY_MODE, parents=True, exist_ok=True)
            details = root.stat(follow_symlinks=False)
        except OSError as error:
            raise _normalized_failure(_CODE_SESSION_STORE_FAILED, error) from None
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_IMODE(details.st_mode) != _SESSION_DIRECTORY_MODE
        ):
            raise ValueError(_CODE_SESSION_STORE_FAILED)
        self._root = root

    def put(self, session_id: str, material: BrowserSessionMaterial, expires_at: str) -> bool:
        """Create one mode-0600 canonical record and immediately prove read-back."""
        exact_id = _exact_session_id(session_id)
        if type(material) is not BrowserSessionMaterial:
            raise TypeError(_CODE_SESSION_STORE_FAILED)
        expires = _stored_expiry(expires_at)
        body = canonicalize(
            checked_json_value(
                {
                    "expires_at": expires,
                    "origin": material.origin,
                    "observed_request_count": material.observed_request_count,
                    "session_id": exact_id,
                    "session_secret": material.session_secret,
                }
            )
        )
        path = self._path(exact_id)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, _SESSION_FILE_MODE)
        except FileExistsError:
            return False
        except OSError as error:
            raise _normalized_failure(_CODE_SESSION_STORE_FAILED, error) from None
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            details = path.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) != _SESSION_FILE_MODE
                or self.get(exact_id) != material
            ):
                raise OSError
        except OSError as error:
            with suppress(OSError):
                path.unlink()
            raise _normalized_failure(_CODE_SESSION_STORE_FAILED, error) from None
        return True

    def get(self, session_id: str) -> BrowserSessionMaterial:
        """Read one exact regular mode-0600 record without following symlinks."""
        exact_id = _exact_session_id(session_id)
        path = self._path(exact_id)
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) != _SESSION_FILE_MODE
            ):
                raise OSError
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                body = stream.read(_MAX_CHILD_IPC_BYTES + 1)
        except OSError as error:
            raise _normalized_failure(_CODE_SESSION_STORE_FAILED, error) from None
        try:
            document = checked_json_value(
                loads(body.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_pairs)
            )
            if (
                type(document) is not dict
                or set(document)
                != {
                    "expires_at",
                    "observed_request_count",
                    "origin",
                    "session_id",
                    "session_secret",
                }
                or canonicalize(document) != body
                or document["session_id"] != exact_id
                or type(document["origin"]) is not str
                or type(document["session_secret"]) is not str
                or type(document["expires_at"]) is not str
                or type(document["observed_request_count"]) is not int
            ):
                raise ValueError
            _stored_expiry(document["expires_at"])
            return BrowserSessionMaterial(
                document["origin"],
                document["session_secret"],
                observed_request_count=document["observed_request_count"],
            )
        except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
            raise _normalized_failure(_CODE_SESSION_STORE_FAILED, error) from None

    def delete(self, session_id: str) -> bool:
        """Unlink exactly one store member and prove its name is absent."""
        path = self._path(_exact_session_id(session_id))
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise _normalized_failure(_CODE_SESSION_STORE_FAILED, error) from None
        return not path.exists() and not path.is_symlink()

    def _path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.json"


def _stored_expiry(value: object) -> str:
    if type(value) is not str:
        raise ValueError(_CODE_SESSION_STORE_FAILED)
    try:
        parsed = datetime.fromisoformat(value)
        exact = _exact_utc_time(parsed)
    except (TypeError, ValueError) as error:
        raise ValueError(_CODE_SESSION_STORE_FAILED) from error
    if value != _format_utc(exact):
        raise ValueError(_CODE_SESSION_STORE_FAILED)
    return value


@dataclass(frozen=True, slots=True)
class _RollbackResult:
    """Exact rollback proof kept separate from the public closed failure code."""

    failure_code: str
    deletion_proved: bool


class _PatchrightAttempt(Protocol):
    """Injectable concrete-Patchright seam; tests never launch Chromium."""

    def establish(
        self,
        *,
        experiment: GldBrowserExperiment,
        start_url: str,
        allowed_hosts: tuple[str, ...],
        deadline_seconds: int,
    ) -> BrowserSessionMaterial:
        """Run one constrained local browser compartment."""
        ...


class _PatchrightCompartment(Protocol):
    """One pre-isolated local browser resource selected by the fixed experiment."""

    def establish(
        self, *, policy: PatchrightGldAttemptPolicy, start_url: str
    ) -> BrowserSessionMaterial:
        """Run one already-isolated compartment without ambient browser state."""
        ...


class _EphemeralCleanPatchrightCompartment:
    """The only default compartment: a clean headless browser closed in every path."""

    def establish(
        self, *, policy: PatchrightGldAttemptPolicy, start_url: str
    ) -> BrowserSessionMaterial:
        """Launch a clean headless context and return only bounded origin session state."""
        if policy.experiment is not GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS:
            raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
        return _run_patchright_compartment(policy, start_url, headless=True)


class _HeadedIsolatedDisplayPatchrightCompartment:
    """A fresh Xvfb display and fresh browser home; ambient desktop/profile is never used."""

    def establish(
        self, *, policy: PatchrightGldAttemptPolicy, start_url: str
    ) -> BrowserSessionMaterial:
        """Run headed only behind a locally owned display, then terminate it exactly."""
        if policy.experiment is not GldBrowserExperiment.HEADED_ISOLATED_DISPLAY:
            raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
        with TemporaryDirectory(
            prefix="asklegal-gld-headed-", dir=_child_attempt_root()
        ) as isolated_home:
            process: Popen[bytes] | None = None
            try:
                xvfb = which("Xvfb")
                if xvfb is None:
                    raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
                process = Popen(
                    (
                        xvfb,
                        "-displayfd",
                        "1",
                        "-screen",
                        "0",
                        "1280x720x24",
                        "-nolisten",
                        "tcp",
                    ),
                    env={"HOME": isolated_home, "PATH": environ.get("PATH", "")},
                    stdin=DEVNULL,
                    stdout=PIPE,
                    stderr=DEVNULL,
                    shell=False,
                )
                display = _owned_xvfb_display(process)
                return _run_patchright_compartment(
                    policy,
                    start_url,
                    headless=False,
                    browser_environment={"DISPLAY": display, "HOME": isolated_home},
                )
            except FileNotFoundError as error:
                raise _normalized_failure(_CODE_CHALLENGE_UNRESOLVED, error) from None
            finally:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except BaseException as error:
                        if not isinstance(error, Exception):
                            raise
                        process.kill()


class _OriginScopedPersistentPatchrightCompartment:
    """A fresh locally owned profile directory used only for one exact GLD origin attempt."""

    def establish(
        self, *, policy: PatchrightGldAttemptPolicy, start_url: str
    ) -> BrowserSessionMaterial:
        """Launch persistent Chromium only into a temporary local profile with exact cleanup."""
        if policy.experiment is not GldBrowserExperiment.ORIGIN_SCOPED_PERSISTENT:
            raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
        with TemporaryDirectory(
            prefix="asklegal-gld-persistent-", dir=_child_attempt_root()
        ) as user_data_dir:
            return _run_patchright_compartment(
                policy, start_url, headless=True, user_data_dir=user_data_dir
            )


def _run_patchright_compartment(
    policy: PatchrightGldAttemptPolicy,
    start_url: str,
    *,
    headless: bool,
    browser_environment: dict[str, str | float | bool] | None = None,
    user_data_dir: str | None = None,
) -> BrowserSessionMaterial:
    """Run one explicitly isolated context and retain only contract-selected cookie state."""
    try:
        with sync_playwright() as engine:
            launch_arguments = (
                "--disable-extensions",
                "--disable-features=PasswordManagerOnboarding",
            )
            close_owner: Callable[[], None] | None = None
            if user_data_dir is None:
                browser = engine.chromium.launch(
                    headless=headless, args=launch_arguments, env=browser_environment
                )
                context = browser.new_context(
                    accept_downloads=False,
                    ignore_https_errors=False,
                    java_script_enabled=True,
                    service_workers="block",
                )
                close_owner = browser.close
            else:
                context = engine.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=headless,
                    args=launch_arguments,
                    accept_downloads=False,
                    ignore_https_errors=False,
                    java_script_enabled=True,
                    service_workers="block",
                )
            try:
                request_counter = [0]
                context.route("**/*", _route_handler_for(policy, request_counter))
                page = context.new_page()
                page.on("popup", _close_popup)
                response = page.goto(
                    start_url,
                    timeout=float(policy.deadline_seconds * 1_000),
                    wait_until="domcontentloaded",
                )
                if response is None or not _page_url_is_allowed(page.url, policy):
                    raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
                navigation_url = page.url
                probe_url = (
                    f"https://{policy.allowed_hosts[0]}{policy.challenge_contract.probe_path}"
                )
                probe_response = page.goto(
                    probe_url,
                    timeout=float(policy.deadline_seconds * 1_000),
                    wait_until="domcontentloaded",
                )
                if probe_response is None:
                    raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
                observation = GldBrowserObservation(
                    response.status,
                    navigation_url,
                    _cookies_from_context(context),
                    probe_response.status,
                    page.url,
                    request_counter[0],
                )
                return policy.challenge_contract.select_material(
                    observation, policy.allowed_hosts[0]
                )
            finally:
                if user_data_dir is None:
                    try:
                        context.close()
                    finally:
                        if close_owner is not None:
                            close_owner()
                else:
                    context.close()
    except GldSessionError:
        raise
    except PatchrightError as error:
        raise _normalized_failure(_CODE_CHALLENGE_UNRESOLVED, error) from None
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise _normalized_failure(_CODE_SESSION_RUNNER_FAILED, error) from None


def _owned_xvfb_display(process: Popen[bytes]) -> str:
    """Accept only a live Xvfb-created display identifier from its private displayfd pipe."""
    if process.stdout is None:
        raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
    ready, _unused_writable, _unused_exceptional = select((process.stdout,), (), (), 1.0)
    if not ready or process.poll() is not None:
        raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
    line = process.stdout.readline().decode("ascii", "strict").strip()
    if not line.isdecimal() or not line or process.poll() is not None:
        raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)
    return f":{line}"


class _LocalPatchrightSupervisor:
    """Supervise one concrete browser child; timeout always terminates its owned resources."""

    def establish(self, request: _GldChildRequest) -> object:
        """Use bounded local IPC and terminate then kill a child that exceeds its full deadline."""
        context = get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        terminal_hold = context.Event()
        process = context.Process(
            target=_child_patchright_attempt, args=(send, request, terminal_hold)
        )
        started = False
        group_ready = False
        termination_done = False
        result: BrowserSessionMaterial | None = None
        deadline_started = monotonic()

        def terminate_owned() -> None:
            nonlocal termination_done
            if termination_done:
                return
            termination_done = True
            if group_ready:
                terminate_child_group(process)
            else:
                terminate_child(process)

        try:
            process.start()
            started = True
            send.close()
            remaining = request.policy.deadline_seconds - (monotonic() - deadline_started)
            if remaining <= 0 or not receive.poll(remaining):
                terminate_owned()
                raise GldSessionError(_CODE_SESSION_DEADLINE_EXCEEDED)
            if child_result_from_payload(receive.recv_bytes(_MAX_CHILD_IPC_BYTES)) != "READY":
                terminate_owned()
                raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
            group_ready = True
            remaining = request.policy.deadline_seconds - (monotonic() - deadline_started)
            if remaining <= 0 or not receive.poll(remaining):
                terminate_owned()
                raise GldSessionError(_CODE_SESSION_DEADLINE_EXCEEDED)
            payload = receive.recv_bytes(_MAX_CHILD_IPC_BYTES)
            remaining = request.policy.deadline_seconds - (monotonic() - deadline_started)
            if remaining <= 0:
                terminate_owned()
                raise GldSessionError(_CODE_SESSION_DEADLINE_EXCEEDED)
            terminate_owned()
            closed_code = child_result_from_payload(payload)
            if closed_code != "SUCCESS":
                raise GldSessionError(closed_code)
            result = child_material_from_payload(payload, request.policy.allowed_hosts[0])
        except GldSessionError:
            raise
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            raise _normalized_failure(_CODE_SESSION_RUNNER_FAILED, error) from None
        finally:
            receive.close()
            send.close()
            if started:
                terminate_owned()
        return result


def terminate_child(process: _ChildProcess) -> None:
    """Terminate, bounded-wait, then kill one parent-owned child with no zombie fallback."""
    process.terminate()
    process.join(1)
    if process.is_alive():
        process.kill()
        process.join(1)
    if process.is_alive():
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)


def terminate_child_group(process: _ChildProcess) -> None:
    """End an anchored owned group before reaping its leader, preventing PGID reuse races."""
    pid = getattr(process, "pid", None)
    if type(pid) is not int or pid < 1:
        terminate_child(process)
        return
    with suppress(ProcessLookupError):
        killpg(pid, 15)
    _unreaped_group_grace()
    with suppress(ProcessLookupError):
        killpg(pid, 9)
    process.join(1)
    if process.is_alive():
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)


def _unreaped_group_grace() -> None:
    """Allow bounded graceful child cleanup while deliberately retaining the anchored leader."""
    grace_deadline = monotonic() + 1.0
    while monotonic() < grace_deadline:
        sleep(0.05)


def cleanup_attempt_root(attempt_root: object) -> None:
    """Remove only a parent-created, exact per-attempt scratch directory after child join."""
    system_temp = Path(gettempdir()).resolve()
    if (
        not isinstance(attempt_root, Path)
        or attempt_root.is_symlink()
        or not attempt_root.name.startswith(_ATTEMPT_ROOT_PREFIX)
        or attempt_root.parent.resolve() != system_temp
    ):
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    for _attempt in range(2):
        if not attempt_root.exists():
            return
        try:
            rmtree(attempt_root)
        except OSError:
            continue
    if attempt_root.exists():
        raise GldSessionError(_CODE_SESSION_CLEANUP_FAILED)


def _child_patchright_attempt(
    send: object,
    request: _GldChildRequest,
    terminal_hold: Event,
    self_group_kill: Callable[[], None] | None = None,
) -> None:
    """Child owns all browser/display/profile resources and sends one closed bounded result."""
    material: BrowserSessionMaterial | None = None
    payload: bytes
    try:
        _CHILD_ATTEMPT_ROOT.set(request.attempt_root)
        setsid()
        send_child_payload(send, b'{"code":"READY"}', terminal=False)
        material = _concrete_compartment_for(request.experiment).establish(
            policy=request.policy, start_url=request.start_url
        )
        payload = dumps(
            {
                "origin": material.origin,
                "observed_request_count": material.observed_request_count,
                "session_secret": material.session_secret,
                "code": "SUCCESS",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    except GldSessionError as error:
        payload = dumps({"code": str(error)}, separators=(",", ":")).encode("utf-8")
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        payload = b'{"code":"GLD_SESSION_RUNNER_FAILED"}'
    send_child_payload(send, payload, terminal=True)
    material, payload = _discard_terminal_state(material, payload)
    released = terminal_hold.wait(_TERMINAL_HOLD_SECONDS)
    if released is not True:
        action = self_group_kill or _kill_own_process_group
        try:
            action()
        except BaseException as error:
            if not isinstance(error, Exception):
                raise


def _child_attempt_root() -> str | None:
    """Return the one child scratch root supplied by the parent, never an ambient profile root."""
    return _CHILD_ATTEMPT_ROOT.get()


def _discard_terminal_state(
    material: BrowserSessionMaterial | None, payload: bytes
) -> tuple[None, bytes]:
    """Drop child-frame references to publisher session material before the terminal hold."""
    del material
    del payload
    return None, b""


def _kill_own_process_group() -> None:
    """Kill the child-created session group after bounded parent-loss hold expiry."""
    with suppress(ProcessLookupError):
        killpg(getpid(), 9)


def send_child_payload(send: object, payload: bytes, *, terminal: bool) -> None:
    """Send one bounded non-traceback child result over the local channel."""
    send_bytes = getattr(send, "send_bytes", None)
    close = getattr(send, "close", None)
    if callable(send_bytes):
        send_bytes(payload[:_MAX_CHILD_IPC_BYTES])
    if terminal and callable(close):
        close()


def _concrete_compartment_for(experiment: GldBrowserExperiment) -> _PatchrightCompartment:
    """Construct exactly one concrete child-owned compartment for the closed experiment set."""
    if experiment is GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS:
        return _EphemeralCleanPatchrightCompartment()
    if experiment is GldBrowserExperiment.HEADED_ISOLATED_DISPLAY:
        return _HeadedIsolatedDisplayPatchrightCompartment()
    if experiment is GldBrowserExperiment.ORIGIN_SCOPED_PERSISTENT:
        return _OriginScopedPersistentPatchrightCompartment()
    raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)


def child_material_from_payload(payload: object, admitted_host: str) -> BrowserSessionMaterial:
    """Validate bounded child IPC anew; errors and tracebacks are never transmitted."""
    decoded = _child_json_payload(payload)
    if type(decoded) is not dict or set(decoded) != {
        "code",
        "observed_request_count",
        "origin",
        "session_secret",
    }:
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    origin = decoded.get("origin")
    secret = decoded.get("session_secret")
    status = decoded.get("code")
    request_count = decoded.get("observed_request_count")
    if (
        type(origin) is not str
        or type(secret) is not str
        or type(status) is not str
        or status != "SUCCESS"
        or type(request_count) is not int
        or origin != f"https://{admitted_host}"
    ):
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    return BrowserSessionMaterial(origin, secret, observed_request_count=request_count)


def child_result_from_payload(payload: object) -> str:
    """Accept an allowlisted child status code; raw child error detail never crosses IPC."""
    decoded = _child_json_payload(payload)
    code = decoded.get("code")
    if type(code) is not str or code not in {
        "READY",
        "SUCCESS",
        _CODE_CHALLENGE_UNRESOLVED,
        _CODE_CHALLENGE_CONTRACT_CHANGED,
        _CODE_SESSION_RUNNER_FAILED,
    }:
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    expected_keys = (
        {"code", "observed_request_count", "origin", "session_secret"}
        if code == "SUCCESS"
        else {"code"}
    )
    if set(decoded) != expected_keys:
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    return code


def _child_json_payload(payload: object) -> dict[str, JsonValue]:
    """Decode one exact child JSON object after leaving any secret-bearing exception scope."""
    if type(payload) is not bytes or not payload or len(payload) > _MAX_CHILD_IPC_BYTES:
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    failure: GldSessionError | None = None
    decoded: object = None
    try:
        decoded = checked_json_value(
            loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_pairs)
        )
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        failure = _normalized_failure(_CODE_SESSION_RUNNER_FAILED, error)
    if failure is not None:
        raise failure
    if type(decoded) is not dict:
        raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
    return decoded


def _reject_duplicate_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Decode JSON objects only when every member name occurs exactly once."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            duplicate_json_key = "GLD_CHILD_IPC_INVALID"
            raise ValueError(duplicate_json_key)
        result[key] = value
    return result


class _BoundPatchrightGldAttempt:
    """Private request-bound concrete attempt with no caller-supplied URL or route policy."""

    def __init__(
        self,
        policy: RenderedBrowserPolicy,
        *,
        supervisor: _ConcreteAttemptSupervisor | None = None,
    ) -> None:
        """Construct the three local resources only from one frozen request policy."""
        if policy.challenge_contract is None:
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        self._policy = policy
        self._supervisor = supervisor or _LocalPatchrightSupervisor()

    def establish(
        self,
        *,
        experiment: GldBrowserExperiment,
        start_url: str,
        allowed_hosts: tuple[str, ...],
        deadline_seconds: int,
    ) -> BrowserSessionMaterial:
        """Reject all drift before choosing one locally owned compartment."""
        if start_url != _registered_start_url(self._policy.request) or allowed_hosts != (
            self._policy.admitted_host,
        ):
            raise GldSessionError(_CODE_SESSION_NAVIGATION_INVALID)
        contract = self._policy.challenge_contract
        if contract is None:
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        policy = _attempt_policy(
            experiment,
            allowed_hosts,
            deadline_seconds,
            contract,
            self._policy.maximum_requests_per_attempt,
        )
        attempt_root = mkdtemp(prefix=_ATTEMPT_ROOT_PREFIX)
        result: BrowserSessionMaterial | None = None
        pending_error: Exception | None = None
        cleanup_failure: GldSessionError | None = None
        try:
            try:
                candidate = self._supervisor.establish(
                    _GldChildRequest(experiment, start_url, policy, attempt_root)
                )
                if type(candidate) is not BrowserSessionMaterial:
                    raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
                result = candidate
            except Exception as error:
                pending_error = error
        finally:
            cleanup_failure = _attempt_root_cleanup_failure(Path(attempt_root))
        if cleanup_failure is not None:
            if result is not None:
                _cleanup_material(result)
            raise cleanup_failure
        if pending_error is not None:
            raise pending_error
        if result is None:
            raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
        return result


def _attempt_root_cleanup_failure(attempt_root: Path) -> GldSessionError | None:
    """Return a closed root-cleanup failure only after the original exception scope has ended."""
    try:
        cleanup_attempt_root(attempt_root)
    except GldSessionError as error:
        return error
    return None


class PatchrightGldBrowserRunner:
    """Fixed-order local Patchright runner; it has no manual or remote fallback."""

    def __init__(
        self,
        policy: RenderedBrowserPolicy,
        *,
        attempt: _PatchrightAttempt | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        supervisor: _ConcreteAttemptSupervisor | None = None,
    ) -> None:
        """Bind the concrete browser to one exact frozen local policy."""
        if type(policy) is not RenderedBrowserPolicy:
            raise TypeError(_MESSAGE_EXACT_POLICY)
        self._policy = policy
        if monotonic_clock is not None and not callable(monotonic_clock):
            raise TypeError(_MESSAGE_CLOCK)
        self._monotonic_clock = monotonic_clock or _monotonic_now
        if policy.challenge_contract is None:
            self._attempt = attempt
        else:
            self._attempt = attempt or _BoundPatchrightGldAttempt(policy, supervisor=supervisor)

    @property
    def attempt_policies(self) -> tuple[PatchrightGldAttemptPolicy, ...]:
        """Expose fixed testable compartment configuration without browser state."""
        return tuple(
            _attempt_policy(
                experiment,
                (self._policy.admitted_host,),
                deadline,
                _required_challenge_contract(self._policy),
                self._policy.maximum_requests_per_attempt,
            )
            for experiment, deadline in zip(
                self._policy.experiment_order,
                self._policy.experiment_deadline_seconds,
                strict=True,
            )
        )

    def establish(
        self, *, start_url: str, allowed_hosts: tuple[str, ...], deadline_seconds: int
    ) -> BrowserSessionMaterial:
        """Try exactly three local compartments, then return unresolved without fallback."""
        if self._policy.challenge_contract is None:
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        if (
            type(start_url) is not str
            or start_url != _registered_start_url(self._policy.request)
            or type(allowed_hosts) is not tuple
            or allowed_hosts != (self._policy.admitted_host,)
        ):
            raise GldSessionError(_CODE_SESSION_NAVIGATION_INVALID)
        expected_deadline = sum(self._policy.experiment_deadline_seconds)
        if type(deadline_seconds) is not int or deadline_seconds != expected_deadline:
            raise GldSessionError(_CODE_SESSION_DEADLINE_INVALID)
        total_started = _exact_monotonic_time(self._monotonic_clock())
        for attempt_policy in self.attempt_policies:
            attempt_started = _exact_monotonic_time(self._monotonic_clock())
            normalized_failure: GldSessionError | None = None
            material: object = None
            try:
                if self._attempt is None:
                    raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
                material = self._attempt.establish(
                    experiment=attempt_policy.experiment,
                    start_url=start_url,
                    allowed_hosts=attempt_policy.allowed_hosts,
                    deadline_seconds=attempt_policy.deadline_seconds,
                )
            except GldSessionError as error:
                elapsed_attempt = _exact_monotonic_time(self._monotonic_clock()) - attempt_started
                elapsed_total = _exact_monotonic_time(self._monotonic_clock()) - total_started
                if (
                    elapsed_attempt > attempt_policy.deadline_seconds
                    or elapsed_total > expected_deadline
                ):
                    raise GldSessionError(_CODE_SESSION_DEADLINE_EXCEEDED) from None
                if str(error) == _CODE_CHALLENGE_UNRESOLVED:
                    continue
                raise
            except BaseException as error:
                if not isinstance(error, Exception):
                    raise
                normalized_failure = _normalized_failure(_CODE_SESSION_RUNNER_FAILED, error)
            if normalized_failure is not None:
                raise normalized_failure
            if (
                _exact_monotonic_time(self._monotonic_clock()) - attempt_started
                > attempt_policy.deadline_seconds
                or _exact_monotonic_time(self._monotonic_clock()) - total_started
                > expected_deadline
            ):
                if type(material) is BrowserSessionMaterial:
                    _cleanup_material(material)
                raise GldSessionError(_CODE_SESSION_DEADLINE_EXCEEDED)
            if type(material) is not BrowserSessionMaterial or material.origin != (
                f"https://{self._policy.admitted_host}"
            ):
                if type(material) is BrowserSessionMaterial:
                    _cleanup_material(material)
                raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
            return material
        raise GldSessionError(_CODE_CHALLENGE_UNRESOLVED)


class LocalGldSessionTransport(GldSessionPort):
    """Store only minimal protected GLD state and return sanitized grants."""

    def __init__(
        self,
        browser: GldBrowserRunner,
        store: ProtectedSessionStore,
        policy: RenderedBrowserPolicy,
        *,
        clock: Callable[[], datetime] | None = None,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        """Bind non-secret seams and reject an expanded or mutable browser policy."""
        if type(policy) is not RenderedBrowserPolicy:
            raise TypeError(_MESSAGE_EXACT_POLICY)
        if not callable(browser.establish):
            raise TypeError(_MESSAGE_RUNNER)
        if not all(callable(getattr(store, name, None)) for name in ("put", "get", "delete")):
            raise TypeError(_MESSAGE_STORE)
        if clock is not None and not callable(clock):
            raise TypeError(_MESSAGE_CLOCK)
        if session_id_factory is not None and not callable(session_id_factory):
            raise TypeError(_MESSAGE_SESSION_ID_FACTORY)
        self._browser = browser
        self._store = store
        self._policy = policy
        self._clock = clock or _utc_now
        self._session_id_factory = session_id_factory or _new_session_id

    def establish(self, request: GldSessionRequest) -> GldSessionGrant:
        """Create one sanitized grant from exact request, policy, runner, and store facts."""
        if type(request) is not GldSessionRequest:
            raise TypeError(_MESSAGE_EXACT_REQUEST)
        if self._policy.challenge_contract is None:
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        if request != self._policy.request:
            raise GldSessionError(_CODE_SESSION_POLICY_REQUEST_MISMATCH)
        host = gld_registered_host(request)
        if host != self._policy.admitted_host:
            raise GldSessionError(_CODE_SESSION_HOST_MISMATCH)
        session_id = _exact_session_id(self._session_id_factory())
        runner_failure: GldSessionError | None = None
        material: object = None
        try:
            material = self._browser.establish(
                start_url=_registered_start_url(request),
                allowed_hosts=(host,),
                deadline_seconds=sum(self._policy.experiment_deadline_seconds),
            )
        except GldSessionError:
            raise
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            runner_failure = _normalized_failure(_CODE_SESSION_RUNNER_FAILED, error)
        if runner_failure is not None:
            raise runner_failure
        if type(material) is not BrowserSessionMaterial or material.origin != f"https://{host}":
            if type(material) is BrowserSessionMaterial:
                _cleanup_material(material)
            raise GldSessionError(_CODE_SESSION_HOST_MISMATCH)
        established = _exact_utc_time(self._clock())
        expires = established + timedelta(seconds=self._policy.session_ttl_seconds)
        expires_at = _format_utc(expires)
        store_failure: GldSessionError | None = None
        created: object = None
        try:
            created = self._store.put(session_id, material, expires_at)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            rollback = _rollback_result(self._store, session_id)
            failure_code = _rollback_failure_code_after_cleanup(rollback, material)
            store_failure = _normalized_failure(failure_code, error)
        if store_failure is not None:
            raise store_failure
        if created is not True:
            rollback = _rollback_result(self._store, session_id)
            failure_code = _rollback_failure_code_after_cleanup(rollback, material)
            raise GldSessionError(failure_code)
        grant_failure: GldSessionError | None = None
        grant: GldSessionGrant | None = None
        try:
            grant = GldSessionGrant(
                session_id,
                _format_utc(established),
                expires_at,
                host,
                self._policy.policy_fingerprint,
                material.observed_request_count,
            )
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            rollback = _rollback_result(self._store, session_id)
            failure_code = _rollback_failure_code_after_cleanup(rollback, material)
            grant_failure = _normalized_failure(failure_code, error)
        if grant_failure is not None:
            raise grant_failure
        if grant is None:
            raise GldSessionError(_CODE_SESSION_RUNNER_FAILED)
        if _exact_utc_time(self._clock()) >= expires:
            rollback = _rollback_result(self._store, session_id)
            failure_code = _rollback_failure_code_after_cleanup(rollback, material)
            if failure_code != _CODE_SESSION_STORE_FAILED:
                raise GldSessionError(failure_code)
            raise GldSessionError(_CODE_SESSION_TTL_EXPIRED)
        return grant

    def invalidate(self, session_id: str) -> None:
        """Remove exactly one stored secret and clean any associated local scratch state."""
        exact_session_id = _exact_session_id(session_id)
        failure: GldSessionError | None = None
        material: object = None
        try:
            material = self._store.get(exact_session_id)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            failure = _normalized_failure(_CODE_SESSION_INVALIDATION_FAILED, error)
        if failure is not None:
            raise failure
        if type(material) is not BrowserSessionMaterial:
            raise GldSessionError(_CODE_SESSION_INVALIDATION_FAILED)
        deleted: object = None
        try:
            deleted = self._store.delete(exact_session_id)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            failure = _normalized_failure(_CODE_SESSION_INVALIDATION_FAILED, error)
        if failure is not None:
            raise failure
        if deleted is not True:
            raise GldSessionError(_CODE_SESSION_INVALIDATION_FAILED)
        if not _cleanup_material(material):
            raise GldSessionError(_CODE_SESSION_CLEANUP_FAILED)


def build_patchright_gld_session_transport(
    request: GldSessionRequest,
    challenge_contract: GldChallengeSessionContract,
    session_root: Path,
    *,
    experiment_deadline_seconds: tuple[int, int, int] = (20, 20, 20),
    maximum_requests_per_attempt: int = 64,
) -> LocalGldSessionTransport:
    """Compose the concrete browser with restart-safe local session storage."""
    if type(request) is not GldSessionRequest:
        raise TypeError(_MESSAGE_EXACT_REQUEST)
    if type(challenge_contract) is not GldChallengeSessionContract:
        message = "GLD_CHALLENGE_CONTRACT_INVALID"
        raise TypeError(message)
    policy = RenderedBrowserPolicy.for_request(
        request,
        challenge_contract=challenge_contract,
        experiment_deadline_seconds=experiment_deadline_seconds,
        maximum_requests_per_attempt=maximum_requests_per_attempt,
    )
    return LocalGldSessionTransport(
        PatchrightGldBrowserRunner(policy),
        FileProtectedSessionStore(session_root),
        policy,
    )


def _attempt_policy(
    experiment: GldBrowserExperiment,
    allowed_hosts: tuple[str, ...],
    deadline_seconds: int,
    challenge_contract: GldChallengeSessionContract,
    maximum_requests: int,
) -> PatchrightGldAttemptPolicy:
    """Translate one frozen policy position into a non-expandable browser compartment."""
    return PatchrightGldAttemptPolicy(
        experiment,
        allowed_hosts,
        challenge_contract,
        deadline_seconds,
        headless=experiment is not GldBrowserExperiment.HEADED_ISOLATED_DISPLAY,
        maximum_requests=maximum_requests,
    )


def _required_challenge_contract(policy: RenderedBrowserPolicy) -> GldChallengeSessionContract:
    """Return the admitted contract or fail before a browser experiment is materialized."""
    contract = policy.challenge_contract
    if contract is None:
        raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
    return contract


def _route_handler_for(
    policy: PatchrightGldAttemptPolicy, request_counter: list[int] | None = None
) -> Callable[[Route], None]:
    """Return a no-logging route gate that denies every disallowed request."""
    counter = request_counter if request_counter is not None else [0]

    def handle(route: Route) -> None:
        counter[0] += 1
        request = route.request
        if counter[0] <= policy.maximum_requests and policy.request_is_allowed(
            request.method, request.url, request.resource_type
        ):
            route.continue_()
        else:
            route.abort()

    return handle


def _cookies_from_context(context: BrowserContext) -> tuple[GldBrowserCookie, ...]:
    """Select bounded cookie facts only; raw storage state never leaves the compartment."""
    try:
        raw_cookies = context.cookies()
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise _normalized_failure(_CODE_SESSION_RUNNER_FAILED, error) from None
    selected: list[GldBrowserCookie] = []
    for raw_cookie in raw_cookies:
        name = raw_cookie.get("name")
        value = raw_cookie.get("value")
        domain = raw_cookie.get("domain")
        path = raw_cookie.get("path")
        if (
            type(name) is not str
            or type(value) is not str
            or type(domain) is not str
            or type(path) is not str
        ):
            raise GldSessionError(_CODE_CHALLENGE_CONTRACT_CHANGED)
        try:
            selected.append(
                GldBrowserCookie(
                    name,
                    value,
                    domain,
                    path,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise _normalized_failure(_CODE_CHALLENGE_CONTRACT_CHANGED, error) from None
    return tuple(selected)


def _close_popup(page: object) -> None:
    """Close a publisher-created popup instead of granting it a browsing path."""
    close = getattr(page, "close", None)
    if callable(close):
        close()


def _registered_start_url(request: GldSessionRequest) -> str:
    """Derive the one inventory URL from the checked-in inert endpoint contract."""
    host = gld_registered_host(request)
    _source, endpoint = load_hk_legislation_source_register().resolve_registered_endpoint(
        request.endpoint_id
    )
    parsed = urlsplit(endpoint.url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != host
        or _safe_port(parsed) not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise GldSessionError(_CODE_SESSION_NAVIGATION_INVALID)
    return endpoint.url


def _policy_fingerprint(
    request: GldSessionRequest,
    challenge_contract: GldChallengeSessionContract | None,
    host: str,
    experiments: tuple[GldBrowserExperiment, ...],
    deadlines: tuple[int, ...],
    session_ttl_seconds: int,
    maximum_requests_per_attempt: int,
) -> str:
    """Fingerprint every policy fact that can change local browser behavior."""
    projection = {
        "admitted_host": host,
        "challenge_contract": (
            None if challenge_contract is None else challenge_contract.fingerprint_projection()
        ),
        "experiment_deadline_seconds": list(deadlines),
        "experiment_order": [experiment.value for experiment in experiments],
        "request": {
            "endpoint_id": request.endpoint_id,
            "endpoint_version": request.endpoint_version,
            "language": request.language,
            "observation_cutoff": request.observation_cutoff,
            "register_fingerprint": request.register_fingerprint,
            "register_version": request.register_version,
            "source_id": request.source_id,
            "source_profile_version": request.source_profile_version,
            "start_date": request.start_date,
            "end_date": request.end_date,
        },
        "session_ttl_seconds": session_ttl_seconds,
        "maximum_requests_per_attempt": maximum_requests_per_attempt,
        "terminal_hold_seconds": _TERMINAL_HOLD_SECONDS,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"


def _valid_origin(value: str) -> bool:
    """Permit only one credential-free HTTPS origin in protected material."""
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and _valid_host(parsed.hostname)
        and _safe_port(parsed) in {None, 443}
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _valid_path(value: str) -> bool:
    """Accept one exact absolute URL path without query-like or traversal notation."""
    return (
        type(value) is str
        and (value == "/" or value.startswith("/"))
        and not value.startswith("//")
        and "?" not in value
        and "#" not in value
        and "\\" not in value
        and (
            value == "/" or all(segment not in {"", ".", ".."} for segment in value.split("/")[1:])
        )
    )


def _valid_session_secret(value: str) -> bool:
    """Bound publisher-controlled sealed state before it can reach protected storage."""
    if not value or len(value) > _MAX_SESSION_SECRET_CHARACTERS:
        return False
    try:
        if len(value.encode("utf-8")) > _MAX_SESSION_SECRET_UTF8_BYTES:
            return False
    except UnicodeEncodeError:
        return False
    return not any(category(character) in _UNSAFE_SESSION_SECRET_CATEGORIES for character in value)


def _valid_host(value: str) -> bool:
    """Keep browser hosts exact, lowercase, credential-free DNS names."""
    return (
        bool(value)
        and value == value.lower()
        and not value.startswith(".")
        and not value.endswith(".")
        and all(character.isalnum() or character in {"-", "."} for character in value)
    )


def _safe_port(parsed: SplitResult) -> int | None:
    """Read a parsed URL port without allowing malformed-port propagation."""
    try:
        return parsed.port
    except ValueError:
        return -1


def _page_url_is_allowed(url: str, policy: PatchrightGldAttemptPolicy) -> bool:
    """Require final navigation to remain in the exact browser compartment."""
    return policy.request_is_allowed("GET", url, "document")


def _exact_session_id(value: object) -> str:
    """Reject string subclasses and invalid local capability identifiers."""
    if type(value) is not str:
        raise TypeError(_MESSAGE_EXACT_SESSION_ID)
    if _SESSION_ID.fullmatch(value) is None:
        session_id_invalid = "GLD_SESSION_ID_INVALID"
        raise ValueError(session_id_invalid)
    return value


def _exact_utc_time(value: object) -> datetime:
    """Require the injected clock to return one exact UTC datetime value."""
    if type(value) is not datetime or value.tzinfo is not UTC or value.microsecond:
        clock_invalid = "GLD_SESSION_CLOCK_INVALID"
        raise ValueError(clock_invalid)
    return value


def _format_utc(value: datetime) -> str:
    """Produce the exact GldSessionGrant whole-second UTC representation."""
    return value.isoformat(timespec="seconds")


def _utc_now() -> datetime:
    """Supply whole-second UTC time when tests do not inject a deterministic clock."""
    return datetime.now(UTC).replace(microsecond=0)


def _monotonic_now() -> float:
    """Supply a process-local monotonic deadline clock, never wall-clock time."""
    return monotonic()


def _exact_monotonic_time(value: object) -> float:
    """Reject booleans, NaNs, and non-clock values at the deadline boundary."""
    if type(value) is not float or not isfinite(value):
        clock_invalid = "GLD_SESSION_MONOTONIC_CLOCK_INVALID"
        raise ValueError(clock_invalid)
    return value


def _new_session_id() -> str:
    """Generate an opaque local identifier compatible with the source contract."""
    return f"gld-{uuid4().hex}"


def _cleanup_material(material: BrowserSessionMaterial) -> bool:
    """Attempt cleanup without letting a secret-bearing cleanup error escape."""
    try:
        material.cleanup()
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        return False
    return True


def _rollback_result(store: ProtectedSessionStore, session_id: str) -> _RollbackResult:
    """Attempt rollback and retain exact deletion proof separately from failure classification."""
    try:
        deleted = store.delete(session_id)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        return _RollbackResult(_CODE_SESSION_ROLLBACK_UNPROVED, deletion_proved=False)
    if deleted is not True:
        return _RollbackResult(_CODE_SESSION_ROLLBACK_UNPROVED, deletion_proved=False)
    return _RollbackResult(_CODE_SESSION_STORE_FAILED, deletion_proved=True)


def _rollback_failure_code_after_cleanup(
    rollback: _RollbackResult, material: BrowserSessionMaterial
) -> str:
    """Clean only after deletion proof, with failure visible over the rollback cause."""
    if not rollback.deletion_proved:
        return rollback.failure_code
    if not _cleanup_material(material):
        return _CODE_SESSION_CLEANUP_FAILED
    return rollback.failure_code
