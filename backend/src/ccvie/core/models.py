"""Internal domain types shared across layers. API shapes live in ccvie.contracts."""

import hashlib
import json
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Classification(StrEnum):
    """Data sensitivity, lowest first. Stored lowercase in the database."""

    INTERNAL = "internal"
    RESTRICTED = "restricted"

    @property
    def rank(self) -> int:
        return _CLASSIFICATION_ORDER.index(self)


_CLASSIFICATION_ORDER = (Classification.INTERNAL, Classification.RESTRICTED)


class Role(StrEnum):
    CARE_ANALYST = "care_analyst"
    QUALITY_MANAGER = "quality_manager"
    REGIONAL_MANAGER = "regional_manager"
    EXECUTIVE = "executive"
    INGEST_SERVICE = "ingest_service"
    PLATFORM_ADMIN = "platform_admin"


class Principal(BaseModel):
    """The verified caller. Built only from a verified token, never from a request body."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    tenant_id: UUID
    roles: frozenset[Role]
    scopes: frozenset[str] = frozenset()
    # None means the token carries no restriction on this dimension.
    regions: frozenset[str] | None = None
    brands: frozenset[str] | None = None


class AccessFilter(BaseModel):
    """What data a principal may see. Every retriever takes one; it can only be narrowed."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    regions: frozenset[str] | None
    brands: frozenset[str] | None
    max_classification: Classification

    def allows(
        self,
        *,
        tenant_id: UUID,
        region: str | None,
        brand: str | None,
        classification: Classification,
    ) -> bool:
        return (
            tenant_id == self.tenant_id
            and (self.regions is None or region in self.regions)
            and (self.brands is None or brand in self.brands)
            and classification.rank <= self.max_classification.rank
        )

    def fingerprint(self) -> str:
        canonical = {
            "tenant_id": str(self.tenant_id),
            "regions": sorted(self.regions) if self.regions is not None else None,
            "brands": sorted(self.brands) if self.brands is not None else None,
            "max_classification": self.max_classification.value,
        }
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


class MetadataFilter(BaseModel):
    """Relevance filters from entity resolution or the UI. Combined with AccessFilter by AND."""

    model_config = ConfigDict(frozen=True)

    products: frozenset[str] | None = None
    packs: frozenset[str] | None = None
    regions: frozenset[str] | None = None
    brands: frozenset[str] | None = None
    issue_types: frozenset[str] | None = None


class RetrievedItem(BaseModel):
    """One ranked verbatim from any retriever, carrying the attributes the post-filter checks."""

    model_config = ConfigDict(frozen=True)

    verbatim_id: UUID
    tenant_id: UUID
    region: str | None
    brand: str | None
    classification: Classification
    retriever: str
    rank: int = Field(ge=1)
    score: float
