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

function applyInlineMarkdown(text) {
  return String(text ?? "")
    .replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
}

function isMarkdownTableRow(line) {
  const trimmed = String(line ?? "").trim();
  if (!trimmed || trimmed.startsWith("#")) {
    return false;
  }
  if (/^[-*]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) {
    return false;
  }
  if (trimmed.startsWith("|")) {
    return trimmed.includes("|", 1);
  }
  return trimmed.includes("|");
}

function isMarkdownTableSeparator(line) {
  const trimmed = String(line ?? "").trim();
  if (!isMarkdownTableRow(trimmed)) {
    return false;
  }
  const cells = parseMarkdownTableRow(trimmed);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function parseMarkdownTableRow(line) {
  let trimmed = String(line ?? "").trim();
  if (trimmed.startsWith("|")) {
    trimmed = trimmed.slice(1);
  }
  if (trimmed.endsWith("|")) {
    trimmed = trimmed.slice(0, -1);
  }
  return trimmed.split("|").map((cell) => cell.trim());
}

function renderMarkdownTable(tableLines) {
  if (!tableLines.length) {
    return "";
  }
  if (tableLines.length === 1) {
    return `<p>${applyInlineMarkdown(tableLines[0])}</p>`;
  }

  const headerCells = parseMarkdownTableRow(tableLines[0]);
  const hasSeparator = isMarkdownTableSeparator(tableLines[1]);
  const bodyLines = hasSeparator ? tableLines.slice(2) : tableLines.slice(1);
  const rows = [headerCells];
  for (const rowLine of bodyLines) {
    if (!isMarkdownTableRow(rowLine)) {
      continue;
    }
    rows.push(parseMarkdownTableRow(rowLine));
  }

  const columnCount = Math.max(...rows.map((row) => row.length), 1);
  const normalizedRows = rows.map((row) => {
    const next = row.slice();
    while (next.length < columnCount) {
      next.push("");
    }
    return next;
  });

  const [head, ...body] = normalizedRows;
  let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
  for (const cell of head) {
    html += `<th>${applyInlineMarkdown(cell)}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of body) {
    html += "<tr>";
    for (const cell of row) {
      html += `<td>${applyInlineMarkdown(cell)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table></div>";
  return html;
}

function renderMarkdownBlock(text) {
  const lines = String(text ?? "").split("\n");
  const html = [];
  let inUl = false;
  let inOl = false;
  let index = 0;

  const closeLists = () => {
    if (inUl) {
      html.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      html.push("</ol>");
      inOl = false;
    }
  };

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (isMarkdownTableRow(line)) {
      closeLists();
      const tableLines = [];
      while (index < lines.length && isMarkdownTableRow(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      html.push(renderMarkdownTable(tableLines));
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      closeLists();
      html.push("<hr>");
      index += 1;
      continue;
    }
    const h3 = line.match(/^### (.+)$/);
    if (h3) {
      closeLists();
      html.push(`<h3>${applyInlineMarkdown(h3[1])}</h3>`);
      index += 1;
      continue;
    }
    const h2 = line.match(/^## (.+)$/);
    if (h2) {
      closeLists();
      html.push(`<h2>${applyInlineMarkdown(h2[1])}</h2>`);
      index += 1;
      continue;
    }
    const h1 = line.match(/^# (.+)$/);
    if (h1) {
      closeLists();
      html.push(`<h1>${applyInlineMarkdown(h1[1])}</h1>`);
      index += 1;
      continue;
    }
    const ul = line.match(/^[-*] (.+)$/);
    if (ul) {
      if (!inUl) {
        closeLists();
        html.push("<ul>");
        inUl = true;
      }
      html.push(`<li>${applyInlineMarkdown(ul[1])}</li>`);
      index += 1;
      continue;
    }
    const ol = line.match(/^\d+\. (.+)$/);
    if (ol) {
      if (!inOl) {
        closeLists();
        html.push("<ol>");
        inOl = true;
      }
      html.push(`<li>${applyInlineMarkdown(ol[1])}</li>`);
      index += 1;
      continue;
    }
    if (!trimmed) {
      closeLists();
      index += 1;
      continue;
    }
    closeLists();
    html.push(`<p>${applyInlineMarkdown(line)}</p>`);
    index += 1;
  }

  closeLists();
  return html.join("\n");
}

function renderMarkdown(source) {
  const text = String(source ?? "");
  if (!text) {
    return "";
  }

  const segments = [];
  const pattern = /```([\s\S]*?)```/g;
  let lastIndex = 0;
  let match = pattern.exec(text);
  while (match) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    segments.push({ type: "code", value: match[1].trim() });
    lastIndex = pattern.lastIndex;
    match = pattern.exec(text);
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  if (!segments.length) {
    segments.push({ type: "text", value: text });
  }

  return segments
    .map((segment) => {
      if (segment.type === "code") {
        return `<pre class="md-pre"><code>${escapeHtml(segment.value)}</code></pre>`;
      }
      return renderMarkdownBlock(escapeHtml(segment.value));
    })
    .join("\n");
}

function preferLongerText(primary, secondary) {
  const left = String(primary ?? "");
  const right = String(secondary ?? "");
  return right.length > left.length ? right : left;
}

function setMessageBody(node, content, { markdown = true, streaming = false } = {}) {
  if (!node) {
    return;
  }
  if (streaming || !markdown) {
    node.textContent = content;
    node.classList.remove("md-body");
    return;
  }
  node.innerHTML = renderMarkdown(content);
  node.classList.add("md-body");
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
