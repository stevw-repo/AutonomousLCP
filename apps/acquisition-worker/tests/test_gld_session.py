"""Strict local-only GLD browser-session adapter tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

import pytest
from asklegal_acquisition_worker import gld_session
from asklegal_acquisition_worker.gld_session import (
    BrowserSessionMaterial,
    FileProtectedSessionStore,
    GldBrowserCookie,
    GldBrowserExperiment,
    GldBrowserObservation,
    GldChallengeSessionContract,
    GldSessionError,
    LocalGldSessionTransport,
    PatchrightGldAttemptPolicy,
    PatchrightGldBrowserRunner,
    RenderedBrowserPolicy,
    build_patchright_gld_session_transport,
    classify_gld_session_failure,
)
from asklegal_source_connectors import (
    GldSessionRequest,
    gld_registered_host,
    load_hk_legislation_source_register,
)

_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"
_INVENTORY_ENDPOINT_ID = "sep_00000000000000000000000000000000000000000000003b"
_REGISTER_FINGERPRINT = "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"
_NOW = datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)
_START_URL = "https://egazette.gld.gov.hk/en/list-of-gazette"
_SESSION_SECRET = "test-session-cookie"
_UNPROVED_SECRET = "unproved"
_SECRET_STORE_DETAIL = "secret-store-detail"
_GROUP_TERMINATION_MESSAGE = "group termination must not fall back to leader termination"
_GROUP_KILL_MESSAGE = "group termination must signal the owned group"
_CLEANUP_FAILURE_CODE = "GLD_SESSION_CLEANUP_FAILED"
_PARENT_LOSS_SECRET = "parent-loss-secret"


def _challenge_contract() -> GldChallengeSessionContract:
    return GldChallengeSessionContract(
        "TEST-GLD-CHALLENGE-1",
        "/en/list-of-gazette",
        "gld_session",
        "/",
        200,
        "/en/list-of-gazette",
        200,
    )


def _construct[Contract](
    constructor: Callable[..., Contract], values: dict[str, object]
) -> Contract:
    """Exercise direct contract construction with deliberately malformed payload values."""
    return constructor(**values)


def _call[Result](function: Callable[..., Result], *arguments: object) -> Result:
    """Exercise a typed public boundary with values intentionally outside its annotation."""
    return function(*arguments)


def _raise(error: Exception) -> None:
    """Raise one scripted ordinary seam error without invoking a live browser process."""
    raise error


def _request(**changes: object) -> GldSessionRequest:
    values: dict[str, object] = {
        "source_id": _SOURCE_ID,
        "endpoint_id": _INVENTORY_ENDPOINT_ID,
        "endpoint_version": "1.0.0",
        "source_profile_version": "1.1.0",
        "register_version": "2026-08-28.3",
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "start_date": "2026-08-24",
        "end_date": "2026-08-25",
        "language": "BILINGUAL",
        "observation_cutoff": "2026-08-25T12:00:00+00:00",
    }
    values.update(changes)
    return _construct(GldSessionRequest, values)


def _policy(
    request: GldSessionRequest,
    *,
    deadlines: tuple[int, int, int] = (10, 15, 20),
    session_ttl_seconds: int = 300,
) -> RenderedBrowserPolicy:
    return RenderedBrowserPolicy.for_request(
        request,
        challenge_contract=_challenge_contract(),
        experiment_deadline_seconds=deadlines,
        session_ttl_seconds=session_ttl_seconds,
    )


class _StringSubclass(str):
    """Exercise direct boundary validation without changing the value."""

    __slots__ = ()


class InMemoryProtectedSessionStore:
    """Test-only protected-store stand-in with observable exact deletion."""

    def __init__(
        self, *, put_error: Exception | None = None, delete_error: Exception | None = None
    ) -> None:
        self._entries: dict[str, BrowserSessionMaterial] = {}
        self.put_error = put_error
        self.delete_error = delete_error
        self.put_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []

    def put(self, session_id: str, material: BrowserSessionMaterial, expires_at: str) -> bool:
        self.put_calls.append((session_id, expires_at))
        if self.put_error is not None:
            raise self.put_error
        self._entries[session_id] = material
        return True

    def get(self, session_id: str) -> BrowserSessionMaterial:
        return self._entries[session_id]

    def delete(self, session_id: str) -> bool:
        self.delete_calls.append(session_id)
        if self.delete_error is not None:
            raise self.delete_error
        del self._entries[session_id]
        return True

    def has(self, session_id: str) -> bool:
        return session_id in self._entries


class ScriptedGldBrowser:
    """Runner substitute that never launches Patchright or reaches a host."""

    def __init__(self, outcome: BrowserSessionMaterial | Exception) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, tuple[str, ...], int]] = []

    def establish(
        self, *, start_url: str, allowed_hosts: tuple[str, ...], deadline_seconds: int
    ) -> BrowserSessionMaterial:
        self.calls.append((start_url, allowed_hosts, deadline_seconds))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class ScriptedPatchrightAttempt:
    """Concrete-runner seam that records the fixed unattended experiment order."""

    def __init__(self, outcomes: tuple[BrowserSessionMaterial | Exception, ...]) -> None:
        self._outcomes = iter(outcomes)
        self.calls: list[tuple[GldBrowserExperiment, str, tuple[str, ...], int]] = []

    def establish(
        self,
        *,
        experiment: GldBrowserExperiment,
        start_url: str,
        allowed_hosts: tuple[str, ...],
        deadline_seconds: int,
    ) -> BrowserSessionMaterial:
        self.calls.append((experiment, start_url, allowed_hosts, deadline_seconds))
        outcome = next(self._outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedConcreteSupervisor:
    """Default-concrete-path seam: no child process or browser is started in tests."""

    def __init__(self, outcome: BrowserSessionMaterial | Exception | object) -> None:
        self.outcome = outcome
        self.calls: list[object] = []

    def establish(self, request: object) -> object:
        self.calls.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class ScriptedPatchrightCompartment:
    """One inert local browser compartment double, distinguished by its policy."""

    def __init__(self) -> None:
        self.calls: list[PatchrightGldAttemptPolicy] = []

    def establish(
        self, *, policy: PatchrightGldAttemptPolicy, start_url: str
    ) -> BrowserSessionMaterial:
        self.calls.append(policy)
        assert start_url == _START_URL
        return _material()


def _material(
    *,
    secret: str = _SESSION_SECRET,
    origin: str = "https://egazette.gld.gov.hk",
    cleaned: list[str] | None = None,
) -> BrowserSessionMaterial:
    def cleanup() -> None:
        if cleaned is not None:
            cleaned.append("cleaned")

    return BrowserSessionMaterial(origin, secret, cleanup)


def _transport(
    browser: ScriptedGldBrowser,
    store: InMemoryProtectedSessionStore,
    policy: RenderedBrowserPolicy,
) -> LocalGldSessionTransport:
    return LocalGldSessionTransport(
        browser,
        store,
        policy,
        clock=lambda: _NOW,
        session_id_factory=lambda: "gld-session-20260825",
    )


def test_establish_returns_sanitized_grant_and_keeps_session_secret_private() -> None:
    """The public grant carries no protected browser-session secret."""
    request = _request()
    policy = _policy(request)
    store = InMemoryProtectedSessionStore()
    browser = ScriptedGldBrowser(_material())

    grant = _transport(browser, store, policy).establish(request)

    assert grant.admitted_host == gld_registered_host(request) == "egazette.gld.gov.hk"
    assert grant.expires_at == "2026-08-25T12:05:00+00:00"
    assert "secret-cookie" not in repr(grant)
    assert "secret-cookie" not in repr(store.get(grant.session_id))
    assert store.has(grant.session_id)
    assert browser.calls == [(_START_URL, ("egazette.gld.gov.hk",), 45)]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("GLD_CHALLENGE_CONTRACT_CHANGED", "CONTRACT"),
        ("GLD_SESSION_NAVIGATION_INVALID", "CONTRACT"),
        ("GLD_CHALLENGE_UNRESOLVED", "RETRYABLE"),
        ("GLD_SESSION_DEADLINE_EXCEEDED", "RETRYABLE"),
    ],
)
def test_session_failure_has_one_sanitized_acquisition_classification(
    code: str, expected: str
) -> None:
    """The family runner can journal challenge failure without raw browser detail."""
    assert classify_gld_session_failure(GldSessionError(code)).value == expected


def test_policy_is_request_bound_frozen_and_fingerprint_stable() -> None:
    """Equivalent exact requests derive the one stable frozen browser policy."""
    request = _request()
    first = _policy(request)
    second = _policy(request)

    assert first == second
    assert first.policy_fingerprint == second.policy_fingerprint
    assert first.experiment_order == (
        GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS,
        GldBrowserExperiment.HEADED_ISOLATED_DISPLAY,
        GldBrowserExperiment.ORIGIN_SCOPED_PERSISTENT,
    )


def test_policy_rejects_host_request_fingerprint_and_deadline_drift() -> None:
    """No host, request, fingerprint, experiment, or deadline drift reaches a runner."""
    request = _request()
    policy = _policy(request)

    with pytest.raises(ValueError, match="GLD_POLICY_HOST_INVALID"):
        replace(policy, admitted_host="www.gld.gov.hk")
    with pytest.raises(ValueError, match="GLD_POLICY_FINGERPRINT_INVALID"):
        replace(policy, policy_fingerprint="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="GLD_POLICY_EXPERIMENTS_INVALID"):
        replace(policy, experiment_order=tuple(reversed(policy.experiment_order)))
    with pytest.raises(ValueError, match="GLD_POLICY_DEADLINES_INVALID"):
        replace(policy, experiment_deadline_seconds=(10, 15, 61))
    with pytest.raises(GldSessionError, match="GLD_SESSION_POLICY_REQUEST_MISMATCH"):
        _transport(
            ScriptedGldBrowser(_material()), InMemoryProtectedSessionStore(), policy
        ).establish(_request(start_date="2026-08-23"))


def test_session_material_rejects_closed_string_subclasses_and_never_reveals_secret() -> None:
    """Secret-bearing material has exact text boundaries and a redacted representation."""
    with pytest.raises(ValueError, match="GLD_SESSION_MATERIAL_INVALID"):
        BrowserSessionMaterial("https://egazette.gld.gov.hk", _StringSubclass("secret-cookie"))
    with pytest.raises(ValueError, match="GLD_SESSION_MATERIAL_INVALID"):
        BrowserSessionMaterial("https://user:secret@egazette.gld.gov.hk", "secret-cookie")
    assert "secret-cookie" not in repr(_material())


@pytest.mark.parametrize(
    "secret",
    [
        "a" * 16_385,
        "法" * 10_923,
        "\u0080c1-control",
        "\u200bformat-control",
        "\u2028line-separator",
        "\uffffnoncharacter",
    ],
)
def test_session_material_bounds_and_sanitizes_publisher_controlled_state(secret: str) -> None:
    """A protected-store payload cannot become an unbounded or ambiguous browser state."""
    with pytest.raises(ValueError, match="GLD_SESSION_MATERIAL_INVALID"):
        BrowserSessionMaterial("https://egazette.gld.gov.hk", secret)


def test_session_material_and_transport_reject_direct_string_and_request_subclasses() -> None:
    """Every local session public boundary rejects values with altered runtime string behavior."""
    request = _request()
    with pytest.raises(ValueError, match="GLD_SESSION_MATERIAL_INVALID"):
        BrowserSessionMaterial(_StringSubclass("https://egazette.gld.gov.hk"), _SESSION_SECRET)
    with pytest.raises(TypeError, match="GldSessionRequest"):
        _call(
            _transport(
                ScriptedGldBrowser(_material()), InMemoryProtectedSessionStore(), _policy(request)
            ).establish,
            object(),
        )


def test_session_establishment_reads_the_registered_profile_without_enabling_an_endpoint() -> None:
    """The adapter consumes only the checked-in GLD binding and leaves endpoint state inert."""
    request = _request()
    before = load_hk_legislation_source_register()
    store = InMemoryProtectedSessionStore()

    _transport(ScriptedGldBrowser(_material()), store, _policy(request)).establish(request)

    after = load_hk_legislation_source_register()
    before_enabled = {
        endpoint.endpoint_id: endpoint.enabled
        for endpoint in before.endpoints
        if endpoint.source_id == _SOURCE_ID
    }
    after_enabled = {
        endpoint.endpoint_id: endpoint.enabled
        for endpoint in after.endpoints
        if endpoint.source_id == _SOURCE_ID
    }
    assert before_enabled == after_enabled


def test_contract_changed_runner_failure_is_normalized_without_storing_or_leaking() -> None:
    """A changed challenge is a closed code, not a stored secret or exception detail."""
    request = _request()
    store = InMemoryProtectedSessionStore()
    error = GldSessionError("GLD_CHALLENGE_CONTRACT_CHANGED")

    with pytest.raises(GldSessionError, match="GLD_CHALLENGE_CONTRACT_CHANGED") as raised:
        _transport(ScriptedGldBrowser(error), store, _policy(request)).establish(request)

    assert "secret-cookie" not in str(raised.value)
    assert store.put_calls == []


def test_runner_exception_is_normalized_and_does_not_create_a_session() -> None:
    """Unexpected browser failures cannot create a protected session record."""
    request = _request()
    store = InMemoryProtectedSessionStore()

    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED") as raised:
        _transport(
            ScriptedGldBrowser(RuntimeError("secret-cookie")), store, _policy(request)
        ).establish(request)

    assert store.put_calls == []
    assert raised.value.__cause__ is None
    assert "secret-cookie" not in repr(raised.value)


def test_transport_normalizes_custom_browser_exception_without_cause_or_context() -> None:
    """A non-standard browser seam error cannot retain secret text in exception chaining."""
    request = _request()

    class SecretBrowserError(Exception):
        """A custom ordinary exception that must not escape this capability boundary."""

    store = InMemoryProtectedSessionStore()
    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED") as raised:
        _transport(
            ScriptedGldBrowser(SecretBrowserError("secret-browser-detail")), store, _policy(request)
        ).establish(request)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "secret-browser-detail" not in repr(raised.value)
    assert store.put_calls == []


def test_store_failure_preserves_material_when_rollback_is_unproved() -> None:
    """A failed store write cannot clean material while exact rollback proof is unavailable."""
    request = _request()
    cleaned: list[str] = []
    store = InMemoryProtectedSessionStore(put_error=RuntimeError("sealed-store-failed"))

    with pytest.raises(GldSessionError, match="GLD_SESSION_ROLLBACK_UNPROVED"):
        _transport(
            ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request)
        ).establish(request)

    assert cleaned == []
    assert store.delete_calls == ["gld-session-20260825"]
    assert not store.has("gld-session-20260825")


def test_store_create_exception_is_normalized_after_proved_rollback_without_context() -> None:
    """A store create failure cannot retain its secret-bearing exception chain."""
    request = _request()

    class SecretCreateError(Exception):
        """A custom store error whose detail must never cross the transport boundary."""

    class RollbackProvingStore(InMemoryProtectedSessionStore):
        def delete(self, session_id: str) -> bool:
            self.delete_calls.append(session_id)
            self._entries.pop(session_id, None)
            return True

    store = RollbackProvingStore(put_error=SecretCreateError("secret-create-detail"))
    with pytest.raises(GldSessionError, match="GLD_SESSION_STORE_FAILED") as raised:
        _transport(ScriptedGldBrowser(_material()), store, _policy(request)).establish(request)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "secret-create-detail" not in repr(raised.value)
    assert store.delete_calls == ["gld-session-20260825"]


def test_store_requires_atomic_create_acknowledgement_and_proved_rollback() -> None:
    """A store may not report a session unless create and failure rollback are both proved."""
    request = _request()
    cleaned: list[str] = []

    class FalseCreateStore(InMemoryProtectedSessionStore):
        def put(self, session_id: str, material: BrowserSessionMaterial, expires_at: str) -> bool:
            super().put(session_id, material, expires_at)
            return False

        def delete(self, session_id: str) -> bool:
            super().delete(session_id)
            return False

    store = FalseCreateStore()
    with pytest.raises(GldSessionError, match="GLD_SESSION_ROLLBACK_UNPROVED"):
        _transport(
            ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request)
        ).establish(request)
    assert cleaned == []
    assert store.delete_calls == ["gld-session-20260825"]


def test_expired_after_browser_work_cannot_return_a_grant() -> None:
    """Established and expiry timestamps begin only after browser success and remain positive."""
    request = _request()
    moments = iter(
        (
            _NOW,
            _NOW.replace(minute=5),
        )
    )
    store = InMemoryProtectedSessionStore()
    transport = LocalGldSessionTransport(
        ScriptedGldBrowser(_material()),
        store,
        _policy(request, session_ttl_seconds=1),
        clock=lambda: next(moments),
        session_id_factory=lambda: "gld-session-20260825",
    )
    with pytest.raises(GldSessionError, match="GLD_SESSION_TTL_EXPIRED"):
        transport.establish(request)
    assert store.delete_calls == ["gld-session-20260825"]


def test_wrong_material_origin_cleans_up_and_never_reaches_the_store() -> None:
    """A runner cannot supply cross-host material to the protected session store."""
    request = _request()
    cleaned: list[str] = []
    store = InMemoryProtectedSessionStore()

    with pytest.raises(GldSessionError, match="GLD_SESSION_HOST_MISMATCH"):
        _transport(
            ScriptedGldBrowser(_material(origin="https://outside.invalid", cleaned=cleaned)),
            store,
            _policy(request),
        ).establish(request)

    assert cleaned == ["cleaned"]
    assert store.put_calls == []


def test_invalidate_exactly_removes_and_cleans_the_stored_material() -> None:
    """Exact invalidation deletes only the requested stored material and cleans it."""
    request = _request()
    cleaned: list[str] = []
    store = InMemoryProtectedSessionStore()
    transport = _transport(ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request))
    grant = transport.establish(request)

    transport.invalidate(grant.session_id)

    assert store.delete_calls == [grant.session_id]
    assert not store.has(grant.session_id)
    assert cleaned == ["cleaned"]
    with pytest.raises(TypeError, match="session_id"):
        transport.invalidate(_StringSubclass(grant.session_id))


def test_invalidation_store_failure_preserves_material_and_is_normalized() -> None:
    """An unproved deletion retains material and returns only the fixed failure code."""
    request = _request()
    cleaned: list[str] = []
    store = InMemoryProtectedSessionStore(delete_error=RuntimeError("delete-failed"))
    transport = _transport(ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request))
    grant = transport.establish(request)

    with pytest.raises(GldSessionError, match="GLD_SESSION_INVALIDATION_FAILED"):
        transport.invalidate(grant.session_id)

    assert cleaned == []
    assert store.delete_calls == [grant.session_id]


def test_invalidation_delete_exception_preserves_retained_material_without_cleanup() -> None:
    """Unproved deletion retains its protected material and must not invoke its cleanup callback."""
    request = _request()
    cleaned: list[str] = []

    class RetainingFailureStore(InMemoryProtectedSessionStore):
        def delete(self, session_id: str) -> bool:
            self.delete_calls.append(session_id)
            delete_failed = "delete-failed-before-removal"
            raise RuntimeError(delete_failed)

    store = RetainingFailureStore()
    transport = _transport(ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request))
    grant = transport.establish(request)

    with pytest.raises(GldSessionError, match="GLD_SESSION_INVALIDATION_FAILED") as raised:
        transport.invalidate(grant.session_id)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert store.has(grant.session_id)
    assert cleaned == []


def test_invalidation_cleanup_failure_after_proved_delete_is_fail_visible() -> None:
    """A true delete cannot be reported as a fully invalidated session when cleanup fails."""
    request = _request()

    def cleanup_failure() -> None:
        cleanup_failed = "cleanup-secret-detail"
        raise RuntimeError(cleanup_failed)

    material = BrowserSessionMaterial(
        "https://egazette.gld.gov.hk", _SESSION_SECRET, cleanup_failure
    )
    store = InMemoryProtectedSessionStore()
    transport = _transport(ScriptedGldBrowser(material), store, _policy(request))
    grant = transport.establish(request)

    with pytest.raises(GldSessionError, match="GLD_SESSION_CLEANUP_FAILED") as raised:
        transport.invalidate(grant.session_id)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "cleanup-secret-detail" not in repr(raised.value)
    assert not store.has(grant.session_id)


def test_unproved_create_rollback_preserves_material_without_cleanup() -> None:
    """An unproved rollback leaves the exact material untouched because it may still be stored."""
    request = _request()
    cleaned: list[str] = []
    store = InMemoryProtectedSessionStore(put_error=RuntimeError("put-failed-before-removal"))

    with pytest.raises(GldSessionError, match="GLD_SESSION_ROLLBACK_UNPROVED"):
        _transport(
            ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request)
        ).establish(request)

    assert store.delete_calls == ["gld-session-20260825"]
    assert cleaned == []


def test_concrete_runner_uses_only_the_fixed_unattended_local_experiment_order() -> None:
    """The concrete runner follows the three fixed local experiments with their own limits."""
    request = _request()
    policy = _policy(request)
    attempt = ScriptedPatchrightAttempt(
        (
            GldSessionError("GLD_CHALLENGE_UNRESOLVED"),
            GldSessionError("GLD_CHALLENGE_UNRESOLVED"),
            _material(),
        )
    )
    runner = PatchrightGldBrowserRunner(policy, attempt=attempt)

    material = runner.establish(
        start_url=_START_URL,
        allowed_hosts=("egazette.gld.gov.hk",),
        deadline_seconds=45,
    )

    assert material.origin == "https://egazette.gld.gov.hk"
    assert [call[0] for call in attempt.calls] == list(policy.experiment_order)
    assert [call[3] for call in attempt.calls] == [10, 15, 20]
    assert all(
        call[1] == _START_URL and call[2] == ("egazette.gld.gov.hk",) for call in attempt.calls
    )


def test_concrete_runner_rejects_user_url_and_contract_change_without_fallback() -> None:
    """User navigation and contract change cannot select an alternate browser path."""
    request = _request()
    policy = _policy(request)
    attempt = ScriptedPatchrightAttempt((GldSessionError("GLD_CHALLENGE_CONTRACT_CHANGED"),))
    runner = PatchrightGldBrowserRunner(policy, attempt=attempt)

    with pytest.raises(GldSessionError, match="GLD_SESSION_NAVIGATION_INVALID"):
        runner.establish(
            start_url="https://outside.invalid/",
            allowed_hosts=("outside.invalid",),
            deadline_seconds=45,
        )
    assert attempt.calls == []
    with pytest.raises(GldSessionError, match="GLD_CHALLENGE_CONTRACT_CHANGED"):
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )
    assert [call[0] for call in attempt.calls] == [GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS]


def test_concrete_patchright_attempt_policy_denies_browser_escape_hatches() -> None:
    """Concrete Patchright compartment policy denies every non-local escape hatch."""
    request = _request()
    runner = PatchrightGldBrowserRunner(
        _policy(request), attempt=ScriptedPatchrightAttempt((_material(),))
    )
    attempt_policy = runner.attempt_policies[0]

    assert type(attempt_policy) is PatchrightGldAttemptPolicy
    assert attempt_policy.experiment is GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS
    assert attempt_policy.headless is True
    assert attempt_policy.accept_downloads is False
    assert attempt_policy.allow_popups is False
    assert attempt_policy.allow_extensions is False
    assert attempt_policy.allow_browser_credentials is False
    assert attempt_policy.allow_cross_host_requests is False
    assert attempt_policy.request_is_allowed("GET", _START_URL, "document") is True
    assert attempt_policy.request_is_allowed("GET", "https://outside.invalid/", "document") is False
    assert (
        attempt_policy.request_is_allowed(
            "GET", "https://user:secret@egazette.gld.gov.hk/", "document"
        )
        is False
    )
    assert attempt_policy.request_is_allowed("POST", _START_URL, "xhr") is False
    assert attempt_policy.request_is_allowed("GET", _START_URL, "websocket") is False


def test_concrete_runner_reports_unresolved_after_all_three_local_attempts() -> None:
    """Three unresolved local experiments end closed without manual or remote fallback."""
    request = _request()
    policy = _policy(request)
    attempt = ScriptedPatchrightAttempt((GldSessionError("GLD_CHALLENGE_UNRESOLVED"),) * 3)

    with pytest.raises(GldSessionError, match="GLD_CHALLENGE_UNRESOLVED"):
        PatchrightGldBrowserRunner(policy, attempt=attempt).establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )

    assert len(attempt.calls) == len(policy.experiment_order)


def test_runner_rejects_a_slow_full_attempt_lifecycle_and_cleans_material() -> None:
    """A deadline covers startup, browser work, and teardown-visible return, not goto metadata."""
    request = _request()
    cleaned: list[str] = []
    moments = iter((0.0, 0.0, 11.0, 11.0))
    runner = PatchrightGldBrowserRunner(
        _policy(request),
        attempt=ScriptedPatchrightAttempt((_material(cleaned=cleaned),)),
        monotonic_clock=lambda: next(moments),
    )
    with pytest.raises(GldSessionError, match="GLD_SESSION_DEADLINE_EXCEEDED"):
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )
    assert cleaned == ["cleaned"]


def test_challenge_contract_filters_only_the_admitted_origin_cookie_after_exact_probe() -> None:
    """An unrelated cookie, status page, or missing authenticated probe cannot mint a grant."""
    contract = _challenge_contract()
    valid = GldBrowserObservation(
        200,
        _START_URL,
        (GldBrowserCookie("gld_session", "proved", "egazette.gld.gov.hk", "/"),),
        200,
        _START_URL,
    )
    material = contract.select_material(valid, "egazette.gld.gov.hk")
    assert material.session_secret == "proved"
    assert "unrelated" not in material.session_secret
    for hostile in (
        GldBrowserObservation(200, _START_URL, (), 200, _START_URL),
        GldBrowserObservation(
            200,
            _START_URL,
            (GldBrowserCookie("unrelated", "unrelated", "egazette.gld.gov.hk", "/"),),
            200,
            _START_URL,
        ),
        GldBrowserObservation(
            403,
            _START_URL,
            (GldBrowserCookie("gld_session", "proved", "egazette.gld.gov.hk", "/"),),
            200,
            _START_URL,
        ),
        GldBrowserObservation(
            200,
            _START_URL,
            (GldBrowserCookie("gld_session", "proved", "egazette.gld.gov.hk", "/"),),
            403,
            _START_URL,
        ),
    ):
        with pytest.raises(GldSessionError, match="GLD_CHALLENGE_CONTRACT_CHANGED"):
            contract.select_material(hostile, "egazette.gld.gov.hk")


def test_policy_fingerprint_names_the_injected_challenge_contract_and_closed_route_set() -> None:
    """A contract/state-selection/path revision invalidates the local browser policy."""
    request = _request()
    first = _policy(request)
    changed = GldChallengeSessionContract(
        "TEST-GLD-CHALLENGE-2",
        "/en/list-of-gazette",
        "gld_session",
        "/",
        200,
        "/en/list-of-gazette",
        200,
    )
    second = RenderedBrowserPolicy.for_request(request, challenge_contract=changed)
    assert first.policy_fingerprint != second.policy_fingerprint
    contract = first.challenge_contract
    assert type(contract) is GldChallengeSessionContract
    assert contract.route_is_allowed("GET", _START_URL) is True
    assert (
        contract.route_is_allowed("GET", "https://egazette.gld.gov.hk/arbitrary/path?anything=1")
        is False
    )


def test_policy_without_an_admitted_challenge_contract_fails_closed() -> None:
    """Task 2 cannot invent an authentic GLD challenge shape before Task 7 admission."""
    request = _request()
    policy = RenderedBrowserPolicy.for_request(request, challenge_contract=None)
    runner = PatchrightGldBrowserRunner(policy, attempt=ScriptedPatchrightAttempt((_material(),)))
    with pytest.raises(GldSessionError, match="GLD_CHALLENGE_CONTRACT_CHANGED"):
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=60,
        )


def test_transport_without_an_admitted_challenge_contract_cannot_store_or_grant() -> None:
    """A scripted seam cannot bypass the final challenge-contract admission boundary."""
    request = _request()
    policy = RenderedBrowserPolicy.for_request(request, challenge_contract=None)
    store = InMemoryProtectedSessionStore()
    transport = LocalGldSessionTransport(
        ScriptedGldBrowser(_material(secret=_UNPROVED_SECRET)),
        store,
        policy,
        clock=lambda: _NOW,
        session_id_factory=lambda: "gld-session-20260825",
    )

    with pytest.raises(GldSessionError, match="GLD_CHALLENGE_CONTRACT_CHANGED"):
        transport.establish(request)

    assert store.put_calls == []
    assert not store.has("gld-session-20260825")


def test_invalidation_requires_exact_true_delete_and_keeps_retained_material_intact() -> None:
    """A false deletion acknowledgement cannot be misreported as invalidation success."""
    request = _request()
    cleaned: list[str] = []

    class FalseDeleteStore(InMemoryProtectedSessionStore):
        def delete(self, session_id: str) -> bool:
            self.delete_calls.append(session_id)
            return False

    store = FalseDeleteStore()
    transport = _transport(ScriptedGldBrowser(_material(cleaned=cleaned)), store, _policy(request))
    grant = transport.establish(request)

    with pytest.raises(GldSessionError, match="GLD_SESSION_INVALIDATION_FAILED") as raised:
        transport.invalidate(grant.session_id)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert store.has(grant.session_id)
    assert cleaned == []


def test_invalidation_normalizes_a_custom_store_exception_without_secret_context() -> None:
    """Every ordinary protected-store exception becomes the fixed invalidation failure."""
    request = _request()

    class SecretStoreError(Exception):
        """A hostile store error with an otherwise secret-bearing detail."""

    class CustomFailureStore(InMemoryProtectedSessionStore):
        def delete(self, session_id: str) -> bool:
            self.delete_calls.append(session_id)
            raise SecretStoreError(_SECRET_STORE_DETAIL)

    store = CustomFailureStore()
    transport = _transport(ScriptedGldBrowser(_material()), store, _policy(request))
    grant = transport.establish(request)

    with pytest.raises(GldSessionError, match="GLD_SESSION_INVALIDATION_FAILED") as raised:
        transport.invalidate(grant.session_id)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "secret-store-detail" not in repr(raised.value)


def test_runner_rejects_late_unresolved_attempts_before_trying_the_next_experiment() -> None:
    """Unresolved outcomes consume the same per-attempt and total deadline budget as success."""
    request = _request()
    moments = iter((0.0, 0.0, 11.0, 11.0))
    attempt = ScriptedPatchrightAttempt((GldSessionError("GLD_CHALLENGE_UNRESOLVED"),) * 3)
    runner = PatchrightGldBrowserRunner(
        _policy(request), attempt=attempt, monotonic_clock=lambda: next(moments)
    )

    with pytest.raises(GldSessionError, match="GLD_SESSION_DEADLINE_EXCEEDED"):
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )

    assert len(attempt.calls) == 1


def test_runner_normalizes_custom_attempt_exception_without_cause_or_context() -> None:
    """Injected ordinary browser exceptions cannot bypass the closed attempt result set."""
    request = _request()

    class SecretAttemptError(Exception):
        """A custom attempt failure with text that must not cross the runner boundary."""

    runner = PatchrightGldBrowserRunner(
        _policy(request), attempt=ScriptedPatchrightAttempt((SecretAttemptError("secret-attempt"),))
    )
    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED") as raised:
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "secret-attempt" not in repr(raised.value)


def test_file_store_is_restart_safe_mode_protected_and_tamper_closed(tmp_path: Path) -> None:
    """A new store instance can invalidate the same minimal protected session."""
    root = tmp_path / "gld-sessions"
    store = FileProtectedSessionStore(root.resolve())
    material = _material()
    assert store.put("gld-restart-proof", material, "2026-08-25T12:05:00+00:00") is True
    path = root / "gld-restart-proof.json"
    assert root.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    assert FileProtectedSessionStore(root.resolve()).get("gld-restart-proof") == material

    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(GldSessionError, match="GLD_SESSION_STORE_FAILED"):
        FileProtectedSessionStore(root.resolve()).get("gld-restart-proof")
    assert FileProtectedSessionStore(root.resolve()).delete("gld-restart-proof") is True


def test_concrete_patchright_transport_composes_without_starting_network(tmp_path: Path) -> None:
    """Supplying the observed challenge contract is enough to build the local runtime."""
    transport = build_patchright_gld_session_transport(
        _request(), _challenge_contract(), (tmp_path / "sessions").resolve()
    )
    assert isinstance(transport, LocalGldSessionTransport)
    assert (tmp_path / "sessions").stat().st_mode & 0o777 == 0o700


def test_child_ipc_rejects_secret_bearing_failure_ready_and_duplicate_key_shapes() -> None:
    """READY and failure IPC are exact code-only records; duplicate JSON keys are malformed."""
    hostile_payloads = (
        b'{"code":"READY","origin":"https://egazette.gld.gov.hk","session_secret":"secret"}',
        b'{"code":"GLD_CHALLENGE_UNRESOLVED","origin":"https://egazette.gld.gov.hk","session_secret":"secret"}',
        b'{"code":"READY","code":"SUCCESS"}',
        b'{"code":"SUCCESS","origin":"https://egazette.gld.gov.hk","session_secret":"secret","extra":true}',
    )

    for payload in hostile_payloads:
        with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED") as raised:
            gld_session.child_result_from_payload(payload)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert "secret" not in repr(raised.value)


def test_get_only_route_policy_rejects_head_consistently() -> None:
    """The closed browser route set is GET-only everywhere, including its public predicate."""
    request = _request()
    policy = PatchrightGldBrowserRunner(
        _policy(request), attempt=ScriptedPatchrightAttempt((_material(),))
    ).attempt_policies[0]

    assert policy.request_is_allowed("GET", _START_URL, "document") is True
    assert policy.request_is_allowed("HEAD", _START_URL, "document") is False
    assert _challenge_contract().route_is_allowed("HEAD", _START_URL) is False


def test_no_public_unbound_patchright_attempt_can_accept_a_caller_url() -> None:
    """Only the request-bound runner owns concrete browser experiment construction."""
    assert not hasattr(gld_session, "PatchrightGldAttempt")


def test_default_concrete_path_uses_one_bound_child_supervisor_request() -> None:
    """The default path transfers only exact policy-bound request facts to a local child."""
    request = _request()
    supervisor = ScriptedConcreteSupervisor(_material())
    runner = PatchrightGldBrowserRunner(_policy(request), supervisor=supervisor)
    material = runner.establish(
        start_url=_START_URL,
        allowed_hosts=("egazette.gld.gov.hk",),
        deadline_seconds=45,
    )
    assert material.origin == "https://egazette.gld.gov.hk"
    assert len(supervisor.calls) == 1
    child_request = supervisor.calls[0]
    assert _START_URL in repr(child_request)
    assert "EPHEMERAL_CLEAN_HEADLESS" in repr(child_request)


def test_default_supervisor_rejects_malformed_child_result_without_secret_leakage() -> None:
    """A malformed local IPC result cannot produce a material or disclose its payload."""
    request = _request()
    supervisor = ScriptedConcreteSupervisor(object())
    runner = PatchrightGldBrowserRunner(_policy(request), supervisor=supervisor)
    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED") as raised:
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )
    assert raised.value.__cause__ is None


def test_child_timeout_termination_escalates_to_kill_and_joins() -> None:
    """A child that ignores terminate is killed and joined; no ambient browser can remain alive."""

    class IgnoringTerminateProcess:
        def __init__(self) -> None:
            self.alive = True
            self.calls: list[str] = []

        def terminate(self) -> None:
            self.calls.append("terminate")

        def join(self, timeout: float | None = None) -> None:
            self.calls.append(f"join:{timeout}")

        def kill(self) -> None:
            self.calls.append("kill")
            self.alive = False

        def is_alive(self) -> bool:
            return self.alive

    process = IgnoringTerminateProcess()
    gld_session.terminate_child(process)
    assert process.calls == ["terminate", "join:1", "kill", "join:1"]


def test_success_shutdown_sends_term_then_kill_before_reaping_the_anchored_leader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Success shutdown uses TERM then KILL even when the direct leader exits on TERM."""

    class ExitedLeader:
        pid = 12345

        def join(self, timeout: float | None = None) -> None:
            assert timeout == 1

        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:
            raise AssertionError(_GROUP_TERMINATION_MESSAGE)

        def kill(self) -> None:
            raise AssertionError(_GROUP_KILL_MESSAGE)

    signals: list[tuple[int, int]] = []

    def capture_signal(pid: int, signal: int) -> None:
        signals.append((pid, signal))

    def no_grace() -> None:
        return None

    monkeypatch.setattr(gld_session, "killpg", capture_signal)
    monkeypatch.setattr(gld_session, "_unreaped_group_grace", no_grace)

    gld_session.terminate_child_group(ExitedLeader())

    assert signals == [(12345, 15), (12345, 9)]


