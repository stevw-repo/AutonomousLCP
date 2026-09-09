"""No-network proofs for the disabled GLD discovery/observation operator boundary."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from multiprocessing.connection import Connection
from pathlib import Path
from time import monotonic
from typing import cast

import pytest
from asklegal_acquisition_worker import gld_operator
from asklegal_acquisition_worker.gld_operator import (
    GldContractDiscoveryObservation,
    GldOperatorError,
    PatchrightGldContractDiscovery,
    PatchrightGldWindowProvider,
    build_gld_window_provider,
    main,
    preflight_gld_operator,
)
from asklegal_acquisition_worker.gld_session import (
    BrowserSessionMaterial,
    FileProtectedSessionStore,
    GldChallengeSessionContract,
    LocalGldSessionTransport,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import LocalImmutableVault, VaultName
from asklegal_source_connectors import (
    GldSessionGrant,
    GldSessionRequest,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
)

_MODE = "ASKLEGAL_HK_V1_GLD_OPERATOR_MODE"
_AUTHORITY = "ASKLEGAL_HK_V1_GLD_CHALLENGE_AUTHORITY_RECEIPT"
_START_DATE = "ASKLEGAL_HK_V1_GLD_START_DATE"
_CYCLE = "cyc_" + "1" * 64
_CUTOFF = "2026-09-08T01:00:00+00:00"


@dataclass
class _Discovery:
    calls: int = 0

    def discover(  # noqa: PLR0913
        self,
        *,
        host: str,
        start_path: str,
        allowed_paths: tuple[str, ...],
        deadline_seconds: int,
        maximum_requests: int,
        maximum_response_bytes: int,
    ) -> GldContractDiscoveryObservation:
        self.calls += 1
        assert host == "egazette.gld.gov.hk"
        assert start_path == "/en/list-of-gazette"
        assert allowed_paths == ("/en/list-of-gazette", "/challenge.js")
        assert deadline_seconds == 60
        assert maximum_requests == 64
        assert maximum_response_bytes == 20_000_000
        return GldContractDiscoveryObservation(
            status_code=403,
            final_url="https://egazette.gld.gov.hk/en/list-of-gazette",
            raw_response=b"raw challenge response",
            truncated=False,
            cookies=(("challenge-cookie", ".egazette.gld.gov.hk", "/"),),
            probe_candidates=("/challenge.js", "/en/list-of-gazette"),
        )


class _OversizedDiscovery:
    def __init__(self, *, truncated: bool) -> None:
        self.truncated = truncated

    def discover(self, **_kwargs: object) -> GldContractDiscoveryObservation:
        return GldContractDiscoveryObservation(
            status_code=200,
            final_url="https://egazette.gld.gov.hk/en/list-of-gazette",
            raw_response=b"x" * 20_000_001 if not self.truncated else b"partial",
            truncated=self.truncated,
            cookies=(),
            probe_candidates=(),
        )


def _hang_before_discovery_result(*_args: object) -> None:
    os.setsid()
    signal.pause()


def _hang_after_discovery_result(connection: Connection, *_args: object) -> None:
    os.setsid()
    connection.send(
        (
            "OK",
            GldContractDiscoveryObservation(
                status_code=200,
                final_url="https://egazette.gld.gov.hk/en/list-of-gazette",
                raw_response=b"bounded",
                truncated=False,
                cookies=(),
                probe_candidates=(),
            ),
        )
    )
    signal.pause()


class _CdpStream:
    def __init__(self, chunks: list[dict[str, object]]) -> None:
        self._chunks = iter(chunks)
        self.read_sizes: list[int] = []
        self.closed = False

    def send(self, method: str, params: Mapping[str, object] | None = None) -> object:
        assert params is not None
        if method == "IO.close":
            assert params == {"handle": "stream-1"}
            self.closed = True
            return {}
        assert method == "IO.read"
        assert params["handle"] == "stream-1"
        size = params["size"]
        assert type(size) is int
        self.read_sizes.append(size)
        return next(self._chunks)

    def on(self, event: str, callback: Callable[[object], None]) -> None:
        del event, callback
        message = "stream reader does not subscribe"
        raise AssertionError(message)


def _attempt_id(cycle_id: str) -> str:
    body = checked_json_value({"cycle_id": cycle_id, "observation_cutoff": _CUTOFF})
    return "gld-discover-" + sha256(canonicalize(body)).hexdigest()[:32]


def _authority(path: Path, vault: LocalImmutableVault, *, cycle_id: str = _CYCLE) -> None:
    register = load_hk_legislation_source_register()
    endpoint = next(
        item
        for item in register.endpoints
        if item.endpoint_id == "sep_00000000000000000000000000000000000000000000003b"
    )
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.gld-challenge-authority",
        "schema_version": "1.0.0",
        "authorization_id": "named-authority-20260908",
        "attempt_id": _attempt_id(cycle_id),
        "named_authorizer": "Local V1 Source Owner",
        "source_id": "HK-LEG-GLD-EGAZETTE",
        "authorized_action": "DISCOVER_GLD_CHALLENGE_CONTRACT",
        "rights_basis": "USER_REPORTED_LEGAL_TEAM_CLEARANCE",
        "authorized_at": "2026-09-08T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "cycle_id": cycle_id,
        "observation_cutoff": _CUTOFF,
        "endpoint_id": endpoint.endpoint_id,
        "endpoint_version": endpoint.version,
        "register_version": register.register_version,
        "register_fingerprint": register.fingerprint,
        "admitted_host": "egazette.gld.gov.hk",
        "allowed_paths": ["/en/list-of-gazette", "/challenge.js"],
        "maximum_response_bytes": endpoint.max_bytes,
        "maximum_requests": 64,
        "deadline_seconds": 60,
        "operation_deadline_seconds": 60,
        "session_deadline_seconds": None,
        "listing_deadline_seconds": None,
        "session_max_attempts": None,
        "session_max_requests_per_attempt": None,
        "listing_max_requests": None,
        "challenge_contract_fingerprint": None,
        "discovery_observation_fingerprint": None,
        "primary_vault": vault.vault_name.value,
        "object_prefix": "poc/isolation/gld-contract-discovery",
        "manifest_prefix": "poc/report/gld-contract-discovery",
        "session_root": None,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    path.write_bytes(canonicalize(checked_json_value({**body, "fingerprint": fingerprint})))


def _rewrite_fingerprinted(path: Path, **changes: JsonValue) -> str:
    document = parse_json_bytes(path.read_bytes(), max_bytes=65_536)
    assert type(document) is dict
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    body.update(changes)
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    path.write_bytes(canonicalize(checked_json_value({**body, "fingerprint": fingerprint})))
    return fingerprint


def _challenge(
    path: Path,
    discovery_observation_fingerprint: str,
    *,
    navigation_status: int = 200,
) -> str:
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.gld-challenge-contract",
        "schema_version": "1.0.0",
        "version": "observed-20260908",
        "navigation_path": "/en/list-of-gazette",
        "required_cookie_name": "challenge-cookie",
        "required_cookie_path": "/",
        "expected_navigation_status": navigation_status,
        "probe_path": "/en/search-gazette",
        "expected_probe_status": 200,
        "discovery_observation_fingerprint": discovery_observation_fingerprint,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    path.write_bytes(canonicalize(checked_json_value({**body, "fingerprint": fingerprint})))
    return fingerprint


def _observe_attempt_id() -> str:
    body = checked_json_value({"cycle_id": _CYCLE, "observation_cutoff": _CUTOFF})
    return "gld-observe-" + sha256(canonicalize(body)).hexdigest()[:32]


def _observe_authority(
    path: Path,
    vault: LocalImmutableVault,
    session_root: Path,
    challenge_fingerprint: str,
    discovery_observation_fingerprint: str,
) -> str:
    _authority(path, vault)
    return _rewrite_fingerprinted(
        path,
        attempt_id=_observe_attempt_id(),
        authorized_action="OBSERVE_GLD_CURRENT_WINDOW",
        allowed_paths=["/en/list-of-gazette", "/en/search-gazette"],
        maximum_requests=None,
        operation_deadline_seconds=60,
        session_deadline_seconds=45,
        listing_deadline_seconds=15,
        session_max_attempts=3,
        session_max_requests_per_attempt=64,
        listing_max_requests=1,
        challenge_contract_fingerprint=challenge_fingerprint,
        discovery_observation_fingerprint=discovery_observation_fingerprint,
        object_prefix="poc/isolation/gld-listing",
        manifest_prefix="poc/report/gld-listing-observation",
        session_root=str(session_root),
    )


class _Session:
    def __init__(self, root: Path, observed_request_count: int = 0) -> None:
        self._store = FileProtectedSessionStore(root)
        self.calls = 0
        self._observed_request_count = observed_request_count

    def establish(self, _request: GldSessionRequest) -> GldSessionGrant:
        self.calls += 1
        session_id = "gld-test-session"
        assert self._store.put(
            session_id,
            BrowserSessionMaterial("https://egazette.gld.gov.hk", "cookie-secret"),
            "2099-01-01T00:00:00+00:00",
        )
        return GldSessionGrant(
            session_id,
            "2026-09-08T00:00:00+00:00",
            "2099-01-01T00:00:00+00:00",
            "egazette.gld.gov.hk",
            "sha256:" + "a" * 64,
            self._observed_request_count,
        )

    def invalidate(self, session_id: str) -> None:
        assert self._store.delete(session_id)


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def __call__(
        self,
        request: GldSessionRequest,
        challenge_contract: GldChallengeSessionContract,
        session_root: Path,
        *,
        experiment_deadline_seconds: tuple[int, int, int],
        maximum_requests_per_attempt: int,
    ) -> LocalGldSessionTransport:
        del request, challenge_contract, session_root
        assert experiment_deadline_seconds == (15, 15, 15)
        assert maximum_requests_per_attempt == 64
        return cast("LocalGldSessionTransport", self._session)


@dataclass
class _Http:
    calls: int = 0
    timeout_seconds: int | None = None

    def request(self, *, endpoint: object, method: object, timeout_seconds: int) -> object:
        del endpoint, method
        assert 1 <= timeout_seconds <= 15
        self.timeout_seconds = timeout_seconds
        self.calls += 1
        body = b"bounded listing observation"
        return OfficialTransportResponse(
            status_code=200,
            final_url="https://egazette.gld.gov.hk/en/list-of-gazette",
            media_type="text/html",
            character_encoding="utf-8",
            body=body,
            declared_length=len(body),
            truncated=False,
        )


class _Clock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


def _observe_provider(
    tmp_path: Path,
    *,
    observed_request_count: int = 0,
    monotonic_clock: Callable[[], float] = monotonic,
) -> tuple[PatchrightGldWindowProvider, Path, Path, LocalImmutableVault, _Session, _Http]:
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "observe-authority.json"
    challenge = tmp_path / "challenge.json"
    session_root = tmp_path / "sessions"
    discovery_authority = tmp_path / "discovery-authority.json"
    _authority(discovery_authority, vault)
    discovery_result = PatchrightGldWindowProvider(
        _environment(discovery_authority),
        "127.0.0.1",
        1,
        vault,
        discovery=_Discovery(),
    ).capture_observation(_CYCLE, _CUTOFF)
    discovery_fingerprint = discovery_result["fingerprint"]
    assert type(discovery_fingerprint) is str
    challenge_fingerprint = _challenge(challenge, discovery_fingerprint)
    _observe_authority(
        authority,
        vault,
        session_root,
        challenge_fingerprint,
        discovery_fingerprint,
    )
    environment = {
        _MODE: "OBSERVE_WINDOW",
        _AUTHORITY: str(authority),
        _START_DATE: "2026-09-01",
        "ASKLEGAL_HK_V1_GLD_CHALLENGE_CONTRACT": str(challenge),
        "ASKLEGAL_HK_V1_GLD_SESSION_ROOT": str(session_root),
    }
    session = _Session(session_root, observed_request_count)
    http = _Http()
    provider = PatchrightGldWindowProvider(
        environment,
        "127.0.0.1",
        1,
        vault,
        session_factory=_SessionFactory(session),
        http_transport=http,
        monotonic_clock=monotonic_clock,
    )
    return provider, authority, challenge, vault, session, http


def _environment(authority: Path) -> dict[str, str]:
    return {
        _MODE: "DISCOVER_CONTRACT",
        _AUTHORITY: str(authority),
        _START_DATE: "2026-09-01",
    }


def test_operator_is_disabled_and_not_composed_by_default(tmp_path: Path) -> None:
    """No generic environment enables GLD source work."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    preflight = preflight_gld_operator({})
    assert preflight.blocker_code == "GLD_OPERATOR_DISABLED"
    assert not preflight.observation_executable
    assert build_gld_window_provider({}, "127.0.0.1", 1, vault) is None


