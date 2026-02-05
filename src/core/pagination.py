"""Cursor-based pagination utilities."""

import base64
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorData(BaseModel):
    """Data encoded in a pagination cursor."""

    # Primary sort field value (e.g., created_at timestamp)
    sort_value: str
    # Unique identifier for tie-breaking
    id: str


def encode_cursor(sort_value: datetime | str, id_value: UUID) -> str:
    """Encode pagination cursor from sort value and ID.

    Args:
        sort_value: The value of the sort field (datetime or string)
        id_value: The unique ID for tie-breaking

    Returns:
        Base64-encoded cursor string
    """
    sort_str = sort_value.isoformat() if isinstance(sort_value, datetime) else str(sort_value)

    data = CursorData(sort_value=sort_str, id=str(id_value))
    json_str = data.model_dump_json()
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> CursorData:
    """Decode pagination cursor.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        CursorData with sort_value and id

    Raises:
        ValueError: If cursor is invalid
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(json_str)
        return CursorData(**data)
    except Exception as e:
        raise ValueError(f"Invalid cursor: {e}") from e


class CursorPage(BaseModel, Generic[T]):
    """A page of results with cursor pagination."""

    items: list[T] = Field(..., description="The items in this page")
    next_cursor: str | None = Field(
        None, description="Cursor for the next page, null if no more results"
    )
    has_more: bool = Field(..., description="Whether there are more results")


def create_cursor_page(
    items: list[T],
    limit: int,
    get_sort_value: Callable[[Any], datetime | str],
    get_id: Callable[[Any], UUID],
) -> CursorPage[T]:
    """Create a cursor page from a list of items.

    Args:
        items: List of items (should be limit + 1 to detect has_more)
        limit: The requested page size
        get_sort_value: Function to extract sort value from an item
        get_id: Function to extract ID from an item

    Returns:
        CursorPage with items, next_cursor, and has_more
    """
    has_more = len(items) > limit
    page_items = items[:limit]

    next_cursor = None
    if has_more and page_items:
        last_item = page_items[-1]
        next_cursor = encode_cursor(get_sort_value(last_item), get_id(last_item))

    return CursorPage(
        items=page_items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
