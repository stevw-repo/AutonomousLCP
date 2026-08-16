"""No-ingress legal-processing-worker process boundary."""

APPLICATION_NAME: str = "legal-processing-worker"
CAPABILITY_PORTS: tuple[str, ...] = (
    "candidate_record_write",
    "corpus_construction",
    "durable_legal_processing_work",
    "evidence_read",
    "generative_llm_provider",
    "legal_interpretation",
    "processing_evidence_write",
)

from asklegal_legal_processing_worker.runtime import create_runtime
from asklegal_legal_processing_worker.service import LegalProcessingService

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS", "LegalProcessingService", "create_runtime"]
