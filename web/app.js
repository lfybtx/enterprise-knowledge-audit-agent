const $ = (selector) => document.querySelector(selector);

const DEMO_QUESTIONS = [
  "销售是否可以直接导出完整客户名单？请说明风险和正确流程。",
  "客服能否对外发送客户手机号、密钥和访问日志？",
  "销售能否承诺高于标准 SLA 的赔偿？",
  "跨部门访问客户数据是否需要审批？",
];

let session = JSON.parse(localStorage.getItem("audit-agent-session") || "null");
let selectedKnowledgeBaseId = localStorage.getItem("audit-agent-kb-id") || "";
let knowledgeBases = [];
let users = [];
let lastQuestion = "";
let authVerified = false;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function currentUserId() {
  return session?.user?.id || "";
}

function isAdmin() {
  return authVerified && session?.user?.role === "admin";
}

function currentKnowledgeBase() {
  return knowledgeBases.find((item) => item.id === selectedKnowledgeBaseId) || knowledgeBases[0] || null;
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;
  if (selectedKnowledgeBaseId) headers["X-Knowledge-Base-Id"] = selectedKnowledgeBaseId;
  return headers;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { ...options, headers: authHeaders(options.headers || {}) });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401 && session?.access_token) {
    session = null;
    authVerified = false;
    localStorage.removeItem("audit-agent-session");
    syncAuthUi();
    applyPermissions();
  }
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => `${item.loc?.join(".") || "请求"}: ${item.msg}`).join("；")
      : payload.detail;
    throw new Error(detail || "请求失败");
  }
  return payload;
}

function setBusy(button, busy, text) {
  if (!button) return;
  if (!button.dataset.readyText) button.dataset.readyText = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? text : button.dataset.readyText;
}

function syncAuthUi() {
  const loggedIn = Boolean(session?.access_token);
  document.body.dataset.userRole = authVerified ? (session?.user?.role || "unknown") : "unknown";
  $("#logout-button").hidden = !loggedIn;
  $("#login-username").hidden = loggedIn;
  $("#login-password").hidden = loggedIn;
  $("#login-button").disabled = loggedIn;
  $("#login-button").textContent = loggedIn ? "已登录" : "登录";
  $("#admin-tab").hidden = !loggedIn;
  document.querySelectorAll("[data-admin-only]").forEach((node) => {
    if (authVerified && !isAdmin()) {
      node.remove();
    } else {
      node.hidden = !isAdmin();
    }
  });
}

function setPage(page) {
  document.querySelectorAll("[data-page]").forEach((node) => {
    node.hidden = node.dataset.page !== page;
  });
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === page);
  });
  if (page === "admin") {
    refreshCurrentUser().then(() => refreshAdminPage());
  }
}

async function refreshCurrentUser() {
  if (!session?.access_token) return false;
  try {
    const me = await fetchJson("/api/me");
    session.user = { ...session.user, ...me };
    authVerified = true;
    localStorage.setItem("audit-agent-session", JSON.stringify(session));
  } catch (error) {
    authVerified = false;
    console.error("Unable to verify current user", error);
  }
  syncAuthUi();
  return authVerified;
}

function renderDemoQuestions() {
  $("#demo-questions").innerHTML = DEMO_QUESTIONS.map((question) => `
    <button type="button" class="demo-question" data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>
  `).join("");
  $("#demo-questions").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-question]");
    if (!button) return;
    $("#question").value = button.dataset.question;
  });
}

async function login(event) {
  event.preventDefault();
  const button = $("#login-button");
  setBusy(button, true, "登录中");
  try {
    const payload = await fetchJson("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("#login-username").value.trim(), password: $("#login-password").value }),
    });
    session = payload;
    localStorage.setItem("audit-agent-session", JSON.stringify(payload));
    await refreshOverview();
  } catch (error) {
    alert(error.message);
  } finally {
    syncAuthUi();
  }
}

