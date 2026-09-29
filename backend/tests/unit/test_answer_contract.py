from uuid import uuid4

import pytest
from pydantic import ValidationError

from ccvie.contracts.answer import (
    AnswerState,
    Claim,
    Groundedness,
    QueryResponse,
    SourceKind,
    SourceRef,
    Usage,
)
from ccvie.contracts.router import DecidedBy, QueryClass, RetrievalStrategy, RoutingDecision


def test_query_response_round_trips() -> None:
    response = QueryResponse(
        requestId=uuid4(),
        answerState=AnswerState.ANSWER,
        claims=[
            Claim(
                text="Leakage reports for the 500ml New Bottle rose in South.",
                citations=["S1", "F1"],
            )
        ],
        sources=[
            SourceRef(handle="S1", kind=SourceKind.VERBATIM, sourceId=str(uuid4())),
            SourceRef(handle="F1", kind=SourceKind.FACT, sourceId="count:leakage:south"),
        ],
        routing=RoutingDecision(
            queryClass=QueryClass.KNOWLEDGE,
            strategies=[RetrievalStrategy.VECTOR, RetrievalStrategy.STRUCTURED],
            confidence=0.9,
            decidedBy=DecidedBy.RULES,
        ),
        groundedness=Groundedness(score=1.0, checkedClaims=1, verified=True),
        usage=Usage(latencyMs=120.0),
    )
    assert QueryResponse.model_validate_json(response.model_dump_json()) == response


def test_claim_without_citation_is_invalid() -> None:
    with pytest.raises(ValidationError):
        Claim(text="Uncited claim", citations=[])


@pytest.mark.parametrize("handle", ["X1", "S0", "S", "1", "S1a"])
def test_source_handles_are_opaque_and_well_formed(handle: str) -> None:
    with pytest.raises(ValidationError):
        SourceRef(handle=handle, kind=SourceKind.VERBATIM, sourceId="x")
