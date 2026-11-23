from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ltc.modules.customer_operation.infrastructure.email_attachment_service import (
    EmailAttachmentInput,
    EmailAttachmentService,
)


_ASSERTIONS = unittest.TestCase()


def test_store_txt_uses_generated_safe_path_and_extracts_text(tmp_path) -> None:
    service = EmailAttachmentService(root=tmp_path, max_file_bytes=1024, max_message_bytes=2048)

    stored = service.store(
        EmailAttachmentInput(
            filename="../proposal.txt",
            content_type="text/plain",
            content="方案一：年度采购方案".encode("utf-8"),
        ),
        scope_key="email-1",
    )

    assert stored.safe_filename == "proposal.txt"
    assert stored.storage_key.startswith("email-attachments/email-1/")
    assert stored.extracted_text == "方案一：年度采购方案"
    assert stored.extraction_status == "extracted"
    assert service.resolve_path(stored.storage_key).read_bytes() == "方案一：年度采购方案".encode("utf-8")


def test_docx_and_xlsx_extract_text(tmp_path) -> None:
    from docx import Document
    from openpyxl import Workbook

    document = Document()
    document.add_paragraph("方案二：企业年度方案")
    docx_buffer = BytesIO()
    document.save(docx_buffer)

    workbook = Workbook()
    workbook.active["A1"] = "最终条款"
    workbook.active["B1"] = "双方已签署"
    xlsx_buffer = BytesIO()
    workbook.save(xlsx_buffer)

    service = EmailAttachmentService(root=tmp_path)
    docx = service.store(EmailAttachmentInput("offer.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_buffer.getvalue()), scope_key="email-2")
    xlsx = service.store(EmailAttachmentInput("contract.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", xlsx_buffer.getvalue()), scope_key="email-2")

    assert "方案二" in docx.extracted_text
    assert "双方已签署" in xlsx.extracted_text


def test_pdf_extractor_collects_page_text(tmp_path) -> None:
    service = EmailAttachmentService(root=tmp_path)
    page = Mock()
    page.extract_text.return_value = "正式提案 option 1"
    reader = Mock(pages=[page])

    with patch("ltc.modules.customer_operation.infrastructure.email_attachment_service.PdfReader", return_value=reader):
        stored = service.store(EmailAttachmentInput("offer.pdf", "application/pdf", b"pdf"), scope_key="email-3")

    assert stored.extracted_text == "正式提案 option 1"
    assert stored.extraction_status == "extracted"


def test_unsupported_attachment_is_stored_without_extraction(tmp_path) -> None:
    service = EmailAttachmentService(root=tmp_path)
    stored = service.store(EmailAttachmentInput("image.png", "image/png", b"png"), scope_key="email-4")

    assert stored.extracted_text == ""
    assert stored.extraction_status == "unsupported"
    assert service.resolve_path(stored.storage_key).read_bytes() == b"png"


def test_attachment_size_and_storage_path_are_enforced(tmp_path) -> None:
    service = EmailAttachmentService(root=tmp_path, max_file_bytes=3, max_message_bytes=10)

    with _ASSERTIONS.assertRaisesRegex(ValueError, "file size"):
        service.store(EmailAttachmentInput("large.txt", "text/plain", b"1234"), scope_key="email-5")

    with _ASSERTIONS.assertRaisesRegex(ValueError, "storage key"):
        service.resolve_path("../../outside.txt")


def load_tests(loader, tests, pattern):
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for name, test in list(globals().items()):
        if not name.startswith("test_") or not callable(test):
            continue

        def run_with_temp_path(test=test):
            with TemporaryDirectory() as temp_dir:
                test(Path(temp_dir))

        suite.addTest(unittest.FunctionTestCase(run_with_temp_path, description=name))
    return suite
