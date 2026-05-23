"""
סכמות משותפות — pagination ועוד.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """תשובה עם דפדוף — נשלפת מ-/leads ו-endpoints דומים."""

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)


class PaginationParams(BaseModel):
    """פרמטרי דפדוף שמגיעים מ-query string."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
