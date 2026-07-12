from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

import app.main as main
from app.services import report_export
from app.services.report_export import PDF_FONT_NAME, export_report, export_report_markdown, register_pdf_font


client = TestClient(main.app)


def sample_report():
    return {
        "question": "客户数据是否可以直接导出？",
        "overall_level": "high",
        "finding_count": 1,
        "risk_counts": {"high": 1, "medium": 0, "low": 0},
        "summary": "客户数据导出需要经理审批，并保留证据。",
        "findings": [
            {
                "level": "高",
                "title": "客户数据导出需要审批",
                "rationale": "当前证据显示导出前必须完成审批。",
                "recommendation": "要求区域经理审批并限制导出字段。",
                "evidence_ids": ["doc-1"],
                "evidence_sources": [],
            }
        ],
        "evidence": [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "title": "客户导出制度",
                "source": "policy.txt",
                "location": {"kind": "document"},
                "location_label": "第 1 页",
                "excerpt": "客户数据导出需要经理审批。",
                "score": 0.92,
            }
        ],
    }


def test_export_report_markdown_contains_key_sections():
    markdown = export_report_markdown(sample_report())

    assert "# Enterprise Knowledge Audit Report" in markdown
    assert "Question: 客户数据是否可以直接导出？" in markdown
    assert "客户数据导出需要审批" in markdown
    assert "## Findings" in markdown


def test_export_report_pdf_is_readable():
    pytest.importorskip("reportlab")
    pdf_bytes, media_type, filename = export_report(sample_report(), "pdf")

    assert media_type == "application/pdf"
    assert filename.endswith(".pdf")
    assert pdf_bytes.startswith(b"%PDF")

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    assert b"?" not in pdf_bytes[:500]


def test_export_api_returns_attachment():
    response = client.post(
        "/api/reports/export",
        headers={"X-User-Id": "local-demo"},
        json={"question": "Can customer data be exported?", "export_format": "markdown"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].endswith('audit-report.md"')


def test_register_pdf_font_skips_incompatible_font(monkeypatch, tmp_path):
    bad_font = tmp_path / "bad.ttc"
    good_font = tmp_path / "good.ttf"
    bad_font.write_text("bad", encoding="utf-8")
    good_font.write_text("good", encoding="utf-8")

    class FakePdfMetrics:
        registered = set()

        @classmethod
        def getRegisteredFontNames(cls):
            return cls.registered

        @classmethod
        def registerFont(cls, font):
            cls.registered.add(font.name)

    class FakeTTFont:
        def __init__(self, name, path):
            if path == str(bad_font):
                raise RuntimeError("incompatible font")
            self.name = name

    monkeypatch.setattr(report_export, "candidate_pdf_font_paths", lambda: [bad_font, good_font])

    assert register_pdf_font(FakePdfMetrics, FakeTTFont) == PDF_FONT_NAME
