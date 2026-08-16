"""Promotion worker M3 startup boundary."""

import pytest
from asklegal_application_runtime import LocalAdapterError
from asklegal_promotion_worker import create_runtime


def test_promotion_worker_starts_without_ingress_and_production_effects() -> None:
    """Start without HTTP and reject local production effects."""
    runtime = create_runtime()
    assert runtime.ready()
    for effect in runtime.effects:
        with pytest.raises(LocalAdapterError):
            effect.invoke({})
    runtime.configuration_source.drift()
    assert runtime.ready() is False
