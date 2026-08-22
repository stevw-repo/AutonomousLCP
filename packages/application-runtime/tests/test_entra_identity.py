"""Pinned-key Entra access-token verification proofs."""

from __future__ import annotations

from collections.abc import Mapping
from time import time

import jwt
import pytest
from asklegal_application_runtime import (
    AuthorizationError,
    AuthorizationErrorCode,
    EntraAccessTokenProfile,
    EntraAccessTokenVerifier,
    EntraSigningKey,
    TokenType,
    authorize,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

_TENANT = "11111111-2222-3333-4444-555555555555"
_ISSUER = f"https://login.microsoftonline.com/{_TENANT}/v2.0"
_AUDIENCE = "api://asklegal-review"
_CLIENT = "66666666-7777-8888-9999-000000000000"
_SCOPE = "asklegal.review"
_KEY_ID = "entra-signing-key-1"


def _key() -> RSAPrivateKey:
    """Create one process-local synthetic RSA key."""
    return rsa.generate_private_key(public_exponent=65_537, key_size=2_048)


def _verifier(private_key: RSAPrivateKey) -> EntraAccessTokenVerifier:
    """Create one exact verifier from the synthetic key's public half."""
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return EntraAccessTokenVerifier(
        EntraAccessTokenProfile(
            issuer=_ISSUER,
            tenant_id=_TENANT,
            audience=_AUDIENCE,
            allowed_clients=frozenset({_CLIENT}),
            delegated_scopes=frozenset({_SCOPE}),
        ),
        (EntraSigningKey(_KEY_ID, public_pem),),
    )


def _claims(**overrides: object) -> dict[str, object]:
    """Return one live delegated v2 access-token claim set."""
    now = int(time())
    values: dict[str, object] = {
        "aud": _AUDIENCE,
        "azp": _CLIENT,
        "exp": now + 3_600,
        "iat": now - 10,
        "iss": _ISSUER,
        "nbf": now - 10,
        "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "roles": ["PipelineAdministrator"],
        "scp": _SCOPE,
        "sub": "stable-pairwise-subject",
        "tid": _TENANT,
        "ver": "2.0",
    }
    values.update(overrides)
    return values


def _token(
    private_key: RSAPrivateKey,
    claims: Mapping[str, object],
    *,
    key_id: str = _KEY_ID,
    headers: Mapping[str, object] | None = None,
) -> str:
    """Sign one synthetic access token."""
    token_headers: dict[str, object] = {"kid": key_id, "typ": "JWT"}
    if headers is not None:
        token_headers.update(headers)
    return jwt.encode(dict(claims), private_key, algorithm="RS256", headers=token_headers)


def _unknown(verifier: EntraAccessTokenVerifier, token: str) -> None:
    """Require safe normalization of one invalid token."""
    with pytest.raises(AuthorizationError) as raised:
        verifier.verify(f"Bearer {token}")
    assert raised.value.code is AuthorizationErrorCode.UNKNOWN


def test_entra_verifier_admits_exact_delegated_named_human() -> None:
    """Verify signature, identity, client, scope, role, and token kind."""
    private_key = _key()
    verifier = _verifier(private_key)
    principal = verifier.verify(f"Bearer {_token(private_key, _claims())}")
    assert principal.subject == (
        "entra:11111111-2222-3333-4444-555555555555:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )
    assert principal.audience == _AUDIENCE
    assert principal.client == _CLIENT
    assert principal.roles == frozenset({"PipelineAdministrator"})
    assert principal.token_type is TokenType.DELEGATED_HUMAN
    authorize(principal, audience=_AUDIENCE, client=_CLIENT)
    assert verifier.check() is True


def test_entra_verifier_rejects_missing_and_malformed_bearer_values() -> None:
    """Never decode a missing, multi-value, non-ASCII, or oversized bearer."""
    verifier = _verifier(_key())
    for authorization, code in (
        (None, AuthorizationErrorCode.MISSING),
        ("Basic abc", AuthorizationErrorCode.MISSING),
        ("Bearer one two", AuthorizationErrorCode.MISSING),
        ("Bearer å", AuthorizationErrorCode.UNKNOWN),
        ("Bearer " + "a" * 16_385, AuthorizationErrorCode.UNKNOWN),
    ):
        with pytest.raises(AuthorizationError) as raised:
            verifier.verify(authorization)
        assert raised.value.code is code


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("aud", "api://wrong"),
        ("azp", "not-admitted"),
        ("iss", "https://issuer.invalid/v2.0"),
        ("tid", "99999999-9999-9999-9999-999999999999"),
        ("ver", "1.0"),
        ("scp", "different.scope"),
        ("exp", 1),
        ("iat", 1),
        ("nbf", 4_102_444_800),
    ],
)
def test_entra_verifier_rejects_claim_drift(claim: str, value: object) -> None:
    """Reject each security-significant claim when it drifts."""
    private_key = _key()
    verifier = _verifier(private_key)
    _unknown(verifier, _token(private_key, _claims(**{claim: value})))


def test_entra_verifier_rejects_signature_key_and_header_drift() -> None:
    """Pin the signing key, algorithm family, and local-only key selection."""
    private_key = _key()
    verifier = _verifier(private_key)
    _unknown(verifier, _token(_key(), _claims()))
    _unknown(verifier, _token(private_key, _claims(), key_id="unknown"))
    _unknown(verifier, _token(private_key, _claims(), headers={"jku": "https://evil.test"}))
    _unknown(verifier, _token(private_key, _claims(), headers={"typ": "id+jwt"}))


def test_entra_verifier_classifies_but_does_not_authorize_app_token() -> None:
    """An expressly app-only token remains barred from human Review."""
    private_key = _key()
    verifier = _verifier(private_key)
    claims = _claims(idtyp="app")
    claims.pop("scp")
    principal = verifier.verify(f"Bearer {_token(private_key, claims)}")
    assert principal.token_type is TokenType.APPLICATION
    with pytest.raises(AuthorizationError) as raised:
        authorize(principal, audience=_AUDIENCE, client=_CLIENT)
    assert raised.value.code is AuthorizationErrorCode.TOKEN_TYPE


def test_entra_verifier_requires_current_pipeline_administrator_role() -> None:
    """A valid human access token without the exact role is unauthorized."""
    private_key = _key()
    verifier = _verifier(private_key)
    principal = verifier.verify(f"Bearer {_token(private_key, _claims(roles=[]))}")
    with pytest.raises(AuthorizationError) as raised:
        authorize(principal, audience=_AUDIENCE, client=_CLIENT)
    assert raised.value.code is AuthorizationErrorCode.ROLE


def test_entra_profile_and_signing_key_fail_closed_at_startup() -> None:
    """Invalid or duplicate admitted metadata cannot reach request handling."""
    private_key = _key()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    profile = EntraAccessTokenProfile(
        issuer=_ISSUER,
        tenant_id=_TENANT,
        audience=_AUDIENCE,
        allowed_clients=frozenset({_CLIENT}),
        delegated_scopes=frozenset({_SCOPE}),
    )
    with pytest.raises(ValueError, match="unique"):
        EntraAccessTokenVerifier(
            profile,
            (
                EntraSigningKey(_KEY_ID, public_pem),
                EntraSigningKey(_KEY_ID, public_pem),
            ),
        )
    with pytest.raises(TypeError, match="RSA"):
        EntraAccessTokenVerifier(
            profile,
            (
                EntraSigningKey(
                    _KEY_ID,
                    ec.generate_private_key(ec.SECP256R1())
                    .public_key()
                    .public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    ),
                ),
            ),
        )
