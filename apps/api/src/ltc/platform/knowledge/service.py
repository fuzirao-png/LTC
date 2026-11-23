from __future__ import annotations

from dataclasses import dataclass

from .client import WeKnoraClient
from .models import KnowledgeSearchItem, KnowledgeSearchResult


class KnowledgeNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class KnowledgeService:
    client: WeKnoraClient | None
    default_knowledge_base_ids: tuple[str, ...] = ()

    def search(self, *, query: str, knowledge_base_ids: list[str] | None, limit: int) -> KnowledgeSearchResult:
        selected_ids = [value.strip() for value in (knowledge_base_ids or self.default_knowledge_base_ids) if value.strip()]
        if self.client is None or not selected_ids:
            raise KnowledgeNotConfiguredError("WeKnora is not configured")
        raw_items = self.client.search(query=query.strip(), knowledge_base_ids=selected_ids, limit=limit)
        items = [
            KnowledgeSearchItem(
                id=str(item.get("id", "")),
                content=str(item.get("content", "")),
                knowledge_id=_optional_string(item.get("knowledge_id")),
                knowledge_title=_optional_string(item.get("knowledge_title")),
                knowledge_filename=_optional_string(item.get("knowledge_filename")),
                knowledge_source=_optional_string(item.get("knowledge_source")),
                score=_optional_float(item.get("score")),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
            for item in raw_items
            if str(item.get("content", "")).strip()
        ]
        return KnowledgeSearchResult(query=query.strip(), items=items, knowledge_base_ids=selected_ids)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
