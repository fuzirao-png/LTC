from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WeKnoraProviderError(RuntimeError):
    """Raised when WeKnora cannot return a valid search response."""


@dataclass(frozen=True)
class WeKnoraClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 20.0

    def search(self, *, query: str, knowledge_base_ids: list[str], limit: int) -> list[dict[str, object]]:
        payload: dict[str, object] = {"query": query}
        if len(knowledge_base_ids) == 1:
            payload["knowledge_base_id"] = knowledge_base_ids[0]
        else:
            payload["knowledge_base_ids"] = knowledge_base_ids
        request = Request(
            f"{self.base_url}/api/v1/knowledge-search",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise WeKnoraProviderError("WeKnora knowledge search request failed") from error
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as error:
            raise WeKnoraProviderError("WeKnora returned invalid JSON") from error
        if not isinstance(body, dict) or body.get("success") is False:
            raise WeKnoraProviderError("WeKnora rejected the knowledge search request")
        data = body.get("data", [])
        if not isinstance(data, list):
            raise WeKnoraProviderError("WeKnora returned an invalid data field")
        return [item for item in data[:limit] if isinstance(item, dict)]