async function register(event) {
  event.preventDefault();
  const button = $("#register-button");
  setBusy(button, true, "注册中");
  try {
    await fetchJson("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#register-username").value.trim(),
        password: $("#register-password").value,
        display_name: $("#register-display-name").value.trim(),
        department: $("#register-department").value.trim() || "general",
      }),
    });
    $("#register-status").textContent = "注册成功，可以登录";
    event.target.reset();
  } catch (error) {
    $("#register-status").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
}

async function logout() {
  localStorage.removeItem("audit-agent-session");
  window.location.assign("/");
}

function applyPermissions() {
  const kb = currentKnowledgeBase();
  const canWrite = Boolean(kb?.can_write);
  const canManage = Boolean(kb?.can_manage);
  const loggedIn = Boolean(session?.access_token);
  $("#active-role").textContent = session?.user?.role === "admin" ? "admin" : (kb?.role || "-");
  ["#upload-title", "#upload-file", "#upload-button", "#url-title", "#url-input", "#url-ingest-button"].forEach((selector) => {
    const node = $(selector);
    if (node) node.disabled = !canWrite;
  });
  ["#member-user-id", "#member-role", "#member-save"].forEach((selector) => {
    const node = $(selector);
    if (node) node.disabled = !canManage;
  });
  ["#ask", "#example"].forEach((selector) => {
    const node = $(selector);
    if (node) node.disabled = !loggedIn;
  });
  $("#knowledge-base-save").disabled = !loggedIn;
  const ownerOption = $("#member-role").querySelector('option[value="owner"]');
  ownerOption.disabled = !isAdmin();
  if (ownerOption.disabled && $("#member-role").value === "owner") $("#member-role").value = "viewer";
  $("#member-status").textContent = canManage ? "" : "只有知识库 owner 或 admin 可以管理成员";
}

function renderKnowledgeBases(items) {
  knowledgeBases = items || [];
  const selected = knowledgeBases.find((item) => item.id === selectedKnowledgeBaseId);
  if (!selected || (!isAdmin() && !selected.can_manage)) {
    const manageable = knowledgeBases.find((item) => item.can_manage);
    selectedKnowledgeBaseId = (manageable || knowledgeBases[0])?.id || "";
  }
  const options = knowledgeBases.map((item) => `
    <option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} (${escapeHtml(item.role)})</option>
  `).join("");
  $("#knowledge-base-select").innerHTML = options;
  $("#knowledge-base-select").value = selectedKnowledgeBaseId;
  $("#management-knowledge-base-select").innerHTML = options;
  $("#management-knowledge-base-select").value = selectedKnowledgeBaseId;
  localStorage.setItem("audit-agent-kb-id", selectedKnowledgeBaseId);
}

function renderUsers() {
  const activeUsers = users.filter((user) => user.is_active !== false);
  $("#member-user-id").innerHTML = activeUsers.map((user) => `
    <option value="${escapeHtml(user.external_id)}">${escapeHtml(user.display_name || user.username)} (${escapeHtml(user.external_id)})</option>
  `).join("");
  const userTable = $("#user-table");
  if (!userTable) return;
  userTable.innerHTML = users.map((user) => `
    <div class="user-row">
      <strong>${escapeHtml(user.display_name || user.username)}</strong>
      <span>${escapeHtml(user.external_id)}</span>
      <span>${escapeHtml(user.role || "user")}</span>
      <span>${user.is_active === false ? "停用" : "启用"}</span>
      <button type="button" class="secondary" data-toggle-user="${escapeHtml(user.external_id)}" data-active="${user.is_active !== false}">
        ${user.is_active === false ? "启用" : "停用"}
      </button>
    </div>
  `).join("") || '<div class="document muted">暂无用户</div>';
}

async function refreshUsers() {
  users = await fetchJson("/api/users").catch(() => []);
  renderUsers();
}

