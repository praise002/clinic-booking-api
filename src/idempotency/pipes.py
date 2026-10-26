import hashlib
import json
from typing import Any

from src.idempotency.constants import MAX_KEY_LENGTH
from src.idempotency.exceptions import IdempotencyKeyTooLong


def parse_key(header: str | None) -> str | None:
    """The Idempotency-Key header, or None when it's absent or blank."""
    if header is None or not header.strip():
        return None
    if len(header) > MAX_KEY_LENGTH:
        raise IdempotencyKeyTooLong()
    return header


def body_hash(body: dict[str, Any]) -> str:
    """SHA-256 of the parsed body in one canonical form.

    "Same body" means the same fields and values: key order and whitespace don't count.
    """
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
