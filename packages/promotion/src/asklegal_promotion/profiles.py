"""Immutable, provider-disabled serving-capability profile contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Never, Protocol
from weakref import ref

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType

from .builder import SERVING_METADATA_KEYS, freeze_embedding_profile
from .model import EmbeddingProfile, EmbeddingProfileInput

_MAX_PROFILE_BYTES = 2_000_000
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_INTEGER_VERSION = re.compile(r"^(0|[1-9][0-9]*)$")
_DATED_VERSION = re.compile(r"^(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])$")
_WHOLE_SECOND_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_PLACEHOLDERS = frozenset({"latest", "default", "current", "auto"})
_SECRET_VALUE = re.compile(
    r"(?:^|[^a-z0-9])(?:sk-(?:proj|svcacct)-[a-z0-9_-]{8,}|sk-[a-z0-9]{8,}|pcsk_[a-z0-9_-]{8,})(?:$|[^a-z0-9])"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?:^|[^a-z0-9])(?:api[_-]?key|access[_-]?token|bearer|secret|password|connection[_-]?string)"
    r"\s*(?:[:=]|\s)\s*[^\s]+"
)
_MAX_DIMENSIONS = 20_000
_MAX_ADAPTER_PAGE_SIZE = 100
_CAPABILITY_REFERENCE_ID = re.compile(r"^cap_[0-9a-f]{48}$")
_DOCUMENT_KEYS = frozenset(
    {
        "backup_profile_ref",
        "batch_size",
        "dimensions",
        "embedding",
        "environment",
        "expires_at",
        "fingerprint",
        "immutable",
        "index_prefix",
        "metric",
        "namespace",
        "pinecone_project_id",
        "readback_page_size",
        "provider_timeout_seconds",
        "target_timeout_seconds",
        "outage_behavior",
        "serving_metadata_keys",
        "schema_id",
        "schema_version",
    }
)
_EMBEDDING_KEYS = frozenset(
    {
        "allowed_environments",
        "api_contract",
        "cost_limit_microunits",
        "deployment_name",
        "dimensions",
        "encoding",
        "expires_at",
        "geography_class",
        "max_input_tokens",
        "metric",
        "model_id",
        "model_version",
        "normalization",
        "profile_fingerprint",
        "profile_id",
        "provider",
        "resource_class",
        "stateful_features",
        "tokenizer",
    }
)
_REFERENCE_KEYS = frozenset({"fingerprint", "ref_id", "ref_type"})


@dataclass(frozen=True, slots=True)
class _IssuanceRecord:
    fingerprint: str
    projection: bytes


class ProfileError(RuntimeError):
    """One closed immutable serving-capability profile failure."""

    def __init__(self, code: str) -> None:
        """Keep provider-profile failures independent of M6 execution codes."""
        super().__init__(code)


class ProfileReader(Protocol):
    """Reader bound to one immutable capability-profile reference."""

    @property
    def reference(self) -> ImmutableReference:
        """Return the sole authoritative immutable reference exactly once."""
        ...

    def read_exact(self, reference: ImmutableReference) -> bytes:
        """Read the exact immutable bytes for one profile reference."""
        ...


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False, eq=False)
class ServingCapabilityProfile:
    """Exact embedding, target, batch, recovery-reference, and expiry values."""

    embedding: EmbeddingProfile
    pinecone_project_id: str
    index_prefix: str
    dimensions: int
    metric: str
    namespace: str
    batch_size: int
    readback_page_size: int
    provider_timeout_seconds: int
    target_timeout_seconds: int
    outage_behavior: str
    serving_metadata_keys: tuple[str, ...]
    backup_profile_ref: ImmutableReference
    expires_at: str
    environment: str
    fingerprint: str
    _witness: object | None = field(default=None, repr=False, compare=False)

    def validate(self) -> None:
        """Keep direct reconstruction subject to the same closed geometry rules."""
        if (
            type(self.embedding) is not EmbeddingProfile
            or not _embedding_is_admitted(self.embedding)
            or type(self.pinecone_project_id) is not str
            or not _safe_direct_text(self.pinecone_project_id)
            or type(self.index_prefix) is not str
            or not _safe_direct_text(self.index_prefix)
            or type(self.namespace) is not str
            or not _safe_direct_text(self.namespace)
            or type(self.dimensions) is not int
            or not 1 <= self.dimensions <= _MAX_DIMENSIONS
            or self.dimensions != self.embedding.dimensions
            or type(self.metric) is not str
            or not _safe_direct_text(self.metric)
            or self.metric != self.embedding.metric
            or type(self.batch_size) is not int
            or not 1 <= self.batch_size <= _MAX_ADAPTER_PAGE_SIZE
            or type(self.readback_page_size) is not int
            or not 1 <= self.readback_page_size <= _MAX_ADAPTER_PAGE_SIZE
            or type(self.provider_timeout_seconds) is not int
            or self.provider_timeout_seconds < 1
            or type(self.target_timeout_seconds) is not int
            or self.target_timeout_seconds < 1
            or type(self.outage_behavior) is not str
            or self.outage_behavior != "FAIL_CLOSED"
            or type(self.serving_metadata_keys) is not tuple
            or any(type(key) is not str for key in self.serving_metadata_keys)
            or self.serving_metadata_keys != SERVING_METADATA_KEYS
            or not _backup_reference_is_admitted(self.backup_profile_ref)
            or not _safe_direct_text(self.environment)
            or self.environment not in self.embedding.allowed_environments
            or self.expires_at != self.embedding.expires_at
            or not _future_timestamp(self.expires_at)
            or type(self.fingerprint) is not str
        ):
            _fail("SERVING_PROFILE_INVALID")
        computed = _serving_profile_fingerprint(self)
        if _FINGERPRINT.fullmatch(self.fingerprint) is None or self.fingerprint != computed:
            _fail("SERVING_PROFILE_INVALID")

    def __reduce__(self) -> Never:
        """Immutable-reader authority is process-local and non-transferable."""
        _assert_issued(self)
        message = "PROFILE_NONTRANSFERABLE"
        raise TypeError(message)


_ISSUED: dict[int, tuple[ref[ServingCapabilityProfile], _IssuanceRecord]] = {}


def _fail(code: str) -> Never:
    raise ProfileError(code)


def _model_version_is_exact(value: str) -> bool:
    """Accept semantic versions, integer revisions, and Azure date versions."""
    return any(
        pattern.fullmatch(value) is not None
        for pattern in (_VERSION, _INTEGER_VERSION, _DATED_VERSION)
    )


def _object(value: JsonValue | None, code: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        _fail(code)
    return value


def _keys(value: dict[str, JsonValue], expected: frozenset[str]) -> None:
    if frozenset(value) != expected:
        _fail("PROFILE_KEYS_INVALID")


def _text(value: JsonValue | None, code: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail(code)
    return value


def _positive(value: JsonValue | None, code: str) -> int:
    if type(value) is not int or value < 1:
        _fail(code)
    return value


def _nonnegative(value: JsonValue | None, code: str) -> int:
    if type(value) is not int or value < 0:
        _fail(code)
    return value


def _fingerprint(value: JsonValue | None) -> str:
    result = _text(value, "PROFILE_FINGERPRINT_MISMATCH")
    if _FINGERPRINT.fullmatch(result) is None:
        _fail("PROFILE_FINGERPRINT_MISMATCH")
    return result


def _timestamp(value: JsonValue | None, code: str) -> tuple[str, datetime]:
    result = _text(value, code)
    parsed = _whole_second_utc(result)
    if parsed is None:
        _fail(code)
    return result, parsed


def _whole_second_utc(value: object) -> datetime | None:
    """Parse precisely the one UTC timestamp grammar accepted by this contract."""
    if type(value) is not str or _WHOLE_SECOND_UTC.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return None
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        return None
    return parsed


def _no_placeholder(value: str, code: str) -> str:
    if any(token in value.casefold() for token in _PLACEHOLDERS):
        _fail(code)
    return value


def _screen(value: JsonValue) -> None:
    """Reject credential-like content even in otherwise recognized profile leaves."""
    if type(value) is str:
        lowered = value.casefold()
        if _SECRET_VALUE.search(lowered) or _SECRET_ASSIGNMENT.search(lowered):
            _fail("PROFILE_SECRET_FORBIDDEN")
    elif type(value) is list:
        for item in value:
            _screen(item)
    elif type(value) is dict:
        for item in value.values():
            _screen(item)


def _safe_direct_text(value: object) -> bool:
    """Check direct dataclass strings without giving them a decoding bypass."""
    if type(value) is not str or not value or value.strip() != value:
        return False
    lowered = value.casefold()
    return not any(token in lowered for token in _PLACEHOLDERS) and not (
        _SECRET_VALUE.search(lowered) or _SECRET_ASSIGNMENT.search(lowered)
    )


def _backup_reference_is_admitted(value: object) -> bool:
    """Replay every immutable backup-reference primitive before fingerprinting it."""
    return (
        type(value) is ImmutableReference
        and type(value.ref_type) is ReferenceType
        and value.ref_type is ReferenceType.CAPABILITY_PROFILE
        and type(value.ref_id) is str
        and _CAPABILITY_REFERENCE_ID.fullmatch(value.ref_id) is not None
        and type(value.fingerprint) is str
        and _FINGERPRINT.fullmatch(value.fingerprint) is not None
    )


def _future_timestamp(value: object) -> bool:
    """Keep direct reconstruction subject to the loader's expiry boundary."""
    parsed = _whole_second_utc(value)
    return parsed is not None and parsed > datetime.now(UTC)