def test_successful_terminal_payload_shuts_down_the_owned_group_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid child success cannot return while its owned browser group may still be alive."""
    request = _request()
    runner = PatchrightGldBrowserRunner(
        _policy(request), attempt=ScriptedPatchrightAttempt((_material(),))
    )
    policy = runner.attempt_policies[0]
    request_type = getattr(gld_session, "_GldChildRequest")
    child_request = request_type(
        GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS,
        _START_URL,
        policy,
        "/tmp/asklegal-gld-child-test",
    )

    class Receive:
        def __init__(self) -> None:
            self.payloads = iter(
                (
                    b'{"code":"READY"}',
                    b'{"code":"SUCCESS","observed_request_count":0,"origin":"https://egazette.gld.gov.hk","session_secret":"proved"}',
                )
            )

        def poll(self, timeout: float) -> bool:
            assert timeout > 0
            return True

        def recv_bytes(self, maximum_length: int) -> bytes:
            assert maximum_length == 65_536
            return next(self.payloads)

        def close(self) -> None:
            return None

    class Send:
        def close(self) -> None:
            return None

    class FakeProcess:
        pid = 54321

        def start(self) -> None:
            return None

        def terminate(self) -> None:
            raise AssertionError(_GROUP_TERMINATION_MESSAGE)

        def kill(self) -> None:
            raise AssertionError(_GROUP_KILL_MESSAGE)

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    process = FakeProcess()

    class Context:
        def Pipe(self, *, duplex: bool) -> tuple[Receive, Send]:
            assert duplex is False
            return Receive(), Send()

        def Process(self, *, target: object, args: tuple[object, ...]) -> FakeProcess:
            assert callable(target)
            assert len(args) == 3
            return process

        def Event(self) -> object:
            return object()

    shutdown_calls: list[FakeProcess] = []

    def fake_context(_name: str) -> Context:
        return Context()

    def record_shutdown(child: FakeProcess) -> None:
        shutdown_calls.append(child)

    monkeypatch.setattr(gld_session, "get_context", fake_context)
    monkeypatch.setattr(gld_session, "monotonic", lambda: 0.0)
    monkeypatch.setattr(gld_session, "terminate_child_group", record_shutdown)

    supervisor_type = getattr(gld_session, "_LocalPatchrightSupervisor")
    material = supervisor_type().establish(child_request)

    assert type(material) is BrowserSessionMaterial
    assert shutdown_calls == [process]


def test_supervisor_does_not_repeat_group_termination_when_shutdown_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed group shutdown is single-entry, so finalization cannot signal twice."""
    request = _request()
    policy = PatchrightGldBrowserRunner(
        _policy(request), attempt=ScriptedPatchrightAttempt((_material(),))
    ).attempt_policies[0]
    request_type = getattr(gld_session, "_GldChildRequest")
    child_request = request_type(
        GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS,
        _START_URL,
        policy,
        "/tmp/asklegal-gld-child-test",
    )

    class Receive:
        def __init__(self) -> None:
            self.payloads = iter((b'{"code":"READY"}', b'{"code":"GLD_CHALLENGE_UNRESOLVED"}'))

        def poll(self, timeout: float) -> bool:
            assert timeout > 0
            return True

        def recv_bytes(self, maximum_length: int) -> bytes:
            assert maximum_length == 65_536
            return next(self.payloads)

        def close(self) -> None:
            return None

    class Send:
        def close(self) -> None:
            return None

    class FakeProcess:
        pid = 32123

        def start(self) -> None:
            return None

        def terminate(self) -> None:
            raise AssertionError(_GROUP_TERMINATION_MESSAGE)

        def kill(self) -> None:
            raise AssertionError(_GROUP_KILL_MESSAGE)

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    class Context:
        def Pipe(self, *, duplex: bool) -> tuple[Receive, Send]:
            assert duplex is False
            return Receive(), Send()

        def Process(self, *, target: object, args: tuple[object, ...]) -> FakeProcess:
            assert callable(target)
            assert len(args) == 3
            return FakeProcess()

        def Event(self) -> object:
            return object()

    shutdown_calls: list[object] = []

    def failed_shutdown(child: FakeProcess) -> None:
        shutdown_calls.append(child)
        raise GldSessionError(_CLEANUP_FAILURE_CODE)

    def fake_context(_name: str) -> Context:
        return Context()

    monkeypatch.setattr(gld_session, "get_context", fake_context)
    monkeypatch.setattr(gld_session, "monotonic", lambda: 0.0)
    monkeypatch.setattr(gld_session, "terminate_child_group", failed_shutdown)

    with pytest.raises(GldSessionError, match="GLD_SESSION_CLEANUP_FAILED"):
        getattr(gld_session, "_LocalPatchrightSupervisor")().establish(child_request)

    assert len(shutdown_calls) == 1