function renderDocuments(documents, me) {
  $("#documents").innerHTML = documents.length ? documents.map((document) => `
    <div class="document">
      ${isAdmin() ? `<div class="document-actions"><button type="button" class="secondary" data-reindex-document="${escapeHtml(document.id)}">Reindex</button><button type="button" class="secondary" data-delete-document="${escapeHtml(document.id)}">Delete</button></div>` : ""}
      <strong>${escapeHtml(document.title)}</strong>
      <span>${escapeHtml(document.source)} · ${escapeHtml(document.chunk_count)} chunks</span>
    </div>
  `).join("") : `<div class="document muted">${escapeHtml(me.display_name)} 当前没有可见文档。</div>`;
}

$("#documents").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-reindex-document], button[data-delete-document]");
  if (!button) return;
  const id = button.dataset.reindexDocument || button.dataset.deleteDocument;
  if (button.dataset.deleteDocument && !window.confirm("Confirm deleting this document and its index?")) return;
  setBusy(button, true, "Working");
  try {
    await fetchJson(`/api/documents/${encodeURIComponent(id)}${button.dataset.deleteDocument ? "" : "/reindex"}`, { method: button.dataset.deleteDocument ? "DELETE" : "POST" });
    await refreshOverview();
  } catch (error) { window.alert(error.message); }
  finally { setBusy(button, false); }
});

function renderAuditHistory(audit) {
  window.auditHistory = audit;
  $("#audit-history").innerHTML = audit.length ? audit.slice(-20).reverse().map((item) => `
    <div class="audit-item" data-trace-id="${escapeHtml(item.trace_id || "")}">
      <div class="audit-item-main">
        <strong>${escapeHtml(item.event || "audit")} · ${escapeHtml(item.user_id || currentUserId())}</strong>
        <span>${escapeHtml(item.summary || item.question || "暂无摘要")}</span>
        <small>${escapeHtml(item.duration_ms ?? 0)} ms · ${escapeHtml(item.step_count ?? 0)} steps · ${escapeHtml(item.approval_status || "not_required")}</small>
      </div>
    </div>
  `).join("") : '<div class="document muted">暂无审计记录</div>';
}

$("#audit-history").addEventListener("click", (event) => {
  const item = event.target.closest(".audit-item");
  const record = window.auditHistory?.find((entry) => entry.trace_id === item?.dataset.traceId);
  if (!record) return;
  $("#empty").hidden = true;
  $("#results").hidden = false;
  $("#answer").textContent = record.summary || record.question || "暂无详情";
  $("#trace").innerHTML = (record.workflow_trace || []).map((step, index) => `<div class="trace-item"><h3>${index + 1}. ${escapeHtml(step.name)} <small>${escapeHtml(step.duration_ms)} ms</small></h3><p>${escapeHtml(step.detail)}</p></div>`).join("");
  $(".review-actions")?.setAttribute("hidden", "hidden");
});

