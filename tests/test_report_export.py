from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

import app.main as main
from app.services.report_export import export_report, export_report_markdown


client = TestClient(main.app)


def sample_report():
    return {
        "question": "Can customer data be exported?",
        "overall_level": "high",
        "finding_count": 1,
        "risk_counts": {"high": 1, "medium": 0, "low": 0},
        "summary": "Manager approval is required.",
        "findings": [
            {
                "level": "high",
                "title": "Export approval required",
                "rationale": "Approval missing",
                "recommendation": "Require manager approval",
                "evidence_ids": ["doc-1"],
                "evidence_sources": [],
            }
        ],
        "evidence": [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "title": "Export policy",
                "source": "policy.txt",
                "location": {"kind": "document"},
                "location_label": "Document",
                "excerpt": "Manager approval is required.",
                "score": 0.92,
            }
        ],
    }


def test_export_report_markdown_contains_key_sections():
    markdown = export_report_markdown(sample_report())

    assert "# Enterprise Knowledge Audit Report" in markdown
    assert "Question: Can customer data be exported?" in markdown
    assert "## Findings" in markdown


def test_export_report_pdf_is_readable():
    pdf_bytes, media_type, filename = export_report(sample_report(), "pdf")

    assert media_type == "application/pdf"
    assert filename.endswith(".pdf")
    assert pdf_bytes.startswith(b"%PDF")

    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1


def test_export_api_returns_attachment():
    response = client.post(
        "/api/reports/export",
        json={"question": "Can customer data be exported?", "export_format": "markdown"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].endswith('audit-report.md"')
