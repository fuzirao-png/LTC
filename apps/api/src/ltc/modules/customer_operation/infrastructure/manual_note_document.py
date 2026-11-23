"""Read Word mail documents without storing files or changing customer data."""

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 30 * 1024 * 1024
MAX_TEXT_CHARACTERS = 100_000


def _block_text(block: Paragraph | Table) -> str:
    if isinstance(block, Paragraph):
        return block.text
    rows = []
    seen_cells = set()
    for row in block.rows:
        cells = []
        for cell in row.cells:
            # Merged cells share an XML element; include their text only once.
            if cell._tc in seen_cells:
                continue
            seen_cells.add(cell._tc)
            cells.append("\n".join(_block_text(item) for item in cell.iter_inner_content()).strip())
        rows.append("\t".join(cells))
    return "\n".join(rows)


def read_manual_note_document(filename: str, content: bytes) -> dict[str, str]:
    filename = PurePosixPath(filename.replace("\\", "/")).name
    if not filename.lower().endswith(".docx"):
        raise ValueError("仅支持 .docx 格式的 Word 文件；旧版 .doc 请先另存为 .docx。")
    if not content:
        raise ValueError("文件为空，请选择包含邮件正文的 Word 文件。")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Word 文件不能超过 10 MB。")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("Word 文件解压后过大，请拆分文档后导入。")
            if "word/document.xml" not in archive.namelist():
                raise ValueError("文件不是有效的 Word 文档，请重新另存为 .docx 后导入。")
    except BadZipFile as exc:
        raise ValueError("无法读取 Word 文件，请确认文件未损坏或加密，并另存为 .docx 后重试。") from exc

    try:
        document = Document(BytesIO(content))
        raw_text = "\n".join(_block_text(block) for block in document.iter_inner_content()).strip()
    except Exception as exc:
        raise ValueError("无法读取 Word 文件，请确认文件未损坏或加密，并另存为 .docx 后重试。") from exc
    if not raw_text:
        raise ValueError("文档中没有可提取的文字；请使用包含邮件正文的 Word 文件，暂不支持纯图片文档。")
    if len(raw_text) > MAX_TEXT_CHARACTERS:
        raise ValueError("文档正文超过 10 万字，请拆分后导入。")
    return {"filename": filename, "rawText": raw_text}
