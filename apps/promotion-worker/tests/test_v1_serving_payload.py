"""The six serving fields must survive the hop between embed and upsert.

They did not once. `embed_records` returned only the record id, the text and the
vector, so by the time `upsert_records` rebuilt a target record the country,
jurisdiction, type, source and authority note were gone. Fixing the adapter alone
would not have been enough, because the fields were already lost here.
"""

import pytest
from asklegal_promotion import serving_metadata, serving_metadata_fingerprint
from asklegal_promotion_worker.v1_pipeline import (
    PromotionPipelineError,
    PromotionRecordInput,
    _target_record,
)

_RECORD = {
    "record_id": "rec_1",
    "text": "A person who is disqualified may not drive.",
    "country": "HK",
    "jurisdiction": "HKSAR",
    "type": "ORDINANCE",
    "source": "HKEL",
    "authority_note": "WARNING: reconstructed from the amending instrument",
}


def test_the_six_fields_survive_the_embed_to_upsert_hop() -> None:
    """What the embed activity emits must still carry the whole payload."""
    parsed = PromotionRecordInput.from_json(_RECORD)
    embedded = {**parsed.to_json(), "vector": [0.1, 0.2], "vector_fingerprint": "sha256:x"}

    record = _target_record(embedded)

    assert record.authority_note == "WARNING: reconstructed from the amending instrument"
    assert record.country == "HK"
    assert record.jurisdiction == "HKSAR"
    assert record.material_type == "ORDINANCE"
    assert record.source == "HKEL"


def test_the_fingerprint_describes_the_payload_that_will_be_written() -> None:
    """The content fingerprint must be of the payload, not of the vector."""
    parsed = PromotionRecordInput.from_json(_RECORD)
    embedded = {**parsed.to_json(), "vector": [0.1], "vector_fingerprint": "sha256:" + "9" * 64}

    record = _target_record(embedded)

    assert record.content_fingerprint == serving_metadata_fingerprint(serving_metadata(record))
    assert record.content_fingerprint != "sha256:" + "9" * 64


@pytest.mark.parametrize(
    "missing",
    ["text", "country", "jurisdiction", "type", "source", "authority_note"],
)
def test_a_record_missing_any_serving_field_is_refused(missing: str) -> None:
    """A record cannot be served honestly without all six fields."""
    incomplete = {key: value for key, value in _RECORD.items() if key != missing}

    with pytest.raises(PromotionPipelineError) as error:
        PromotionRecordInput.from_json(incomplete)

    assert missing in str(error.value)
