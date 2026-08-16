"""Legal-processing worker M3 startup boundary."""

import pytest
from asklegal_application_runtime import LocalAdapterError
from asklegal_legal_processing_worker import create_runtime


def test_legal_worker_starts_without_ingress_and_model_access() -> None:
    """Start without HTTP and reject local model access."""
    runtime = create_runtime()
    assert runtime.ready()
    for effect in runtime.effects:
        with pytest.raises(LocalAdapterError):
            effect.invoke({})
    runtime.configuration_source.drift()
    assert runtime.ready() is False
