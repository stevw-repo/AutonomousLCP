"""Strict immutable serving-capability profile contract tests."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from hashlib import sha256

import asklegal_promotion.profiles as serving_profiles
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_promotion.profiles import ProfileError, load_serving_capability_profile


class _Reader:
    """One immutable synthetic profile object for loader tests."""

    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.CAPABILITY_PROFILE,
            f"cap_{'1' * 48}",
            f"sha256:{sha256(raw).hexdigest()}",
        )
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        """Return bytes only for the exact expected immutable reference."""
        assert reference == self.reference
        return self._raw

    def replace_bytes(self, raw: bytes) -> None:
        """Simulate immutable-storage drift after reference issuance."""
        self._raw = raw


@dataclass(frozen=True, slots=True)
class _ProfileOptions:
    """Only synthetic profile variations used by hostile contract tests."""

    dimensions: int = 4
    metric: str = "cosine"
    environment: str = "LOCAL_SYNTHETIC"
    allowed_environments: list[str] | None = None
    stateful_features: bool = False
    expires_at: str = "2099-01-01T00:00:00Z"
    extra_field: bool = False


def _serving_profile_bytes(options: _ProfileOptions | None = None) -> bytes:
    settings = options or _ProfileOptions()
    embedding = {
        "allowed_environments": settings.allowed_environments or [settings.environment],
        "api_contract": "2026-08-01",
        "cost_limit_microunits": 1000,
        "deployment_name": "synthetic-embedding-v1",
        "dimensions": settings.dimensions,
        "encoding": "FLOAT32",
        "expires_at": settings.expires_at,
        "geography_class": "SYNTHETIC",
        "max_input_tokens": 2048,
        "metric": settings.metric,
        "model_id": "synthetic-embedding-model-v1",
        "model_version": "1.0.0",
        "normalization": "UNIT_LENGTH",
        "profile_fingerprint": "",
        "profile_id": "",
        "provider": "AZURE_OPENAI",
        "resource_class": "SYNTHETIC",
        "stateful_features": settings.stateful_features,
        "tokenizer": "synthetic-tokenizer-v1",
    }
    profile_projection = dict(embedding)
    profile_projection.pop("profile_fingerprint")
    profile_projection.pop("profile_id")
    fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(profile_projection))).hexdigest()}"
    )
    embedding["profile_fingerprint"] = fingerprint
    embedding["profile_id"] = f"emp_{sha256(fingerprint.encode()).hexdigest()[:48]}"
    document = {
        "backup_profile_ref": {
            "fingerprint": f"sha256:{'3' * 64}",
            "ref_id": f"cap_{'4' * 48}",
            "ref_type": "CAPABILITY_PROFILE",
        },
        "batch_size": 2,
        "dimensions": settings.dimensions,
        "embedding": embedding,
        "environment": settings.environment,
        "expires_at": settings.expires_at,
        "fingerprint": "",
        "immutable": True,
        "index_prefix": "asklegal-local-synthetic-",
        "metric": settings.metric,
        "namespace": "synthetic-v1",
        "pinecone_project_id": "synthetic-project-v1",
        "readback_page_size": 2,
        "provider_timeout_seconds": 60,
        "target_timeout_seconds": 60,
        "outage_behavior": "FAIL_CLOSED",
        "serving_metadata_keys": [
            "authority_note",
            "country",
            "jurisdiction",
            "source",
            "text",
            "type",
        ],
        "schema_id": "asklegal.hk-v1-serving-capability-profile",
        "schema_version": "1.0.0",
    }
    if settings.extra_field:
        document["credential"] = "forbidden"
    fingerprint_projection = dict(document)
    fingerprint_projection.pop("fingerprint")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(fingerprint_projection))).hexdigest()}"
    )
    return canonicalize(checked_json_value(document))


def _reseal(document: dict[str, JsonValue]) -> bytes:
    """Return exact canonical synthetic bytes after one hostile mutation."""
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    )
    return canonicalize(checked_json_value(document))


def test_serving_profile_rejects_fingerprint_drift() -> None:
    """A byte drift after immutable reference issuance must fail closed."""
    raw = _serving_profile_bytes()
    reader = _Reader(raw)
    reader.replace_bytes(raw + b" ")
    with pytest.raises(ProfileError, match="PROFILE_FINGERPRINT_MISMATCH"):
        load_serving_capability_profile(reader)


def test_serving_profile_loads_exact_embedding_and_target_values() -> None:
    """A closed synthetic serving document becomes immutable promotion values."""
    loaded = load_serving_capability_profile(_Reader(_serving_profile_bytes()))
    assert loaded.embedding.dimensions == 4
    assert loaded.dimensions == 4
    assert loaded.metric == "cosine"


def test_serving_profile_accepts_exact_azure_dated_model_version() -> None:
    """Azure embedding deployments may also expose a calendar-date revision."""
    raw = _serving_profile_bytes()
    document = parse_json_bytes(raw, max_bytes=100_000)
    assert isinstance(document, dict)
    embedding = document["embedding"]
    assert isinstance(embedding, dict)
    embedding["model_version"] = "2026-03-05"
    projection = dict(embedding)
    projection.pop("profile_fingerprint")
    projection.pop("profile_id")
    profile_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    )
    embedding["profile_fingerprint"] = profile_fingerprint
    embedding["profile_id"] = f"emp_{sha256(profile_fingerprint.encode()).hexdigest()[:48]}"
    loaded = load_serving_capability_profile(_Reader(_reseal(document)))
    assert loaded.embedding.model_version == "2026-03-05"


def test_serving_profile_rejects_embedding_dimensions_mismatch() -> None:
    """The target vector geometry must be the embedding geometry."""
    raw = _serving_profile_bytes()
    # Build a valid document first, then drift only its target dimensions and reseal it.
    document = parse_json_bytes(raw, max_bytes=100_000)
    assert isinstance(document, dict)
    document["dimensions"] = 5
    with pytest.raises(ProfileError, match="DIMENSIONS_MISMATCH"):
        load_serving_capability_profile(_Reader(_reseal(document)))


def test_serving_profile_rejects_environment_mismatch() -> None:
    """The embedding can run only in the profile's declared environment."""
    with pytest.raises(ProfileError, match="PROFILE_ENVIRONMENT_MISMATCH"):
        load_serving_capability_profile(
            _Reader(_serving_profile_bytes(_ProfileOptions(allowed_environments=["OTHER"])))
        )