def _embedding_is_admitted(embedding: EmbeddingProfile) -> bool:
    """Replay the pure embedding-profile admission rules for direct values."""
    if any(
        type(value) is not str
        for value in (
            embedding.provider,
            embedding.encoding,
            embedding.normalization,
            embedding.metric,
        )
    ):
        return False
    if (
        embedding.provider != "AZURE_OPENAI"
        or not all(
            _safe_direct_text(value)
            for value in (
                embedding.profile_id,
                embedding.profile_fingerprint,
                embedding.resource_class,
                embedding.geography_class,
                embedding.deployment_name,
                embedding.model_id,
                embedding.model_version,
                embedding.api_contract,
                embedding.tokenizer,
            )
        )
        or not _model_version_is_exact(embedding.model_version)
        or type(embedding.dimensions) is not int
        or not 1 <= embedding.dimensions <= _MAX_DIMENSIONS
        or embedding.encoding != "FLOAT32"
        or embedding.normalization not in {"NONE", "UNIT_LENGTH"}
        or embedding.metric not in {"cosine", "dotproduct", "euclidean"}
        or type(embedding.max_input_tokens) is not int
        or embedding.max_input_tokens < 1
        or type(embedding.cost_limit_microunits) is not int
        or embedding.cost_limit_microunits < 0
        or not _future_timestamp(embedding.expires_at)
        or type(embedding.allowed_environments) is not tuple
        or not embedding.allowed_environments
        or any(not _safe_direct_text(item) for item in embedding.allowed_environments)
        or len(set(embedding.allowed_environments)) != len(embedding.allowed_environments)
        or embedding.allowed_environments != tuple(sorted(embedding.allowed_environments))
        or embedding.stateful_features is not False
        or _FINGERPRINT.fullmatch(embedding.profile_fingerprint) is None
    ):
        return False
    expected = freeze_embedding_profile(
        EmbeddingProfileInput(
            embedding.provider,
            embedding.resource_class,
            embedding.geography_class,
            embedding.deployment_name,
            embedding.model_id,
            embedding.model_version,
            embedding.api_contract,
            embedding.tokenizer,
            embedding.dimensions,
            embedding.encoding,
            embedding.normalization,
            embedding.metric,
            embedding.max_input_tokens,
            embedding.cost_limit_microunits,
            embedding.expires_at,
            embedding.allowed_environments,
            stateful_features=False,
        )
    )
    return expected == embedding


