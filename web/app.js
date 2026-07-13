const $ = (selector) => document.querySelector(selector);

const USERS = [
  { id: "local-demo", label: "Local Demo" },
  { id: "demo-alice", label: "Alice" },
  { id: "demo-bob", label: "Bob" },
];

let lastQuestion = "";
let lastWorkflowTrace = [];
let selectedTraceId = "";
let selectedKnowledgeBaseId = "";
let knowledgeBases = [];
let currentSession = JSON.parse(localStorage.getItem("audit-agent-session") || "null");

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
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
  $("#upload-status").textContent = canWrite ? "" : "当前角色无上传权限。";
  $("#url-ingest-status").textContent = canWrite ? "" : "当前角色无网页入库权限。";
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
  $("#evaluation-summary").innerHTML = [
    ["题目数", summary.total ?? 0],
    ["Recall@1", percent(summary.recall_at_1)],
    ["Recall@3", percent(summary.recall_at_3)],
    ["引用准确率", percent(summary.citation_accuracy)],
    ["回答质量", percent(summary.answer_quality_rate)],
  ].map(([label, value]) => `
    <div class="evaluation-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
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
    ${trace.map((step, index) => `
      <div class="trace-item">
        <h3>${index + 1}. ${escapeHtml(step.name)} <small>${escapeHtml(step.status)} - ${escapeHtml(step.duration_ms)} ms</small></h3>
        <p>${escapeHtml(step.detail)}</p>
        <div class="trace-meta">
          <span>Prompt: ${escapeHtml(step.prompt)}</span>
          <span>Tools: ${escapeHtml((step.tool_calls || []).join(", "))}</span>
          <span>Tokens: in ${escapeHtml(step.input_tokens)}, out ${escapeHtml(step.output_tokens)}</span>
          <span>${step.failure_reason ? `Failure: ${escapeHtml(step.failure_reason)}` : "Failure: none"}</span>
        </div>
        ${renderRetrievalCandidates(step.trace_data?.retrieval)}
      </div>
    `).join("")}
  `;
}

function renderEmptyAuditHistory() {
  const trace = [
    { name: "检索 Agent", status: "待运行", duration_ms: 0, detail: "执行关键词与向量混合检索。", prompt: "等待问题输入", tool_calls: ["keyword_search", "vector_search"], input_tokens: 0, output_tokens: 0, failure_reason: "暂无审计记录" },
    { name: "审计 Agent", status: "待运行", duration_ms: 0, detail: "检查风险、冲突和缺失信息。", prompt: "等待检索结果", tool_calls: ["conflict_check", "risk_assessment"], input_tokens: 0, output_tokens: 0, failure_reason: "暂无审计记录" },
    { name: "报告 Agent", status: "待运行", duration_ms: 0, detail: "生成结论、依据、建议动作和引用。", prompt: "等待审计结果", tool_calls: ["report_builder"], input_tokens: 0, output_tokens: 0, failure_reason: "暂无审计记录" },
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
            ${hasTrace ? "查看 trace" : "暂无 trace"}
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
  $("#answer").textContent = payload.answer;
  renderApprovalPanel(payload);
  $("#findings").innerHTML = payload.findings.map((finding) => `
    <div class="finding ${finding.level.toLowerCase().includes("high") ? "high" : ""}">
      <h3>${escapeHtml(finding.level)} - ${escapeHtml(finding.title)}</h3>
      <p>${escapeHtml(finding.rationale)}</p>
      <p><strong>建议动作：</strong> ${escapeHtml(finding.recommendation)}</p>
    </div>
  `).join("");
  $("#citations").innerHTML = payload.citations.map((citation, index) => `
    <div class="citation">
      <h3>证据 ${index + 1} - ${escapeHtml(citation.title)} <small>(${escapeHtml(citation.score)})</small></h3>
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
  `).join("");
  selectedTraceId = "";
  lastWorkflowTrace = payload.workflow_trace || [];
  renderTrace(lastWorkflowTrace, `当前流程 trace - ${payload.trace_id}`);
}

function renderApprovalPanel(payload) {
  const panel = $("#approval-panel");
  if (payload.approval_status !== "pending") {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `<div><strong>待人工确认</strong><span>该审计报告需要负责人确认。</span></div><div class="approval-actions"><button type="button" class="secondary" id="approve-current-audit">批准报告</button><button type="button" class="secondary" id="reject-current-audit">驳回报告</button></div>`;
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
    $("#upload-status").textContent = "当前角色无上传权限。";
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
    status.textContent = `已为 ${currentUserLabel()} 上传`;
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
    $("#url-ingest-status").textContent = "当前角色无网页入库权限。";
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
$("#export-md").addEventListener("click", () => exportReport("markdown").catch((error) => alert(error.message)));
$("#export-pdf").addEventListener("click", () => exportReport("pdf").catch((error) => alert(error.message)));
$("#example").addEventListener("click", () => {
  $("#question").value = "旧版销售工具是否可以直接下载完整客户名单？请说明与当前制度的冲突，并给出整改建议。";
  ask();
});
$("#user-select").addEventListener("change", switchUser);
$("#knowledge-base-select").addEventListener("change", switchKnowledgeBase);

restorePreferences();
syncLoginState();
refreshOverview();
