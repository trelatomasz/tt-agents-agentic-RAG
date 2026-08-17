from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    request_id: str = Field(min_length=3, max_length=100)


class Citation(BaseModel):
    source_id: str
    catalog_version: str
    part_id: str
    label: str


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    catalog_version: str
    retrieval_score: float = Field(ge=0, le=1)
    degraded: bool = False


class ErrorBody(BaseModel):
    code: Literal[
        "CATALOG_STALE",
        "NO_EVIDENCE",
        "GROUNDING_FAILED",
        "DEPENDENCY_FAILED",
        "DEADLINE_EXCEEDED",
    ]
    message: str
    retryable: bool
    fallback: Literal["CONVENTIONAL_SEARCH", "RETRY", "NONE"]


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorBody
