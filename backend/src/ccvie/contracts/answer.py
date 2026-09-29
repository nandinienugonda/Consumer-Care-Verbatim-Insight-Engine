"""QueryResponse: a verified, cited answer."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from ccvie.contracts.router import RoutingDecision


class AnswerState(StrEnum):
    ANSWER = "ANSWER"
    PARTIAL = "PARTIAL"
    CLARIFICATION = "CLARIFICATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REFUSAL = "REFUSAL"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"


class SourceKind(StrEnum):
    VERBATIM = "VERBATIM"
    FACT = "FACT"
    TOOL_RESULT = "TOOL_RESULT"


class SourceRef(BaseModel):
    handle: str = Field(pattern=r"^[SFT][1-9][0-9]*$")
    kind: SourceKind
    sourceId: str
    label: str | None = None


class Claim(BaseModel):
    text: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)


class DropReason(StrEnum):
    CITATION_MISSING = "CITATION_MISSING"
    CITATION_UNKNOWN = "CITATION_UNKNOWN"
    NUMBER_UNTRACED = "NUMBER_UNTRACED"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    UNSUPPORTED = "UNSUPPORTED"


class DroppedClaim(BaseModel):
    text: str
    reason: DropReason


class Groundedness(BaseModel):
    score: float = Field(ge=0, le=1)
    checkedClaims: int = Field(ge=0)
    droppedClaims: list[DroppedClaim] = Field(default_factory=list)
    verified: bool


class Usage(BaseModel):
    latencyMs: float = Field(ge=0)
    inputTokens: int = Field(default=0, ge=0)
    outputTokens: int = Field(default=0, ge=0)
    costUsd: float = Field(default=0, ge=0)
    cacheHits: int = Field(default=0, ge=0)


class QueryResponse(BaseModel):
    requestId: UUID
    answerState: AnswerState
    claims: list[Claim] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    routing: RoutingDecision
    groundedness: Groundedness
    degraded: list[str] = Field(default_factory=list)
    clarification: str | None = None
    usage: Usage
