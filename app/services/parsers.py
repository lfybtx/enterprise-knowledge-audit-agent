from __future__ import annotations

from io import BytesIO
from pathlib import Path


SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".txt", ".xlsx"}


class UnsupportedFileTypeError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


class DocumentParseError(ValueError):
    pass


def parse_document(filename: str, content: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"Unsupported file type '{extension}'. Supported types: {supported}")

    if extension == ".txt":
        return "txt", parse_txt(content)
    if extension == ".pdf":
        return "pdf", parse_pdf(content)
    if extension == ".docx":
        return "docx", parse_docx(content)
    if extension == ".xlsx":
        return "xlsx", parse_xlsx(content)

    raise UnsupportedFileTypeError(f"Unsupported file type '{extension}'")


def parse_txt(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="ignore")

    return normalize_text(text)


def parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParseError("PDF parser is unavailable. Install pypdf first.") from exc

    try:
        reader = PdfReader(BytesIO(content))
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"[Page {page_number}]\n{page_text}")
    except Exception as exc:
        raise DocumentParseError("Unable to read this PDF. Please upload a valid, unencrypted PDF.") from exc

    if not pages:
        raise EmptyDocumentError(
            "PDF has no extractable text. It may be a scanned document and needs OCR before upload."
        )
    return normalize_text("\n\n".join(pages))


def parse_docx(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise DocumentParseError("Word parser is unavailable. Install python-docx first.") from exc

    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise DocumentParseError("Unable to read this Word document. Please upload a valid .docx file.") from exc

    sections = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table_number, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            sections.append(f"[Table {table_number}]\n" + "\n".join(rows))
    return normalize_text("\n\n".join(sections))


def parse_xlsx(content: bytes) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise DocumentParseError("Excel parser is unavailable. Install openpyxl first.") from exc

    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise DocumentParseError("Unable to read this Excel workbook. Please upload a valid .xlsx file.") from exc

    sections = []
    try:
        for worksheet in workbook.worksheets:
            rows = [
                [cell_to_text(value) for value in row]
                for row in worksheet.iter_rows(values_only=True)
            ]
            non_empty_rows = [row for row in rows if any(row)]
            if not non_empty_rows:
                continue

            headers = non_empty_rows[0]
            records = [f"[Sheet: {worksheet.title}]"]
            if len(non_empty_rows) == 1:
                records.append(" | ".join(headers))
            else:
                for row in non_empty_rows[1:]:
                    fields = []
                    for column_index, value in enumerate(row):
                        if not value:
                            continue
                        header = headers[column_index] if column_index < len(headers) and headers[column_index] else f"Column {column_index + 1}"
                        fields.append(f"{header}: {value}")
                    if fields:
                        records.append(" | ".join(fields))
            sections.append("\n".join(records))
    finally:
        workbook.close()

    return normalize_text("\n\n".join(sections))


def cell_to_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(text: str) -> str:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(normalized) < 20:
        raise EmptyDocumentError("Document text is too short after parsing")
    return normalized
