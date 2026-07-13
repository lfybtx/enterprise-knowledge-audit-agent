const $ = (selector) => document.querySelector(selector);

const USERS = [
  { id: "local-demo", label: "Local Demo" },
  { id: "demo-alice", label: "Alice" },
  { id: "demo-bob", label: "Bob" },
];

const DEMO_QUESTIONS = [
  "销售是否可以直接导出完整客户名单？请说明风险和正确流程。",
  "客服能否对外发送客户手机号、密钥和访问日志？",
  "销售能否承诺高于标准 SLA 的赔偿？",
  "跨部门访问客户数据是否需要审批？",
  "发生客户数据泄露或异常访问后应该怎么处理？",
];

const STEP_LABELS = {
  retrieval_agent: "检索 Agent",
  audit_agent: "审计 Agent",
  report_agent: "报告 Agent",
  human_review: "人工确认",
};

let lastQuestion = "";
let lastWorkflowTrace = [];
let selectedTraceId = "";
let selectedKnowledgeBaseId = "";
let knowledgeBases = [];
let currentSession = JSON.parse(localStorage.getItem("audit-agent-session") || "null");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[character]));
}

function currentUserId() {
  const selectedUser = $("#user-select").value;
  return USERS.some((user) => user.id === selectedUser) ? selectedUser : "local-demo";
}

function currentUserLabel() {
  return currentSession?.user?.display_name || USERS.find((user) => user.id === currentUserId())?.label || currentUserId();
}

function currentKnowledgeBase() {
  return knowledgeBases.find((item) => item.id === selectedKnowledgeBaseId) || knowledgeBases[0] || null;
}

function authHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  if (currentSession?.access_token) headers.Authorization = `Bearer ${currentSession.access_token}`;
  else headers["X-User-Id"] = currentUserId();
  if (selectedKnowledgeBaseId) headers["X-Knowledge-Base-Id"] = selectedKnowledgeBaseId;
  return headers;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { ...options, headers: authHeaders(options.headers || {}) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "请求失败");
  return payload;
}

function savePreferences() {
  localStorage.setItem("audit-agent-user-id", currentUserId());
  localStorage.setItem("audit-agent-kb-id", selectedKnowledgeBaseId);
  $("#active-user").textContent = currentUserLabel();
}

function restorePreferences() {
  const storedUser = localStorage.getItem("audit-agent-user-id");
  if (USERS.some((user) => user.id === storedUser)) $("#user-select").value = storedUser;
  selectedKnowledgeBaseId = localStorage.getItem("audit-agent-kb-id") || "";
  savePreferences();
}

function syncLoginState() {
  const loggedIn = Boolean(currentSession?.access_token);
  $("#logout-button").hidden = !loggedIn;
  $("#login-button").textContent = loggedIn ? "已登录" : "登录";
  $("#login-button").disabled = loggedIn;
  $("#user-select").disabled = loggedIn;
}

function setWriteEnabled(enabled) {
  ["#upload-button", "#upload-title", "#upload-file", "#url-ingest-button", "#url-title", "#url-input"].forEach((selector) => {
    const node = $(selector);
    if (node) node.disabled = !enabled;
  });
}

function applyPermissions() {
  const kb = currentKnowledgeBase();
  const canWrite = Boolean(kb?.can_write);
  $("#active-role").textContent = kb?.role || "-";
  $("#upload-status").textContent = canWrite ? "" : "当前角色没有上传权限";
  $("#url-ingest-status").textContent = canWrite ? "" : "当前角色没有网页入库权限";
  setWriteEnabled(canWrite);
}

function clearResult() {
  lastQuestion = "";
  lastWorkflowTrace = [];
  selectedTraceId = "";
  $("#results").hidden = true;
  $("#empty").hidden = false;
  $("#answer").textContent = "";
  $("#findings").innerHTML = "";
  $("#citations").innerHTML = "";
  $("#trace").innerHTML = "";
  $("#upload-status").textContent = "";
  $("#url-ingest-status").textContent = "";
}

