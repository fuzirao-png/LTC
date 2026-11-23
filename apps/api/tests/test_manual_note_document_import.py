from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ltc.modules.customer_operation.infrastructure.manual_note_document import (
    read_manual_note_document,
)
from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context


def _word_file() -> bytes:
    stream = BytesIO()
    document = Document()
    document.add_paragraph("Subject: Q3 rollout")
    document.add_paragraph("The customer expects to decide before October.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Budget"
    table.cell(0, 1).text = "USD 50,000"
    table.cell(1, 0).text = "Decision maker"
    table.cell(1, 1).text = "CFO"
    document.save(stream)
    return stream.getvalue()


def _sales_actor() -> CurrentActor:
    return CurrentActor(uuid4(), "sales.actor", "Sales Actor", "sales", "MA", "EA", 10, 1, ())


class ManualNoteDocumentTests(unittest.TestCase):
    def test_reads_paragraphs_and_table_cells_in_document_order(self) -> None:
        result = read_manual_note_document("customer-email.docx", _word_file())

        self.assertEqual(result["filename"], "customer-email.docx")
        self.assertEqual(
            result["rawText"],
            "Subject: Q3 rollout\n"
            "The customer expects to decide before October.\n"
            "Budget\tUSD 50,000\n"
            "Decision maker\tCFO",
        )

    def test_rejects_legacy_doc_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "仅支持 .docx"):
            read_manual_note_document("customer-email.doc", b"legacy-word")

    def test_rejects_invalid_docx(self) -> None:
        with self.assertRaisesRegex(ValueError, "无法读取 Word 文件"):
            read_manual_note_document("customer-email.docx", b"not-a-word-document")


class ManualNoteDocumentRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = Mock()
        self.service.can_sales_access_company.return_value = True
        self.service.import_manual_note_document.return_value = {
            "filename": "customer-email.docx",
            "rawText": "Imported email body",
        }
        app = FastAPI()
        app.include_router(build_customer_operation_router(self.service), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    def test_upload_returns_editable_email_text_without_saving_a_note(self) -> None:
        company_id = uuid4()
        response = self.client.post(
            f"/api/v1/customers/{company_id}/manual-notes/import",
            files={
                "file": (
                    "customer-email.docx",
                    _word_file(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "filename": "customer-email.docx",
                "rawText": "Imported email body",
            },
        )
        self.service.import_manual_note_document.assert_called_once()
        self.service.confirm_manual_note.assert_not_called()
        self.service.trigger_manual_note_analysis.assert_not_called()


if __name__ == "__main__":
    unittest.main()