def _embedding_projection(embedding: EmbeddingProfile) -> dict[str, object]:
    """Return every influential frozen embedding field in canonical JSON shape."""
    return {
        "allowed_environments": list(embedding.allowed_environments),
        "api_contract": embedding.api_contract,
        "cost_limit_microunits": embedding.cost_limit_microunits,
        "deployment_name": embedding.deployment_name,
        "dimensions": embedding.dimensions,
        "encoding": embedding.encoding,
        "expires_at": embedding.expires_at,
        "geography_class": embedding.geography_class,
        "max_input_tokens": embedding.max_input_tokens,
        "metric": embedding.metric,
        "model_id": embedding.model_id,
        "model_version": embedding.model_version,
        "normalization": embedding.normalization,
        "profile_fingerprint": embedding.profile_fingerprint,
        "profile_id": embedding.profile_id,
        "provider": embedding.provider,
        "resource_class": embedding.resource_class,
        "stateful_features": embedding.stateful_features,
        "tokenizer": embedding.tokenizer,
    }


def _serving_profile_fingerprint(profile: ServingCapabilityProfile) -> str:
    """Fingerprint the complete durable public serving-profile projection."""
    return f"sha256:{sha256(_serving_projection_bytes(profile)).hexdigest()}"


def _serving_projection_bytes(profile: ServingCapabilityProfile) -> bytes:
    """Canonical immutable public projection used for issuance and replay."""
    projection = {
        "backup_profile_ref": {
            "fingerprint": profile.backup_profile_ref.fingerprint,
            "ref_id": profile.backup_profile_ref.ref_id,
            "ref_type": profile.backup_profile_ref.ref_type.value,
        },
        "batch_size": profile.batch_size,
        "dimensions": profile.dimensions,
        "embedding": _embedding_projection(profile.embedding),
        "environment": profile.environment,
        "expires_at": profile.expires_at,
        "index_prefix": profile.index_prefix,
        "metric": profile.metric,
        "namespace": profile.namespace,
        "outage_behavior": profile.outage_behavior,
        "pinecone_project_id": profile.pinecone_project_id,
        "provider_timeout_seconds": profile.provider_timeout_seconds,
        "readback_page_size": profile.readback_page_size,
        "serving_metadata_keys": list(profile.serving_metadata_keys),
        "target_timeout_seconds": profile.target_timeout_seconds,
        "type": "asklegal.serving-capability-profile.public.v1",
    }
    return canonicalize(checked_json_value(projection))


