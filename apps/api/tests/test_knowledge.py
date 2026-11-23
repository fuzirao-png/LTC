from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from ltc.platform.knowledge import KnowledgeService, WeKnoraClient


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class KnowledgeTests(unittest.TestCase):
    def test_client_uses_weknora_search_contract(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _Response({"success": True, "data": [{"id": "chunk-1", "content": "hello", "score": 0.9}]})

        with patch("ltc.platform.knowledge.client.urlopen", fake_urlopen):
            rows = WeKnoraClient("http://weknora", "secret", 4).search(query="hello", knowledge_base_ids=["kb-1"], limit=5)

        self.assertEqual(captured["url"], "http://weknora/api/v1/knowledge-search")
        self.assertEqual(captured["payload"], {"query": "hello", "knowledge_base_id": "kb-1"})
        self.assertEqual(rows[0]["id"], "chunk-1")

    def test_service_rejects_missing_configuration(self) -> None:
        with self.assertRaises(RuntimeError):
            KnowledgeService(None).search(query="hello", knowledge_base_ids=None, limit=5)


if __name__ == "__main__":
    unittest.main()