def test_installed_module_preflight_is_operator_reachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The packaged module exposes a real read-only CLI without repository tools."""
    monkeypatch.delenv(_MODE, raising=False)
    assert main(["preflight"]) == 0
    assert '"blocker_code": "GLD_OPERATOR_DISABLED"' in capsys.readouterr().out


def test_discovery_has_no_challenge_contract_bootstrap_loop_and_replays(tmp_path: Path) -> None:
    """First observation retains only raw/sanitized facts and replays without an effect."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    environment = _environment(authority)
    assert preflight_gld_operator(
        environment, cycle_id=_CYCLE, observation_cutoff=_CUTOFF, vault=vault
    ).observation_executable
    discovery = _Discovery()
    provider = PatchrightGldWindowProvider(
        environment,
        "127.0.0.1",
        1,
        vault,
        discovery=discovery,
    )

    first = provider.capture_observation(_CYCLE, _CUTOFF)
    second = provider.capture_observation(_CYCLE, _CUTOFF)

    assert first == second
    assert discovery.calls == 1
    assert first["challenge_contract_issued"] is False
    assert first["terms_accepted"] is False
    assert first["window_issued"] is False
    assert first["cookie_candidates"] == [
        {
            "domain": ".egazette.gld.gov.hk",
            "name": "challenge-cookie",
            "path": "/",
        }
    ]
    with pytest.raises(GldOperatorError, match="GLD_OBSERVE_WINDOW_MODE_REQUIRED"):
        provider.load_window(_CYCLE, _CUTOFF)


