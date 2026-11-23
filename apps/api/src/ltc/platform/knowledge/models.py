from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSearchItem(BaseModel):
    id: str
    content: str
    knowledge_id: str | None = None
    knowledge_title: str | None = None
    knowledge_filename: str | None = None
    knowledge_source: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResult(BaseModel):
    query: str
    items: list[KnowledgeSearchItem]
    knowledge_base_ids: list[str]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    knowledge_base_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)
    limit: int = Field(default=10, ge=1, le=50)