def _assert_issued(value: ServingCapabilityProfile) -> None:
    """Deeply replay nested facts before accepting issued process-local identity."""
    entry = _ISSUED.pop(id(value), None)
    if entry is None or entry[0]() is not value:
        _fail("SERVING_PROFILE_INVALID")
    try:
        projection = _serving_projection_bytes(value)
    except Exception as error:
        message = "SERVING_PROFILE_INVALID"
        raise ProfileError(message) from error
    record = entry[1]
    if record.fingerprint != value.fingerprint or record.projection != projection:
        _fail("SERVING_PROFILE_INVALID")
    if entry[0]() is not value or id(value) in _ISSUED:
        _fail("SERVING_PROFILE_INVALID")
    _ISSUED[id(value)] = entry


def validate_serving_capability_profile_authority(value: ServingCapabilityProfile) -> None:
    """Revalidate the exact process-local immutable serving-profile authority."""
    _assert_issued(value)


def _environments(value: JsonValue | None) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("PROFILE_ENVIRONMENT_INVALID")
    result = tuple(
        _no_placeholder(_text(item, "PROFILE_ENVIRONMENT_INVALID"), "PROFILE_PLACEHOLDER_FORBIDDEN")
        for item in value
    )
    if not result or len(set(result)) != len(result) or result != tuple(sorted(result)):
        _fail("PROFILE_ENVIRONMENT_INVALID")
    return result


