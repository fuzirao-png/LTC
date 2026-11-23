from __future__ import annotations

from typing import Any
import unicodedata

from pydantic import BaseModel, Field, field_validator


DEFAULT_LEAD_SEARCH_TARGET = 500
MAX_LEAD_SEARCH_RESULTS = 2000


class LeadSearchRunCreate(BaseModel):
    query_text: str = Field(min_length=1, max_length=4000)
    search_mode: str = Field(default="both", pattern="^(company_only|contact_only|both)$")
    target_count: int = Field(
        default=DEFAULT_LEAD_SEARCH_TARGET,
        ge=1,
        le=MAX_LEAD_SEARCH_RESULTS,
    )
    scene_code: str = Field(default="S1", pattern="^(S1|S2|S3)$")

    @field_validator("query_text")
    @classmethod
    def normalize_query_text(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value).strip()
        # A run of replacement question marks is what Windows clients produce
        # when Chinese text is encoded with the wrong code page. Reject it
        # before it can become a permanent database value.
        question_marks = value.count("?")
        if question_marks >= 3 and question_marks >= len(value) // 3:
            raise ValueError("query_text appears to be encoding-corrupted; send the request as UTF-8")
        return value


class AcceptedData(BaseModel):
    resource_type: str
    resource_id: str
    job: dict[str, Any]


class AcceptedEnvelope(BaseModel):
    request_id: str
    data: AcceptedData
