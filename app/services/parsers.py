from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt"}


class UnsupportedFileTypeError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


def parse_document(filename: str, content: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"Unsupported file type '{extension}'. Supported types: {supported}")

    if extension == ".txt":
        return "txt", parse_txt(content)

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

    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(normalized) < 20:
        raise EmptyDocumentError("Document text is too short after parsing")
    return normalized
