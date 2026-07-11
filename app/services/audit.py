from __future__ import annotations

from dataclasses import dataclass

from app.services.retrieval import RetrievedChunk


@dataclass
class AuditFinding:
    level: str
    title: str
    rationale: str
    recommendation: str
    evidence_ids: list[str]


def assess(question: str, evidence: list[RetrievedChunk]) -> list[AuditFinding]:
    corpus = " ".join(item.text for item in evidence)
    findings: list[AuditFinding] = []

    if "导出" in question and ("未经审批" in corpus or "审批" in corpus):
        findings.append(
            AuditFinding(
                level="高",
                title="客户数据导出需要审批",
                rationale="知识库要求在导出客户信息前完成审批；高敏感信息不得导出。",
                recommendation="在 CRM 发起导出申请，并限制导出字段与文件保存期限。",
                evidence_ids=[item.document_id for item in evidence if "导出" in item.text or "审批" in item.text],
            )
        )

    if "旧版" in corpus and ("直接下载完整客户清单" in corpus or "未包含当前数据保护要求" in corpus):
        findings.append(
            AuditFinding(
                level="高",
                title="发现与现行控制冲突的历史资料",
                rationale="历史说明允许直接下载完整客户清单，但现行制度要求审批、字段限制和时限管理。",
                recommendation="将历史资料标记为失效，更新索引并向销售团队发布替代流程。",
                evidence_ids=[item.document_id for item in evidence if "旧版" in item.text or "历史" in item.title],
            )
        )

    if any(keyword in question for keyword in ["泄露", "异常访问", "安全事件"]):
        findings.append(
            AuditFinding(
                level="高",
                title="安全事件需要升级处理",
                rationale="安全制度要求隔离风险账号、保留日志，并在对外通知前经过法务审核。",
                recommendation="立即通知安全与法务团队，保留证据并启动事件响应流程。",
                evidence_ids=[item.document_id for item in evidence if "安全" in item.title or "泄露" in item.text],
            )
        )

    if not findings:
        findings.append(
            AuditFinding(
                level="低",
                title="未发现明确的高风险冲突",
                rationale="当前检索证据未触发内置风险规则；这不代表流程已通过完整合规审查。",
                recommendation="保留引用并由业务负责人确认适用范围。",
                evidence_ids=[item.document_id for item in evidence],
            )
        )

    return findings