@pytest.mark.parametrize(
    "child_target",
    [_hang_before_discovery_result, _hang_after_discovery_result],
    ids=["hung-launch", "hung-close"],
)
def test_patchright_discovery_deadline_bounds_whole_child_lifetime(
    monkeypatch: pytest.MonkeyPatch,
    child_target: Callable[..., None],
) -> None:
    """A hung launch or close is killed with no false observation returned."""
    monkeypatch.setattr(gld_operator, "_run_discovery_child", child_target)
    started = monotonic()
    with pytest.raises(GldOperatorError, match="GLD_CONTRACT_DISCOVERY_DEADLINE_EXCEEDED"):
        PatchrightGldContractDiscovery().discover(
            host="egazette.gld.gov.hk",
            start_path="/en/list-of-gazette",
            allowed_paths=("/en/list-of-gazette",),
            deadline_seconds=1,
            maximum_requests=1,
            maximum_response_bytes=128,
        )
    assert monotonic() - started < 3


def test_discovery_reads_chromium_stream_only_to_exact_body_cap_plus_sentinel() -> None:
    """The browser body interface cannot materialize more than the 20 MB authority cap."""
    stream = _CdpStream(
        [
            {"data": "abcd", "base64Encoded": False, "eof": False},
            {"data": "ef", "base64Encoded": False, "eof": False},
        ]
    )

    body, exceeded = gld_operator._bounded_cdp_stream(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        stream, "stream-1", 5
    )

    assert body == b"abcde"
    assert exceeded
    assert stream.read_sizes == [6, 2]
    assert stream.closed


