"""Framework-free worker lease, fencing, shutdown, and disabled-effect runtime."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from asklegal_application_runtime.config import ApplicationConfiguration, LocalConfigurationSource
from asklegal_application_runtime.local import DisabledEffectPort


class WorkerResultCode(StrEnum):
    """Closed local worker results."""

    CLAIMED = "CLAIMED"
    INTERRUPTED = "INTERRUPTED"
    NO_WORK = "NO_WORK"
    STALE_FENCE = "STALE_FENCE"


@dataclass(frozen=True, slots=True)
class WorkLease:
    """One generation-fenced work claim."""

    work_id: str
    generation: int
    fencing_token: str


class LocalTaskHub:
    """Deterministic local task hub with lease-generation fencing."""

    _pending: list[str]
    _generation: dict[str, int]
    interruptions: list[str]

    def __init__(self, work_ids: tuple[str, ...] = ()) -> None:
        """Create a task hub with an exact initial queue."""
        self._pending = list(work_ids)
        self._generation = {}
        self.interruptions = []

    def claim(self) -> WorkLease | None:
        """Claim one item and advance its generation."""
        if not self._pending:
            return None
        work_id = self._pending.pop(0)
        generation = self._generation.get(work_id, 0) + 1
        self._generation[work_id] = generation
        return WorkLease(work_id, generation, f"{work_id}:{generation}")

    def reissue(self, work_id: str) -> WorkLease:
        """Issue a later lease generation for stale-fence tests."""
        generation = self._generation.get(work_id, 0) + 1
        self._generation[work_id] = generation
        return WorkLease(work_id, generation, f"{work_id}:{generation}")

    def is_current(self, lease: WorkLease) -> bool:
        """Check the exact generation and fencing token."""
        return (
            self._generation.get(lease.work_id) == lease.generation
            and lease.fencing_token == f"{lease.work_id}:{lease.generation}"
        )

    def interrupt(self, lease: WorkLease) -> None:
        """Record bounded cooperative interruption."""
        self.interruptions.append(lease.fencing_token)

    def check(self) -> bool:
        """Perform one non-mutating local readiness check."""
        return True


class WorkerRuntime:
    """One no-ingress worker revision with cooperative shutdown."""

    configuration: ApplicationConfiguration
    task_hub: LocalTaskHub
    effect: DisabledEffectPort
    effects: tuple[DisabledEffectPort, ...]
    configuration_source: LocalConfigurationSource
    accepting_work: bool
    current_lease: WorkLease | None

    def __init__(
        self,
        configuration: ApplicationConfiguration,
        task_hub: LocalTaskHub,
        effect: DisabledEffectPort,
        additional_effects: tuple[DisabledEffectPort, ...] = (),
    ) -> None:
        """Create one worker revision from explicit adapters."""
        if configuration.task_hub is None:
            msg = "worker configuration requires one task hub"
            raise ValueError(msg)
        self.configuration = configuration
        self.task_hub = task_hub
        self.effect = effect
        self.effects = (effect, *additional_effects)
        self.configuration_source = LocalConfigurationSource(configuration)
        self.accepting_work = True
        self.current_lease = None

    def run_once(self, work: Callable[[WorkLease], None]) -> WorkerResultCode:
        """Run one bounded unit only while its fence remains current."""
        if not self.accepting_work:
            return WorkerResultCode.NO_WORK
        lease = self.task_hub.claim()
        if lease is None:
            return WorkerResultCode.NO_WORK
        self.current_lease = lease
        if not self.task_hub.is_current(lease):
            self.current_lease = None
            return WorkerResultCode.STALE_FENCE
        work(lease)
        if self._was_interrupted():
            return WorkerResultCode.INTERRUPTED
        if not self.task_hub.is_current(lease):
            self.current_lease = None
            return WorkerResultCode.STALE_FENCE
        self.current_lease = None
        return WorkerResultCode.CLAIMED

    def _was_interrupted(self) -> bool:
        return self.current_lease is None

    def shutdown(self) -> WorkerResultCode:
        """Stop intake and record any in-flight claim as interrupted."""
        self.accepting_work = False
        lease = self.current_lease
        if lease is None:
            return WorkerResultCode.NO_WORK
        self.task_hub.interrupt(lease)
        self.current_lease = None
        return WorkerResultCode.INTERRUPTED

    def ready(self) -> bool:
        """Validate only local configuration and task-hub reachability."""
        return (
            self.configuration_source.is_current(self.configuration.configuration_fingerprint)
            and self.task_hub.check()
        )
