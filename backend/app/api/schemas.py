"""Request/response μοντέλα του API layer.

Τα response μοντέλα ενσωματώνουν (embed) τα υπάρχοντα StructuredResult /
SemanticResult του retrieval layer — δεν επαναλαμβάνουν τα πεδία τους.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.retrieval.models import SemanticResult, StructuredResult


class StructuredQueryRequest(BaseModel):
    person_id: str
    period: str
    operation: Literal["get_scores", "compare_periods", "top_bottom_sections"]
    other_period: Optional[str] = Field(
        default=None, description="Απαιτείται μόνο για operation='compare_periods'"
    )
    n: Optional[int] = Field(
        default=None, ge=1, description="Απαιτείται μόνο για operation='top_bottom_sections'"
    )

    @model_validator(mode="after")
    def _check_operation_fields(self) -> "StructuredQueryRequest":
        if self.operation == "compare_periods":
            if not self.other_period:
                raise ValueError("other_period είναι υποχρεωτικό για operation='compare_periods'")
            if self.n is not None:
                raise ValueError("n δεν επιτρέπεται για operation='compare_periods'")
        elif self.operation == "top_bottom_sections":
            if self.other_period is not None:
                raise ValueError("other_period δεν επιτρέπεται για operation='top_bottom_sections'")
        else:  # get_scores
            if self.other_period is not None or self.n is not None:
                raise ValueError("other_period/n δεν επιτρέπονται για operation='get_scores'")
        return self


class SemanticQueryRequest(BaseModel):
    person_id: str
    period: str
    question: str = Field(min_length=3)


class StructuredQueryResponse(BaseModel):
    result: StructuredResult
    audit_id: int


class SemanticQueryResponse(BaseModel):
    result: SemanticResult
    audit_id: int