function percent(value) {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`;
}

function renderDemoQuestions() {
  $("#demo-questions").innerHTML = DEMO_QUESTIONS.map((question) => `
    <button type="button" class="demo-question" data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>
  `).join("");
  $("#demo-questions").querySelectorAll("button[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      $("#question").value = button.getAttribute("data-question");
      $("#question").focus();
    });
  });
}

async function login(event) {
  event.preventDefault();
  const button = $("#login-button");
  button.disabled = true;
  button.textContent = "登录中";
  try {
    const payload = await fetchJson("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#login-username").value.trim(),
        password: $("#login-password").value,
      }),
    });
    currentSession = payload;
    localStorage.setItem("audit-agent-session", JSON.stringify(payload));
    syncLoginState();
    clearResult();
    await refreshOverview();
  } catch (error) {
    alert(error.message);
    button.disabled = false;
    button.textContent = "登录";
  }
}

async function logout() {
  currentSession = null;
  localStorage.removeItem("audit-agent-session");
  syncLoginState();
  clearResult();
  await refreshOverview();
}

function renderKnowledgeBaseOptions(items) {
  knowledgeBases = items || [];
  const previous = selectedKnowledgeBaseId;
  $("#knowledge-base-select").innerHTML = knowledgeBases.map((item) => `
    <option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} (${escapeHtml(item.role)})</option>
  `).join("");
  selectedKnowledgeBaseId = previous && knowledgeBases.some((item) => item.id === previous)
    ? previous
    : knowledgeBases[0]?.id || "";
  $("#knowledge-base-select").value = selectedKnowledgeBaseId;
}

function renderEvaluationResults(payload) {
  const summary = payload.summary || {};
  const groups = [
    ["检索质量", [
      ["题目数", summary.total ?? 0],
      ["Recall@1", percent(summary.recall_at_1)],
      ["Recall@3", percent(summary.recall_at_3)],
      ["引用准确率", percent(summary.citation_accuracy)],
    ]],
    ["审计质量", [
      ["风险识别", percent(summary.risk_type_accuracy)],
      ["冲突检测", percent(summary.conflict_accuracy)],
      ["证据绑定", percent(summary.evidence_binding_accuracy)],
      ["审批触发", percent(summary.review_trigger_accuracy)],
    ]],
    ["性能稳定性", [
      ["回答质量", percent(summary.answer_quality_rate)],
      ["平均延迟", `${Number(summary.average_latency_ms || 0).toFixed(2)} ms`],
      ["P95 延迟", `${Number(summary.p95_latency_ms || 0).toFixed(2)} ms`],
      ["失败率", percent(summary.failure_rate)],
    ]],
  ];
  $("#evaluation-summary").innerHTML = groups.map(([group, items]) => `
    <div class="evaluation-group">
      <h3>${escapeHtml(group)}</h3>
      <div class="evaluation-group-grid">
        ${items.map(([label, value]) => `
          <div class="evaluation-card">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");
}

function modelLabel(model) {
  if (!model) return "-";
  const provider = model.provider || "-";
  const name = model.model || model.chat_model || model.embedding_model || "";
  return name ? `${provider} / ${name}` : provider;
}

function renderSystemStatus(payload) {
  const database = payload?.database || {};
  const counts = database.table_counts || {};
  const index = payload?.index || {};
  const models = payload?.models || {};
  const cards = [
    ["数据库", database.connected ? "已连接" : "未连接", database.connected ? "ok" : "error"],
    ["pgvector", database.pgvector_installed ? "已启用" : "未启用", database.pgvector_installed ? "ok" : "warn"],
    ["迁移版本", database.alembic_version || "-", database.alembic_version ? "ok" : "warn"],
    ["索引健康", index.healthy ? "正常" : "需检查", index.healthy ? "ok" : "warn"],
    ["文档", counts.documents ?? 0, "ok"],
    ["切片", counts.document_chunks ?? 0, "ok"],
    ["审计记录", counts.workflow_runs ?? 0, "ok"],
    ["Trace 步骤", counts.workflow_trace_steps ?? 0, "ok"],
    ["Embedding", modelLabel(models.embedding), "ok"],
    ["LLM", modelLabel(models.chat), "ok"],
    ["缺失向量切片", index.chunks_missing_embeddings ?? 0, index.chunks_missing_embeddings ? "warn" : "ok"],
    ["最近审计", payload?.recent_audit_runs?.length ?? 0, "ok"],
  ];
  $("#system-status").innerHTML = cards.map(([label, value, state]) => `
    <div class="system-card ${state}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");

  const issues = index.issues || [];
  const withoutChunks = index.documents_without_chunks || [];
  const duplicates = index.duplicate_documents || [];
  const issueRows = [];
  if (!issues.length && !withoutChunks.length && !duplicates.length) {
    issueRows.push('<div class="system-issue">未发现索引异常。</div>');
  }
  issues.forEach((issue) => issueRows.push(`<div class="system-issue warn">${escapeHtml(issue)}</div>`));
  withoutChunks.forEach((document) => issueRows.push(`
    <div class="system-issue warn">文档没有切片：${escapeHtml(document.title)} (${escapeHtml(document.id)})</div>
  `));
  duplicates.forEach((item) => issueRows.push(`
    <div class="system-issue warn">疑似重复文档：${escapeHtml(item.title)}，数量 ${escapeHtml(item.duplicate_count)}</div>
  `));
  $("#system-issues").innerHTML = issueRows.join("");
}

