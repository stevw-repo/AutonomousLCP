"""Tests for exact non-secret HK V1 provider-profile preparation."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from tools.hk_v1_prepare_provider_profiles import (
    ProviderProfileInputs,
    ProviderProfilePreparationError,
    prepare_provider_profiles,
)

_TOKENIZER = (
    Path(__file__).parents[2]
    / "packages/processing/src/asklegal_processing/_resources/o200k_base.tiktoken"
)


def _credential(path: Path, value: dict[str, object]) -> Path:
    path.write_bytes(canonicalize(checked_json_value(value)))
    path.chmod(0o600)
    return path.resolve()


def _inputs(tmp_path: Path, *, legacy_project: bool = False) -> ProviderProfileInputs:
    project_field = "project" if legacy_project else "project_id"
    return ProviderProfileInputs(
        model_credential=_credential(
            tmp_path / "model",
            {
                "api_key": "model-secret-not-for-output",
                "api_version": "2024-10-21",
                "deployment": "gpt-5.4",
                "endpoint": "https://example.openai.azure.com",
            },
        ),
        embedding_credential=_credential(
            tmp_path / "embedding",
            {
                "api_key": "embedding-secret-not-for-output",
                "api_version": "2024-10-21",
                "deployment": "text-embedding-3-small",
                "endpoint": "https://example.openai.azure.com",
            },
        ),
        pinecone_credential=_credential(
            tmp_path / "pinecone",
            {
                "api_key": "pinecone-secret-not-for-output",
                "control_plane_host": "https://api.pinecone.io",
                "index": "testing-index-1",
                project_field: "DatabaseWorkerTest",
            },
        ),
        tokenizer_resource=_TOKENIZER.resolve(),
        output_root=(tmp_path / "profiles").resolve(),
        environment="V1_POC",
        expires_at="2099-01-01T00:00:00Z",
        model_id="gpt-5.4",
        model_version="2026-03-05",
        embedding_model_id="text-embedding-3-small",
        embedding_model_version="1",
        semantic_input_cost_microunits_per_million=100_000_000,
        semantic_output_cost_microunits_per_million=100_000_000,
        embedding_cost_limit_microunits=10_000_000,
        total_cost_limit_microunits=5_000_000,
    )


@pytest.mark.parametrize("project_schema", ["current", "legacy"])
def test_prepares_and_replays_exact_non_secret_profiles(
    tmp_path: Path, project_schema: str
) -> None:
    """Current and retained credential spellings produce exact secret-free output."""
    inputs = _inputs(tmp_path, legacy_project=project_schema == "legacy")
    first = prepare_provider_profiles(inputs)
    second = prepare_provider_profiles(inputs)
    assert first == second
    assert stat.S_IMODE(inputs.output_root.stat().st_mode) == 0o700
    assert {path.name for path in inputs.output_root.iterdir()} == {
        "manifest.json",
        "o200k_base.tiktoken",
        "provider-evaluation-backup-policy.json",
        "semantic-profile.json",
        "serving-evaluation-profile.json",
    }
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in inputs.output_root.iterdir())
    combined = b"".join(path.read_bytes() for path in inputs.output_root.iterdir())
    assert b"model-secret-not-for-output" not in combined
    assert b"embedding-secret-not-for-output" not in combined
    assert b"pinecone-secret-not-for-output" not in combined
    semantic = json.loads((inputs.output_root / "semantic-profile.json").read_bytes())
    assert {item["model_version"] for item in semantic["profiles"]} == {"2026-03-05"}
    serving = json.loads((inputs.output_root / "serving-evaluation-profile.json").read_bytes())
    assert serving["pinecone_project_id"] == "DatabaseWorkerTest"
    assert serving["embedding"]["model_version"] == "1"


def test_existing_output_drift_is_never_overwritten(tmp_path: Path) -> None:
    """An existing publication is immutable and fails on any byte drift."""
    inputs = _inputs(tmp_path)
    prepare_provider_profiles(inputs)
    target = inputs.output_root / "semantic-profile.json"
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ProviderProfilePreparationError, match="PROVIDER_PROFILE_OUTPUT_DRIFT"):
        prepare_provider_profiles(inputs)


def test_credential_secret_never_appears_in_failure(tmp_path: Path) -> None:
    """Malformed credential failures reveal neither supplied value nor output."""
    inputs = _inputs(tmp_path)
    inputs.model_credential.write_bytes(b'{"api_key":"top-secret"}')
    with pytest.raises(ProviderProfilePreparationError) as raised:
        prepare_provider_profiles(inputs)
    assert "top-secret" not in str(raised.value)
    assert not inputs.output_root.exists()
