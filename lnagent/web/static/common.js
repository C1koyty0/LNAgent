async function apiRequest(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.error || `请求失败 (${response.status})`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function setStatus(element, message, kind) {
  if (!element) {
    return;
  }
  element.textContent = message || "";
  element.className = "status";
  if (message) {
    element.classList.add(kind || "info");
  }
}

function setBusy(buttons, busy) {
  buttons.forEach((button) => {
    if (button) {
      button.disabled = busy;
    }
  });
}

function setPageLoading(overlay, textEl, busy, message) {
  if (!overlay) {
    return;
  }
  overlay.classList.toggle("hidden", !busy);
  if (textEl && message) {
    textEl.textContent = message;
  }
}

function downloadText(filename, content) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function withPageBusy({ overlay, textEl, buttons, message }, task) {
  setPageLoading(overlay, textEl, true, message || "处理中…");
  setBusy(buttons, true);
  try {
    return await task();
  } finally {
    setPageLoading(overlay, textEl, false);
    setBusy(buttons, false);
  }
}
