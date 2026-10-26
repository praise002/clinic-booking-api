from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """A naive datetime is taken to be UTC; an aware one is converted to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_slot_time(value: datetime) -> str:
    """`2026-12-10T09:00:00Z`, with fractional seconds only when they are non-zero."""
    text = as_utc(value).replace(tzinfo=None).isoformat()
    return f"{text}Z"


def format_created_at(value: datetime) -> str:
    """`2026-10-25T23:18:20.836Z`: always milliseconds, as in the contract's examples."""
    text = as_utc(value).replace(tzinfo=None).isoformat(timespec="milliseconds")
    return f"{text}Z"