def test_serving_profile_rejects_stateful_features() -> None:
    """Stateful embedding features are never an admitted serving capability."""
    with pytest.raises(ProfileError, match="STATEFUL_PROVIDER_FEATURE_FORBIDDEN"):
        load_serving_capability_profile(
            _Reader(_serving_profile_bytes(_ProfileOptions(stateful_features=True)))
        )


def test_serving_profile_rejects_expired_profile() -> None:
    """Expired serving coordinates cannot be carried into promotion."""
    with pytest.raises(ProfileError, match="PROFILE_EXPIRED"):
        load_serving_capability_profile(
            _Reader(_serving_profile_bytes(_ProfileOptions(expires_at="2000-01-01T00:00:00Z")))
        )


def test_serving_profile_rejects_secret_field() -> None:
    """Profile documents carry references only, never a credential value."""
    with pytest.raises(ProfileError, match="PROFILE_KEYS_INVALID"):
        load_serving_capability_profile(
            _Reader(_serving_profile_bytes(_ProfileOptions(extra_field=True)))
        )


def test_serving_profile_rejects_structured_secret_value() -> None:
    """A real token-shaped value is forbidden in a known embedding field."""
    document = parse_json_bytes(_serving_profile_bytes(), max_bytes=100_000)
    assert isinstance(document, dict)
    embedding = document["embedding"]
    assert isinstance(embedding, dict)
    embedding["model_id"] = "sk-abcdef123456"
    with pytest.raises(ProfileError, match="PROFILE_SECRET_FORBIDDEN"):
        load_serving_capability_profile(_Reader(_reseal(document)))


