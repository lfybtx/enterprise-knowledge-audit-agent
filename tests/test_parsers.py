from io import BytesIO

import pytest

from app.services.parsers import (
    EmptyDocumentError,
    UnsupportedFileTypeError,
    parse_document,
    parse_document_sections,
    parse_txt,
)


def test_parse_txt_utf8():
    text = parse_txt("客户名单导出必须经过区域经理审批，导出文件保存不得超过 7 天。".encode("utf-8"))
    assert "区域经理审批" in text


def test_parse_txt_gbk():
    text = parse_txt("客户信息访问必须完成数据保护培训，且不得私自导出。".encode("gbk"))
    assert "数据保护培训" in text


def test_parse_rejects_short_text():
    with pytest.raises(EmptyDocumentError):
        parse_txt("太短".encode("utf-8"))


def test_parse_rejects_unsupported_file_type():
    with pytest.raises(UnsupportedFileTypeError):
        parse_document("policy.exe", b"policy")


def test_parse_html_extracts_visible_blocks():
    file_type, text = parse_document(
        "policy.html",
        b"""
        <html>
          <head><style>.hidden{display:none}</style><script>alert('skip')</script></head>
          <body>
            <h1>Customer export policy</h1>
            <p>Customer export requires manager approval.</p>
            <ul><li>Retention cannot exceed seven days.</li></ul>
          </body>
        </html>
        """,
    )

    assert file_type == "html"
    assert "[HTML Paragraph 1]" in text
    assert "Customer export policy" in text
    assert "manager approval" in text
    assert "alert" not in text


def test_parse_pdf_preserves_page_marker():
    pytest.importorskip("pypdf")
    file_type, text = parse_document("policy.pdf", make_text_pdf("Export requires regional manager approval."))

    assert file_type == "pdf"
    assert "[Page 1]" in text
    assert "regional manager approval" in text


def test_parse_docx_extracts_paragraphs_and_tables():
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("客户名单导出必须由区域经理审批。")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "风险等级"
    table.cell(0, 1).text = "建议动作"
    table.cell(1, 0).text = "高"
    table.cell(1, 1).text = "保留审批记录"
    stream = BytesIO()
    document.save(stream)

    file_type, text = parse_document("policy.docx", stream.getvalue())

    assert file_type == "docx"
    assert "区域经理审批" in text
    assert "[Table 1 Row 2]" in text
    assert "建议动作" in text


def test_parse_xlsx_uses_sheet_and_header_labels():
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "客户导出"
    worksheet.append(["审批人", "保存期限"])
    worksheet.append(["区域经理", "7 天"])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    file_type, text = parse_document("policy.xlsx", stream.getvalue())

    assert file_type == "xlsx"
    assert "[Sheet: 客户导出]" in text
    assert "审批人: 区域经理" in text
    assert "保存期限: 7 天" in text


def test_parse_txt_sections_keep_line_numbers():
    parsed = parse_document_sections(
        "policy.txt",
        "客户名单导出必须经过区域经理审批。\n导出文件保存期限不得超过七天。".encode("utf-8"),
    )

    assert parsed.sections[0].location == {"kind": "lines", "start_line": 1, "end_line": 1}
    assert parsed.sections[1].location == {"kind": "lines", "start_line": 2, "end_line": 2}


def make_text_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(f'BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET'.encode('utf-8'))} >>\nstream\nBT /F1 12 Tf 72 720 Td ({escaped}) Tj ET\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, object_body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n{object_body}\nendobj\n".encode("utf-8"))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)
