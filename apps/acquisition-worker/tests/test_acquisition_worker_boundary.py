"""Acquisition worker M3 startup boundary."""

import pytest
from asklegal_acquisition_worker import create_runtime
from asklegal_application_runtime import LocalAdapterError


def test_acquisition_worker_starts_without_ingress_and_effects_fail_closed() -> None:
    """Start without HTTP and reject every local external effect."""
    runtime = create_runtime()
    assert runtime.ready()
    for effect in runtime.effects:
        with pytest.raises(LocalAdapterError):
            effect.invoke({})
    runtime.configuration_source.drift()
    assert runtime.ready() is False
