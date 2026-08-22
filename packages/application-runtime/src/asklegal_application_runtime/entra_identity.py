"""Pinned-key Microsoft Entra access-token verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeIs

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt import InvalidTokenError

from asklegal_application_runtime.identity import (
    AuthorizationError,
    AuthorizationErrorCode,
    Principal,
    TokenType,
)

_ALGORITHM = "RS256"
_HEADER_TYPES = frozenset({"JWT", "at+jwt"})
_MAX_KEY_BYTES = 16_384
_MAX_LEEWAY_SECONDS = 300
_MAX_LIFETIME_SECONDS = 86_400
_MAX_TOKEN_BYTES = 65_536
_MIN_LIFETIME_SECONDS = 300
_MIN_TOKEN_BYTES = 1_024


@dataclass(frozen=True, slots=True)
class EntraAccessTokenProfile:
    """Exact single-tenant resource-server token contract."""

    issuer: str
    tenant_id: str
    audience: str
    allowed_clients: frozenset[str]
    delegated_scopes: frozenset[str]
    max_token_bytes: int = 16_384
    max_lifetime_seconds: int = 7_200
    leeway_seconds: int = 60

    def __post_init__(self) -> None:
        """Reject a floating, empty, or unbounded identity profile."""
        for value in (self.issuer, self.tenant_id, self.audience):
            if type(value) is not str or not value or value.strip() != value:
                message = "Entra profile strings must be exact and non-empty"
                raise ValueError(message)
        _exact_string_set(self.allowed_clients, "allowed_clients")
        _exact_string_set(self.delegated_scopes, "delegated_scopes")
        if not self.allowed_clients or not self.delegated_scopes:
            message = "Entra client and delegated-scope allow-lists must be non-empty"
            raise ValueError(message)
        if (
            type(self.max_token_bytes) is not int
            or not _MIN_TOKEN_BYTES <= self.max_token_bytes <= _MAX_TOKEN_BYTES
        ):
            message = "max_token_bytes is outside the admitted range"
            raise ValueError(message)
        if (
            type(self.max_lifetime_seconds) is not int
            or not _MIN_LIFETIME_SECONDS <= self.max_lifetime_seconds <= _MAX_LIFETIME_SECONDS
        ):
            message = "max_lifetime_seconds is outside the admitted range"
            raise ValueError(message)
        if (
            type(self.leeway_seconds) is not int
            or not 0 <= self.leeway_seconds <= _MAX_LEEWAY_SECONDS
        ):
            message = "leeway_seconds is outside the admitted range"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class EntraSigningKey:
    """One locally admitted tenant signing key version."""

    key_id: str
    public_key_pem: bytes

    def __post_init__(self) -> None:
        """Require an exact identifier and bounded public key bytes."""
        if type(self.key_id) is not str or not self.key_id or self.key_id.strip() != self.key_id:
            message = "signing key ID must be exact and non-empty"
            raise ValueError(message)
        if (
            type(self.public_key_pem) is not bytes
            or not self.public_key_pem
            or len(self.public_key_pem) > _MAX_KEY_BYTES
        ):
            message = "signing public key must be bounded non-empty bytes"
            raise ValueError(message)


class EntraAccessTokenVerifier:
    """Verify an Entra v2 access token without discovery or network fallback."""

    def __init__(
        self,
        profile: EntraAccessTokenProfile,
        signing_keys: tuple[EntraSigningKey, ...],
    ) -> None:
        """Load and pin the complete admitted tenant signing-key set."""
        if not signing_keys:
            message = "at least one admitted signing key is required"
            raise ValueError(message)
        parsed: dict[str, RSAPublicKey] = {}
        for item in signing_keys:
            if item.key_id in parsed:
                message = "signing key IDs must be unique"
                raise ValueError(message)
            key = serialization.load_pem_public_key(item.public_key_pem)
            if not isinstance(key, RSAPublicKey):
                message = "Entra signing keys must be RSA public keys"
                raise TypeError(message)
            parsed[item.key_id] = key
        self._profile = profile
        self._keys = parsed

    def verify(self, authorization: str | None) -> Principal:
        """Verify signature and every admitted access-token claim."""
        token = _bearer_token(authorization, self._profile.max_token_bytes)
        try:
            header = jwt.get_unverified_header(token)
            _validate_header(header)
            key_id = _required_string(header, "kid")
            key = self._keys[key_id]
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[_ALGORITHM],
                audience=self._profile.audience,
                issuer=self._profile.issuer,
                leeway=self._profile.leeway_seconds,
                options={
                    "require": [
                        "aud",
                        "azp",
                        "exp",
                        "iat",
                        "iss",
                        "nbf",
                        "oid",
                        "sub",
                        "tid",
                        "ver",
                    ]
                },
            )
            return _principal(claims, self._profile)
        except InvalidTokenError, KeyError, TypeError, ValueError:
            raise AuthorizationError(AuthorizationErrorCode.UNKNOWN) from None

    def check(self) -> bool:
        """Report whether one exact local profile and key set is loaded."""
        return bool(self._keys)


def _bearer_token(authorization: str | None, maximum: int) -> str:
    """Extract exactly one bounded bearer value."""
    if authorization is None:
        raise AuthorizationError(AuthorizationErrorCode.MISSING)
    scheme, separator, token = authorization.partition(" ")
    if scheme != "Bearer" or separator != " " or not token or " " in token:
        raise AuthorizationError(AuthorizationErrorCode.MISSING)
    try:
        encoded = token.encode("ascii")
    except UnicodeEncodeError:
        raise AuthorizationError(AuthorizationErrorCode.UNKNOWN) from None
    if len(encoded) > maximum:
        raise AuthorizationError(AuthorizationErrorCode.UNKNOWN)
    return token


def _validate_header(header: dict[str, object]) -> None:
    """Reject algorithm switching and caller-selected remote key locations."""
    if header.get("alg") != _ALGORITHM or header.get("typ") not in _HEADER_TYPES:
        message = "unsupported access-token header"
        raise ValueError(message)
    if any(name in header for name in ("crit", "jku", "x5u")):
        message = "remote or critical token headers are not admitted"
        raise ValueError(message)
    _required_string(header, "kid")


def _principal(claims: dict[str, object], profile: EntraAccessTokenProfile) -> Principal:
    """Validate exact v2 claims and reduce them to the trusted principal."""
    client, object_id = _identity_claims(claims, profile)
    _validate_lifetime(claims, profile.max_lifetime_seconds)
    roles = _roles(claims.get("roles"))
    token_type = _token_type(claims.get("scp"), claims.get("idtyp"), profile)
    return Principal(
        subject=f"entra:{profile.tenant_id}:{object_id}",
        audience=profile.audience,
        client=client,
        roles=roles,
        token_type=token_type,
    )


def _identity_claims(
    claims: dict[str, object], profile: EntraAccessTokenProfile
) -> tuple[str, str]:
    """Validate version, resource, tenant, client, and stable identities."""
    if claims.get("ver") != "2.0":
        message = "only Entra v2 access tokens are admitted"
        raise ValueError(message)
    if _required_string(claims, "iss") != profile.issuer:
        message = "issuer drift"
        raise ValueError(message)
    if _required_string(claims, "tid") != profile.tenant_id:
        message = "tenant drift"
        raise ValueError(message)
    if _required_string(claims, "aud") != profile.audience:
        message = "audience drift"
        raise ValueError(message)
    client = _required_string(claims, "azp")
    if client not in profile.allowed_clients:
        message = "client is not admitted"
        raise ValueError(message)
    _required_string(claims, "sub")
    return client, _required_string(claims, "oid")


def _validate_lifetime(claims: dict[str, object], maximum: int) -> None:
    """Reject inverted or overlong token lifetimes."""
    issued_at = _required_integer(claims, "iat")
    not_before = _required_integer(claims, "nbf")
    expires_at = _required_integer(claims, "exp")
    if expires_at <= issued_at or not_before > expires_at or expires_at - issued_at > maximum:
        message = "token lifetime is not admitted"
        raise ValueError(message)


def _token_type(
    scope_claim: object,
    identity_type: object,
    profile: EntraAccessTokenProfile,
) -> TokenType:
    """Classify an expressly delegated or app-only access token."""
    if scope_claim is None:
        if identity_type != "app":
            message = "non-delegated token must be explicitly app-only"
            raise ValueError(message)
        return TokenType.APPLICATION
    if type(scope_claim) is not str or identity_type == "app":
        message = "delegated scope claim is malformed"
        raise ValueError(message)
    scopes = frozenset(scope_claim.split(" "))
    if "" in scopes or not profile.delegated_scopes.issubset(scopes):
        message = "required delegated scope is absent"
        raise ValueError(message)
    return TokenType.DELEGATED_HUMAN


def _roles(value: object) -> frozenset[str]:
    """Parse one exact application-role array."""
    if value is None:
        return frozenset()
    if not _is_object_list(value):
        message = "roles claim must be a string array"
        raise ValueError(message)
    roles: set[str] = set()
    for item in value:
        if type(item) is not str or not item:
            message = "roles claim must be a string array"
            raise ValueError(message)
        roles.add(item)
    return frozenset(roles)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    """Narrow an exact built-in list without a trust-creating static cast."""
    return type(value) is list


def _required_string(values: dict[str, object], name: str) -> str:
    """Read one exact non-empty string claim."""
    value = values.get(name)
    if type(value) is not str or not value:
        message = f"{name} must be one non-empty string"
        raise ValueError(message)
    return value


def _required_integer(values: dict[str, object], name: str) -> int:
    """Read one exact integer NumericDate claim."""
    value = values.get(name)
    if type(value) is not int:
        message = f"{name} must be one integer"
        raise ValueError(message)
    return value


def _exact_string_set(value: frozenset[str], name: str) -> None:
    """Reject mutable, empty, or whitespace-ambiguous allow-list values."""
    if type(value) is not frozenset or any(
        type(item) is not str or not item or item.strip() != item for item in value
    ):
        message = f"{name} must be an exact frozen string set"
        raise TypeError(message)
