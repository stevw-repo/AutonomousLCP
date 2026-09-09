"""Prepare exact non-secret provider-evaluation profiles from local credentials.

This tool reads credentials only to bind their public deployment and target
coordinates.  It never copies or serializes API keys and performs no network
call.  Pricing inputs are explicit conservative authorization ceilings rather
than an assertion about the account's final invoice.
"""

from __future__ import annotations

import argparse
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_legal_desks import GenerativeTask
from asklegal_processing import (
    AzureDeployment,
    ExactTokenCounter,
    SemanticProfileSet,
    load_semantic_profile_set,
    semantic_prompt_fingerprint,
)
from asklegal_promotion import (
    AzureOpenAIConfig,
    EmbeddingProfileInput,
    PineconeConfig,
    ServingCapabilityProfile,
    freeze_embedding_profile,
    load_serving_capability_profile,
)

_MAX_CREDENTIAL_BYTES = 1_048_576
_MAX_TOKENIZER_BYTES = 8_388_608
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
_TIKTOKEN_DISTRIBUTION_FINGERPRINT = (
    "sha256:d186a5c60c6a0213f04a7a802264083dea1bbde92a2d4c7069e1a56630aef830"
)
_SERVING_METADATA_KEYS = (
    "authority_note",
    "country",
    "jurisdiction",
    "source",
    "text",
    "type",
)
_OUTPUT_NAMES = (
    "manifest.json",
    "o200k_base.tiktoken",
    "provider-evaluation-backup-policy.json",
    "semantic-profile.json",
    "serving-evaluation-profile.json",
)


class ProviderProfilePreparationError(ValueError):
    """One sanitized local preparation failure."""


def _fail(code: str) -> Never:
    raise ProviderProfilePreparationError(code)


@dataclass(frozen=True, slots=True)
class ProviderProfileInputs:
    """Exact local inputs and conservative cost ceilings for one profile set."""

    model_credential: Path
    embedding_credential: Path
    pinecone_credential: Path
    tokenizer_resource: Path
    output_root: Path
    environment: str
    expires_at: str
    model_id: str
    model_version: str
    embedding_model_id: str
    embedding_model_version: str
    semantic_input_cost_microunits_per_million: int
    semantic_output_cost_microunits_per_million: int
    embedding_cost_limit_microunits: int
    total_cost_limit_microunits: int


@dataclass(frozen=True, slots=True)
class _PublicCoordinates:
    model_deployment: str
    embedding_deployment: str
    pinecone_index: str
    pinecone_project_id: str


class _Reader:
    """One exact immutable in-memory profile reader used for owning validation."""

    def __init__(self, raw: bytes, ref_type: ReferenceType, prefix: str) -> None:
        digest = sha256(raw).hexdigest()
        self.reference = ImmutableReference(ref_type, prefix + digest[:48], f"sha256:{digest}")
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        if reference != self.reference:
            _fail("PROVIDER_PROFILE_INTERNAL_REFERENCE_INVALID")
        return self._raw


def _read(path: Path, *, maximum: int, code: str) -> bytes:
    try:
        metadata = path.lstat()
        if (
            not path.is_absolute()
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= maximum
            or path.resolve(strict=True) != path
        ):
            _fail(code)
        raw = path.read_bytes()
    except ProviderProfilePreparationError:
        raise
    except OSError as error:
        raise ProviderProfilePreparationError(code) from error
    if len(raw) != metadata.st_size:
        _fail(code)
    return raw


def _canonical(document: dict[str, object]) -> bytes:
    return canonicalize(checked_json_value(document))


def _sealed(document: dict[str, object]) -> bytes:
    projection = dict(document)
    projection.pop("fingerprint", None)
    document["fingerprint"] = f"sha256:{sha256(_canonical(projection)).hexdigest()}"
    return _canonical(document)