@pytest.mark.parametrize("response_case", ["no-length-oversize", "truncated"])
def test_discovery_response_limit_failure_retains_nothing(
    tmp_path: Path, response_case: str
) -> None:
    """Absent length metadata or an indicated truncation cannot become retained evidence."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    provider = PatchrightGldWindowProvider(
        _environment(authority),
        "127.0.0.1",
        1,
        vault,
        discovery=_OversizedDiscovery(truncated=response_case == "truncated"),
    )

    with pytest.raises(GldOperatorError, match="GLD_CONTRACT_DISCOVERY_RESPONSE_LIMIT_EXCEEDED"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert vault.resolve_current(f"poc/report/gld-contract-discovery/{_CYCLE}/attempt.json") is None


def test_discovery_authority_is_exact_cycle_bound_before_browser(tmp_path: Path) -> None:
    """Cycle drift stops before Patchright receives a call."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    discovery = _Discovery()
    provider = PatchrightGldWindowProvider(
        _environment(authority),
        "127.0.0.1",
        1,
        vault,
        discovery=discovery,
    )

    with pytest.raises(GldOperatorError, match="GLD_CHALLENGE_AUTHORITY_BINDING_INVALID"):
        provider.capture_observation("cyc_" + "2" * 64, _CUTOFF)
    assert discovery.calls == 0


