from datetime import datetime
import uuid

from pydantic import BaseModel, Field, field_serializer

from src.bookings.models import Booking
from src.core.timefmt import format_created_at


class BookingRequest(BaseModel):
    """The documented shape of the `POST /bookings` body.

    Used for the OpenAPI docs only: the router parses the body by hand so that every
    validation failure is a 400 with a contract message.
    """

    model_config = {
        "json_schema_extra": {
            "examples": [{"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}]
        }
    }

    slot_id: str = Field(description="The id of the slot to book.")
    name: str = Field(description="The patient's name.")
    email: str = Field(description="The patient's email.")


class BookingResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "7e473ed0-6b98-4b73-a3c2-2b4ede2e91cb",
                    "slot_id": "s1",
                    "name": "Ada Obi",
                    "email": "ada@example.com",
                    "status": "confirmed",
                    "created_at": "2026-10-25T23:18:20.836Z",
                }
            ]
        }
    }

    id: uuid.UUID = Field(description="The booking id (UUID). Use it to look the booking up.")
    slot_id: str
    name: str
    email: str
    status: str = Field(description="`confirmed` or `cancelled`.")
    created_at: datetime = Field(description="UTC with milliseconds and a `Z` suffix.")

    @field_serializer("id")
    def format_id(self, value: uuid.UUID) -> str:
        return str(value)

    @field_serializer("created_at")
    def format_time(self, value: datetime) -> str:
        return format_created_at(value)

    @classmethod
    def from_model(cls, booking: Booking) -> "BookingResponse":
        return cls(
            id=booking.id,
            slot_id=booking.slot_id,
            name=booking.name,
            email=booking.email,
            status=booking.status,
            created_at=booking.created_at,
        )