function renderEvaluation(payload) {
  const summary = payload.summary || {};
  const cards = [
    ["题目数", summary.total ?? 0],
    ["Recall@1", `${((summary.recall_at_1 || 0) * 100).toFixed(1)}%`],
    ["引用准确率", `${((summary.citation_accuracy || 0) * 100).toFixed(1)}%`],
    ["平均延迟", `${Number(summary.average_latency_ms || 0).toFixed(1)} ms`],
  ];
  $("#evaluation-summary").innerHTML = cards.map(([label, value]) => `
    <div class="evaluation-card"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("");
}

function renderMembers(members) {
  const canManage = Boolean(currentKnowledgeBase()?.can_manage);
  const canRemove = canManage;
  $("#permission-members").innerHTML = members.length ? members.map((member) => {
    const isSelf = member.user_id === currentUserId();
    return `
      <div class="member-row">
        <div><strong>${escapeHtml(member.display_name || member.user_id)}</strong><span>${escapeHtml(member.user_id)}</span></div>
        <span>${escapeHtml(member.role)}</span>
        <button type="button" class="secondary" data-remove-member="${escapeHtml(member.user_id)}" ${!canRemove || isSelf ? "disabled" : ""}>移除</button>
      </div>
    `;
  }).join("") : '<div class="document muted">当前知识库暂无成员</div>';
}

async function refreshMembers() {
  if (!selectedKnowledgeBaseId) return renderMembers([]);
  try {
    const members = await fetchJson(`/api/knowledge-bases/${encodeURIComponent(selectedKnowledgeBaseId)}/members`);
    renderMembers(members);
  } catch (error) {
    $("#permission-members").innerHTML = `<div class="document muted">${escapeHtml(error.message)}</div>`;
  }
}

function renderSystemStatus(payload) {
  const db = payload.database || {};
  const counts = db.table_counts || {};
  const models = payload.models || {};
  const cards = [
    ["数据库", db.connected ? "已连接" : "未连接"],
    ["pgvector", db.pgvector_installed ? "已启用" : "未启用"],
    ["迁移版本", db.alembic_version || "-"],
    ["文档", counts.documents ?? 0],
    ["切片", counts.document_chunks ?? 0],
    ["审计记录", counts.workflow_runs ?? 0],
    ["Embedding", models.embedding?.model || models.embedding?.provider || "-"],
    ["LLM", models.chat?.chat_model || models.chat?.provider || "-"],
  ];
  $("#system-status").innerHTML = cards.map(([label, value]) => `
    <div class="system-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("");
  $("#system-issues").innerHTML = (payload.index?.issues || []).map((issue) => `
    <div class="system-issue warn">${escapeHtml(issue)}</div>
  `).join("") || '<div class="system-issue">未发现索引异常</div>';
}

async function refreshSystemStatus() {
  if (!isAdmin()) return;
  try {
    renderSystemStatus(await fetchJson("/api/admin/system-status"));
  } catch (error) {
    $("#system-status").innerHTML = `<div class="system-card error"><span>系统运维</span><strong>${escapeHtml(error.message)}</strong></div>`;
  }
}

async function refreshAdminPage() {
  if (!session?.access_token) return;
  await Promise.all([refreshUsers(), refreshMembers()]);
  if (isAdmin()) await refreshSystemStatus();
}

async function refreshOverview() {
  const healthRequest = fetch("/api/health")
    .then((response) => response.json())
    .catch(() => ({ status: "error" }));
  void healthRequest.then((health) => {
    $("#health").textContent = health.status === "ok" ? "服务正常" : "服务异常";
  });
  if (!session?.access_token) {
    applyPermissions();
    return;
  }
  const [me, docs, audit, evaluation, kbList] = await Promise.all([
    fetchJson("/api/me"),
    fetchJson("/api/documents"),
    fetchJson("/api/audit-log"),
    fetchJson("/api/evaluation-results").catch(() => ({ summary: {} })),
    fetchJson("/api/knowledge-bases"),
  ]);
  if (session?.user) {
    session.user = { ...session.user, ...me };
    authVerified = true;
    localStorage.setItem("audit-agent-session", JSON.stringify(session));
    syncAuthUi();
  }
  $("#document-count").textContent = docs.length;
  $("#active-user").textContent = `${me.display_name} (${me.id})`;
  $("#audit-count").textContent = audit.length;
  renderKnowledgeBases(kbList);
  renderDocuments(docs, me);
  renderAuditHistory(audit);
  renderEvaluation(evaluation);
  await refreshUsers();
  applyPermissions();
  if (document.querySelector('[data-tab="admin"]').classList.contains("active")) await refreshAdminPage();
}

async function ask() {
  const question = $("#question").value.trim();
  if (!question) return;
  const button = $("#ask");
  lastQuestion = question;
  setBusy(button, true, "运行中");
  try {
    const payload = await fetchJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    lastAuditPayload = payload;
    $(".review-actions")?.removeAttribute("hidden");
    $("#empty").hidden = true;
    $("#results").hidden = false;
    $("#answer").textContent = payload.answer || "未检索到可用证据。";
    $("#findings").innerHTML = (payload.findings || []).map((finding) => `
      <div class="finding"><h3>${escapeHtml(finding.level)} · ${escapeHtml(finding.title)}</h3><p>${escapeHtml(finding.rationale)}</p></div>
    `).join("") || '<div class="document muted">暂无风险发现</div>';
    $("#citations").innerHTML = (payload.citations || []).map((citation, index) => `
      <div class="citation"><h3>Evidence ${index + 1} · ${escapeHtml(citation.title)}</h3><p>${escapeHtml(citation.excerpt)}</p></div>
    `).join("") || '<div class="document muted">暂无证据引用</div>';
    $("#trace").innerHTML = (payload.workflow_trace || []).map((step, index) => `
      <div class="trace-item"><h3>${index + 1}. ${escapeHtml(step.name)} <small>${escapeHtml(step.duration_ms)} ms</small></h3><p>${escapeHtml(step.detail)}</p></div>
    `).join("");
    await refreshOverview();
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(button, false);
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const button = $("#upload-button");
  setBusy(button, true, "上传中");
  try {
    await fetchJson("/api/documents/upload", { method: "POST", body: new FormData(event.target) });
    event.target.reset();
    $("#upload-status").textContent = "已上传并入库";
    await refreshOverview();
  } catch (error) {
    $("#upload-status").textContent = error.message;
  } finally {
    setBusy(button, false);
    applyPermissions();
  }
}

async function ingestUrl(event) {
  event.preventDefault();
  const button = $("#url-ingest-button");
  setBusy(button, true, "抓取中");
  try {
    await fetchJson("/api/documents/ingest-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("#url-title").value.trim(), url: $("#url-input").value.trim() }),
    });
    event.target.reset();
    $("#url-ingest-status").textContent = "已抓取网页";
    await refreshOverview();
  } catch (error) {
    $("#url-ingest-status").textContent = error.message;
  } finally {
    setBusy(button, false);
    applyPermissions();
  }
}

async function saveMember(event) {
  event.preventDefault();
  const role = $("#member-role").value;
  if (role === "owner" && !isAdmin()) {
    $("#member-status").textContent = "只有 admin 可以添加 owner";
    return;
  }
  const button = $("#member-save");
  setBusy(button, true, "保存中");
  try {
    await fetchJson(`/api/knowledge-bases/${encodeURIComponent(selectedKnowledgeBaseId)}/members`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: $("#member-user-id").value, role }),
    });
    $("#member-status").textContent = "已保存成员";
    await refreshMembers();
  } catch (error) {
    $("#member-status").textContent = error.message;
  } finally {
    setBusy(button, false);
    applyPermissions();
  }
}

