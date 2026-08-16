"""Adversarial tests for strict raw-byte parsing and JCS."""

import pytest
from asklegal_contracts import (
    ContractErrorCode,
    ContractViolation,
    canonicalize,
    fingerprint,
    parse_json_bytes,
)
from asklegal_contracts.strict_json import MAX_SAFE_INTEGER
from hypothesis import given
from hypothesis import strategies as st


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'\xef\xbb\xbf{"a":1}', ContractErrorCode.NON_CANONICAL_JSON),
        (b'{"a":1,"a":2}', ContractErrorCode.MALFORMED_JSON),
        (b'"\\ud800"', ContractErrorCode.MALFORMED_JSON),
        (b"\xff", ContractErrorCode.MALFORMED_JSON),
        (b"NaN", ContractErrorCode.MALFORMED_JSON),
        (b"Infinity", ContractErrorCode.MALFORMED_JSON),
        (b"-0", ContractErrorCode.NON_CANONICAL_JSON),
        (b"-0.0", ContractErrorCode.NON_CANONICAL_JSON),
        (str(MAX_SAFE_INTEGER + 1).encode(), ContractErrorCode.NON_CANONICAL_JSON),
        (b'{"a":1} trailing', ContractErrorCode.MALFORMED_JSON),
    ],
)
def test_rejects_forbidden_raw_json(raw: bytes, code: ContractErrorCode) -> None:
    """Every rejected raw form has a stable repository-owned code."""
    with pytest.raises(ContractViolation) as captured:
        parse_json_bytes(raw, max_bytes=1_024)
    assert captured.value.code is code


def test_requires_and_enforces_an_explicit_size_ceiling() -> None:
    """The parser fails before decoding a body beyond its declared ceiling."""
    with pytest.raises(ContractViolation) as captured:
        parse_json_bytes(b'{"a":1}', max_bytes=6)
    assert captured.value.code is ContractErrorCode.BODY_TOO_LARGE


@given(st.integers(min_value=-MAX_SAFE_INTEGER, max_value=MAX_SAFE_INTEGER))
def test_safe_integers_round_trip_exactly(value: int) -> None:
    """Safe integers survive strict parsing and canonicalization exactly."""
    raw = str(value).encode()
    parsed = parse_json_bytes(raw, max_bytes=len(raw))
    assert parsed == value
    assert canonicalize(parsed) == raw


def test_jcs_adapter_uses_rfc_number_and_hash_encoding() -> None:
    """The adapter emits UTF-8 bytes and the lowercase prefixed digest."""
    parsed = parse_json_bytes(b'{"b":2,"a":1.5}', max_bytes=64)
    assert canonicalize(parsed) == b'{"a":1.5,"b":2}'
    assert (
        fingerprint(parsed)
        == "sha256:0d3dca5cdef44c0cd2d025eed57a39b476c4975913d96266f4992fc53fdc3d61"
    )


def test_error_text_never_exposes_decoder_details() -> None:
    """Dependency messages do not become the boundary contract."""
    with pytest.raises(ContractViolation) as captured:
        parse_json_bytes(b"{", max_bytes=8)
    assert str(captured.value) == "CONTRACT_MALFORMED_JSON at $"
