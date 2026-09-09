"""Installed-input checks for the local V1 Promotion runtime configuration."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from asklegal_contracts import parse_json_bytes
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_processing import ExactTokenizerResourceCounter
from asklegal_promotion import load_serving_capability_profile

_ROOT = Path(__file__).resolve().parents[2]
_PROFILE = _ROOT / "infrastructure/poc/config/hk-v1-promotion/serving-profile.json"
_TOKENIZER = _ROOT / "packages/processing/src/asklegal_processing/_resources/o200k_base.tiktoken"


class _ProfileReader:
    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.CAPABILITY_PROFILE,
            "cap_" + sha256(raw).hexdigest()[:48],
            "sha256:" + sha256(raw).hexdigest(),
        )
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        assert reference == self.reference
        return self._raw


def test_checked_in_promotion_profile_and_tokenizer_are_compatible() -> None:
    """The public runtime profile can be loaded without any provider secret."""
    raw = _PROFILE.read_bytes().removesuffix(b"\n")
    profile = load_serving_capability_profile(_ProfileReader(raw))

    counter = ExactTokenizerResourceCounter(
        profile.embedding.tokenizer,
        _TOKENIZER.read_bytes(),
    )

    assert profile.environment == "V1_POC"
    document = parse_json_bytes(raw, max_bytes=10_000)
    assert isinstance(document, dict)
    assert document["fingerprint"] == (
        "sha256:613889cc244e531cdddd64fa3fd695d7c89d147f81754e1f41c57a04381afb44"
    )
    assert counter.tokenizer_id == profile.embedding.tokenizer


def test_host_apply_stages_the_exact_promotion_runtime_inputs() -> None:
    """Phase two installs both future Promotion inputs before service startup."""
    helper = (_ROOT / "infrastructure/poc/provisioning/90-host-apply.sh").read_text()

    assert "infrastructure/poc/config/hk-v1-promotion/serving-profile.json" in helper
    assert "asklegal_processing/_resources/o200k_base.tiktoken" in helper
    assert "/etc/asklegal/config/hk-v1-promotion/serving-profile.json" in helper
    assert "/etc/asklegal/config/hk-v1-promotion/o200k_base.tiktoken" in helper
    assert helper.count("asklegal-vault-primary-root-rotation-network") == 4