def test_serving_profile_rejects_reader_toctou_drift() -> None:
    """A mutation after the first immutable read cannot become a capability."""
    raw = _serving_profile_bytes()

    class _DriftingReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            value = super().read_exact(reference)
            self.replace_bytes(raw + b"x")
            return value

    with pytest.raises(ProfileError, match="PROFILE_READBACK_MISMATCH"):
        load_serving_capability_profile(_DriftingReader(raw))


def test_serving_reader_gets_disposable_reference_copies() -> None:
    """Both reads receive recreated references, never reader-owned identity."""
    raw = _serving_profile_bytes()

    class _IdentityReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            assert reference is not self.reference
            return super().read_exact(reference)

    assert load_serving_capability_profile(_IdentityReader(raw)).dimensions == 4


def test_serving_reader_oserror_is_normalized() -> None:
    """Ordinary immutable-storage failure becomes one closed profile error."""
    raw = _serving_profile_bytes()

    class _BrokenReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            del reference
            message = "offline"
            raise OSError(message)

    with pytest.raises(ProfileError, match="PROFILE_READ_FAILED"):
        load_serving_capability_profile(_BrokenReader(raw))


def test_serving_reference_property_oserror_is_normalized() -> None:
    """Reference acquisition is inside the same ordinary-reader fault boundary."""

    class _PropertyFaultReader:
        @property
        def reference(self) -> ImmutableReference:
            message = "offline"
            raise OSError(message)

        def read_exact(self, reference: ImmutableReference) -> bytes:
            del reference
            raise AssertionError

    with pytest.raises(ProfileError, match="PROFILE_READ_FAILED"):
        load_serving_capability_profile(_PropertyFaultReader())


def test_serving_reader_reference_is_sampled_once_and_remains_stable() -> None:
    """The loader uses one snapshotted reference and detects reader mutation."""
    raw = _serving_profile_bytes()

    class _OneSampleReader(_Reader):
        @property
        def reference(self) -> ImmutableReference:
            if getattr(self, "_reference_sampled", False):
                raise AssertionError
            self._reference_sampled = True
            return self._reference

        @reference.setter
        def reference(self, value: ImmutableReference) -> None:
            self._reference = value

        def read_exact(self, reference: ImmutableReference) -> bytes:
            assert reference == self._reference
            return self._raw

    assert load_serving_capability_profile(_OneSampleReader(raw)).dimensions == 4

    class _MutatingReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            value = super().read_exact(reference)
            object.__setattr__(self.reference, "ref_id", f"cap_{'2' * 48}")
            return value

    with pytest.raises(ProfileError, match="PROFILE_REFERENCE_MUTATED"):
        load_serving_capability_profile(_MutatingReader(raw))


def test_serving_direct_reconstruction_replays_adapter_bounds() -> None:
    """Replacement cannot exceed the real adapter batch, page, or dimension bounds."""
    loaded = load_serving_capability_profile(_Reader(_serving_profile_bytes()))
    with pytest.raises(TypeError):
        replace(loaded, batch_size=101)
    with pytest.raises(TypeError):
        replace(loaded, dimensions=20_001)
    with pytest.raises(TypeError):
        replace(loaded, batch_size=3)
    object.__setattr__(loaded, "metric", [])
    with pytest.raises(TypeError):
        replace(loaded)

    class _Text(str):
        __slots__ = ()

    with pytest.raises(TypeError):
        replace(loaded, pinecone_project_id=_Text("synthetic-project-v1"))


def test_serving_profile_copy_and_pickle_are_nontransferable() -> None:
    """Reader-issued immutable authority cannot be copied or serialized."""
    loaded = load_serving_capability_profile(_Reader(_serving_profile_bytes()))
    with pytest.raises(TypeError, match="PROFILE_NONTRANSFERABLE"):
        copy.copy(loaded)