@pytest.mark.parametrize("outcome", [_material(), RuntimeError("secret-supervisor-error")])
def test_attempt_cleanup_failure_is_closed_on_success_and_error_paths(
    monkeypatch: pytest.MonkeyPatch, outcome: BrowserSessionMaterial | Exception
) -> None:
    """A retained child root cannot be hidden behind success or a prior supervisor failure."""
    request = _request()
    roots: list[Path] = []
    original_cleanup = gld_session.cleanup_attempt_root
    cleaned: list[str] = []
    material = (
        _material(cleaned=cleaned) if isinstance(outcome, BrowserSessionMaterial) else outcome
    )

    class RootRecordingSupervisor:
        def establish(self, request: object) -> object:
            roots.append(Path(request.__getattribute__("attempt_root")))
            return material if isinstance(material, BrowserSessionMaterial) else (_raise(material))

    def failed_cleanup(attempt_root: object) -> None:
        assert isinstance(attempt_root, Path)
        raise GldSessionError(_CLEANUP_FAILURE_CODE)

    monkeypatch.setattr(gld_session, "cleanup_attempt_root", failed_cleanup)
    runner = PatchrightGldBrowserRunner(_policy(request), supervisor=RootRecordingSupervisor())
    try:
        with pytest.raises(GldSessionError, match="GLD_SESSION_CLEANUP_FAILED") as raised:
            runner.establish(
                start_url=_START_URL,
                allowed_hosts=("egazette.gld.gov.hk",),
                deadline_seconds=45,
            )
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert "secret-supervisor-error" not in repr(raised.value)
    finally:
        for root in roots:
            original_cleanup(root)
    if isinstance(material, BrowserSessionMaterial):
        assert cleaned == ["cleaned"]


