"""Exact disabled-by-deployment V1 Durable Task emulator factories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from durabletask.azuremanaged.client import DurableTaskSchedulerClient
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from durabletask.worker import ConcurrencyOptions

_APPLICATION_SCHEDULERS = {
    "ACQUISITION_WORKER": ("dts-general", "acquisition"),
    "CONTROL_PLANE": ("dts-general", "control"),
    "LEGAL_PROCESSING_WORKER": ("dts-general", "legal-processing"),
    "PROMOTION_WORKER": ("dts-promotion", "promotion"),
}
_SCHEDULER_PORT = 8080
_PERSISTENCE = "MEMORY_ONLY"
_LOSS_RESULT = "REPLACEMENT_FROM_SAFE_CHECKPOINT"


class V1SchedulerErrorCode(StrEnum):
    """Closed safe V1 scheduler configuration rejection reasons."""

    APPLICATION = "V1_SCHEDULER_APPLICATION_INVALID"
    CONCURRENCY = "V1_SCHEDULER_CONCURRENCY_INVALID"
    SETTINGS = "V1_SCHEDULER_SETTINGS_INVALID"
    VERSION = "V1_SCHEDULER_VERSION_INVALID"


class V1SchedulerError(ValueError):
    """Scheduler rejection that exposes no runtime payload or topology drift."""

    code: V1SchedulerErrorCode

    def __init__(self, code: V1SchedulerErrorCode) -> None:
        """Create one safe scheduler failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class V1SchedulerSettings:
    """One exact application-to-emulator/task-hub binding."""

    application_code: str
    scheduler_service: str
    task_hub: str
    persistence: str = _PERSISTENCE
    loss_result: str = _LOSS_RESULT

    def __post_init__(self) -> None:
        """Reject Review, cross-hub use, and false durability semantics."""
        expected = _APPLICATION_SCHEDULERS.get(self.application_code)
        if expected is None:
            raise V1SchedulerError(V1SchedulerErrorCode.APPLICATION)
        if (
            (self.scheduler_service, self.task_hub) != expected
            or self.persistence != _PERSISTENCE
            or self.loss_result != _LOSS_RESULT
        ):
            raise V1SchedulerError(V1SchedulerErrorCode.SETTINGS)

    @classmethod
    def for_application(cls, application_code: str) -> V1SchedulerSettings:
        """Return the one scheduler binding permitted for an application."""
        expected = _APPLICATION_SCHEDULERS.get(application_code)
        if expected is None:
            raise V1SchedulerError(V1SchedulerErrorCode.APPLICATION)
        return cls(application_code, expected[0], expected[1])

    @property
    def host_address(self) -> str:
        """Return the internal topology DNS name and fixed emulator gRPC port."""
        return f"{self.scheduler_service}:{_SCHEDULER_PORT}"

    def create_client(self, *, default_version: str) -> DurableTaskSchedulerClient:
        """Create a no-token client for one private internal emulator task hub."""
        if (
            type(default_version) is not str
            or not default_version
            or default_version.strip() != default_version
        ):
            raise V1SchedulerError(V1SchedulerErrorCode.VERSION)
        return DurableTaskSchedulerClient(
            host_address=self.host_address,
            taskhub=self.task_hub,
            token_credential=None,
            secure_channel=False,
            default_version=default_version,
        )

    def create_worker(
        self, *, concurrency_options: ConcurrencyOptions
    ) -> DurableTaskSchedulerWorker:
        """Create a no-token worker only with an explicit admitted concurrency profile."""
        if type(concurrency_options) is not ConcurrencyOptions:
            raise V1SchedulerError(V1SchedulerErrorCode.CONCURRENCY)
        return DurableTaskSchedulerWorker(
            host_address=self.host_address,
            taskhub=self.task_hub,
            token_credential=None,
            secure_channel=False,
            concurrency_options=concurrency_options,
        )