function renderSystemStatusError(message) {
  $("#system-status").innerHTML = `
    <div class="system-card error">
      <span>系统诊断</span>
      <strong>无法读取</strong>
    </div>
  `;
  $("#system-issues").innerHTML = `<div class="system-issue warn">${escapeHtml(message)}</div>`;
}

async function refreshSystemStatus() {
  try {
    const payload = await fetchJson("/api/admin/system-status");
    renderSystemStatus(payload);
  } catch (error) {
    renderSystemStatusError(error.message);
  }
}

function renderRetrievalCandidates(retrieval) {
  const candidates = retrieval?.candidate_ranking;
  if (!Array.isArray(candidates) || !candidates.length) return "";
  return `
    <div class="retrieval-candidates">
      <h4>候选重排明细</h4>
      ${candidates.map((candidate) => `
        <div class="candidate-row ${candidate.decision === "selected" ? "selected" : "discarded"}">
          <strong>${candidate.decision === "selected" ? "入选" : "淘汰"}</strong>
          <span>${escapeHtml(candidate.title)}</span>
          <small>融合 #${escapeHtml(candidate.fusion_rank)} | 最终 ${candidate.final_rank ? `#${escapeHtml(candidate.final_rank)}` : "未入选"} | 重排 ${escapeHtml(candidate.rerank_score ?? "未执行")}</small>
          <small>${escapeHtml(candidate.reason)}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderLlmTrace(traceData) {
  const llm = traceData?.llm;
  if (!llm) return "";
  const status = llm.status || "success";
  return `
    <div class="llm-trace">
      <strong>LLM 调用</strong>
      <span>Provider：${escapeHtml(llm.provider || "-")}</span>
      <span>Model：${escapeHtml(llm.chat_model || "-")}</span>
      <span>状态：${status === "fallback" ? "已回退" : "成功"}</span>
      ${llm.failure_reason ? `<span>回退原因：${escapeHtml(llm.failure_reason)}</span>` : ""}
      ${llm.citation_count !== undefined ? `<span>引用数量：${escapeHtml(llm.citation_count)}</span>` : ""}
    </div>
  `;
}

function renderTrace(trace, title = "工作流 Trace") {
  if (!trace || !trace.length) {
    $("#trace").innerHTML = `
      <div class="trace-head"><h3>${escapeHtml(title)}</h3></div>
      <div class="document muted">当前没有可展示的流程步骤。</div>
    `;
    return;
  }
  $("#trace").innerHTML = `
    <div class="trace-head"><h3>${escapeHtml(title)}</h3></div>
    ${trace.map((step, index) => {
      const stepName = STEP_LABELS[step.name] || step.name;
      return `
        <div class="trace-item">
          <h3>${index + 1}. ${escapeHtml(stepName)} <small>${escapeHtml(step.status)} - ${escapeHtml(step.duration_ms)} ms</small></h3>
          <p>${escapeHtml(step.detail)}</p>
          <div class="trace-meta">
            <span>Prompt：${escapeHtml(step.prompt)}</span>
            <span>工具调用：${escapeHtml((step.tool_calls || []).join(", ") || "-")}</span>
            <span>Token 估算：输入 ${escapeHtml(step.input_tokens)}, 输出 ${escapeHtml(step.output_tokens)}</span>
            <span>${step.failure_reason ? `失败原因：${escapeHtml(step.failure_reason)}` : "失败原因：无"}</span>
          </div>
          ${renderLlmTrace(step.trace_data)}
          ${renderRetrievalCandidates(step.trace_data?.retrieval)}
        </div>
      `;
    }).join("")}
  `;
}

function renderEmptyAuditHistory() {
  const trace = [
    { name: "retrieval_agent", status: "待运行", duration_ms: 0, detail: "执行关键词、向量、融合与重排检索。", prompt: "等待问题输入", tool_calls: ["keyword_search", "pgvector_search", "fusion", "local_reranker"], input_tokens: 0, output_tokens: 0, failure_reason: "暂无审计记录" },
    { name: "audit_agent", status: "待运行", duration_ms: 0, detail: "识别风险、冲突和证据不足。", prompt: "等待检索结果", tool_calls: ["assess"], input_tokens: 0, output_tokens: 0, failure_reason: "暂无审计记录" },
    { name: "report_agent", status: "待运行", duration_ms: 0, detail: "生成带证据回答、风险清单和建议动作。", prompt: "等待审计结果", tool_calls: ["build_risk_report", "openai_compatible_chat"], input_tokens: 0, output_tokens: 0, failure_reason: "暂无审计记录" },
  ];
  $("#audit-history").innerHTML = `<div class="document muted">当前没有审计记录，可以先查看工作流预览。</div><div class="actions" style="margin-top: 10px;"><button type="button" class="secondary" id="replay-current-trace">查看 Trace 流程</button></div>`;
  $("#replay-current-trace").addEventListener("click", () => {
    $("#empty").hidden = true;
    $("#results").hidden = false;
    $("#answer").textContent = "尚未运行审计，当前显示的是工作流预览。";
    $("#findings").innerHTML = '<div class="document muted">暂无风险发现</div>';
    $("#citations").innerHTML = '<div class="document muted">暂无证据引用</div>';
    renderTrace(lastWorkflowTrace.length ? lastWorkflowTrace : trace, "审计工作流 Trace 预览");
  });
}

function approvalStatusLabel(status) {
  return {
    pending: "待人工确认",
    approved: "已批准",
    rejected: "已驳回",
    not_required: "无需审核",
  }[status] || status;
}

function renderAuditHistory(audit) {
  if (!audit.length) {
    renderEmptyAuditHistory();
    return;
  }
  $("#audit-history").innerHTML = audit.map((event) => {
    const traceId = event.trace_id || "";
    const hasTrace = Boolean(traceId && event.workflow_trace && event.workflow_trace.length);
    const isSelected = hasTrace && traceId === selectedTraceId;
    const approvalStatus = event.approval_status || "not_required";
    const label = event.event === "report_exported" ? "导出" : "问答";
    const summary = event.summary || event.question || "暂无摘要";
    return `
      <div class="audit-item ${isSelected ? "selected" : ""}">
        <div class="audit-item-main">
          <strong>${escapeHtml(label)} - ${escapeHtml(event.user_id || currentUserId())}</strong>
          <span>${escapeHtml(summary)}</span>
          <small>${escapeHtml(event.duration_ms ?? 0)} ms - ${escapeHtml(event.step_count ?? 0)} steps</small>
          <small class="approval-status ${escapeHtml(approvalStatus)}">${escapeHtml(approvalStatusLabel(approvalStatus))}</small>
        </div>
        <div class="audit-item-actions">
          ${approvalStatus === "pending" ? `
            <button type="button" class="secondary" data-review-trace-id="${escapeHtml(traceId)}" data-review-decision="approved">批准</button>
            <button type="button" class="secondary" data-review-trace-id="${escapeHtml(traceId)}" data-review-decision="rejected">驳回</button>
          ` : ""}
          <button type="button" class="secondary" data-trace-id="${escapeHtml(traceId)}" ${hasTrace ? "" : "disabled"}>
            ${hasTrace ? "查看 Trace" : "暂无 Trace"}
          </button>
        </div>
      </div>
    `;
  }).join("");

  $("#audit-history").querySelectorAll("button[data-trace-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const traceId = button.getAttribute("data-trace-id");
      const event = audit.find((item) => item.trace_id === traceId);
      selectedTraceId = traceId || "";
      $("#empty").hidden = true;
      $("#results").hidden = false;
      $("#answer").textContent = event?.question || event?.summary || "该审计记录没有保存回答正文。";
      $("#findings").innerHTML = '<div class="document muted">历史记录中未保存风险明细，请查看下方 Trace 步骤。</div>';
      $("#citations").innerHTML = '<div class="document muted">历史记录中未保存证据明细，请查看 Trace 中的检索步骤。</div>';
      renderTrace(event?.workflow_trace || [], `${event?.event || "workflow"} - ${traceId}`);
      refreshAuditSelection();
      $("#trace").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  $("#audit-history").querySelectorAll("button[data-review-trace-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const traceId = button.getAttribute("data-review-trace-id");
      const decision = button.getAttribute("data-review-decision");
      button.disabled = true;
      try {
        await fetchJson(`/api/audit-runs/${encodeURIComponent(traceId)}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        });
        await refreshOverview();
      } catch (error) {
        alert(error.message);
        button.disabled = false;
      }
    });
  });
}

function refreshAuditSelection() {
  $("#audit-history").querySelectorAll(".audit-item").forEach((item) => {
    item.classList.toggle("selected", item.querySelector("button[data-trace-id]")?.getAttribute("data-trace-id") === selectedTraceId);
  });
}

async function refreshOverview() {
  const [health, me, documents, audit, evaluation, kbList] = await Promise.all([
    fetch("/api/health").then((response) => response.json()),
    fetchJson("/api/me"),
    fetchJson("/api/documents"),
    fetchJson("/api/audit-log"),
    fetchJson("/api/evaluation-results").catch(() => ({ summary: {} })),
    fetchJson("/api/knowledge-bases"),
  ]);
  $("#health").textContent = health.status === "ok" ? "服务正常" : "服务异常";
  $("#document-count").textContent = documents.length;
  $("#active-user").textContent = `${me.display_name} (${me.id})`;
  $("#audit-count").textContent = audit.length;
  renderKnowledgeBaseOptions(kbList);
  selectedKnowledgeBaseId = $("#knowledge-base-select").value;
  applyPermissions();
  $("#documents").innerHTML = documents.length
    ? documents.map((document) => `
        <div class="document">
          <strong>${escapeHtml(document.title)}</strong>
          <span>${escapeHtml(document.source)} - ${escapeHtml(document.chunk_count)} chunks</span>
        </div>
      `).join("")
    : `<div class="document muted">${escapeHtml(me.display_name)} 当前没有可见文档。</div>`;
  renderAuditHistory(audit);
  renderEvaluationResults(evaluation);
  await refreshSystemStatus();
  if (selectedTraceId) {
    const selected = audit.find((item) => item.trace_id === selectedTraceId);
    if (selected?.workflow_trace) renderTrace(selected.workflow_trace, `${selected.event} - ${selected.trace_id}`);
    else selectedTraceId = "";
    refreshAuditSelection();
  }
}

function renderResult(payload) {
  $("#empty").hidden = true;
  $("#results").hidden = false;
  $("#answer").textContent = payload.answer || "未检索到可用证据，系统不会直接回答。";
  renderApprovalPanel(payload);
  $("#findings").innerHTML = payload.findings?.length
    ? payload.findings.map((finding) => `
        <div class="finding ${String(finding.level).toLowerCase().includes("high") ? "high" : ""}">
          <h3>${escapeHtml(finding.level)} - ${escapeHtml(finding.title)}</h3>
          <p>${escapeHtml(finding.rationale)}</p>
          <p><strong>建议动作：</strong> ${escapeHtml(finding.recommendation)}</p>
          ${renderFindingEvidence(finding)}
        </div>
      `).join("")
    : '<div class="document muted">暂无风险发现。</div>';
  $("#citations").innerHTML = payload.citations?.length
    ? payload.citations.map((citation, index) => `
        <div class="citation">
          <h3>Evidence ${index + 1} - ${escapeHtml(citation.title)} <small>${escapeHtml(citation.score)}</small></h3>
          <p>${escapeHtml(citation.excerpt)}</p>
          <div class="source">${escapeHtml(citation.source)} - ${escapeHtml(citation.location_label)}</div>
          <div class="retrieval-scores">
            <span>最终排名 ${escapeHtml(citation.selected_rank ?? index + 1)}</span>
            <span>关键词 ${escapeHtml(citation.lexical_score ?? "-")}</span>
            <span>向量 ${escapeHtml(citation.semantic_score ?? "-")}</span>
            <span>融合 ${escapeHtml(citation.fusion_score ?? "-")}</span>
            <span>重排 ${escapeHtml(citation.rerank_score ?? "未执行")}</span>
          </div>
        </div>
      `).join("")
    : '<div class="document muted">未检索到可用证据，系统不会直接回答。</div>';
  selectedTraceId = "";
  lastWorkflowTrace = payload.workflow_trace || [];
  renderTrace(lastWorkflowTrace, `当前流程 Trace - ${payload.trace_id}`);
}

function renderFindingEvidence(finding) {
  const refs = finding.evidence_refs || [];
  const sources = finding.evidence_sources || [];
  if (!refs.length && !sources.length) return "";
  return `
    <div class="finding-evidence">
      ${refs.length ? `<div><strong>引用证据：</strong> ${refs.map(escapeHtml).join(", ")}</div>` : ""}
      ${sources.length ? `
        <ul>
          ${sources.map((source) => `
            <li>
              ${source.evidence_rank ? `Evidence ${escapeHtml(source.evidence_rank)} - ` : ""}
              ${escapeHtml(source.title || source.document_id)}
              <span>${escapeHtml(source.source || "")} ${escapeHtml(source.location_label || "")}</span>
            </li>
          `).join("")}
        </ul>
      ` : ""}
    </div>
  `;
}

function renderApprovalPanel(payload) {
  const panel = $("#approval-panel");
  if (payload.approval_status !== "pending") {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <div><strong>待人工确认</strong><span>该审计报告包含高风险或冲突结论，需要负责人确认。</span></div>
    <div class="approval-actions">
      <button type="button" class="secondary" id="approve-current-audit">批准报告</button>
      <button type="button" class="secondary" id="reject-current-audit">驳回报告</button>
    </div>
  `;
  $("#approve-current-audit").addEventListener("click", () => reviewCurrentAudit(payload.trace_id, "approved"));
  $("#reject-current-audit").addEventListener("click", () => reviewCurrentAudit(payload.trace_id, "rejected"));
}

async function reviewCurrentAudit(traceId, decision) {
  document.querySelectorAll("#approval-panel button").forEach((button) => { button.disabled = true; });
  try {
    await fetchJson(`/api/audit-runs/${encodeURIComponent(traceId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    $("#approval-panel").innerHTML = `<strong>${decision === "approved" ? "已批准" : "已驳回"}</strong>`;
    await refreshOverview();
  } catch (error) {
    alert(error.message);
    document.querySelectorAll("#approval-panel button").forEach((button) => { button.disabled = false; });
  }
}

async function ask() {
  const button = $("#ask");
  const question = $("#question").value.trim();
  if (!question) return;
  lastQuestion = question;
  button.disabled = true;
  button.textContent = "运行中...";
  try {
    const payload = await fetchJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderResult(payload);
    await refreshOverview();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "运行审计";
  }
}

async function exportReport(exportFormat) {
  const question = lastQuestion || $("#question").value.trim();
  if (!question) return;
  const response = await fetch("/api/reports/export", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ question, export_format: exportFormat }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "导出失败");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  const filename = filenameMatch ? filenameMatch[1] : `audit-report.${exportFormat}`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function uploadDocument(event) {
  event.preventDefault();
  if (!currentKnowledgeBase()?.can_write) {
    $("#upload-status").textContent = "当前角色没有上传权限";
    return;
  }
  const form = $("#upload-form");
  const button = $("#upload-button");
  const status = $("#upload-status");
  const file = $("#upload-file").files[0];
  if (!file) return;

  button.disabled = true;
  status.textContent = "上传中...";
  try {
    await fetchJson("/api/documents/upload", { method: "POST", body: new FormData(form) });
    form.reset();
    $("#knowledge-base-select").value = selectedKnowledgeBaseId;
    status.textContent = `已为 ${currentUserLabel()} 上传并索引`;
    await refreshOverview();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function ingestUrlDocument(event) {
  event.preventDefault();
  if (!currentKnowledgeBase()?.can_write) {
    $("#url-ingest-status").textContent = "当前角色没有网页入库权限";
    return;
  }
  const form = $("#url-ingest-form");
  const button = $("#url-ingest-button");
  const status = $("#url-ingest-status");
  const title = $("#url-title").value.trim();
  const url = $("#url-input").value.trim();
  if (!title || !url) return;

  button.disabled = true;
  status.textContent = "抓取中...";
  try {
    await fetchJson("/api/documents/ingest-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, url }),
    });
    form.reset();
    status.textContent = `已抓取 ${new URL(url).hostname}`;
    await refreshOverview();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function switchUser() {
  savePreferences();
  clearResult();
  await refreshOverview();
}

async function switchKnowledgeBase() {
  selectedKnowledgeBaseId = $("#knowledge-base-select").value;
  savePreferences();
  applyPermissions();
  await refreshOverview();
}

$("#ask").addEventListener("click", ask);
$("#upload-form").addEventListener("submit", uploadDocument);
$("#url-ingest-form").addEventListener("submit", ingestUrlDocument);
$("#login-form").addEventListener("submit", login);
$("#logout-button").addEventListener("click", logout);
$("#refresh-system-status").addEventListener("click", refreshSystemStatus);
$("#export-md").addEventListener("click", () => exportReport("markdown").catch((error) => alert(error.message)));
$("#export-pdf").addEventListener("click", () => exportReport("pdf").catch((error) => alert(error.message)));
$("#example").addEventListener("click", () => {
  $("#question").value = "旧版销售工具是否可以直接下载完整客户名单？请说明它和当前制度的冲突，并给出整改建议。";
  ask();
});
$("#user-select").addEventListener("change", switchUser);
$("#knowledge-base-select").addEventListener("change", switchKnowledgeBase);

renderDemoQuestions();
restorePreferences();
syncLoginState();
refreshOverview();
