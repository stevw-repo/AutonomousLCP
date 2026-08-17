"""V1 two-emulator scheduler topology and factory proofs."""

from dataclasses import replace
from operator import methodcaller

import asklegal_durable_task.v1 as v1_module
import pytest
from asklegal_durable_task import (
    V1SchedulerError,
    V1SchedulerErrorCode,
    V1SchedulerSettings,
)
from durabletask.worker import ConcurrencyOptions

_APPLICATIONS = {
    "ACQUISITION_WORKER": ("dts-general", "acquisition"),
    "CONTROL_PLANE": ("dts-general", "control"),
    "LEGAL_PROCESSING_WORKER": ("dts-general", "legal-processing"),
    "PROMOTION_WORKER": ("dts-promotion", "promotion"),
}


@pytest.mark.parametrize(("application_code", "expected"), _APPLICATIONS.items())
def test_v1_scheduler_settings_bind_each_application_to_one_exact_hub(
    application_code: str, expected: tuple[str, str]
) -> None:
    """Keep general and promotion task hubs disjoint and Review excluded."""
    settings = V1SchedulerSettings.for_application(application_code)
    assert (settings.scheduler_service, settings.task_hub) == expected
    assert settings.host_address == f"{expected[0]}:8080"
    assert settings.persistence == "MEMORY_ONLY"
    assert settings.loss_result == "REPLACEMENT_FROM_SAFE_CHECKPOINT"


def test_v1_scheduler_rejects_review_unknown_and_cross_hub_settings() -> None:
    """Review has no task hub and no application may cross scheduler ownership."""
    for application_code in ("REVIEW_API", "UNKNOWN"):
        with pytest.raises(V1SchedulerError) as error:
            V1SchedulerSettings.for_application(application_code)
        assert error.value.code is V1SchedulerErrorCode.APPLICATION

    control = V1SchedulerSettings.for_application("CONTROL_PLANE")
    for field, value in (
        ("scheduler_service", "dts-promotion"),
        ("task_hub", "promotion"),
        ("persistence", "DURABLE"),
        ("loss_result", "RESUMED"),
    ):
        with pytest.raises(V1SchedulerError) as error:
            replace(control, **{field: value})
        assert error.value.code is V1SchedulerErrorCode.SETTINGS


def test_v1_scheduler_factories_use_private_emulator_without_token_or_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construct exact SDK boundaries without opening a connection or adding authority."""
    client_calls: list[dict[str, object]] = []
    worker_calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_calls.append(kwargs)

    class FakeWorker:
        def __init__(self, **kwargs: object) -> None:
            worker_calls.append(kwargs)

    monkeypatch.setattr(v1_module, "DurableTaskSchedulerClient", FakeClient)
    monkeypatch.setattr(v1_module, "DurableTaskSchedulerWorker", FakeWorker)
    concurrency = ConcurrencyOptions(
        maximum_concurrent_activity_work_items=2,
        maximum_concurrent_orchestration_work_items=1,
        maximum_thread_pool_workers=2,
    )
    settings = V1SchedulerSettings.for_application("PROMOTION_WORKER")

    settings.create_client(default_version="1.0.0")
    settings.create_worker(concurrency_options=concurrency)

    assert client_calls == [
        {
            "default_version": "1.0.0",
            "host_address": "dts-promotion:8080",
            "secure_channel": False,
            "taskhub": "promotion",
            "token_credential": None,
        }
    ]
    assert worker_calls == [
        {
            "concurrency_options": concurrency,
            "host_address": "dts-promotion:8080",
            "secure_channel": False,
            "taskhub": "promotion",
            "token_credential": None,
        }
    ]


def test_v1_scheduler_requires_explicit_version_and_concurrency_profile() -> None:
    """Do not invent workflow version or operational capacity defaults."""
    settings = V1SchedulerSettings.for_application("ACQUISITION_WORKER")
    for version in ("", " 1.0.0", "1.0.0 "):
        with pytest.raises(V1SchedulerError) as error:
            settings.create_client(default_version=version)
        assert error.value.code is V1SchedulerErrorCode.VERSION

    with pytest.raises(V1SchedulerError) as error:
        methodcaller("create_worker", concurrency_options=None)(settings)
    assert error.value.code is V1SchedulerErrorCode.CONCURRENCY
