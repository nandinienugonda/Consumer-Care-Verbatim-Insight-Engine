"""ErrorResponse: the body of every non-2xx response."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    requestId: str