def _whole_second_future(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        message = "PROVIDER_PROFILE_EXPIRY_INVALID"
        raise ProviderProfilePreparationError(message) from error
    if (
        not value.endswith("Z")
        or parsed.microsecond != 0
        or parsed.tzinfo is None
        or parsed <= datetime.now(UTC)
    ):
        _fail("PROVIDER_PROFILE_EXPIRY_INVALID")


def _positive(value: int, code: str) -> int:
    if type(value) is not int or value < 1:
        _fail(code)
    return value


def _semantic_document(
    inputs: ProviderProfileInputs,
    deployment: AzureDeployment,
    tokenizer_fingerprint: str,
) -> bytes:
    profiles: list[dict[str, object]] = []
    budgets: list[dict[str, object]] = []
    for index, task in enumerate(GenerativeTask, start=1):
        profile_id = f"hkv1-semantic-{index:02d}-{task.value.lower().replace('_', '-')}"
        profiles.append(
            {
                "allowed_environments": [inputs.environment],
                "api_contract": deployment.api_version,
                "content_filter_policy": "AZURE_DEPLOYMENT_POLICY",
                "data_handling_profile": "AZURE_STATELESS_NO_TRAINING",
                "deployment_name": deployment.deployment,
                "evaluator_id": "hk-v1-provider-golden-suite",
                "evidence_budget_bytes": 131_072,
                "expires_at": inputs.expires_at,
                "geography_class": "AZURE_EASTUS_ENDPOINT",
                "input_schema": "asklegal.semantic-task-request/1.0.0",
                "max_output_tokens": 512,
                "model_id": inputs.model_id,
                "model_version": inputs.model_version,
                "output_schema": "asklegal.semantic-decision/1.0.0",
                "profile_id": profile_id,
                "prompt_fingerprint": semantic_prompt_fingerprint(),
                "provider": "AZURE_OPENAI",
                "resource_class": "USER_SUPPLIED_DEPLOYMENT",
                "retry_policy": "bounded-v1",
                "stateful_features": False,
                "task": task.value,
                "threshold_basis_points": 9000,
                "tokenizer": "o200k_base",
            }
        )
        budgets.append(
            {
                "input_cost_microunits_per_million": (
                    inputs.semantic_input_cost_microunits_per_million
                ),
                "max_input_tokens": 8192,
                "output_cost_microunits_per_million": (
                    inputs.semantic_output_cost_microunits_per_million
                ),
                "profile_id": profile_id,
            }
        )
    document: dict[str, object] = {
        "billing_denominator_tokens": 1_000_000,
        "billing_rounding_rule": "PER_REQUEST_PER_DIRECTION_CEILING",
        "budget_profiles": budgets,
        "cost_limit_microunits": inputs.total_cost_limit_microunits,
        "environment": inputs.environment,
        "expires_at": inputs.expires_at,
        "fingerprint": "",
        "immutable": True,
        "profiles": profiles,
        "quota_limit_tokens": 196_608,
        "request_quota": 24,
        "retry_profile": {
            "attempt_ceiling": 2,
            "backoff_seconds": [1],
            "timeout_seconds": 60,
        },
        "revision": "1.0.0",
        "schema_id": "asklegal.hk-v1-semantic-profile-set",
        "schema_version": "1.1.0",
        "tokenizer_specifications": [
            {
                "distribution_fingerprint": _TIKTOKEN_DISTRIBUTION_FINGERPRINT,
                "distribution_name": "tiktoken",
                "distribution_version": "0.12.0",
                "encoding_resource_fingerprint": tokenizer_fingerprint,
                "tokenizer_id": "o200k_base",
            }
        ],
    }
    return _sealed(document)


def _backup_policy(inputs: ProviderProfileInputs) -> bytes:
    return _sealed(
        {
            "environment": inputs.environment,
            "fingerprint": "",
            "immutable": True,
            "policy": "NO_BACKUP_GATE_D_EVALUATION_ONLY",
            "schema_id": "asklegal.hk-v1-provider-evaluation-backup-policy/v1",
            "schema_version": 1,
        }
    )


def _serving_document(
    inputs: ProviderProfileInputs,
    embedding: AzureOpenAIConfig,
    pinecone: PineconeConfig,
    backup_policy: bytes,
) -> bytes:
    frozen = freeze_embedding_profile(
        EmbeddingProfileInput(
            "AZURE_OPENAI",
            "USER_SUPPLIED_DEPLOYMENT",
            "AZURE_EASTUS_ENDPOINT",
            embedding.deployment,
            inputs.embedding_model_id,
            inputs.embedding_model_version,
            embedding.api_version,
            "o200k_base",
            1536,
            "FLOAT32",
            "NONE",
            "cosine",
            8192,
            inputs.embedding_cost_limit_microunits,
            inputs.expires_at,
            (inputs.environment,),
            stateful_features=False,
        )
    )
    embedding_document = {
        "allowed_environments": list(frozen.allowed_environments),
        "api_contract": frozen.api_contract,
        "cost_limit_microunits": frozen.cost_limit_microunits,
        "deployment_name": frozen.deployment_name,
        "dimensions": frozen.dimensions,
        "encoding": frozen.encoding,
        "expires_at": frozen.expires_at,
        "geography_class": frozen.geography_class,
        "max_input_tokens": frozen.max_input_tokens,
        "metric": frozen.metric,
        "model_id": frozen.model_id,
        "model_version": frozen.model_version,
        "normalization": frozen.normalization,
        "profile_fingerprint": frozen.profile_fingerprint,
        "profile_id": frozen.profile_id,
        "provider": frozen.provider,
        "resource_class": frozen.resource_class,
        "stateful_features": frozen.stateful_features,
        "tokenizer": frozen.tokenizer,
    }
    backup_digest = sha256(backup_policy).hexdigest()
    return _sealed(
        {
            "backup_profile_ref": {
                "fingerprint": f"sha256:{backup_digest}",
                "ref_id": f"cap_{backup_digest[:48]}",
                "ref_type": "CAPABILITY_PROFILE",
            },
            "batch_size": 2,
            "dimensions": frozen.dimensions,
            "embedding": embedding_document,
            "environment": inputs.environment,
            "expires_at": inputs.expires_at,
            "fingerprint": "",
            "immutable": True,
            "index_prefix": pinecone.index,
            "metric": frozen.metric,
            "namespace": "hk-v1-provider-golden-v1",
            "outage_behavior": "FAIL_CLOSED",
            "pinecone_project_id": pinecone.project_id,
            "provider_timeout_seconds": 60,
            "readback_page_size": 2,
            "schema_id": "asklegal.hk-v1-serving-capability-profile",
            "schema_version": "1.0.0",
            "serving_metadata_keys": list(_SERVING_METADATA_KEYS),
            "target_timeout_seconds": 60,
        }
    )


def _validate_profiles(
    semantic_raw: bytes,
    serving_raw: bytes,
    tokenizer_raw: bytes,
) -> tuple[SemanticProfileSet, ServingCapabilityProfile]:
    semantic = load_semantic_profile_set(
        _Reader(semantic_raw, ReferenceType.WORKFLOW_PROFILE, "wap_")
    )
    serving = load_serving_capability_profile(
        _Reader(serving_raw, ReferenceType.CAPABILITY_PROFILE, "cap_")
    )
    ExactTokenCounter(semantic, "o200k_base", tokenizer_raw)
    return semantic, serving


def _artifact_manifest(
    inputs: ProviderProfileInputs,
    artifacts: dict[str, bytes],
    semantic: SemanticProfileSet,
    serving: ServingCapabilityProfile,
    coordinates: _PublicCoordinates,
) -> bytes:
    return _sealed(
        {
            "artifacts": [
                {
                    "byte_length": len(raw),
                    "filename": name,
                    "fingerprint": f"sha256:{sha256(raw).hexdigest()}",
                }
                for name, raw in sorted(artifacts.items())
            ],
            "credential_values_retained": False,
            "embedding_deployment": coordinates.embedding_deployment,
            "environment": inputs.environment,
            "expires_at": inputs.expires_at,
            "fingerprint": "",
            "immutable": True,
            "model_deployment": coordinates.model_deployment,
            "pinecone_index": coordinates.pinecone_index,
            "pinecone_project_id": coordinates.pinecone_project_id,
            "pricing_basis": "CONSERVATIVE_CALLER_SUPPLIED_AUTHORIZATION_CEILINGS",
            "schema_id": "asklegal.hk-v1-provider-profile-preparation/v1",
            "schema_version": 1,
            "semantic_profile_fingerprint": semantic.fingerprint,
            "serving_profile_fingerprint": serving.fingerprint,
        }
    )


def _validate_existing_output(root: Path, artifacts: dict[str, bytes]) -> None:
    if (
        not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) != _DIRECTORY_MODE
        or {path.name for path in root.iterdir()} != set(artifacts)
    ):
        _fail("PROVIDER_PROFILE_OUTPUT_DRIFT")
    for name, raw in artifacts.items():
        path = root / name
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != _FILE_MODE
            or path.read_bytes() != raw
        ):
            _fail("PROVIDER_PROFILE_OUTPUT_DRIFT")


