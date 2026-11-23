from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from ltc.platform.config import get_settings


from ltc.modules.customer_operation.application.email_attachment_models import EmailAttachmentInput


@dataclass(frozen=True)
class StoredEmailAttachment:
    storage_key: str
    safe_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    extracted_text: str
    extraction_status: str


class EmailAttachmentService:
    def __init__(
        self,
        *,
        root: Path | str | None = None,
        max_file_bytes: int | None = None,
        max_message_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.root = Path(root or settings.mail_attachment_dir).resolve()
        self.max_file_bytes = int(max_file_bytes or settings.mail_attachment_max_file_bytes)
        self.max_message_bytes = int(max_message_bytes or settings.mail_attachment_max_message_bytes)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(str(filename or "attachment.bin").replace("\\", "/")).name
        cleaned = re.sub(r"[^A-Za-z0-9._-一-鿿]+", "_", name).strip("._")
        return cleaned or "attachment.bin"

    def resolve_path(self, storage_key: str) -> Path:
        candidate = (self.root / str(storage_key or "")).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Invalid attachment storage key.") from exc
        return candidate

    def store(self, attachment: EmailAttachmentInput, *, scope_key: str) -> StoredEmailAttachment:
        content = bytes(attachment.content)
        if len(content) > self.max_file_bytes:
            raise ValueError("Attachment file size exceeds the configured limit.")
        safe_filename = self._safe_filename(attachment.filename)
        safe_scope = re.sub(r"[^A-Za-z0-9._-]+", "_", str(scope_key or "email"))
        storage_key = f"email-attachments/{safe_scope}/{uuid4()}-{safe_filename}"
        destination = self.resolve_path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        extracted_text, extraction_status = self._extract(safe_filename, attachment.content_type, content)
        return StoredEmailAttachment(
            storage_key=storage_key,
            safe_filename=safe_filename,
            content_type=str(attachment.content_type or "application/octet-stream"),
            size_bytes=len(content),
            sha256=sha256(content).hexdigest(),
            extracted_text=extracted_text,
            extraction_status=extraction_status,
        )

    def _extract(self, filename: str, content_type: str, content: bytes) -> tuple[str, str]:
        suffix = Path(filename).suffix.lower()
        try:
            if suffix == ".txt" or content_type.startswith("text/plain"):
                return content.decode("utf-8", errors="replace").strip(), "extracted"
            if suffix == ".pdf" or content_type == "application/pdf":
                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
                return text.strip(), "extracted"
            if suffix == ".docx":
                document = Document(BytesIO(content))
                return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text).strip(), "extracted"
            if suffix == ".xlsx":
                workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
                values = []
                for sheet in workbook.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        values.extend(str(value) for value in row if value is not None)
                workbook.close()
                return "\n".join(values).strip(), "extracted"
        except Exception:
            return "", "failed"
        return "", "unsupported"
