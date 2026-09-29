"""RouteDecision (legacy, used by the frontend routing page) and RoutingDecision (ADR-0005)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class RouteDecision(StrEnum):
    graph = "graph"
    vector = "vector"


class QueryClass(StrEnum):
    KNOWLEDGE = "KNOWLEDGE"
    REAL_TIME_DATA = "REAL_TIME_DATA"
    TRANSACTIONAL = "TRANSACTIONAL"
    HYBRID = "HYBRID"


class RetrievalStrategy(StrEnum):
    VECTOR = "VECTOR"
    KEYWORD = "KEYWORD"
    GRAPH = "GRAPH"
    STRUCTURED = "STRUCTURED"


class DecidedBy(StrEnum):
    RULES = "RULES"
    PLANNER = "PLANNER"
    FALLBACK = "FALLBACK"


class RoutingDecision(BaseModel):
    queryClass: QueryClass
    strategies: list[RetrievalStrategy] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    decidedBy: DecidedBy
    reasons: list[str] = Field(default_factory=list)