def _reader_exact(reader: ProfileReader, original: tuple[ReferenceType, str, str]) -> bytes:
    """Read a disposable reference while normalizing ordinary reader failures."""
    try:
        result = reader.read_exact(ImmutableReference(*original))
    except Exception as error:
        message = "PROFILE_READ_FAILED"
        raise ProfileError(message) from error
    if type(result) is not bytes:
        _fail("PROFILE_READ_INVALID")
    return bytes(memoryview(result))


def _immutable_raw(reader: ProfileReader) -> bytes:
    try:
        candidate = reader.reference
    except Exception as error:
        message = "PROFILE_READ_FAILED"
        raise ProfileError(message) from error
    if type(candidate) is not ImmutableReference:
        _fail("PROFILE_REFERENCE_INVALID")
    original: tuple[ReferenceType, str, str] = (
        candidate.ref_type,
        candidate.ref_id,
        candidate.fingerprint,
    )
    try:
        reference = ImmutableReference(*original)
    except Exception as error:
        message = "PROFILE_REFERENCE_INVALID"
        raise ProfileError(message) from error
    if reference.ref_type is not ReferenceType.CAPABILITY_PROFILE:
        _fail("PROFILE_REFERENCE_INVALID")
    raw = _reader_exact(reader, original)
    if (candidate.ref_type, candidate.ref_id, candidate.fingerprint) != original:
        _fail("PROFILE_REFERENCE_MUTATED")
    if not raw or f"sha256:{sha256(raw).hexdigest()}" != reference.fingerprint:
        _fail("PROFILE_FINGERPRINT_MISMATCH")
    second = _reader_exact(reader, original)
    if (candidate.ref_type, candidate.ref_id, candidate.fingerprint) != original:
        _fail("PROFILE_REFERENCE_MUTATED")
    if second != raw:
        _fail("PROFILE_READBACK_MISMATCH")
    return raw


def _reference(value: JsonValue | None) -> ImmutableReference:
    item = _object(value, "PROFILE_DOCUMENT_INVALID")
    _keys(item, _REFERENCE_KEYS)
    ref_type = _text(item.get("ref_type"), "PROFILE_REFERENCE_INVALID")
    try:
        reference = ImmutableReference(
            ReferenceType(ref_type),
            _text(item.get("ref_id"), "PROFILE_REFERENCE_INVALID"),
            _fingerprint(item.get("fingerprint")),
        )
    except ValueError as error:
        message = "PROFILE_REFERENCE_INVALID"
        raise ProfileError(message) from error
    if reference.ref_type is not ReferenceType.CAPABILITY_PROFILE:
        _fail("PROFILE_REFERENCE_INVALID")
    return reference