@pytest.mark.parametrize(
    "allowed_paths",
    [
        ["/en/list-of-gazette?query=1", "/challenge.js"],
        ["/en/list-of-gazette#fragment", "/challenge.js"],
        ["/en/list-of-gazette", "/en/list-of-gazette"],
    ],
    ids=["query", "fragment", "duplicate"],
)
def test_preflight_and_capture_share_exact_allowed_route_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allowed_paths: list[str],
) -> None:
    """Route ambiguity stops in preflight and remains stopped after a simulated TOCTOU."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    environment = _environment(authority)
    admitted = preflight_gld_operator(
        environment, cycle_id=_CYCLE, observation_cutoff=_CUTOFF, vault=vault
    )
    _rewrite_fingerprinted(authority, allowed_paths=checked_json_value(allowed_paths))
    rejected = preflight_gld_operator(
        environment, cycle_id=_CYCLE, observation_cutoff=_CUTOFF, vault=vault
    )
    assert rejected.blocker_code == "GLD_CHALLENGE_AUTHORITY_BINDING_INVALID"
    assert not rejected.observation_executable

    def bypass_preflight(*_args: object, **_kwargs: object) -> object:
        return admitted

    monkeypatch.setattr(gld_operator, "preflight_gld_operator", bypass_preflight)
    discovery = _Discovery()
    provider = PatchrightGldWindowProvider(environment, "127.0.0.1", 1, vault, discovery=discovery)
    with pytest.raises(GldOperatorError, match="GLD_CHALLENGE_AUTHORITY_BINDING_INVALID"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert discovery.calls == 0


@pytest.mark.parametrize(
    "authority_change",
    [
        {"authorized_at": "2026-09-08T00:00:01+00:00"},
        {"authorization_id": "replacement-authority-20260908"},
        {
            "allowed_paths": [
                "/en/list-of-gazette",
                "/challenge.js",
                "/replacement-probe",
            ]
        },
    ],
)
def test_discovery_replay_rejects_authority_or_route_drift(
    tmp_path: Path, authority_change: dict[str, JsonValue]
) -> None:
    """Retained discovery belongs to one exact authority fingerprint and route set."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    discovery = _Discovery()
    provider = PatchrightGldWindowProvider(
        _environment(authority), "127.0.0.1", 1, vault, discovery=discovery
    )
    provider.capture_observation(_CYCLE, _CUTOFF)
    _rewrite_fingerprinted(authority, **authority_change)

    with pytest.raises(GldOperatorError, match="GLD_CONTRACT_DISCOVERY_READBACK_INVALID"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert discovery.calls == 1


def test_observation_replay_rejects_authority_fingerprint_drift(tmp_path: Path) -> None:
    """A replacement observation authority cannot inherit an earlier retained effect."""
    provider, authority, _challenge_path, _vault, session, http = _observe_provider(tmp_path)
    provider.capture_observation(_CYCLE, _CUTOFF)
    _rewrite_fingerprinted(authority, authorization_id="replacement-observe-authority")

    with pytest.raises(GldOperatorError, match="GLD_LISTING_OBSERVATION_READBACK_INVALID"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert session.calls == 1
    assert http.calls == 1


def test_observation_replay_rejects_challenge_contract_fingerprint_drift(
    tmp_path: Path,
) -> None:
    """A newly frozen challenge contract cannot inherit an old listing observation."""
    provider, authority, challenge_path, vault, session, http = _observe_provider(tmp_path)
    provider.capture_observation(_CYCLE, _CUTOFF)
    discovery_reference = vault.resolve_current(
        f"poc/report/gld-contract-discovery/{_CYCLE}/attempt.json"
    )
    assert discovery_reference is not None
    discovery_fingerprint = discovery_reference.fingerprint
    replacement_fingerprint = _challenge(
        challenge_path, discovery_fingerprint, navigation_status=201
    )
    _observe_authority(
        authority,
        vault,
        tmp_path / "sessions",
        replacement_fingerprint,
        discovery_fingerprint,
    )

    with pytest.raises(GldOperatorError, match="GLD_LISTING_OBSERVATION_READBACK_INVALID"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert session.calls == 1
    assert http.calls == 1


def test_observation_rejects_over_budget_session_before_listing(tmp_path: Path) -> None:
    """The authority-bound per-attempt request ceiling is enforced before inert HTTP."""
    provider, _authority_path, _challenge_path, _vault, session, http = _observe_provider(
        tmp_path, observed_request_count=65
    )
    with pytest.raises(GldOperatorError, match="GLD_SESSION_GRANT_INVALID"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert session.calls == 1
    assert http.calls == 0


def test_observation_whole_operation_deadline_crossing_retains_no_manifest(
    tmp_path: Path,
) -> None:
    """Session, listing and cleanup share one clock and cannot publish after expiry."""
    provider, _authority_path, _challenge_path, vault, session, http = _observe_provider(
        tmp_path, monotonic_clock=_Clock([0.0, 46.0, 61.0])
    )
    with pytest.raises(GldOperatorError, match="GLD_OPERATION_DEADLINE_EXCEEDED"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert session.calls == 1
    assert http.calls == 1
    assert (
        vault.resolve_current(f"poc/report/gld-listing-observation/{_CYCLE}/attempt.json") is None
    )


def test_observation_production_listing_transport_forbids_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One listing-request authority constructs a transport that cannot follow a second hop."""
    provider, _authority_path, _challenge_path, _vault, _session, http = _observe_provider(tmp_path)
    provider._http_transport = None  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def transport_factory(
        proxy_host: str,
        proxy_port: int,
        max_redirects: int = 3,
        session_cookies: dict[str, str] | None = None,
    ) -> _Http:
        assert (proxy_host, proxy_port) == ("127.0.0.1", 1)
        assert max_redirects == 0
        assert session_cookies == {"challenge-cookie": "cookie-secret"}
        return http

    monkeypatch.setattr(gld_operator, "ProxiedOfficialHttpTransport", transport_factory)
    provider.capture_observation(_CYCLE, _CUTOFF)
    assert http.calls == 1


def test_observation_refuses_to_round_subsecond_remaining_budget_into_a_request(
    tmp_path: Path,
) -> None:
    """A request cannot receive a fresh one-second timeout after the shared deadline is spent."""
    provider, _authority_path, _challenge_path, _vault, session, http = _observe_provider(
        tmp_path, monotonic_clock=_Clock([0.0, 59.5])
    )
    with pytest.raises(GldOperatorError, match="GLD_OPERATION_DEADLINE_EXCEEDED"):
        provider.capture_observation(_CYCLE, _CUTOFF)
    assert session.calls == 1
    assert http.calls == 0


def test_observe_mode_requires_frozen_contract_and_never_becomes_window_ready(
    tmp_path: Path,
) -> None:
    """Window observation cannot bootstrap or infer its challenge contract."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    preflight = preflight_gld_operator(
        {**_environment(authority), _MODE: "OBSERVE_WINDOW"},
        cycle_id=_CYCLE,
        observation_cutoff=_CUTOFF,
        vault=vault,
    )
    assert preflight.blocker_code == "GLD_CHALLENGE_CONTRACT_REQUIRED"
    assert not preflight.observation_executable
    assert not preflight.window_issuance_ready


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        (
            {
                "authorized_at": "2020-01-01T00:00:00+00:00",
                "expires_at": "2021-01-01T00:00:00+00:00",
            },
            "GLD_CHALLENGE_AUTHORITY_NOT_CURRENT",
        ),
        (
            {
                "authorized_at": "2090-01-01T00:00:00+00:00",
                "expires_at": "2099-01-01T00:00:00+00:00",
            },
            "GLD_CHALLENGE_AUTHORITY_NOT_CURRENT",
        ),
        (
            {"authorized_action": "OBSERVE_GLD_CURRENT_WINDOW"},
            "GLD_CHALLENGE_AUTHORITY_BINDING_INVALID",
        ),
    ],
)
def test_preflight_never_reports_expired_future_or_wrong_action_authority_executable(
    tmp_path: Path, change: dict[str, JsonValue], blocker: str
) -> None:
    """Config presence cannot be promoted to executable authority truth."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    authority = tmp_path / "authority.json"
    _authority(authority, vault)
    _rewrite_fingerprinted(authority, **change)

    preflight = preflight_gld_operator(
        _environment(authority),
        cycle_id=_CYCLE,
        observation_cutoff=_CUTOFF,
        vault=vault,
    )
    assert preflight.blocker_code == blocker
    assert not preflight.observation_executable
