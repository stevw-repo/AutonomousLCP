"""Promotion worker composition with every production effect disabled locally."""

from asklegal_application_runtime import (
    DisabledEffectPort,
    LocalTaskHub,
    WorkerRuntime,
    build_local_configuration,
)


def create_runtime(task_hub: LocalTaskHub | None = None) -> WorkerRuntime:
    """Build one exact local promotion-worker revision without HTTP ingress."""
    configuration = build_local_configuration(
        "PROMOTION_WORKER",
        audience="api://asklegal-promotion-worker",
        client="asklegal-promotion-worker",
        task_hub="promotion-local-task-hub",
    )
    return WorkerRuntime(
        configuration,
        task_hub or LocalTaskHub(),
        DisabledEffectPort("embedding-provider"),
        (
            DisabledEffectPort("serving-target"),
            DisabledEffectPort("backup-store"),
            DisabledEffectPort("routing"),
            DisabledEffectPort("recovery-store"),
        ),
    )