def _direct_serving_profile(
    expires_at: str, embedding_expires_at: str | None = None
) -> serving_profiles.ServingCapabilityProfile:
    """Build a coherent, unissued public projection for direct-validator tests."""
    loaded = load_serving_capability_profile(_Reader(_serving_profile_bytes()))
    embedding = replace(loaded.embedding, expires_at=embedding_expires_at or expires_at)
    direct = object.__new__(serving_profiles.ServingCapabilityProfile)
    for name, value in (
        ("embedding", embedding),
        ("pinecone_project_id", loaded.pinecone_project_id),
        ("index_prefix", loaded.index_prefix),
        ("dimensions", loaded.dimensions),
        ("metric", loaded.metric),
        ("namespace", loaded.namespace),
        ("batch_size", loaded.batch_size),
        ("readback_page_size", loaded.readback_page_size),
        ("provider_timeout_seconds", loaded.provider_timeout_seconds),
        ("target_timeout_seconds", loaded.target_timeout_seconds),
        ("outage_behavior", loaded.outage_behavior),
        ("serving_metadata_keys", loaded.serving_metadata_keys),
        ("backup_profile_ref", loaded.backup_profile_ref),
        ("expires_at", expires_at),
        ("environment", loaded.environment),
        ("fingerprint", ""),
        ("_witness", None),
    ):
        object.__setattr__(direct, name, value)
    projection = {
        "backup_profile_ref": {
            "fingerprint": direct.backup_profile_ref.fingerprint,
            "ref_id": direct.backup_profile_ref.ref_id,
            "ref_type": direct.backup_profile_ref.ref_type.value,
        },
        "batch_size": direct.batch_size,
        "dimensions": direct.dimensions,
        "embedding": {
            "allowed_environments": list(direct.embedding.allowed_environments),
            "api_contract": direct.embedding.api_contract,
            "cost_limit_microunits": direct.embedding.cost_limit_microunits,
            "deployment_name": direct.embedding.deployment_name,
            "dimensions": direct.embedding.dimensions,
            "encoding": direct.embedding.encoding,
            "expires_at": direct.embedding.expires_at,
            "geography_class": direct.embedding.geography_class,
            "max_input_tokens": direct.embedding.max_input_tokens,
            "metric": direct.embedding.metric,
            "model_id": direct.embedding.model_id,
            "model_version": direct.embedding.model_version,
            "normalization": direct.embedding.normalization,
            "profile_fingerprint": direct.embedding.profile_fingerprint,
            "profile_id": direct.embedding.profile_id,
            "provider": direct.embedding.provider,
            "resource_class": direct.embedding.resource_class,
            "stateful_features": direct.embedding.stateful_features,
            "tokenizer": direct.embedding.tokenizer,
        },
        "environment": direct.environment,
        "expires_at": direct.expires_at,
        "index_prefix": direct.index_prefix,
        "metric": direct.metric,
        "namespace": direct.namespace,
        "outage_behavior": direct.outage_behavior,
        "pinecone_project_id": direct.pinecone_project_id,
        "provider_timeout_seconds": direct.provider_timeout_seconds,
        "readback_page_size": direct.readback_page_size,
        "serving_metadata_keys": list(direct.serving_metadata_keys),
        "target_timeout_seconds": direct.target_timeout_seconds,
        "type": "asklegal.serving-capability-profile.public.v1",
    }
    fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    object.__setattr__(direct, "fingerprint", fingerprint)
    return direct


def test_serving_direct_validator_requires_whole_second_utc_expiry() -> None:
    """Unissued coherent projections share the loader/schema whole-second grammar."""
    _direct_serving_profile("2099-01-01T00:00:00Z").validate()

    class _Timestamp(str):
        __slots__ = ()

    for expires_at in (
        "2099-01-01T00:00:00.123000Z",
        "2099-01-01T00:00:00+00:00",
        "20990101T000000Z",
        "2099-01-01T00:00:00,123000Z",
        "2099-02-30T00:00:00Z",
        _Timestamp("2099-01-01T00:00:00Z"),
    ):
        with pytest.raises(ProfileError, match="SERVING_PROFILE_INVALID"):
            _direct_serving_profile(expires_at).validate()


def test_serving_direct_validator_requires_embedding_expiry_match() -> None:
    """Unissued outer and embedding projections preserve the loader expiry binding."""
    _direct_serving_profile("2099-01-01T00:00:00Z").validate()
    with pytest.raises(ProfileError, match="SERVING_PROFILE_INVALID"):
        _direct_serving_profile("2098-01-01T00:00:00Z", "2099-01-01T00:00:00Z").validate()
