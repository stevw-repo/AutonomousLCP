"""Small strict typed boundary models used by the contract spike."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

type NonEmptyString = Annotated[str, StringConstraints(min_length=1, strict=True)]
type SearchRecordId = Annotated[
    str,
    StringConstraints(pattern=r"^rec_[0-9a-f]{48}$", strict=True),
]


class ServingMetadataBoundary(BaseModel):
    """The exact closed six-field serving metadata envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    text: NonEmptyString
    country: NonEmptyString
    jurisdiction: NonEmptyString
    type: NonEmptyString
    source: NonEmptyString
    authority_note: NonEmptyString


class ServingRecordBoundary(BaseModel):
    """Strict typed binding after normative schema validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: SearchRecordId
    metadata: ServingMetadataBoundary