def _write_output(root: Path, artifacts: dict[str, bytes]) -> None:
    if not root.is_absolute() or root.is_symlink() or not root.parent.is_dir():
        _fail("PROVIDER_PROFILE_OUTPUT_INVALID")
    if root.exists():
        _validate_existing_output(root, artifacts)
        return
    temporary = root.parent / f".{root.name}.{token_hex(16)}.tmp"
    try:
        temporary.mkdir(mode=_DIRECTORY_MODE)
        for name, raw in artifacts.items():
            path = temporary / name
            path.write_bytes(raw)
            path.chmod(_FILE_MODE)
            if path.read_bytes() != raw:
                _fail("PROVIDER_PROFILE_OUTPUT_INVALID")
        temporary.replace(root)
    finally:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink(missing_ok=True)
            temporary.rmdir()


def prepare_provider_profiles(inputs: ProviderProfileInputs) -> bytes:
    """Create or replay one complete, canonical, non-secret profile directory."""
    if type(inputs) is not ProviderProfileInputs or not inputs.environment:
        _fail("PROVIDER_PROFILE_INPUT_INVALID")
    _whole_second_future(inputs.expires_at)
    for value in (
        inputs.semantic_input_cost_microunits_per_million,
        inputs.semantic_output_cost_microunits_per_million,
        inputs.embedding_cost_limit_microunits,
        inputs.total_cost_limit_microunits,
    ):
        _positive(value, "PROVIDER_PROFILE_COST_CEILING_INVALID")
    model_raw = _read(
        inputs.model_credential, maximum=_MAX_CREDENTIAL_BYTES, code="MODEL_CREDENTIAL_INVALID"
    )
    embedding_raw = _read(
        inputs.embedding_credential,
        maximum=_MAX_CREDENTIAL_BYTES,
        code="EMBEDDING_CREDENTIAL_INVALID",
    )
    pinecone_raw = _read(
        inputs.pinecone_credential,
        maximum=_MAX_CREDENTIAL_BYTES,
        code="PINECONE_CREDENTIAL_INVALID",
    )
    tokenizer_raw = _read(
        inputs.tokenizer_resource,
        maximum=_MAX_TOKENIZER_BYTES,
        code="TOKENIZER_RESOURCE_INVALID",
    )
    try:
        deployment = AzureDeployment.from_credential_json(model_raw)
        embedding = AzureOpenAIConfig.from_credential_json(embedding_raw)
        pinecone = PineconeConfig.from_credential_json(pinecone_raw)
    except Exception as error:
        message = "PROVIDER_CREDENTIAL_SHAPE_INVALID"
        raise ProviderProfilePreparationError(message) from error
    tokenizer_fingerprint = f"sha256:{sha256(tokenizer_raw).hexdigest()}"
    semantic_raw = _semantic_document(inputs, deployment, tokenizer_fingerprint)
    backup_raw = _backup_policy(inputs)
    serving_raw = _serving_document(inputs, embedding, pinecone, backup_raw)
    semantic, serving = _validate_profiles(semantic_raw, serving_raw, tokenizer_raw)
    core = {
        "o200k_base.tiktoken": tokenizer_raw,
        "provider-evaluation-backup-policy.json": backup_raw,
        "semantic-profile.json": semantic_raw,
        "serving-evaluation-profile.json": serving_raw,
    }
    coordinates = _PublicCoordinates(
        deployment.deployment,
        embedding.deployment,
        pinecone.index,
        pinecone.project_id,
    )
    manifest = _artifact_manifest(inputs, core, semantic, serving, coordinates)
    artifacts = {"manifest.json": manifest, **core}
    if tuple(sorted(artifacts)) != tuple(sorted(_OUTPUT_NAMES)):
        _fail("PROVIDER_PROFILE_INTERNAL_OUTPUT_INVALID")
    _write_output(inputs.output_root, artifacts)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-credential", required=True, type=Path)
    parser.add_argument("--embedding-credential", required=True, type=Path)
    parser.add_argument("--pinecone-credential", required=True, type=Path)
    parser.add_argument("--tokenizer-resource", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--embedding-model-id", required=True)
    parser.add_argument("--embedding-model-version", required=True)
    parser.add_argument("--semantic-input-cost-microunits-per-million", required=True, type=int)
    parser.add_argument("--semantic-output-cost-microunits-per-million", required=True, type=int)
    parser.add_argument("--embedding-cost-limit-microunits", required=True, type=int)
    parser.add_argument("--total-cost-limit-microunits", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Prepare public profiles without invoking any external provider."""
    arguments = _parser().parse_args(argv)
    try:
        manifest = prepare_provider_profiles(
            ProviderProfileInputs(
                model_credential=arguments.model_credential,
                embedding_credential=arguments.embedding_credential,
                pinecone_credential=arguments.pinecone_credential,
                tokenizer_resource=arguments.tokenizer_resource,
                output_root=arguments.output_root,
                environment=arguments.environment,
                expires_at=arguments.expires_at,
                model_id=arguments.model_id,
                model_version=arguments.model_version,
                embedding_model_id=arguments.embedding_model_id,
                embedding_model_version=arguments.embedding_model_version,
                semantic_input_cost_microunits_per_million=(
                    arguments.semantic_input_cost_microunits_per_million
                ),
                semantic_output_cost_microunits_per_million=(
                    arguments.semantic_output_cost_microunits_per_million
                ),
                embedding_cost_limit_microunits=arguments.embedding_cost_limit_microunits,
                total_cost_limit_microunits=arguments.total_cost_limit_microunits,
            )
        )
        document = parse_json_bytes(manifest, max_bytes=len(manifest))
        if type(document) is not dict or type(document.get("fingerprint")) is not str:
            _fail("PROVIDER_PROFILE_INTERNAL_OUTPUT_INVALID")
    except ProviderProfilePreparationError as error:
        print(error, file=sys.stderr)  # noqa: T201
        return 2
    print(  # noqa: T201
        f"READY_NO_EFFECTS {document['fingerprint']} artifacts={len(_OUTPUT_NAMES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
