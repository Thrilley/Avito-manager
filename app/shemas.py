from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

ListingStatus = Literal['active', 'reserved', 'sold', 'archived']
Condition = Literal['new', 'used']

class ListingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    title: str = Field(min_length=1, max_length=250)
    description: str
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    status: ListingStatus = 'active'
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    size: str | None = Field(default=None, min_length=1, max_length=30)
    condition: Condition | None = None
    currency: Literal['RUB'] = 'RUB'

class ListingResponse(ListingCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str  # Preserve legacy/external status values in responses.
    created_at: datetime

class ListingUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    status: ListingStatus | None = None
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    size: str | None = Field(default=None, min_length=1, max_length=30)
    condition: Condition | None = None

    @field_validator('title', 'description', 'price', 'status')
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError('Field cannot be null')
        return value

class ListingUpdateStatus(BaseModel):
    status: ListingStatus