def test_parent_revalidates_oversized_or_failed_child_ipc_without_leaking_secret() -> None:
    """Bounded local IPC accepts only the exact safe success shape."""
    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED"):
        gld_session.child_material_from_payload(b"x" * 65_537, "egazette.gld.gov.hk")
    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED") as raised:
        gld_session.child_material_from_payload(b'{"status":"FAILED"}', "egazette.gld.gov.hk")
    assert "secret" not in repr(raised.value)


def test_child_ipc_preserves_only_closed_unresolved_and_contract_changed_codes() -> None:
    """Unresolved advances experiments while contract change remains an immediate closed abort."""
    assert gld_session.child_result_from_payload(b'{"code":"GLD_CHALLENGE_UNRESOLVED"}') == (
        "GLD_CHALLENGE_UNRESOLVED"
    )
    assert gld_session.child_result_from_payload(b'{"code":"GLD_CHALLENGE_CONTRACT_CHANGED"}') == (
        "GLD_CHALLENGE_CONTRACT_CHANGED"
    )
    with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED"):
        gld_session.child_result_from_payload(b'{"code":"secret-cookie"}')


def test_parent_owned_attempt_root_is_removed_after_group_escalation() -> None:
    """A killed child cannot leave its exact parent-created scratch root behind."""
    attempt_root = Path(mkdtemp(prefix="asklegal-gld-child-"))
    gld_session.cleanup_attempt_root(attempt_root)
    assert not attempt_root.exists()


