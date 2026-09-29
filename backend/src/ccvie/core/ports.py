"""Interfaces application code depends on. Adapters in ccvie.adapters implement them;
ccvie.bootstrap.container is the only place that picks an implementation."""

from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from ccvie.core.models import AccessFilter, MetadataFilter, RetrievedItem

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class EmbeddingModel(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def version(self) -> str: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    async def search(
        self,
        vector: Sequence[float],
        access: AccessFilter,
        filters: MetadataFilter,
        k: int,
    ) -> list[RetrievedItem]: ...


class KeywordIndex(Protocol):
    async def search(
        self,
        query: str,
        access: AccessFilter,
        filters: MetadataFilter,
        k: int,
    ) -> list[RetrievedItem]: ...


class RerankCandidate(BaseModel):
    item: RetrievedItem
    text: str


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: Sequence[RerankCandidate], top_n: int
    ) -> list[RerankCandidate]: ...


class ChatMessage(BaseModel):
    role: str
    content: str


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResult(BaseModel, Generic[SchemaT]):
    output: SchemaT
    usage: TokenUsage
    model: str
    latency_ms: float


class LLMClient(Protocol):
    async def generate(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        max_tokens: int,
    ) -> LLMResult[SchemaT]: ...


class GroundednessChecker(Protocol):
    async def entailment(self, claim: str, evidence: Sequence[str]) -> float: ...


class Cache(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, ttl_s: int) -> None: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...
