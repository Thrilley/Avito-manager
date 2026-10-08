"""Normalized source contract, independent of unverified Avito HTTP methods."""
from decimal import Decimal
from typing import Iterator, Protocol, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

class SourceItem(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    external_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=250)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    description: str | None = None
    url: HttpUrl | None = None
    external_status: str | None = Field(default=None, max_length=100)
    # Default unavailable: an unknown source status must not activate a product.
    catalog_status: Literal['active', 'archived'] = 'archived'

class SourcePage(BaseModel):
    items: list[SourceItem]
    complete: bool = False

class CatalogSource(Protocol):
    def pages(self) -> Iterator[SourcePage]: ...

class SourceUnavailable(Exception):
    pass

class AvitoSource:
    def pages(self):
        raise SourceUnavailable('Official API contract and account permissions are not verified')
