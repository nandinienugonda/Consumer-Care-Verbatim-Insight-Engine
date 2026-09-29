"""Product, Pack, Region, IssueType, Verbatim."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class IssueType(StrEnum):
    packaging = "packaging"
    taste = "taste"
    shipping = "shipping"
    freshness = "freshness"
    quantity = "quantity"
    quality = "quality"
    damaged = "damaged"
    other = "other"


class PackType(StrEnum):
    bag = "bag"
    box = "box"
    bottle = "bottle"
    can = "can"


class VerbatimSource(StrEnum):
    call = "call"
    email = "email"
    social = "social"
    review = "review"
    survey = "survey"


class Product(BaseModel):
    id: UUID
    name: str
    category: str
    createdAt: datetime


class Pack(BaseModel):
    id: UUID
    productId: UUID
    size: str
    type: PackType
    launchDate: datetime


class Region(BaseModel):
    id: UUID
    name: str
    code: str


class Verbatim(BaseModel):
    id: UUID
    text: str
    productId: UUID
    packId: UUID
    regionId: UUID
    issueType: IssueType | None = None
    source: VerbatimSource
    timestamp: datetime
    customerSegment: str | None = None
    verbatimHash: str
