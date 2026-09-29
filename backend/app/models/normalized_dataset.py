"""Strict domain models produced by the read-only source normalizer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Territory = Literal["east", "southeast", "southcenter"]


class StrictModel(BaseModel):
    """Reject unknown fields and keep normalized records immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class NormalizedRequest(StrictModel):
    """One request row, with its source provenance retained verbatim."""

    request_id: str = Field(
        description="Stable internal ID: territory:source_request_id."
    )
    source_request_id: str
    source_order: int = Field(ge=0)
    source_line: int = Field(ge=2)
    territory: Territory
    source_filename: str
    source_address: str
    district: str
    bk_request_type: str
    hd_request_type: str
    gigabit_connection: str
    connection: str | None
    window_start: datetime
    window_end: datetime
    source_fields: dict[str, str]

    @model_validator(mode="after")
    def validate_time_window(self) -> NormalizedRequest:
        """Require a complete Moscow-aware, forward-moving source window."""

        for value in (self.window_start, self.window_end):
            if value.tzinfo is None or value.tzname() != "MSK":
                raise ValueError("Normalized time windows must use Europe/Moscow")
        if self.window_end <= self.window_start:
            raise ValueError("Normalized window_end must be later than window_start")
        return self


class NormalizedOffice(StrictModel):
    """One office service row; it is deliberately not a request."""

    office_id: str = Field(description="Stable office ID: office:territory.")
    territory: Territory
    source_filename: str
    source_line: int = Field(ge=2)
    source_address: str


class NormalizedDataset(StrictModel):
    """The three normalized territories in source-file order."""

    requests: tuple[NormalizedRequest, ...]
    offices: tuple[NormalizedOffice, ...]
