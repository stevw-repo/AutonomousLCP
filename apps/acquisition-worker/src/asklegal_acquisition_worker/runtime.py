"""Acquisition worker composition with source and vault effects disabled locally."""

from asklegal_application_runtime import (
    DisabledEffectPort,
    LocalTaskHub,
    WorkerRuntime,
    build_local_configuration,
)


def create_runtime(task_hub: LocalTaskHub | None = None) -> WorkerRuntime:
    """Build one exact local acquisition-worker revision without HTTP ingress."""
    configuration = build_local_configuration(
        "ACQUISITION_WORKER",
        audience="api://asklegal-acquisition-worker",
        client="asklegal-acquisition-worker",
        task_hub="acquisition-local-task-hub",
    )
    return WorkerRuntime(
        configuration,
        task_hub or LocalTaskHub(),
        DisabledEffectPort("source"),
        (DisabledEffectPort("primary-evidence-vault"),),
    )
