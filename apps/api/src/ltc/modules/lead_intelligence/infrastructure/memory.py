"""File-backed lead memory compatible with the existing markdown corpus."""

from __future__ import annotations

import os
from pathlib import Path


class MarkdownMemory:
    def __init__(self, root: str | None = None) -> None:
        configured = root or os.getenv("LTC_LEAD_MEMORY_ROOT")
        if configured:
            self.root = Path(configured)
        else:
            # In the API image the application is rooted at /app; in local
            # development the relative path resolves from the repository.
            candidates = (
                Path("/app/data/lead_memory"),
                Path("data/lead_memory"),
                Path(__file__).resolve().parents[5] / "data" / "lead_memory",
            )
            self.root = next((path for path in candidates if path.exists()), candidates[0])

    def read(self, request) -> list[dict]:
        if not self.root.exists():
            return []
        scope_tokens = _scope_tokens(getattr(request, "query_text", ""))
        rows: list[dict] = []
        paths = [path for path in self.root.glob("*.md") if _path_matches_scope(path, scope_tokens)]
        for path in paths:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "|" not in line or line.lstrip().startswith("|---"):
                    continue
                cells = [part.strip() for part in line.strip().strip("|").split("|")]
                if cells and cells[0] and cells[0].lower() not in {"company", "company_name", "企业"}:
                    rows.append({"company_name": cells[0], "website": cells[2] if len(cells) > 2 else "", "source": str(path)})
        return rows

    def write(self, request, candidate) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        country = (candidate.country_code or "unknown").lower()
        path = self.root / f"{country}.md"
        if not path.exists():
            path.write_text("| company_name | domain | website | status |\n|---|---|---|---|\n", encoding="utf-8")
        content = path.read_text(encoding="utf-8")
        row = f"| {candidate.company_name} | {candidate.website or ''} | {candidate.website or ''} | enriched |\n"
        if candidate.company_name.casefold() not in content.casefold():
            path.write_text(content + row, encoding="utf-8")


def _scope_tokens(query_text: str) -> set[str]:
    text = str(query_text or "").casefold()
    if any(token in text for token in ("日本", "japan", "日文")):
        return {"jp", "日本", "东亚", "companies_by_region"}
    if any(token in text for token in ("美国", "美國", "united states", "usa", "us ")):
        return {"us", "美国", "北美", "companies_by_region"}
    if any(token in text for token in ("加拿大", "canada")):
        return {"ca", "加拿大", "北美", "companies_by_region"}
    if any(token in text for token in ("英国", "英國", "united kingdom", "uk")):
        return {"gb", "英国", "欧洲", "companies_by_region"}
    return set()


def _path_matches_scope(path: Path, tokens: set[str]) -> bool:
    return not tokens or any(token in path.stem.casefold() for token in tokens)