def test_child_pipe_keeps_ready_channel_open_until_terminal_payload() -> None:
    """A READY handshake must not close the only child-to-parent terminal-result channel."""

    class Pipe:
        def __init__(self) -> None:
            self.payloads: list[bytes] = []
            self.closed = False

        def send_bytes(self, payload: bytes) -> None:
            if self.closed:
                closed = "closed"
                raise RuntimeError(closed)
            self.payloads.append(payload)

        def close(self) -> None:
            self.closed = True

    pipe = Pipe()
    gld_session.send_child_payload(pipe, b'{"code":"READY"}', terminal=False)
    gld_session.send_child_payload(pipe, b'{"code":"SUCCESS"}', terminal=True)
    assert pipe.payloads == [b'{"code":"READY"}', b'{"code":"SUCCESS"}']
    assert pipe.closed is True


def test_terminal_hold_is_bounded_clears_child_secret_state_and_self_kills_on_parent_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing parent cannot leave a terminal child, secret, or owned descendants indefinitely."""
    request = _request()
    policy = PatchrightGldBrowserRunner(
        _policy(request), attempt=ScriptedPatchrightAttempt((_material(),))
    ).attempt_policies[0]
    child_request = getattr(gld_session, "_GldChildRequest")(
        GldBrowserExperiment.EPHEMERAL_CLEAN_HEADLESS,
        _START_URL,
        policy,
        "/tmp/asklegal-gld-child-test",
    )

    class Send:
        def __init__(self) -> None:
            self.payloads: list[bytes] = []
            self.closed = False

        def send_bytes(self, payload: bytes) -> None:
            self.payloads.append(payload)

        def close(self) -> None:
            self.closed = True

    class Hold:
        def __init__(self) -> None:
            self.timeouts: list[float | None] = []

        def wait(self, timeout: float | None = None) -> bool:
            self.timeouts.append(timeout)
            return False

    class Compartment:
        def establish(
            self, *, policy: PatchrightGldAttemptPolicy, start_url: str
        ) -> BrowserSessionMaterial:
            assert policy is child_request.policy
            assert start_url == _START_URL
            return _material(secret=_PARENT_LOSS_SECRET)

    self_kills: list[str] = []
    send = Send()
    hold = Hold()

    def concrete_compartment(_experiment: GldBrowserExperiment) -> Compartment:
        return Compartment()

    monkeypatch.setattr(gld_session, "setsid", lambda: None)
    monkeypatch.setattr(gld_session, "_concrete_compartment_for", concrete_compartment)

    getattr(gld_session, "_child_patchright_attempt")(
        send,
        child_request,
        hold,
        lambda: self_kills.append("owned-group-killed"),
    )

    assert hold.timeouts == [getattr(gld_session, "_TERMINAL_HOLD_SECONDS")]
    assert self_kills == ["owned-group-killed"]
    assert send.closed is True
    assert _PARENT_LOSS_SECRET.encode("utf-8") in send.payloads[-1]
    assert getattr(gld_session, "_discard_terminal_state")(
        _material(secret=_PARENT_LOSS_SECRET), _PARENT_LOSS_SECRET.encode("utf-8")
    ) == (None, b"")


@pytest.mark.parametrize("outcome", [_material(), RuntimeError("supervisor-failed")])
def test_attempt_creator_removes_its_exact_root_after_supervisor_success_or_raise(
    outcome: BrowserSessionMaterial | Exception,
) -> None:
    """The component that creates the child root cleans it even when a seam fails."""
    request = _request()

    class RootRecordingSupervisor:
        def __init__(self) -> None:
            self.root: Path | None = None

        def establish(self, request: object) -> object:
            self.root = Path(request.__getattribute__("attempt_root"))
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    supervisor = RootRecordingSupervisor()
    runner = PatchrightGldBrowserRunner(_policy(request), supervisor=supervisor)
    if isinstance(outcome, Exception):
        with pytest.raises(GldSessionError, match="GLD_SESSION_RUNNER_FAILED"):
            runner.establish(
                start_url=_START_URL,
                allowed_hosts=("egazette.gld.gov.hk",),
                deadline_seconds=45,
            )
    else:
        runner.establish(
            start_url=_START_URL,
            allowed_hosts=("egazette.gld.gov.hk",),
            deadline_seconds=45,
        )
    assert supervisor.root is not None
    assert not supervisor.root.exists()
