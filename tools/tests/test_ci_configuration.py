"""Fail-closed checks for the unprivileged Azure Pipelines shipping gate."""

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PATH = REPOSITORY_ROOT / "azure-pipelines.yml"
BOOTSTRAP_PATH = REPOSITORY_ROOT / "tools/ci/bootstrap.sh"


def test_pipeline_runs_the_complete_gate_without_privileged_resources() -> None:
    """PR CI may validate source but must receive no Azure or production authority."""
    pipeline = PIPELINE_PATH.read_text(encoding="utf-8")

    assert "vmImage: ubuntu-24.04" in pipeline
    assert "persistCredentials: false" in pipeline
    assert "tools/ci/bootstrap.sh" in pipeline
    assert "python3 -m tools.dev_test" in pipeline
    assert "--uv" in pipeline
    assert "--node" in pipeline
    assert "pytest_arguments" not in pipeline
    assert not re.search(
        r"serviceConnection|azureSubscription|environment:|deployment:|Docker@|AzureCLI@",
        pipeline,
        flags=re.IGNORECASE,
    )


def test_bootstrap_pins_and_hashes_every_downloaded_executable() -> None:
    """A mutable installer or version-only download is not a reproducible CI toolchain."""
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert 'uv_version="0.12.5"' in bootstrap
    assert (
        'uv_sha256="68a509da24b06b4223a1c0175fb5eb5bc79342b76cbeff0cfe51ac3f5b17b6b2"' in bootstrap
    )
    assert 'node_version="24.19.0"' in bootstrap
    assert (
        'node_sha256="14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647"'
        in bootstrap
    )
    assert bootstrap.count("sha256sum --check --status") == 2
    assert "uv-installer.sh" not in bootstrap
    assert re.search(r"curl[^\n]*\|\s*sh", bootstrap) is None
    assert "python install --no-bin 3.14.7" in bootstrap
    assert "python find --managed-python 3.14.7" in bootstrap
