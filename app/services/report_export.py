from __future__ import annotations

import json
import textwrap
from typing import Any


SUPPORTED_EXPORT_FORMATS = {"json", "markdown", "pdf"}


def export_report(report: dict[str, Any], export_format: str) -> tuple[bytes, str, str]:
    normalized_format = export_format.lower()
    if normalized_format == "json":
        return export_report_json(report), "application/json", "audit-report.json"
    if normalized_format == "markdown":
        return export_report_markdown(report).encode("utf-8"), "text/markdown; charset=utf-8", "audit-report.md"
    if normalized_format == "pdf":
        return export_report_pdf(report), "application/pdf", "audit-report.pdf"
    supported = ", ".join(sorted(SUPPORTED_EXPORT_FORMATS))
    raise ValueError(f"Unsupported export format '{export_format}'. Supported formats: {supported}")


def export_report_json(report: dict[str, Any]) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def export_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Enterprise Knowledge Audit Report",
        "",
        f"Question: {report['question']}",
        f"Overall risk: {report['overall_level']}",
        f"Finding count: {report['finding_count']}",
        "",
        "## Summary",
        "",
        str(report["summary"]),
        "",
        "## Findings",
        "",
    ]
    for index, finding in enumerate(report["findings"], start=1):
        lines.extend(
            [
                f"### {index}. {finding['title']}",
                "",
                f"- Level: {finding['level']}",
                f"- Rationale: {finding['rationale']}",
                f"- Recommendation: {finding['recommendation']}",
                f"- Evidence IDs: {', '.join(finding['evidence_ids'])}",
                "",
            ]
        )
    lines.extend(["## Evidence", ""])
    for index, evidence in enumerate(report["evidence"], start=1):
        lines.extend(
            [
                f"### Evidence {index}: {evidence['title']}",
                "",
                f"- Document ID: {evidence['document_id']}",
                f"- Chunk ID: {evidence['chunk_id']}",
                f"- Source: {evidence['source']}",
                f"- Location: {evidence['location_label']}",
                f"- Score: {evidence['score']}",
                "",
                str(evidence["excerpt"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def export_report_pdf(report: dict[str, Any]) -> bytes:
    markdown = export_report_markdown(report)
    lines = []
    for line in markdown.splitlines():
        if not line:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(line, width=88, replace_whitespace=False) or [""])
    return build_simple_pdf(lines)


def build_simple_pdf(lines: list[str]) -> bytes:
    page_width = 612
    page_height = 792
    margin_left = 54
    margin_top = 738
    line_height = 14
    lines_per_page = 48
    pages = [lines[index : index + lines_per_page] for index in range(0, len(lines), lines_per_page)] or [[]]

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + page_index * 2} 0 R" for page_index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))

    for page_index, page_lines in enumerate(pages):
        page_object_id = 3 + page_index * 2
        content_object_id = page_object_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        content = render_pdf_page_content(page_lines, margin_left, margin_top, line_height)
        objects.append(b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def render_pdf_page_content(lines: list[str], margin_left: int, margin_top: int, line_height: int) -> bytes:
    commands = ["BT", "/F1 10 Tf"]
    for line_index, line in enumerate(lines):
        y_position = margin_top - line_index * line_height
        commands.append(f"1 0 0 1 {margin_left} {y_position} Tm")
        commands.append(f"({escape_pdf_text(to_pdf_safe_text(line))}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def to_pdf_safe_text(value: str) -> str:
    return value.encode("latin-1", errors="replace").decode("latin-1")


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
