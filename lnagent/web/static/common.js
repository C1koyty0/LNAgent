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
