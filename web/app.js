const $ = (selector) => document.querySelector(selector);

const USERS = [
  { id: "local-demo", label: "Local Demo" },
  { id: "demo-alice", label: "Alice" },
  { id: "demo-bob", label: "Bob" },
];

let lastQuestion = "";
let selectedTraceId = "";

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
  return USERS.find((user) => user.id === currentUserId())?.label || currentUserId();
}

function authHeaders(extraHeaders = {}) {
  return { ...extraHeaders, "X-User-Id": currentUserId() };
}

function saveCurrentUser() {
  localStorage.setItem("audit-agent-user-id", currentUserId());
  $("#active-user").textContent = currentUserLabel();
}

function restoreCurrentUser() {
  const storedUser = localStorage.getItem("audit-agent-user-id");
  if (USERS.some((user) => user.id === storedUser)) {
    $("#user-select").value = storedUser;
  }
  saveCurrentUser();
}

function clearResult() {
  lastQuestion = "";
  selectedTraceId = "";
  $("#results").hidden = true;
  $("#empty").hidden = false;
  $("#answer").textContent = "";
  $("#findings").innerHTML = "";
  $("#citations").innerHTML = "";
  $("#trace").innerHTML = "";
  $("#upload-status").textContent = "";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Request failed");
  return payload;
}

