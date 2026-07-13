from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.services.retrieval import RetrievedChunk


@dataclass
class AuditFinding:
    level: str
    title: str
    rationale: str
    recommendation: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class PolicyClaim:
    topic: str
    polarity: str
    value: int | None
    value_unit: str | None
    chunk: RetrievedChunk
    matched_text: str


def assess(question: str, evidence: list[RetrievedChunk]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    findings.extend(_risk_rule_findings(question, evidence))
    findings.extend(_conflict_findings(evidence))

    if not findings:
        findings.append(
            AuditFinding(
                level="Low",
                title="未发现明确的高风险冲突",
                rationale="当前检索证据未触发内置风险规则；这不代表流程已经通过完整合规审查。",
                recommendation="保留引用证据，并由业务负责人确认适用范围和最新制度版本。",
                evidence_ids=_unique_document_ids(evidence),
            )
        )

    return _deduplicate_findings(findings)


def _risk_rule_findings(question: str, evidence: list[RetrievedChunk]) -> list[AuditFinding]:
    question_text = _normalize(question)
    corpus = _normalize(" ".join(item.text for item in evidence))
    findings: list[AuditFinding] = []

    export_evidence = _matching_evidence(evidence, _EXPORT_TERMS)
    if _contains_any(question_text + " " + corpus, _EXPORT_TERMS):
        if export_evidence and _contains_any(corpus, _APPROVAL_TERMS + _LIMIT_TERMS + _SENSITIVE_TERMS):
            findings.append(
                AuditFinding(
                    level="High",
                    title="客户或敏感数据导出需要审批与范围控制",
                    rationale="检索证据显示导出客户数据、敏感字段或完整清单前需要审批、字段限制或保留期限控制。",
                    recommendation="发起正式导出申请，限制导出字段，记录审批人，并设置文件保存期限。",
                    evidence_ids=_unique_document_ids(export_evidence),
                )
            )
        elif export_evidence:
            findings.append(
                AuditFinding(
                    level="Medium",
                    title="导出问题存在证据不足",
                    rationale="问题涉及数据导出，但当前证据没有明确说明审批、字段范围或保存期限。",
                    recommendation="补充最新数据导出制度；在证据不足前不要直接给出允许导出的结论。",
                    evidence_ids=_unique_document_ids(export_evidence),
                )
            )

    permission_evidence = _matching_evidence(evidence, _PERMISSION_TERMS)
    if permission_evidence and _contains_any(corpus, _PERMISSION_TERMS):
        findings.append(
            AuditFinding(
                level="High",
                title="可能存在权限越权或访问控制风险",
                rationale="证据涉及管理员权限、跨部门访问、共享账号、白名单或角色授权，可能影响最小权限原则。",
                recommendation="核验用户角色、部门、租户和知识库成员关系；对高权限操作增加审批与审计日志。",
                evidence_ids=_unique_document_ids(permission_evidence),
            )
        )

    contract_evidence = _matching_evidence(evidence, _CONTRACT_TERMS)
    if contract_evidence and _contains_any(corpus, _CONTRACT_TERMS):
        findings.append(
            AuditFinding(
                level="Medium",
                title="合同或服务承诺需要法务确认",
                rationale="证据涉及合同、赔偿、违约、保密、服务等级或响应时限，可能产生对外承诺。",
                recommendation="由法务或售前负责人确认条款版本、适用客户和例外条件，再对外答复。",
                evidence_ids=_unique_document_ids(contract_evidence),
            )
        )

    sensitive_evidence = _matching_evidence(evidence, _SENSITIVE_TERMS)
    if sensitive_evidence and _contains_any(corpus, _SENSITIVE_TERMS + _LEAK_TERMS):
        findings.append(
            AuditFinding(
                level="High",
                title="敏感信息处理存在泄露风险",
                rationale="证据包含个人信息、客户名单、手机号、身份证、密钥、日志或泄露处理要求。",
                recommendation="最小化展示字段，脱敏后使用；如已泄露，应立即隔离账号、保留日志并启动安全事件流程。",
                evidence_ids=_unique_document_ids(sensitive_evidence),
            )
        )

    approval_evidence = _matching_evidence(evidence, _APPROVAL_TERMS)
    if _contains_any(question_text, _ACTION_TERMS) and evidence and not approval_evidence:
        findings.append(
            AuditFinding(
                level="Medium",
                title="缺少审批依据，不能直接下结论",
                rationale="用户问题涉及业务动作，但当前检索证据没有明确审批人、审批节点或授权条件。",
                recommendation="补充审批制度或授权记录；在证据不足前输出保守结论。",
                evidence_ids=_unique_document_ids(evidence),
            )
        )

    return findings


def _conflict_findings(evidence: list[RetrievedChunk]) -> list[AuditFinding]:
    claims = _extract_claims(evidence)
    findings: list[AuditFinding] = []
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            if left.chunk.document_id == right.chunk.document_id:
                continue
            if left.topic != right.topic:
                continue
            if not _claims_conflict(left, right):
                continue
            findings.append(
                AuditFinding(
                    level="High",
                    title=f"发现制度冲突：{_topic_label(left.topic)}",
                    rationale=(
                        f"不同资料对同一主题给出不一致要求。证据 A：{left.matched_text}；"
                        f"证据 B：{right.matched_text}。"
                    ),
                    recommendation="不要直接给出单一结论；应确认最新生效版本、适用部门和例外条件，并将旧制度标记为失效或待复核。",
                    evidence_ids=_unique_document_ids([left.chunk, right.chunk]),
                )
            )
    return findings


def _extract_claims(evidence: Iterable[RetrievedChunk]) -> list[PolicyClaim]:
    claims: list[PolicyClaim] = []
    for chunk in evidence:
        text = _normalize(chunk.text)
        for topic, terms in _TOPIC_TERMS.items():
            if not _contains_any(text, terms):
                continue
            polarity = _detect_polarity(text)
            if polarity:
                claims.append(PolicyClaim(topic, polarity, None, None, chunk, _short_match(chunk.text, terms)))
            days = _extract_days(text)
            if days is not None and topic in {"retention", "export"}:
                claims.append(PolicyClaim("retention", "retention_days", days, "days", chunk, _short_match(chunk.text, terms)))
    return claims


def _claims_conflict(left: PolicyClaim, right: PolicyClaim) -> bool:
    opposite_pairs = {
        ("allow", "deny"),
        ("deny", "allow"),
        ("must", "not_required"),
        ("not_required", "must"),
        ("must", "deny"),
        ("deny", "must"),
    }
    if (left.polarity, right.polarity) in opposite_pairs:
        return True
    if left.polarity == right.polarity == "retention_days" and left.value is not None and right.value is not None:
        return abs(left.value - right.value) >= 1
    return False


def _detect_polarity(text: str) -> str | None:
    if _contains_any(text, _DENY_TERMS):
        return "deny"
    if _contains_any(text, _NOT_REQUIRED_TERMS):
        return "not_required"
    if _contains_any(text, _MUST_TERMS):
        return "must"
    if _contains_any(text, _ALLOW_TERMS):
        return "allow"
    return None


def _extract_days(text: str) -> int | None:
    patterns = [
        r"(\d+)\s*(?:day|days)",
        r"(\d+)\s*(?:天|日)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _matching_evidence(evidence: Iterable[RetrievedChunk], terms: list[str]) -> list[RetrievedChunk]:
    return [item for item in evidence if _contains_any(_normalize(f"{item.title} {item.text}"), terms)]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _normalize(text: str) -> str:
    return text.lower()


def _short_match(text: str, terms: list[str]) -> str:
    normalized_text = _normalize(text)
    for term in terms:
        index = normalized_text.find(term)
        if index >= 0:
            start = max(0, index - 30)
            end = min(len(text), index + 90)
            return text[start:end].strip()
    return text[:120].strip()


def _unique_document_ids(chunks: Iterable[RetrievedChunk]) -> list[str]:
    ids: list[str] = []
    for chunk in chunks:
        if chunk.document_id not in ids:
            ids.append(chunk.document_id)
    return ids


def _deduplicate_findings(findings: list[AuditFinding]) -> list[AuditFinding]:
    unique: list[AuditFinding] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for finding in findings:
        key = (finding.title, tuple(sorted(finding.evidence_ids)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _topic_label(topic: str) -> str:
    return {
        "export": "数据导出",
        "approval": "审批要求",
        "retention": "文件保留期限",
        "permission": "访问权限",
        "sla": "服务承诺",
        "confidentiality": "保密要求",
    }.get(topic, topic)


_EXPORT_TERMS = ["export", "download", "customer list", "customer data", "导出", "下载", "客户名单", "客户数据", "完整清单"]
_APPROVAL_TERMS = ["approval", "approve", "review", "manager", "legal", "审批", "批准", "审核", "复核", "经理", "法务"]
_LIMIT_TERMS = ["limit", "field", "scope", "retention", "days", "限制", "字段", "范围", "保存", "保留", "期限"]
_PERMISSION_TERMS = ["permission", "role", "admin", "tenant", "department", "shared account", "权限", "角色", "管理员", "租户", "部门", "共享账号", "白名单"]
_CONTRACT_TERMS = ["contract", "sla", "service level", "compensation", "breach", "confidential", "合同", "服务等级", "赔偿", "违约", "保密", "承诺"]
_SENSITIVE_TERMS = ["sensitive", "personal information", "phone", "id card", "secret", "token", "log", "敏感", "个人信息", "手机号", "身份证", "密钥", "令牌", "日志"]
_LEAK_TERMS = ["leak", "breach", "incident", "abnormal access", "泄露", "安全事件", "异常访问"]
_ACTION_TERMS = ["can", "should", "allow", "export", "download", "share", "是否", "可以", "能否", "导出", "下载", "共享", "发送"]

_ALLOW_TERMS = ["allow", "allowed", "can", "may", "permit", "permitted", "允许", "可以", "可直接", "准许"]
_DENY_TERMS = ["forbid", "forbidden", "prohibit", "prohibited", "must not", "cannot", "不得", "禁止", "不允许", "不能"]
_MUST_TERMS = ["must", "required", "requires", "need", "shall", "必须", "需要", "应当", "要求"]
_NOT_REQUIRED_TERMS = ["no approval", "without approval", "not required", "无需审批", "不需要审批", "免审批", "无需批准"]

_TOPIC_TERMS = {
    "export": _EXPORT_TERMS,
    "approval": _APPROVAL_TERMS,
    "retention": ["retention", "keep", "delete", "保存", "保留", "删除", "销毁", "期限"],
    "permission": _PERMISSION_TERMS,
    "sla": ["sla", "service level", "response time", "availability", "服务等级", "响应时间", "可用性"],
    "confidentiality": ["confidential", "non-disclosure", "secret", "保密", "不得披露", "密钥"],
}
