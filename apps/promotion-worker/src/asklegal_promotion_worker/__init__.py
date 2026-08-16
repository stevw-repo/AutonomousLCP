"""Declarative promotion-worker boundary; no production effects."""

APPLICATION_NAME: str = "promotion-worker"
CAPABILITY_PORTS: tuple[str, ...] = (
    "approved_manifest_read",
    "asklegal_routing",
    "backup_mutation",
    "durable_promotion_work",
    "embedding_provider",
    "pinecone_mutation",
    "recovery_copy",
    "serving_state_write",
)

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS"]