function percent(value) {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`;
}

function renderEvaluationResults(payload) {
  const summary = payload.summary || {};
  $("#evaluation-summary").innerHTML = [
    ["评测问题", summary.total ?? 0],
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

function renderTrace(trace, title = "工作流追踪") {
  $("#trace").innerHTML = `
    <div class="trace-head">
      <h3>${escapeHtml(title)}</h3>
    </div>
    ${trace.map((step, index) => `
      <div class="trace-item">
        <h3>${index + 1}. ${escapeHtml(step.name)} <small>${escapeHtml(step.status)} - ${step.duration_ms} ms</small></h3>
        <p>${escapeHtml(step.detail)}</p>
        <div class="trace-meta">
          <span>Prompt: ${escapeHtml(step.prompt)}</span>
          <span>Tools: ${escapeHtml((step.tool_calls || []).join(", "))}</span>
          <span>Tokens: in ${step.input_tokens}, out ${step.output_tokens}</span>
          <span>${step.failure_reason ? `Failure: ${escapeHtml(step.failure_reason)}` : "Failure: none"}</span>
        </div>
      </div>
    `).join("")}
  `;
}

function renderAuditHistory(audit) {
  if (!audit.length) {
    $("#audit-history").innerHTML = '<div class="document muted">当前用户没有审计记录。</div>';
    return;
  }
  $("#audit-history").innerHTML = audit.map((event) => {
    const traceId = event.trace_id || "";
    const isSelected = traceId && traceId === selectedTraceId;
    const label = event.event === "report_exported" ? "导出" : "问答";
    const summary = event.summary || event.question || "No summary";
    return `
      <div class="audit-item ${isSelected ? "selected" : ""}">
        <div class="audit-item-main">
          <strong>${escapeHtml(label)} - ${escapeHtml(event.user_id || currentUserId())}</strong>
          <span>${escapeHtml(summary)}</span>
          <small>${escapeHtml(event.duration_ms ?? 0)} ms - ${escapeHtml(event.step_count ?? 0)} steps</small>
        </div>
        <div class="audit-item-actions">
          <button type="button" class="secondary" data-trace-id="${escapeHtml(traceId)}">查看 trace</button>
        </div>
      </div>
    `;
  }).join("");

  $("#audit-history").querySelectorAll("button[data-trace-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const traceId = button.getAttribute("data-trace-id");
      const event = audit.find((item) => item.trace_id === traceId);
      if (!event || !event.workflow_trace) return;
      selectedTraceId = traceId || "";
      renderTrace(event.workflow_trace, `${event.event} - ${traceId}`);
      refreshAuditSelection();
    });
  });
}

function refreshAuditSelection() {
  $("#audit-history").querySelectorAll(".audit-item").forEach((item) => {
    item.classList.toggle("selected", item.querySelector("button[data-trace-id]")?.getAttribute("data-trace-id") === selectedTraceId);
  });
}

async function refreshOverview() {
  const [health, me, documents, audit, evaluation] = await Promise.all([
    fetch("/api/health").then((response) => response.json()),
    fetchJson("/api/me"),
    fetchJson("/api/documents"),
    fetchJson("/api/audit-log"),
    fetchJson("/api/evaluation-results").catch(() => ({ summary: {} })),
  ]);
  $("#health").textContent = health.status === "ok" ? "Service healthy" : "Service error";
  $("#document-count").textContent = documents.length;
  $("#active-user").textContent = `${me.display_name} (${me.id})`;
  $("#mode").textContent = health.llm_enabled ? "LLM + evidence" : "Local evidence mode";
  $("#audit-count").textContent = audit.length;
  $("#documents").innerHTML = documents.length
    ? documents.map((document) => `
        <div class="document">
          <strong>${escapeHtml(document.title)}</strong>
          <span>${escapeHtml(document.source)} - ${document.chunk_count} chunks</span>
        </div>
      `).join("")
    : `<div class="document muted">${escapeHtml(me.display_name)} has no visible documents.</div>`;
  renderAuditHistory(audit);
  renderEvaluationResults(evaluation);
  if (selectedTraceId) {
    const selected = audit.find((item) => item.trace_id === selectedTraceId);
    if (selected?.workflow_trace) {
      renderTrace(selected.workflow_trace, `${selected.event} - ${selected.trace_id}`);
      refreshAuditSelection();
    }
  }
}

function renderResult(payload) {
  $("#empty").hidden = true;
  $("#results").hidden = false;
  $("#answer").textContent = payload.answer;
  $("#findings").innerHTML = payload.findings.map((finding) => `
    <div class="finding ${finding.level.toLowerCase().includes("high") ? "high" : ""}">
      <h3>${escapeHtml(finding.level)} - ${escapeHtml(finding.title)}</h3>
      <p>${escapeHtml(finding.rationale)}</p>
      <p><strong>Recommendation:</strong> ${escapeHtml(finding.recommendation)}</p>
    </div>
  `).join("");
  $("#citations").innerHTML = payload.citations.map((citation, index) => `
    <div class="citation">
      <h3>Evidence ${index + 1} - ${escapeHtml(citation.title)} <small>(${citation.score})</small></h3>
      <p>${escapeHtml(citation.excerpt)}</p>
      <div class="source">${escapeHtml(citation.source)} - ${escapeHtml(citation.location_label)}</div>
    </div>
  `).join("");
  selectedTraceId = "";
  renderTrace(payload.workflow_trace, `Current trace - ${payload.trace_id}`);
}

async function ask() {
  const button = $("#ask");
  const question = $("#question").value.trim();
  if (!question) return;
  lastQuestion = question;
  button.disabled = true;
  button.textContent = "Running...";
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
    throw new Error(payload.detail || "Export failed");
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
  const form = $("#upload-form");
  const button = $("#upload-button");
  const status = $("#upload-status");
  const file = $("#upload-file").files[0];
  if (!file) return;

  button.disabled = true;
  status.textContent = "Uploading...";
  try {
    await fetchJson("/api/documents/upload", {
      method: "POST",
      body: new FormData(form),
    });
    form.reset();
    status.textContent = `Uploaded for ${currentUserLabel()}`;
    await refreshOverview();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function switchUser() {
  saveCurrentUser();
  clearResult();
  await refreshOverview();
}

$("#ask").addEventListener("click", ask);
$("#upload-form").addEventListener("submit", uploadDocument);
$("#export-md").addEventListener("click", () => exportReport("markdown").catch((error) => alert(error.message)));
$("#export-pdf").addEventListener("click", () => exportReport("pdf").catch((error) => alert(error.message)));
$("#example").addEventListener("click", () => {
  $("#question").value = "旧版销售工具是否可以直接下载完整客户名单？请指出它和当前制度的冲突，并给出整改建议。";
  ask();
});
$("#user-select").addEventListener("change", switchUser);

restoreCurrentUser();
refreshOverview();
