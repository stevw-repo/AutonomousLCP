"""Exact process configuration boundary shared without an HTTP framework."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from asklegal_contracts import canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue


class ConfigurationErrorCode(StrEnum):
    """Closed reasons an application configuration cannot become ready."""

    FINGERPRINT_MISMATCH = "CONFIGURATION_FINGERPRINT_MISMATCH"
    INVALID = "CONFIGURATION_INVALID"
    RAW_SECRET = "CONFIGURATION_RAW_SECRET"


class ConfigurationError(ValueError):
    """Safe configuration failure with no configuration value in its message."""

    code: ConfigurationErrorCode

    def __init__(self, code: ConfigurationErrorCode) -> None:
        """Create one safe configuration failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    """Bounded resource and shutdown profile."""

    max_body_bytes: int
    max_concurrency: int
    max_retries: int
    shutdown_seconds: int
    lease_seconds: int


@dataclass(frozen=True, slots=True)
class ApplicationConfiguration:
    """One validated immutable application revision configuration."""

    schema_version: int
    application_code: str
    environment: str
    revision: str
    identity_audience: str
    identity_client: str
    build_ref: str
    contract_set_ref: str
    policy_profile_refs: tuple[str, ...]
    register_views: tuple[str, ...]
    register_procedures: tuple[str, ...]
    task_hub: str | None
    network_destinations: tuple[str, ...]
    secret_references: tuple[str, ...]
    limits: RuntimeLimits
    logging_policy: str
    configuration_fingerprint: str

    @classmethod
    def from_bytes(cls, raw: bytes, *, max_bytes: int = 32_768) -> ApplicationConfiguration:
        """Parse, close, and authenticate one exact configuration document."""
        value = parse_json_bytes(raw, max_bytes=max_bytes)
        root = _mapping(value)
        expected = {
            "application_code",
            "build_ref",
            "configuration_fingerprint",
            "contract_set_ref",
            "environment",
            "identity",
            "limits",
            "logging_policy",
            "network_destinations",
            "policy_profile_refs",
            "register_procedures",
            "register_views",
            "revision",
            "schema_version",
            "secret_references",
            "task_hub",
        }
        _exact_keys(root, expected)
        unsigned: dict[str, JsonValue] = dict(root)
        claimed = _text(unsigned.pop("configuration_fingerprint"))
        if claimed != fingerprint(unsigned):
            raise ConfigurationError(ConfigurationErrorCode.FINGERPRINT_MISMATCH)
        identity = _mapping(root["identity"])
        _exact_keys(identity, {"audience", "client"})
        limits = _mapping(root["limits"])
        _exact_keys(
            limits,
            {
                "lease_seconds",
                "max_body_bytes",
                "max_concurrency",
                "max_retries",
                "shutdown_seconds",
            },
        )
        secret_references = _text_tuple(root["secret_references"])
        if any(not item.startswith("secretref:") for item in secret_references):
            raise ConfigurationError(ConfigurationErrorCode.RAW_SECRET)
        task_hub_value = root["task_hub"]
        task_hub = None if task_hub_value is None else _text(task_hub_value)
        return cls(
            schema_version=_integer(root["schema_version"], minimum=1),
            application_code=_text(root["application_code"]),
            environment=_text(root["environment"]),
            revision=_text(root["revision"]),
            identity_audience=_text(identity["audience"]),
            identity_client=_text(identity["client"]),
            build_ref=_text(root["build_ref"]),
            contract_set_ref=_text(root["contract_set_ref"]),
            policy_profile_refs=_text_tuple(root["policy_profile_refs"]),
            register_views=_text_tuple(root["register_views"]),
            register_procedures=_text_tuple(root["register_procedures"]),
            task_hub=task_hub,
            network_destinations=_text_tuple(root["network_destinations"]),
            secret_references=secret_references,
            limits=RuntimeLimits(
                max_body_bytes=_integer(limits["max_body_bytes"], minimum=1),
                max_concurrency=_integer(limits["max_concurrency"], minimum=1),
                max_retries=_integer(limits["max_retries"], minimum=0),
                shutdown_seconds=_integer(limits["shutdown_seconds"], minimum=1),
                lease_seconds=_integer(limits["lease_seconds"], minimum=1),
            ),
            logging_policy=_text(root["logging_policy"]),
            configuration_fingerprint=claimed,
        )


@dataclass(slots=True)
class LocalConfigurationSource:
    """Mutable local source used only to prove readiness drift handling."""

    configuration: ApplicationConfiguration

    def is_current(self, expected_fingerprint: str) -> bool:
        """Return whether the running revision still has its admitted bundle."""
        return self.configuration.configuration_fingerprint == expected_fingerprint

    def drift(self) -> None:
        """Make the local source differ without changing the running configuration."""
        self.configuration = replace(
            self.configuration,
            configuration_fingerprint="sha256:" + "f" * 64,
        )


def build_local_configuration(
    application_code: str,
    *,
    audience: str,
    client: str,
    task_hub: str | None,
) -> ApplicationConfiguration:
    """Build and parse a deterministic non-secret local configuration fixture."""
    unsigned: dict[str, JsonValue] = {
        "application_code": application_code,
        "build_ref": "bld_" + "1" * 48,
        "contract_set_ref": "cst_" + "2" * 48,
        "environment": "LOCAL_TEST",
        "identity": {"audience": audience, "client": client},
        "limits": {
            "lease_seconds": 30,
            "max_body_bytes": 16_384,
            "max_concurrency": 2,
            "max_retries": 3,
            "shutdown_seconds": 10,
        },
        "logging_policy": "SAFE_METADATA_ONLY",
        "network_destinations": [],
        "policy_profile_refs": ["pol_" + "3" * 48],
        "register_procedures": ["resolve_command_v1"],
        "register_views": ["application_readiness_v1"],
        "revision": "local-r1",
        "schema_version": 1,
        "secret_references": [f"secretref:{application_code}/local-test"],
        "task_hub": task_hub,
    }
    complete = {**unsigned, "configuration_fingerprint": fingerprint(unsigned)}
    return ApplicationConfiguration.from_bytes(canonicalize(complete))


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ConfigurationError(ConfigurationErrorCode.INVALID)
    return value


def _exact_keys(value: Mapping[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise ConfigurationError(ConfigurationErrorCode.INVALID)


def _text(value: JsonValue) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ConfigurationError(ConfigurationErrorCode.INVALID)
    return value


def _integer(value: JsonValue, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ConfigurationError(ConfigurationErrorCode.INVALID)
    return value


def _text_tuple(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigurationError(ConfigurationErrorCode.INVALID)
    result = tuple(_text(item) for item in value)
    if len(set(result)) != len(result):
        raise ConfigurationError(ConfigurationErrorCode.INVALID)
    return result
