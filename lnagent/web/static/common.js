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

function parseSseEvent(raw) {
  let name = "message";
  const dataLines = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  return { name, data: dataLines.join("\n") };
}

function consumeSseBuffer(buffer, handlers) {
  const segments = buffer.split("\n\n");
  const rest = segments.pop() || "";
  for (const segment of segments) {
    if (!segment.trim()) {
      continue;
    }
    const event = parseSseEvent(segment);
    if (event.name === "token") {
      const payload = JSON.parse(event.data);
      handlers.onToken?.(payload.text || "");
    } else if (event.name === "done") {
      handlers.onDone?.(JSON.parse(event.data));
    } else if (event.name === "error") {
      const payload = JSON.parse(event.data);
      handlers.onError?.(payload.error || "流式请求失败");
    }
  }
  return rest;
}

async function streamPost(path, body, handlers) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const payload = await response.json();
      if (payload.error) {
        message = payload.error;
      }
    } catch (_error) {
      // ignore non-JSON error bodies
    }
    throw new Error(message);
  }
  if (!response.body) {
    throw new Error("浏览器不支持流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = consumeSseBuffer(buffer, handlers);
  }
  if (buffer.trim()) {
    consumeSseBuffer(`${buffer}\n\n`, handlers);
  }
}