async function createKnowledgeBase(event) {
  event.preventDefault();
  const button = $("#knowledge-base-save");
  setBusy(button, true, "创建中");
  try {
    const knowledgeBase = await fetchJson("/api/knowledge-bases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("#knowledge-base-name").value.trim(),
        department: $("#knowledge-base-department").value.trim() || "general",
      }),
    });
    selectedKnowledgeBaseId = knowledgeBase.id;
    $("#knowledge-base-status").textContent = "知识库已创建";
    event.target.reset();
    await refreshOverview();
    await refreshMembers();
  } catch (error) {
    $("#knowledge-base-status").textContent = error.message;
  } finally {
    setBusy(button, false);
    applyPermissions();
  }
}

async function createAdminUser(event) {
  event.preventDefault();
  const button = $("#admin-user-save");
  setBusy(button, true, "创建中");
  try {
    await fetchJson("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#admin-username").value.trim(),
        password: $("#admin-password").value,
        display_name: $("#admin-display-name").value.trim(),
        role: $("#admin-user-role").value,
        department: $("#admin-department").value.trim() || "general",
      }),
    });
    event.target.reset();
    await refreshUsers();
  } catch (error) {
    $("#admin-user-status").textContent = error.message;
  } finally {
    setBusy(button, false);
  }
}