def _embedding(value: JsonValue | None, environment: str, expires_at: str) -> EmbeddingProfile:
    item = _object(value, "PROFILE_DOCUMENT_INVALID")
    _keys(item, _EMBEDDING_KEYS)
    model_version = _no_placeholder(
        _text(item.get("model_version"), "MODEL_VERSION_NOT_EXACT"), "MODEL_VERSION_NOT_EXACT"
    )
    if not _model_version_is_exact(model_version):
        _fail("MODEL_VERSION_NOT_EXACT")
    stateful = item.get("stateful_features")
    if type(stateful) is not bool:
        _fail("PROFILE_DOCUMENT_INVALID")
    if stateful:
        _fail("STATEFUL_PROVIDER_FEATURE_FORBIDDEN")
    environments = _environments(item.get("allowed_environments"))
    if environment not in environments:
        _fail("PROFILE_ENVIRONMENT_MISMATCH")
    embedded_expiry, embedded_expiry_at = _timestamp(
        item.get("expires_at"), "PROFILE_EXPIRY_INVALID"
    )
    if embedded_expiry != expires_at:
        _fail("PROFILE_EXPIRY_MISMATCH")
    if embedded_expiry_at <= datetime.now(UTC):
        _fail("PROFILE_EXPIRED")
    provider = _text(item.get("provider"), "PROVIDER_INVALID")
    if provider != "AZURE_OPENAI":
        _fail("PROVIDER_INVALID")
    strings = {
        key: _no_placeholder(
            _text(item.get(key), "PROFILE_DOCUMENT_INVALID"), "PROFILE_PLACEHOLDER_FORBIDDEN"
        )
        for key in (
            "api_contract",
            "deployment_name",
            "geography_class",
            "model_id",
            "resource_class",
            "tokenizer",
        )
    }
    deployment = _no_placeholder(strings["deployment_name"], "DEPLOYMENT_NOT_EXACT")
    model_id = _no_placeholder(strings["model_id"], "MODEL_ID_NOT_EXACT")
    encoding = _text(item.get("encoding"), "EMBEDDING_ENCODING_INVALID")
    normalization = _text(item.get("normalization"), "EMBEDDING_NORMALIZATION_INVALID")
    metric = _text(item.get("metric"), "METRIC_INVALID")
    if (
        encoding != "FLOAT32"
        or normalization not in {"NONE", "UNIT_LENGTH"}
        or metric not in {"cosine", "dotproduct", "euclidean"}
    ):
        _fail("EMBEDDING_GEOMETRY_INVALID")
    candidate = freeze_embedding_profile(
        EmbeddingProfileInput(
            provider,
            strings["resource_class"],
            strings["geography_class"],
            deployment,
            model_id,
            model_version,
            strings["api_contract"],
            strings["tokenizer"],
            _positive(item.get("dimensions"), "PROFILE_DOCUMENT_INVALID"),
            encoding,
            normalization,
            metric,
            _positive(item.get("max_input_tokens"), "PROFILE_DOCUMENT_INVALID"),
            _nonnegative(item.get("cost_limit_microunits"), "PROFILE_DOCUMENT_INVALID"),
            embedded_expiry,
            environments,
            stateful_features=False,
        )
    )
    if candidate.profile_id != _text(
        item.get("profile_id"), "PROFILE_DOCUMENT_INVALID"
    ) or candidate.profile_fingerprint != _fingerprint(item.get("profile_fingerprint")):
        _fail("PROFILE_FINGERPRINT_MISMATCH")
    return candidate


def _serving_document(raw: bytes) -> tuple[dict[str, JsonValue], str, str]:
    """Decode, authenticate, and bind the immutable outer serving document."""
    try:
        parsed = parse_json_bytes(raw, max_bytes=_MAX_PROFILE_BYTES)
    except ContractViolation as error:
        message = "PROFILE_DOCUMENT_INVALID"
        raise ProfileError(message) from error
    if raw != canonicalize(checked_json_value(parsed)):
        _fail("PROFILE_CANONICAL_BYTES_REQUIRED")
    document = _object(parsed, "PROFILE_DOCUMENT_INVALID")
    _screen(document)
    _keys(document, _DOCUMENT_KEYS)
    if (
        document.get("schema_id") != "asklegal.hk-v1-serving-capability-profile"
        or document.get("schema_version") != "1.0.0"
        or document.get("immutable") is not True
    ):
        _fail("PROFILE_DOCUMENT_INVALID")
    environment = _no_placeholder(
        _text(document.get("environment"), "PROFILE_ENVIRONMENT_INVALID"),
        "PROFILE_PLACEHOLDER_FORBIDDEN",
    )
    expires_at, expires_value = _timestamp(document.get("expires_at"), "PROFILE_EXPIRY_INVALID")
    if expires_value <= datetime.now(UTC):
        _fail("PROFILE_EXPIRED")
    projection = dict(document)
    supplied_fingerprint = _fingerprint(projection.pop("fingerprint", None))
    if (
        supplied_fingerprint
        != f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    ):
        _fail("PROFILE_FINGERPRINT_MISMATCH")
    return document, environment, expires_at


