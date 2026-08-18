"""Complete bilingual official-inventory capture over exact endpoint contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from .model import HttpMethod, exact_text
from .official import OfficialSourceState
from .official_http import (
    OfficialFetchCode,
    OfficialFetchRequest,
    OfficialFetchResult,
    OfficialHttpConnector,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class OfficialInventoryCode(StrEnum):
    """Closed outcomes for one required complete-inventory member set."""

    COMPLETE_CAPTURED = "COMPLETE_CAPTURED"
    COMPLETE_CAPTURED_IDENTICAL = "COMPLETE_CAPTURED_IDENTICAL"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"


@dataclass(frozen=True, slots=True)
class OfficialInventoryRequest:
    """Exact source/member versions and optional prior member fingerprints."""

    source_id: str
    endpoint_versions: tuple[tuple[str, str], ...]
    prior_fingerprints: tuple[tuple[str, str], ...]
    timeout_seconds: int

    def __post_init__(self) -> None:
        exact_text(self.source_id, "source_id")
        _pairs(self.endpoint_versions, "endpoint_versions", fingerprint=False)
        _pairs(self.prior_fingerprints, "prior_fingerprints", fingerprint=True)
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be an exact integer from 1 through 120")


@dataclass(frozen=True, slots=True)
class OfficialInventoryResult:
    """All required member results with an aggregate only for complete capture."""

    code: OfficialInventoryCode
    source_id: str
    member_results: tuple[OfficialFetchResult, ...]
    inventory_fingerprint: str | None
    failure_code: str | None

    def __post_init__(self) -> None:
        if type(self.code) is not OfficialInventoryCode:
            raise TypeError("code must be an exact OfficialInventoryCode")
        exact_text(self.source_id, "source_id")
        if type(self.member_results) is not tuple or not self.member_results:
            raise TypeError("member_results must be one non-empty exact tuple")
        if any(item.source_id != self.source_id for item in self.member_results):
            raise ValueError("member results must belong to their source")
        if (
            self.inventory_fingerprint is not None
            and _SHA256.fullmatch(self.inventory_fingerprint) is None
        ):
            raise ValueError("inventory_fingerprint must be an exact SHA-256 or None")
        if self.failure_code is not None:
            exact_text(self.failure_code, "failure_code")
        complete = self.code in {
            OfficialInventoryCode.COMPLETE_CAPTURED,
            OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL,
        }
        if complete != (self.inventory_fingerprint is not None):
            raise ValueError("only complete capture may have an inventory fingerprint")
        if complete == (self.failure_code is not None):
            raise ValueError("complete and failed inventory result fields disagree")


class OfficialInventoryConnector:
    """Capture every required member before reporting one complete inventory."""

    def __init__(self, connector: OfficialHttpConnector) -> None:
        """Bind the inventory operation to one exact official HTTP connector."""
        if type(connector) is not OfficialHttpConnector:
            raise TypeError("connector must be an exact OfficialHttpConnector")
        self.connector = connector

    def capture(self, request: OfficialInventoryRequest) -> OfficialInventoryResult:
        """Fetch all and only the exact required members in deterministic order."""
        if type(request) is not OfficialInventoryRequest:
            raise TypeError("request must be an exact OfficialInventoryRequest")
        source = next(
            (
                item
                for item in self.connector.register.sources
                if item.source_id == request.source_id
            ),
            None,
        )
        if source is None:
            raise LookupError("official inventory source is unavailable")
        if source.operational_state is not OfficialSourceState.CONFIGURED:
            raise PermissionError("official inventory source is not operationally configured")
        endpoints = {
            item.endpoint_id: item
            for item in self.connector.register.endpoints
            if item.source_id == request.source_id and item.complete_inventory_required
        }
        if not endpoints:
            raise ValueError("source declares no complete-inventory member set")
        expected_versions = tuple(
            sorted((item.endpoint_id, item.version) for item in endpoints.values())
        )
        if request.endpoint_versions != expected_versions:
            raise ValueError("request must bind the exact complete-inventory member versions")
        prior = dict(request.prior_fingerprints)
        if not set(prior).issubset(endpoints):
            raise ValueError("prior fingerprints must belong to required inventory members")
        member_results = tuple(
            self.connector.fetch(
                OfficialFetchRequest(
                    endpoint_id,
                    endpoint_version,
                    HttpMethod.GET,
                    prior.get(endpoint_id),
                    request.timeout_seconds,
                )
            )
            for endpoint_id, endpoint_version in expected_versions
        )
        failure = _inventory_failure(member_results)
        if failure is not None:
            code, failure_code = failure
            return OfficialInventoryResult(
                code,
                request.source_id,
                member_results,
                None,
                failure_code,
            )
        digest = sha256()
        for result in member_results:
            if result.fingerprint is None:
                raise AssertionError("successful member capture requires a fingerprint")
            for value in (result.endpoint_id, result.endpoint_version, result.fingerprint):
                digest.update(value.encode("utf-8"))
                digest.update(b"\x00")
        identical = all(
            result.code is OfficialFetchCode.CAPTURED_IDENTICAL for result in member_results
        )
        return OfficialInventoryResult(
            (
                OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL
                if identical
                else OfficialInventoryCode.COMPLETE_CAPTURED
            ),
            request.source_id,
            member_results,
            f"sha256:{digest.hexdigest()}",
            None,
        )


def _inventory_failure(
    results: tuple[OfficialFetchResult, ...],
) -> tuple[OfficialInventoryCode, str] | None:
    precedence = (
        (OfficialFetchCode.UNSAFE_RESPONSE, OfficialInventoryCode.UNSAFE_RESPONSE),
        (
            OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
            OfficialInventoryCode.SOURCE_CONTRACT_CHANGED,
        ),
        (OfficialFetchCode.SOURCE_UNAVAILABLE, OfficialInventoryCode.SOURCE_UNAVAILABLE),
    )
    for member_code, inventory_code in precedence:
        if any(item.code is member_code for item in results):
            return inventory_code, f"REQUIRED_MEMBER_{member_code.value}"
    if any(item.code is OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED for item in results):
        raise AssertionError("required inventory members cannot be discovery-only signals")
    return None


def _pairs(
    value: tuple[tuple[str, str], ...],
    field: str,
    *,
    fingerprint: bool,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field} must be an exact tuple")
    if any(type(item) is not tuple or len(item) != 2 for item in value):
        raise TypeError(f"{field} must contain exact string pairs")
    if any(type(key) is not str or type(item) is not str for key, item in value):
        raise TypeError(f"{field} must contain exact string pairs")
    if value != tuple(sorted(value)) or len({key for key, _ in value}) != len(value):
        raise ValueError(f"{field} must be unique and sorted")
    for key, item in value:
        exact_text(key, f"{field} key")
        if fingerprint:
            if _SHA256.fullmatch(item) is None:
                raise ValueError(f"{field} values must be exact SHA-256 fingerprints")
        else:
            exact_text(item, f"{field} value")
