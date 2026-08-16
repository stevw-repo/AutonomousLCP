"""Legal-processing worker composition with model/vault effects disabled locally."""

from asklegal_application_runtime import (
    DisabledEffectPort,
    LocalTaskHub,
    WorkerRuntime,
    build_local_configuration,
)


def create_runtime(task_hub: LocalTaskHub | None = None) -> WorkerRuntime:
    """Build one exact local legal-processing revision without HTTP ingress."""
    configuration = build_local_configuration(
        "LEGAL_PROCESSING_WORKER",
        audience="api://asklegal-legal-processing-worker",
        client="asklegal-legal-processing-worker",
        task_hub="legal-processing-local-task-hub",
    )
    return WorkerRuntime(
        configuration,
        task_hub or LocalTaskHub(),
        DisabledEffectPort("generative-model"),
        (
            DisabledEffectPort("processing-evidence-vault"),
            DisabledEffectPort("candidate-release-store"),
        ),
    )
