"""Declarative legal-processing-worker boundary; no model access."""

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

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS"]
