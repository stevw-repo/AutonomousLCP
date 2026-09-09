"""Restart-safe file-backed Serving State compare-and-set port."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import (
    PromotionError,
    PromotionErrorCode,
    ServingStateCandidate,
    ServingStateReceipt,
)

_SCHEMA = "asklegal.local-serving-state/v1"


def initial_serving_state_bytes(active_state_id: str) -> bytes:
    """Freeze an empty retained Serving State projection for one predecessor."""
    if not active_state_id.startswith("srv_"):
        message = "invalid initial Serving State"
        raise ValueError(message)
    return canonicalize(
        checked_json_value(
            {
                "activation": None,
                "active_state_id": active_state_id,
                "rollback": None,
                "schema_id": _SCHEMA,
            }
        )
    )


def _candidate(value: ServingStateCandidate) -> dict[str, str]:
    return {
        "approval_id": value.approval_id,
        "candidate_serving_state_id": value.state_id,
        "candidate_serving_state_fingerprint": value.state_fingerprint,
        "coverage_fingerprint": value.coverage_fingerprint,
        "desired_inventory_fingerprint": value.desired_inventory_fingerprint,
        "embedding_profile_fingerprint": value.embedding_profile_fingerprint,
        "embedding_profile_id": value.embedding_profile_id,
        "execution_lineage_id": value.execution_lineage_id,
        "predecessor_state_id": value.predecessor_state_id,
        "target_name": value.target_name,
    }


def _receipt(operation: str, predecessor: str, state: str, fingerprint: str) -> ServingStateReceipt:
    material = canonicalize(
        checked_json_value(
            {
                "candidate_fingerprint": fingerprint,
                "operation": operation,
                "predecessor_state_id": predecessor,
                "state_id": state,
            }
        )
    )
    return ServingStateReceipt(
        f"ssr_{sha256(material).hexdigest()[:48]}",
        operation,
        predecessor,
        state,
        fingerprint,
    )


def _entry(candidate: ServingStateCandidate, receipt: ServingStateReceipt) -> dict[str, object]:
    return {"candidate": _candidate(candidate), "receipt_id": receipt.receipt_id}


class FileServingStateStore:
    """Atomic retained Serving State CAS with exact replay after process restart."""

    def __init__(self, state_path: Path) -> None:
        """Open one existing canonical non-symlink retained projection."""
        if state_path.is_symlink() or not state_path.is_file():
            raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT, "Serving State unavailable")
        self._state_path = state_path
        self._load()

    @property
    def active_state_id(self) -> str:
        """Reread the current exact Serving State identity."""
        value = self._load().get("active_state_id")
        if type(value) is not str:
            raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT)
        return value

    def canonical_bytes(self) -> bytes:
        """Reread the exact canonical retained state for owner evidence."""
        return canonicalize(checked_json_value(self._load()))

    def activate(self, expected_base: str, candidate: ServingStateCandidate) -> ServingStateReceipt:
        """Atomically compare-and-set or exactly replay one activation."""
        with exclusive_local_state_lock(self._state_path):
            document = self._load()
            retained = document.get("activation")
            expected_receipt = _receipt(
                "ACTIVATED", expected_base, candidate.state_id, candidate.state_fingerprint
            )
            entry = _entry(candidate, expected_receipt)
            if retained == entry and document.get("active_state_id") == candidate.state_id:
                return ServingStateReceipt(
                    expected_receipt.receipt_id,
                    expected_receipt.operation,
                    expected_receipt.predecessor_state_id,
                    expected_receipt.state_id,
                    expected_receipt.candidate_fingerprint,
                    replayed=True,
                )
            if (
                document.get("active_state_id") != expected_base
                or candidate.predecessor_state_id != expected_base
                or retained is not None
            ):
                raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT)
            next_document = dict(document)
            next_document["activation"] = checked_json_value(entry)
            next_document["active_state_id"] = candidate.state_id
            self._write(next_document)
            return expected_receipt

    def verify(self, candidate_state_id: str) -> None:
        """Reread and verify the active candidate identity."""
        if self.active_state_id != candidate_state_id:
            raise PromotionError(PromotionErrorCode.POST_CUTOVER_FAILED)

    def rollback(
        self,
        candidate: ServingStateCandidate,
        activation_receipt_id: str,
    ) -> ServingStateReceipt:
        """Atomically reverse or replay the exact retained activation."""
        with exclusive_local_state_lock(self._state_path):
            document = self._load()
            activation = document.get("activation")
            expected_activation = _entry(
                candidate,
                _receipt(
                    "ACTIVATED",
                    candidate.predecessor_state_id,
                    candidate.state_id,
                    candidate.state_fingerprint,
                ),
            )
            receipt = _receipt(
                "ROLLED_BACK",
                candidate.state_id,
                candidate.predecessor_state_id,
                candidate.state_fingerprint,
            )
            rollback_entry = _entry(candidate, receipt)
            if (
                document.get("rollback") == rollback_entry
                and document.get("active_state_id") == candidate.predecessor_state_id
            ):
                return ServingStateReceipt(
                    receipt.receipt_id,
                    receipt.operation,
                    receipt.predecessor_state_id,
                    receipt.state_id,
                    receipt.candidate_fingerprint,
                    replayed=True,
                )
            if (
                activation != expected_activation
                or activation_receipt_id != expected_activation["receipt_id"]
                or document.get("active_state_id") != candidate.state_id
                or document.get("rollback") is not None
            ):
                raise PromotionError(PromotionErrorCode.POST_CUTOVER_FAILED)
            next_document = dict(document)
            next_document["active_state_id"] = candidate.predecessor_state_id
            next_document["rollback"] = checked_json_value(rollback_entry)
            self._write(next_document)
            return receipt

    def restore(
        self,
        candidate: ServingStateCandidate,
        rollback_receipt_id: str,
    ) -> ServingStateReceipt:
        """Atomically restore or replay the exact previously rolled-back candidate."""
        with exclusive_local_state_lock(self._state_path):
            document = self._load()
            rollback_receipt = _receipt(
                "ROLLED_BACK",
                candidate.state_id,
                candidate.predecessor_state_id,
                candidate.state_fingerprint,
            )
            expected_rollback = _entry(candidate, rollback_receipt)
            expected_activation = _entry(
                candidate,
                _receipt(
                    "ACTIVATED",
                    candidate.predecessor_state_id,
                    candidate.state_id,
                    candidate.state_fingerprint,
                ),
            )
            receipt = _receipt(
                "RESTORED",
                candidate.predecessor_state_id,
                candidate.state_id,
                candidate.state_fingerprint,
            )
            if (
                document.get("rollback") == expected_rollback
                and document.get("activation") == expected_activation
                and document.get("active_state_id") == candidate.state_id
                and rollback_receipt_id == rollback_receipt.receipt_id
            ):
                return ServingStateReceipt(
                    receipt.receipt_id,
                    receipt.operation,
                    receipt.predecessor_state_id,
                    receipt.state_id,
                    receipt.candidate_fingerprint,
                    replayed=True,
                )
            if (
                document.get("activation") != expected_activation
                or document.get("rollback") != expected_rollback
                or document.get("active_state_id") != candidate.predecessor_state_id
                or rollback_receipt_id != rollback_receipt.receipt_id
            ):
                raise PromotionError(PromotionErrorCode.POST_CUTOVER_FAILED)
            next_document = dict(document)
            next_document["active_state_id"] = candidate.state_id
            self._write(next_document)
            return receipt

    def _load(self) -> dict[str, JsonValue]:
        try:
            content = self._state_path.read_bytes()
            value = parse_json_bytes(content, max_bytes=1_000_000)
        except (OSError, RuntimeError, ValueError) as error:
            raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT) from error
        if (
            not isinstance(value, dict)
            or set(value) != {"activation", "active_state_id", "rollback", "schema_id"}
            or value.get("schema_id") != _SCHEMA
            or canonicalize(value) != content
        ):
            raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT)
        return value

    def _write(self, value: dict[str, JsonValue]) -> None:
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_bytes(canonicalize(checked_json_value(value)))
        temporary.replace(self._state_path)
