"""PrincipalView: what the UI may know about the signed-in caller."""

from uuid import UUID

from pydantic import BaseModel


class PrincipalView(BaseModel):
    userId: str
    tenantId: UUID
    roles: list[str]
    capabilities: list[str]
    regions: list[str] | None = None
    brands: list[str] | None = None
