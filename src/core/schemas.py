from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """The body of every error response in the contract."""

    error: str = Field(description="A short, human-readable reason.", examples=["slot not found"])


def error_doc(description: str, *messages: str) -> dict[str, Any]:
    """An OpenAPI `responses` entry for an error status, with one example per message."""
    content: dict[str, Any] = (
        {"example": {"error": messages[0]}}
        if len(messages) == 1
        else {"examples": {message: {"value": {"error": message}} for message in messages}}
    )
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": content},
    }


INTERNAL_ERROR_DOC = error_doc("Unexpected server error.", "internal server error")
