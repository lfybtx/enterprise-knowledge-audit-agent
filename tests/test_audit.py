from app.services.audit import assess
from app.services.retrieval import RetrievedChunk
from app.services.workflow import build_risk_report


def chunk(document_id, title, text):
    return RetrievedChunk(
        chunk_id=f"{document_id}-chunk",
        document_id=document_id,
        title=title,
        source=f"{document_id}.txt",
        text=text,
        location={"kind": "document"},
        score=0.9,
    )


def test_audit_rules_detect_multiple_enterprise_risks():
    evidence = [
        chunk("doc-export", "Export Policy", "Customer data export requires manager approval and field limits."),
        chunk("doc-permission", "Permission Policy", "Admin role and shared account access must be reviewed by department."),
        chunk("doc-contract", "SLA Terms", "The contract includes service level compensation and confidentiality commitments."),
    ]

    findings = assess("Can sales export customer data?", evidence)
    titles = {finding.title for finding in findings}

    assert "客户或敏感数据导出需要审批与范围控制" in titles
    assert "可能存在权限越权或访问控制风险" in titles
    assert "合同或服务承诺需要法务确认" in titles


def test_audit_detects_policy_conflicts_between_documents():
    evidence = [
        chunk("doc-old", "Old Sales Guide", "Sales can directly export the full customer list without approval. Keep files for 30 days."),
        chunk("doc-new", "Current Export Policy", "Customer data export is prohibited without manager approval. Export files must be deleted within 7 days."),
    ]

    findings = assess("Can sales export the full customer list?", evidence)
    conflict_findings = [finding for finding in findings if finding.title.startswith("发现制度冲突")]

    assert conflict_findings
    assert any(set(finding.evidence_ids) == {"doc-old", "doc-new"} for finding in conflict_findings)


def test_risk_report_binds_findings_to_evidence_refs():
    evidence = [
        chunk("doc-old", "Old Sales Guide", "Sales can directly export the full customer list without approval."),
        chunk("doc-new", "Current Export Policy", "Customer data export is prohibited without manager approval."),
    ]
    findings = assess("Can sales export the full customer list?", evidence)

    report = build_risk_report("Can sales export the full customer list?", evidence, findings)

    assert report["findings"][0]["evidence_refs"]
    assert report["findings"][0]["evidence_sources"][0]["evidence_rank"] == 1
