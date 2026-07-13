from __future__ import annotations

import json
import os
from pathlib import Path
from io import BytesIO
from typing import Any


SUPPORTED_EXPORT_FORMATS = {"json", "markdown", "pdf"}
PDF_FONT_NAME = "AuditReportUnicode"
PDF_FONT_CANDIDATES = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


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
                f"- Evidence refs: {', '.join(finding.get('evidence_refs', [])) or 'None'}",
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
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError as exc:
        raise RuntimeError("PDF export requires reportlab. Run: pip install -r requirements.txt") from exc

    registered_font = register_pdf_font(pdfmetrics, TTFont)
    if registered_font is None:
        raise RuntimeError(
            "PDF export requires a Unicode font. Set AUDIT_PDF_FONT_PATH to a Chinese-capable .ttf/.ttc font."
        )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Enterprise Knowledge Audit Report",
    )
    styles = build_pdf_styles(getSampleStyleSheet(), ParagraphStyle, colors)
    story = [
        Paragraph("Enterprise Knowledge Audit Report", styles["Title"]),
        Spacer(1, 7 * mm),
        Paragraph(f"<b>Question:</b> {escape_html(str(report['question']))}", styles["Body"]),
        Paragraph(f"<b>Overall risk:</b> {escape_html(str(report['overall_level']))}", styles["Body"]),
        Paragraph(f"<b>Finding count:</b> {report['finding_count']}", styles["Body"]),
        Spacer(1, 5 * mm),
        Paragraph("Summary", styles["Heading"]),
        Paragraph(escape_html(str(report["summary"])), styles["Body"]),
        Spacer(1, 5 * mm),
        Paragraph("Findings", styles["Heading"]),
    ]

    for index, finding in enumerate(report["findings"], start=1):
        story.extend(
            [
                Paragraph(f"{index}. {escape_html(str(finding['title']))}", styles["Subheading"]),
                Paragraph(f"<b>Level:</b> {escape_html(str(finding['level']))}", styles["Body"]),
                Paragraph(f"<b>Rationale:</b> {escape_html(str(finding['rationale']))}", styles["Body"]),
                Paragraph(f"<b>Recommendation:</b> {escape_html(str(finding['recommendation']))}", styles["Body"]),
                Paragraph(
                    f"<b>Evidence refs:</b> {escape_html(', '.join(finding.get('evidence_refs', [])) or 'None')}",
                    styles["Body"],
                ),
                Paragraph(f"<b>Evidence IDs:</b> {escape_html(', '.join(finding['evidence_ids']))}", styles["Body"]),
                Spacer(1, 3 * mm),
            ]
        )

    story.extend([Spacer(1, 4 * mm), Paragraph("Evidence", styles["Heading"])])
    for index, evidence in enumerate(report["evidence"], start=1):
        story.extend(
            [
                Paragraph(f"Evidence {index}: {escape_html(str(evidence['title']))}", styles["Subheading"]),
                Paragraph(f"<b>Source:</b> {escape_html(str(evidence['source']))}", styles["Body"]),
                Paragraph(f"<b>Location:</b> {escape_html(str(evidence['location_label']))}", styles["Body"]),
                Paragraph(f"<b>Score:</b> {evidence['score']}", styles["Body"]),
                Paragraph(escape_html(str(evidence["excerpt"])), styles["Quote"]),
                Spacer(1, 3 * mm),
            ]
        )

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()


def build_pdf_styles(sample_styles: Any, paragraph_style_class: Any, colors_module: Any) -> dict[str, Any]:
    base = {
        "fontName": PDF_FONT_NAME,
        "leading": 16,
        "wordWrap": "CJK",
        "spaceAfter": 6,
    }
    return {
        "Title": paragraph_style_class(
            "AuditTitle",
            parent=sample_styles["Title"],
            fontName=PDF_FONT_NAME,
            fontSize=18,
            leading=24,
            textColor=colors_module.HexColor("#10243f"),
            spaceAfter=10,
        ),
        "Heading": paragraph_style_class(
            "AuditHeading",
            parent=sample_styles["Heading2"],
            **base,
            fontSize=13,
            textColor=colors_module.HexColor("#10243f"),
        ),
        "Subheading": paragraph_style_class(
            "AuditSubheading",
            parent=sample_styles["Heading3"],
            **base,
            fontSize=11,
            textColor=colors_module.HexColor("#263b57"),
        ),
        "Body": paragraph_style_class(
            "AuditBody",
            parent=sample_styles["BodyText"],
            **base,
            fontSize=10,
        ),
        "Quote": paragraph_style_class(
            "AuditQuote",
            parent=sample_styles["BodyText"],
            **base,
            fontSize=9,
            leftIndent=10,
            textColor=colors_module.HexColor("#475569"),
            backColor=colors_module.HexColor("#f5f7fb"),
            borderPadding=6,
        ),
    }


def draw_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont(PDF_FONT_NAME, 8)
    canvas.setFillColorRGB(0.39, 0.45, 0.55)
    canvas.drawRightString(document.pagesize[0] - document.rightMargin, 10 * 2.83465, f"Page {document.page}")
    canvas.restoreState()


def escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def candidate_pdf_font_paths() -> list[Path]:
    configured_path = os.getenv("AUDIT_PDF_FONT_PATH")
    candidates = [configured_path] if configured_path else []
    candidates.extend(PDF_FONT_CANDIDATES)
    paths: list[Path] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            paths.append(path)
    return paths


def register_pdf_font(pdfmetrics: Any, ttfont_class: Any) -> str | None:
    if PDF_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return PDF_FONT_NAME
    for font_path in candidate_pdf_font_paths():
        try:
            pdfmetrics.registerFont(ttfont_class(PDF_FONT_NAME, str(font_path)))
            return PDF_FONT_NAME
        except Exception:
            continue
    return None
