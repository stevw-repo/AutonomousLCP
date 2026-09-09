"""Canonical local V1 adapter for the shared legal identity Register port."""

from __future__ import annotations

import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_management_register_ports.legal_identity import (
    IssuedLegalIdentity,
    IssuedSearchRecordIdentity,
    LegalIdentityKind,
    LegalIdentityRequest,
    SearchRecordIdentityRequest,
)

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_PREFIX = {
    LegalIdentityKind.LEGAL_ITEM: "lit",
    LegalIdentityKind.OFFICIAL_VERSION: "ofv",
    LegalIdentityKind.LEGAL_LOCATION: "loc",
    LegalIdentityKind.LEGAL_STATUS_EVENT: "lse",
    LegalIdentityKind.DECISION: "dec",
    LegalIdentityKind.ARTIFACT: "art",
    LegalIdentityKind.EVIDENCE: "evi",
    LegalIdentityKind.VALIDATION: "val",
    LegalIdentityKind.TRACEABILITY_LOOKUP: "rtl",
    LegalIdentityKind.TRACEABILITY_SHARD: "rts",
}


def _fail(code: str) -> Never:
    raise ValueError(code)


def _object(value: JsonValue | object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
    return parsed


class LocalLegalIdentityRegister:
    """Single-file canonical create-or-match prototype Register adapter."""

    def __init__(self, path: Path) -> None:
        """Bind one absolute, non-symlink retained Register file."""
        if not path.is_absolute() or path.is_symlink():
            _fail("LEGAL_IDENTITY_REGISTER_PATH_INVALID")
        self._path = path
        self._identities: dict[str, str] = {}
        self._records: dict[str, dict[str, JsonValue]] = {}
        if path.exists():
            if not path.is_file():
                _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
            value = parse_json_bytes(path.read_bytes(), max_bytes=8_388_608)
            if type(value) is not dict or canonicalize(value) != path.read_bytes():
                _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
            document = _object(value)
            if (
                frozenset(document)
                != frozenset({"schema_id", "schema_version", "identities", "search_records"})
                or document.get("schema_id") != "asklegal.local-legal-identity-register/v1"
                or document.get("schema_version") != "1.0.0"
                or type(document.get("identities")) is not dict
                or type(document.get("search_records")) is not dict
            ):
                _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
            raw_identities = _object(document["identities"])
            raw_records = _object(document["search_records"])
            for key, item in raw_identities.items():
                if type(key) is not str or type(item) is not str:
                    _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
                self._identities[key] = item
            for key, item in raw_records.items():
                if type(key) is not str:
                    _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
                self._records[key] = _object(item)

    @staticmethod
    def _id(prefix: str, key: str) -> str:
        return f"{prefix}_{sha256(key.encode()).hexdigest()[:48]}"

    def issue_identity(self, request: LegalIdentityRequest) -> IssuedLegalIdentity:
        """Create or replay one deterministic family-prefixed opaque ID."""
        if (
            type(request) is not LegalIdentityRequest
            or type(request.kind) is not LegalIdentityKind
            or type(request.natural_key) is not str
            or not request.natural_key
        ):
            _fail("LEGAL_IDENTITY_REQUEST_INVALID")
        key = f"{request.kind.value}:{request.natural_key}"
        expected = self._id(_PREFIX[request.kind], key)
        current = self._identities.get(key)
        if current is not None and current != expected:
            _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
        self._identities[key] = expected
        return IssuedLegalIdentity(request, expected)

    def issue_search_record(
        self, request: SearchRecordIdentityRequest
    ) -> IssuedSearchRecordIdentity:
        """Issue INITIAL, REUSE, or SUCCESSOR from an exact serving slot."""
        if (
            type(request) is not SearchRecordIdentityRequest
            or type(request.scope_code) is not str
            or not request.scope_code
            or type(request.natural_key) is not str
            or not request.natural_key
            or type(request.serving_payload_fingerprint) is not str
            or _FINGERPRINT.fullmatch(request.serving_payload_fingerprint) is None
        ):
            _fail("SEARCH_RECORD_IDENTITY_REQUEST_INVALID")
        key = f"{request.scope_code}:{request.natural_key}"
        previous = self._records.get(key)
        if previous is None:
            record_id = self._id("rec", f"{key}:{request.serving_payload_fingerprint}")
            continuity = "INITIAL"
            predecessor_id = predecessor_fingerprint = None
        else:
            predecessor_id = str(previous.get("search_record_id"))
            predecessor_fingerprint = str(previous.get("serving_payload_fingerprint"))
            if _FINGERPRINT.fullmatch(predecessor_fingerprint) is None:
                _fail("LEGAL_IDENTITY_REGISTER_DRIFT")
            if predecessor_fingerprint == request.serving_payload_fingerprint:
                record_id = predecessor_id
                continuity = "REUSE"
            else:
                record_id = self._id("rec", f"{key}:{request.serving_payload_fingerprint}")
                continuity = "SUCCESSOR"
        self._records[key] = {
            "search_record_id": record_id,
            "serving_payload_fingerprint": request.serving_payload_fingerprint,
        }
        return IssuedSearchRecordIdentity(
            request,
            record_id,
            continuity,
            predecessor_id,
            predecessor_fingerprint,
        )

    def commit(self) -> None:
        """Atomically retain and verify the canonical local Register snapshot."""
        content = canonicalize(
            checked_json_value(
                {
                    "schema_id": "asklegal.local-legal-identity-register/v1",
                    "schema_version": "1.0.0",
                    "identities": dict(sorted(self._identities.items())),
                    "search_records": dict(sorted(self._records.items())),
                }
            )
        )
        if self._path.exists():
            current = self._path.read_bytes()
            if current == content:
                return
        self._path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        temporary = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._path)
        finally:
            if temporary.exists():
                temporary.unlink()
        if self._path.read_bytes() != content:
            _fail("LEGAL_IDENTITY_REGISTER_READBACK_FAILED")
