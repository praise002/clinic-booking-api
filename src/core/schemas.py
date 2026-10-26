from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """The body of every error response in the contract."""

    error: str = Field(description="A short, human-readable reason.", examples=["slot not found"])


def error_doc(description: str, example: str) -> dict[str, Any]:
    """An OpenAPI `responses` entry for an error status, with its example message."""
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"example": {"error": example}}},
    }


INTERNAL_ERROR_DOC = error_doc("Unexpected server error.", "internal server error")
