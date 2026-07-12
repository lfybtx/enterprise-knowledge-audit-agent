const $ = (selector) => document.querySelector(selector);
let lastQuestion = "";

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[character]));
}

async function refreshOverview() {
  const [health, documents, audit] = await Promise.all([
    fetch("/api/health").then((response) => response.json()),
    fetch("/api/documents").then((response) => response.json()),
    fetch("/api/audit-log").then((response) => response.json()),
  ]);
  $("#health").textContent = health.status === "ok" ? "Service healthy" : "Service error";
  $("#document-count").textContent = documents.length;
  $("#mode").textContent = health.llm_enabled ? "LLM + evidence" : "Local evidence mode";
  $("#audit-count").textContent = audit.length;
  $("#documents").innerHTML = documents.map((document) => `
    <div class="document">
      <strong>${escapeHtml(document.title)}</strong>
      <span>${escapeHtml(document.source)} - ${document.chunk_count} chunks</span>
    </div>
  `).join("");
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
}

async function ask() {
  const button = $("#ask");
  const question = $("#question").value.trim();
  if (!question) return;
  lastQuestion = question;
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Request failed");
    renderResult(payload);
    await refreshOverview();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Run audit";
  }
}

async function exportReport(exportFormat) {
  const question = lastQuestion || $("#question").value.trim();
  if (!question) return;
  const response = await fetch("/api/reports/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    const response = await fetch("/api/documents/upload", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Upload failed");
    form.reset();
    status.textContent = "Uploaded and indexed";
    await refreshOverview();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

$("#ask").addEventListener("click", ask);
$("#upload-form").addEventListener("submit", uploadDocument);
$("#export-md").addEventListener("click", () => exportReport("markdown").catch((error) => alert(error.message)));
$("#export-pdf").addEventListener("click", () => exportReport("pdf").catch((error) => alert(error.message)));
$("#example").addEventListener("click", () => {
  $("#question").value = "Can the legacy sales tool directly download the full customer list? Please explain conflicts and remediation.";
  ask();
});
refreshOverview();
