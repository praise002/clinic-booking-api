from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from src.core.timefmt import as_utc, format_slot_time

NonEmptyStr = Annotated[str, StringConstraints(strict=True, min_length=1)]

SLOT_EXAMPLE = {
    "id": "s1",
    "provider": "Dr Ade",
    "start": "2026-12-10T09:00:00Z",
    "end": "2026-12-10T09:30:00Z",
}


class SlotIn(BaseModel):
    model_config = {"json_schema_extra": {"examples": [SLOT_EXAMPLE]}}

    id: NonEmptyStr = Field(description="Your id for the slot; booked by this id.")
    provider: NonEmptyStr = Field(description="Who the appointment is with.")
    start: datetime = Field(description="ISO 8601. A time without an offset is taken as UTC.")
    end: datetime = Field(description="ISO 8601. A time without an offset is taken as UTC.")

    @field_validator("start", "end")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class ResetRequest(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"slots": [SLOT_EXAMPLE]}]}}

    slots: list[SlotIn] = Field(description="Every slot to keep. Ids must be unique.")

    @model_validator(mode="after")
    def ids_are_unique(self) -> "ResetRequest":
        ids = [slot.id for slot in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError("slot ids must be unique")
        return self


class ResetResponse(BaseModel):
    status: str = Field(default="ok", examples=["ok"])


class SlotResponse(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{**SLOT_EXAMPLE, "available": True}]}}

    id: str
    provider: str
    start: datetime = Field(description="UTC, with a `Z` suffix.")
    end: datetime = Field(description="UTC, with a `Z` suffix.")
    available: bool = Field(
        description="`false` when the slot has a confirmed booking. A slot that has "
        "already started but isn't booked is still `true`; booking it returns 400."
    )

    @field_serializer("start", "end")
    def format_time(self, value: datetime) -> str:
        return format_slot_time(value)


class SlotListResponse(BaseModel):
    slots: list[SlotResponse] = Field(description="Earliest start first.")