def load_serving_capability_profile(reader: ProfileReader) -> ServingCapabilityProfile:
    """Load one exact canonical serving profile and close reader TOCTOU races."""
    document, environment, expires_at = _serving_document(_immutable_raw(reader))
    embedding = _embedding(document.get("embedding"), environment, expires_at)
    dimensions = _positive(document.get("dimensions"), "PROFILE_DOCUMENT_INVALID")
    if dimensions > _MAX_DIMENSIONS:
        _fail("DIMENSIONS_INVALID")
    metric = _text(document.get("metric"), "METRIC_INVALID")
    if dimensions != embedding.dimensions:
        _fail("DIMENSIONS_MISMATCH")
    if metric != embedding.metric:
        _fail("METRIC_MISMATCH")
    project = _no_placeholder(
        _text(document.get("pinecone_project_id"), "TARGET_NOT_EXACT"), "TARGET_NOT_EXACT"
    )
    prefix = _no_placeholder(
        _text(document.get("index_prefix"), "TARGET_NOT_EXACT"), "TARGET_NOT_EXACT"
    )
    namespace = _no_placeholder(
        _text(document.get("namespace"), "TARGET_NOT_EXACT"), "TARGET_NOT_EXACT"
    )
    batch_size = _bounded_page(document.get("batch_size"))
    readback_page_size = _bounded_page(document.get("readback_page_size"))
    provider_timeout = _positive(
        document.get("provider_timeout_seconds"), "PROFILE_DOCUMENT_INVALID"
    )
    target_timeout = _positive(document.get("target_timeout_seconds"), "PROFILE_DOCUMENT_INVALID")
    outage_behavior = _outage_behavior(document.get("outage_behavior"))
    payload_keys = _payload_keys(document.get("serving_metadata_keys"))
    backup_profile_ref = _reference(document.get("backup_profile_ref"))
    prototype = object.__new__(ServingCapabilityProfile)
    for name, item in (
        ("embedding", embedding),
        ("pinecone_project_id", project),
        ("index_prefix", prefix),
        ("dimensions", dimensions),
        ("metric", metric),
        ("namespace", namespace),
        ("batch_size", batch_size),
        ("readback_page_size", readback_page_size),
        ("provider_timeout_seconds", provider_timeout),
        ("target_timeout_seconds", target_timeout),
        ("outage_behavior", outage_behavior),
        ("serving_metadata_keys", payload_keys),
        ("backup_profile_ref", backup_profile_ref),
        ("expires_at", expires_at),
        ("environment", environment),
    ):
        object.__setattr__(prototype, name, item)
    fingerprint = _serving_profile_fingerprint(prototype)
    object.__setattr__(prototype, "fingerprint", fingerprint)
    object.__setattr__(prototype, "_witness", None)
    prototype.validate()
    key = id(prototype)

    def cleanup(stored: ref[ServingCapabilityProfile], key: int = key) -> None:
        if _ISSUED.get(key, (None, None))[0] is stored:
            _ISSUED.pop(key, None)

    stored = ref(prototype, cleanup)
    _ISSUED[key] = (stored, _IssuanceRecord(fingerprint, _serving_projection_bytes(prototype)))
    return prototype


def _bounded_page(value: JsonValue | None) -> int:
    """Match the maximum upsert and list page sizes in the serving adapter."""
    result = _positive(value, "PROFILE_DOCUMENT_INVALID")
    if result > _MAX_ADAPTER_PAGE_SIZE:
        _fail("PROFILE_PAGE_SIZE_INVALID")
    return result


def _outage_behavior(value: JsonValue | None) -> str:
    """Require the live-spec fail-visible provider and target outage policy."""
    result = _text(value, "PROFILE_DOCUMENT_INVALID")
    if result != "FAIL_CLOSED":
        _fail("PROFILE_OUTAGE_BEHAVIOR_INVALID")
    return result


def _payload_keys(value: JsonValue | None) -> tuple[str, ...]:
    """Bind target configuration to the established six-field serving payload."""
    if type(value) is not list or any(type(item) is not str for item in value):
        _fail("PROFILE_PAYLOAD_CONTRACT_INVALID")
    result = tuple(_text(item, "PROFILE_PAYLOAD_CONTRACT_INVALID") for item in value)
    if result != SERVING_METADATA_KEYS:
        _fail("PROFILE_PAYLOAD_CONTRACT_INVALID")
    return result