$("#login-form").addEventListener("submit", login);
$("#register-form").addEventListener("submit", register);
$("#logout-button").addEventListener("click", logout);
$("#ask").addEventListener("click", ask);
$("#example").addEventListener("click", () => { $("#question").value = DEMO_QUESTIONS[0]; ask(); });
$("#upload-form").addEventListener("submit", uploadDocument);
$("#url-ingest-form").addEventListener("submit", ingestUrl);
$("#member-form").addEventListener("submit", saveMember);
$("#knowledge-base-form").addEventListener("submit", createKnowledgeBase);
$("#admin-user-form").addEventListener("submit", createAdminUser);
$("#refresh-system-status").addEventListener("click", refreshSystemStatus);
function handleKnowledgeBaseChange(event) {
  selectedKnowledgeBaseId = event.target.value;
  $("#knowledge-base-select").value = selectedKnowledgeBaseId;
  $("#management-knowledge-base-select").value = selectedKnowledgeBaseId;
  localStorage.setItem("audit-agent-kb-id", selectedKnowledgeBaseId);
  applyPermissions();
  refreshMembers();
}
$("#knowledge-base-select").addEventListener("change", handleKnowledgeBaseChange);
$("#management-knowledge-base-select").addEventListener("change", handleKnowledgeBaseChange);
document.querySelector(".tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (button && !button.hidden) setPage(button.dataset.tab);
});
$("#permission-members").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-remove-member]");
  if (!button || button.disabled) return;
  setBusy(button, true, "移除中");
  try {
    await fetch(`/api/knowledge-bases/${encodeURIComponent(selectedKnowledgeBaseId)}/members/${encodeURIComponent(button.dataset.removeMember)}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    await refreshMembers();
  } catch (error) {
    $("#member-status").textContent = error.message;
  }
});
$("#user-table").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-toggle-user]");
  if (!button || !isAdmin()) return;
  setBusy(button, true, "处理中");
  try {
    await fetchJson(`/api/admin/users/${encodeURIComponent(button.dataset.toggleUser)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: button.dataset.active !== "true" }),
    });
    await refreshUsers();
  } catch (error) {
    $("#admin-user-status").textContent = error.message;
  }
});

let lastAuditPayload = null;
$("#review-approve")?.addEventListener("click", () => submitReview("approved"));
$("#review-reject")?.addEventListener("click", () => submitReview("rejected"));
async function submitReview(decision) {
  if (!lastAuditPayload?.trace_id) return;
  let corrected_findings = null;
  const raw = $("#corrected-findings")?.value.trim();
  if (raw) { try { corrected_findings = JSON.parse(raw); } catch (_) { $("#review-status").textContent = "修正 JSON 格式错误"; return; } }
  try { await fetchJson(`/api/audit-runs/${lastAuditPayload.trace_id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, corrected_findings }) }); $("#review-status").textContent = "人工修正已回写"; $(".review-actions")?.setAttribute("hidden", "hidden"); }
  catch (error) { $("#review-status").textContent = error.message; }
}

$("#export-report")?.addEventListener("click", async () => {
  if (!lastAuditPayload?.question && !window.lastQuestion) return;
  const question = lastAuditPayload?.question || window.lastQuestion;
  const response = await fetch("/api/reports/export", { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ question, export_format: "markdown" }) });
  if (!response.ok) { alert(await response.text()); return; }
  const blob = await response.blob(); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "audit-report.md"; link.click(); URL.revokeObjectURL(link.href);
});

renderDemoQuestions();
syncAuthUi();
setPage("workspace");
refreshOverview().catch((error) => {
  console.error("Unable to refresh workspace data", error);
});
