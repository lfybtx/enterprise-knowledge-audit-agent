const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[character]));
}

async function refreshOverview() {
  const [health, documents, audit] = await Promise.all([
    fetch("/api/health").then((response) => response.json()),
    fetch("/api/documents").then((response) => response.json()),
    fetch("/api/audit-log").then((response) => response.json())
  ]);
  $("#health").textContent = health.status === "ok" ? "服务正常" : "服务异常";
  $("#document-count").textContent = documents.length;
  $("#mode").textContent = health.llm_enabled ? "LLM + 证据约束" : "本地证据模式";
  $("#audit-count").textContent = audit.length;
  $("#documents").innerHTML = documents.map((document) => `
    <div class="document">
      <strong>${escapeHtml(document.title)}</strong>
      <span>${escapeHtml(document.source)} · ${document.chunk_count} 个检索片段</span>
    </div>
  `).join("");
}

function renderResult(payload) {
  $("#empty").hidden = true;
  $("#results").hidden = false;
  $("#answer").textContent = payload.answer;
  $("#findings").innerHTML = payload.findings.map((finding) => `
    <div class="finding ${finding.level === "高" ? "high" : ""}">
      <h3>${escapeHtml(finding.level)}风险 · ${escapeHtml(finding.title)}</h3>
      <p>${escapeHtml(finding.rationale)}</p>
      <p><strong>建议：</strong>${escapeHtml(finding.recommendation)}</p>
    </div>
  `).join("");
  $("#citations").innerHTML = payload.citations.map((citation, index) => `
    <div class="citation">
      <h3>证据 ${index + 1} · ${escapeHtml(citation.title)} <small>(${citation.score})</small></h3>
      <p>${escapeHtml(citation.excerpt)}</p>
      <div class="source">${escapeHtml(citation.source)} · ${escapeHtml(citation.location_label)}</div>
    </div>
  `).join("");
}

async function ask() {
  const button = $("#ask");
  const question = $("#question").value.trim();
  if (!question) return;
  button.disabled = true;
  button.textContent = "审计中...";
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "请求失败");
    renderResult(payload);
    await refreshOverview();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "运行审计";
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const form = $("#upload-form");
  const button = $("#upload-button");
  const status = $("#upload-status");
  const file = $("#upload-file").files[0];
  if (!file) return;

  button.disabled = true;
  status.textContent = "上传中...";
  try {
    const response = await fetch("/api/documents/upload", {
      method: "POST",
      body: new FormData(form)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "上传失败");
    form.reset();
    status.textContent = "已上传并加入索引";
    await refreshOverview();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

$("#ask").addEventListener("click", ask);
$("#upload-form").addEventListener("submit", uploadDocument);
$("#example").addEventListener("click", () => {
  $("#question").value = "旧版销售工具允许直接下载完整客户清单，这是否符合现行制度？请列出冲突、风险和整改建议。";
  ask();
});
refreshOverview();
