from __future__ import annotations

import csv
import io
import uuid

from ..domain.models import CompanyCandidate, SearchRequest
from ..domain.field_mapping import normalize_company_intro


_INDUSTRIES = {"TMC", "TRAVEL_OTA", "FINTECH", "OTHER"}
_REGIONS = {"NA", "EA", "SEA", "EU", "ME", "OTHER"}


class LeadCandidateImportService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def import_csv(self, *, content: bytes, filename: str) -> dict:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 encoding.") from exc
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "company_name" not in reader.fieldnames:
            raise ValueError("CSV must include a company_name column.")
        rows = [row for row in reader if str(row.get("company_name") or "").strip()]
        if not rows:
            raise ValueError("CSV contains no valid company rows.")
        if len(rows) > 200:
            raise ValueError("CSV import is limited to 200 rows.")

        request = SearchRequest(
            query_text=f"manual upload: {filename}",
            search_mode="company_only",
            target_count=len(rows),
            scene_code="S1",
        )
        search_run_id, job_id = self.repository.create_search_run(request)
        self.repository.start_search_run(search_run_id)
        imported = 0
        try:
            for row in rows:
                name = str(row.get("company_name") or "").strip()
                website = str(row.get("website") or "").strip() or None
                industry = str(row.get("industry_code") or "").strip().upper() or None
                region = str(row.get("region_code") or "").strip().upper() or None
                employee_text = str(row.get("employee_count") or "").strip()
                employee_count = int(employee_text) if employee_text else None
                if industry not in _INDUSTRIES:
                    industry = "OTHER"
                if region not in _REGIONS:
                    region = "OTHER" if region else None
                stable_key = (website or name).strip().casefold()
                candidate = CompanyCandidate(
                    candidate_id=str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key)),
                    company_name=name,
                    website=website,
                    company_intro=normalize_company_intro(row.get("company_intro")),
                    industry_code=industry,
                    employee_count=employee_count,
                    region_code=region,
                    country_code=str(row.get("country_code") or "").strip().upper() or None,
                    city=str(row.get("city") or "").strip() or None,
                    raw_ai_output={"source": "manual_upload", "filename": filename},
                )
                self.repository.upsert_candidate(search_run_id=search_run_id, candidate=candidate)
                imported += 1
            self.repository.record_provider(
                search_run_id=search_run_id,
                job_id=job_id,
                provider_code="manual_upload",
                operation="csv_import",
                payload={"filename": filename},
                status="succeeded",
                result_count=imported,
            )
            self.repository.finish_search_run(
                search_run_id,
                job_id,
                status="completed",
                counts={"candidate_count": imported, "enriched_count": imported, "scored_count": 0},
            )
        except Exception as exc:
            self.repository.finish_search_run(
                search_run_id,
                job_id,
                status="failed",
                counts={"candidate_count": imported, "enriched_count": imported, "scored_count": 0},
                error=str(exc),
            )
            raise
        return {"search_run_id": search_run_id, "imported_count": imported}
