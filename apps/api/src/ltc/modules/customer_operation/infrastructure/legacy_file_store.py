import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ltc.platform.config import get_settings


class LegacyFileStore:
    """Read/write adapter for the current 8787 demo data files.

    This lets the new customer-operation-agent own the code path gradually
    without breaking the frontend that still uses the old server.
    """

    def __init__(self, demo_dir: Path | None = None) -> None:
        settings = get_settings()
        self.demo_dir = demo_dir or settings.resolve_legacy_demo_dir() or self._fallback_demo_dir()

    def _fallback_demo_dir(self) -> Path:
        # Use writable path in container (source is mounted read-only)
        return Path("/app/data")

    @property
    def available(self) -> bool:
        return self.demo_dir is not None

    @property
    def data_dir(self) -> Path:
        if self.demo_dir is None:
            raise RuntimeError("Legacy demo directory was not found.")
        path = Path(self.demo_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _read_json_array(self, filename: str) -> list[dict[str, Any]]:
        if not self.available:
            return []
        path = self.data_dir / filename
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig") or "[]")
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _write_json_array(self, filename: str, items: list[dict[str, Any]]) -> None:
        if not self.available:
            return
        path = self.data_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _prepend_json_record(
        self,
        filename: str,
        record: dict[str, Any],
        *,
        limit: int = 500,
    ) -> dict[str, Any]:
        if not self.available:
            return record
        items = self._read_json_array(filename)
        items.insert(0, record)
        self._write_json_array(filename, items[:limit])
        return record

    def read_json_array(self, filename: str) -> list[dict[str, Any]]:
        return self._read_json_array(filename)

    def write_json_array(self, filename: str, items: list[dict[str, Any]]) -> None:
        self._write_json_array(filename, items)

    def prepend_json_record(
        self,
        filename: str,
        record: dict[str, Any],
        *,
        limit: int = 500,
    ) -> dict[str, Any]:
        return self._prepend_json_record(filename, record, limit=limit)

    def list_mail_history(self, customer_name: str | None = None) -> list[dict[str, Any]]:
        items = self._read_json_array("mail-history.json")
        if customer_name:
            items = [item for item in items if item.get("customerName") == customer_name]
        return items

    def append_mail_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if not record.get("id"):
            record["id"] = str(uuid4())
        if not self.available:
            return record
        return self._prepend_json_record("mail-history.json", record, limit=200)

    def list_meeting_history(self, customer_name: str | None = None) -> list[dict[str, Any]]:
        items = self._read_json_array("meeting-history.json")
        if customer_name:
            items = [item for item in items if item.get("customerName") == customer_name]
        return items

    def list_meeting_jobs(self, record_id: str | None = None) -> list[dict[str, Any]]:
        items = self._read_json_array("meeting-jobs.json")
        if record_id:
            items = [item for item in items if item.get("recordId") == record_id]
        return items

    def get_meeting_job(self, job_id: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        return next((item for item in self._read_json_array("meeting-jobs.json") if item.get("id") == job_id), None)

    def save_meeting_job(self, job: dict[str, Any]) -> dict[str, Any]:
        items = self._read_json_array("meeting-jobs.json")
        index = next((idx for idx, item in enumerate(items) if item.get("id") == job.get("id")), -1)
        if index >= 0:
            items[index] = job
        else:
            items.insert(0, job)
        self._write_json_array("meeting-jobs.json", items[:500])
        return job

    def append_meeting_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if not record.get("id"):
            record["id"] = str(uuid4())
        return self._prepend_json_record("meeting-history.json", record, limit=500)

    def meeting_audio_dir(self, customer_name: str) -> Path:
        safe_name = "".join(
            "-" if char in '<>:"/\\|?*' or ord(char) < 32 else char
            for char in (customer_name or "meeting").strip()
        )
        safe_name = "-".join(safe_name.split())[:80] or "meeting"
        return self.data_dir / "meeting-audios" / safe_name

    def get_meeting_audio_path(self, record_id: str) -> Path | None:
        record = next(
            (item for item in self.list_meeting_history() if item.get("id") == record_id),
            None,
        )
        if record is None:
            return None

        stored_file = record.get("storedFilePath")
        if not stored_file:
            return None

        path = Path(stored_file)
        if not path.exists():
            return None
        return path

    def delete_meeting_record(self, record_id: str) -> bool:
        items = self._read_json_array("meeting-history.json")
        record = next((item for item in items if item.get("id") == record_id), None)
        if record is None:
            return False

        next_items = [item for item in items if item.get("id") != record_id]
        self._write_json_array("meeting-history.json", next_items)

        stored_file = record.get("storedFilePath")
        if stored_file:
            path = Path(stored_file)
            if path.exists():
                path.unlink()

        jobs = self._read_json_array("meeting-jobs.json")
        self._write_json_array(
            "meeting-jobs.json",
            [item for item in jobs if item.get("recordId") != record_id],
        )
        return True



