"""Framework-free local identity verifier and exact authorization boundary."""

from dataclasses import dataclass
from enum import StrEnum


class TokenType(StrEnum):
    """Closed token subject kinds admitted by the application boundary."""

    APPLICATION = "APPLICATION"
    DELEGATED_HUMAN = "DELEGATED_HUMAN"


class AuthorizationErrorCode(StrEnum):
    """Safe authorization rejection reasons."""

    AUDIENCE = "AUTH_WRONG_AUDIENCE"
    CLIENT = "AUTH_WRONG_CLIENT"
    FORGED_PROXY_HEADER = "AUTH_FORGED_PROXY_HEADER"
    MISSING = "AUTH_MISSING_TOKEN"
    ORIGIN = "AUTH_WRONG_ORIGIN"
    ROLE = "AUTH_MISSING_ROLE"
    TOKEN_TYPE = "AUTH_WRONG_TOKEN_TYPE"
    UNKNOWN = "AUTH_UNKNOWN_TOKEN"


class AuthorizationError(PermissionError):
    """One normalized authentication or authorization rejection."""

    code: AuthorizationErrorCode

    def __init__(self, code: AuthorizationErrorCode) -> None:
        """Create one safe authorization failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class Principal:
    """Verified claims returned by an injected identity adapter."""

    subject: str
    audience: str
    client: str
    roles: frozenset[str]
    token_type: TokenType


class LocalIdentityVerifier:
    """Explicit token-to-principal mapping; it never trusts request claims."""

    _principals: dict[str, Principal]

    def __init__(self, principals: dict[str, Principal]) -> None:
        """Create a verifier from explicit opaque-token mappings."""
        self._principals = dict(principals)

    def verify(self, authorization: str | None) -> Principal:
        """Resolve one opaque local token without decoding caller-controlled data."""
        if authorization is None or not authorization.startswith("Bearer "):
            raise AuthorizationError(AuthorizationErrorCode.MISSING)
        principal = self._principals.get(authorization.removeprefix("Bearer "))
        if principal is None:
            raise AuthorizationError(AuthorizationErrorCode.UNKNOWN)
        return principal


def authorize(
    principal: Principal,
    *,
    audience: str,
    client: str,
    delegated_human: bool = True,
) -> None:
    """Apply the one human role without weakening the application boundary."""
    if principal.audience != audience:
        raise AuthorizationError(AuthorizationErrorCode.AUDIENCE)
    if principal.client != client:
        raise AuthorizationError(AuthorizationErrorCode.CLIENT)
    if "PipelineAdministrator" not in principal.roles:
        raise AuthorizationError(AuthorizationErrorCode.ROLE)
    if delegated_human and principal.token_type is not TokenType.DELEGATED_HUMAN:
        raise AuthorizationError(AuthorizationErrorCode.TOKEN_TYPE)


def default_local_identity(audience: str, client: str) -> LocalIdentityVerifier:
    """Return a deterministic successful principal for local startup tests."""
    return LocalIdentityVerifier(
        {
            "local-human": Principal(
                subject="person-local-1",
                audience=audience,
                client=client,
                roles=frozenset({"PipelineAdministrator"}),
                token_type=TokenType.DELEGATED_HUMAN,
            )
        }
    )
