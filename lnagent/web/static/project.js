document.addEventListener("DOMContentLoaded", () => {
  const projectId = document.body.dataset.projectId;
  if (!projectId) {
    return;
  }

  const statusEl = document.getElementById("status-message");
  const loadingEl = document.getElementById("page-loading");
  const loadingTextEl = document.getElementById("page-loading-text");
  const sendInput = document.getElementById("send-input");
  const adoptText = document.getElementById("adopt-text");
  const adoptPreview = document.getElementById("adopt-preview");
  const fixIntent = document.getElementById("fix-intent");
  const fixPreview = document.getElementById("fix-preview");
  const scenePanel = document.getElementById("scene-panel");
  const sceneReconcile = document.getElementById("scene-reconcile");
  const sceneCold = document.getElementById("scene-cold");
  const sceneSummary = document.getElementById("scene-summary");
  const sceneSuggestion = document.getElementById("scene-suggestion");
  const sceneSuggestionText = document.getElementById("scene-suggestion-text");
  const exportResult = document.getElementById("export-result");
  const configForm = document.getElementById("config-form");

  const actionButtons = Array.from(document.querySelectorAll("[data-action]"));
  let pendingReconcileIndex = 0;
  let scenePrepareData = null;

  actionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.action === "send") {
        sendMessage().catch((error) => {
          setStatus(statusEl, error.message, "error");
        });
        return;
      }
      runAction(button.dataset.action).catch((error) => {
        setStatus(statusEl, error.message, "error");
      });
    });
  });

  sendInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendMessage().catch((error) => {
        setStatus(statusEl, error.message, "error");
      });
    }
  });

  if (configForm) {
    configForm.addEventListener("submit", (event) => {
      event.preventDefault();
      runAction("config-set").catch((error) => {
        setStatus(statusEl, error.message, "error");
      });
    });
  }

  init().catch((error) => {
    setStatus(statusEl, error.message, "error");
  });

  async function init() {
    await withPageBusy(
      { overlay: loadingEl, textEl: loadingTextEl, buttons: actionButtons, message: "正在打开项目…" },
      async () => {
        setStatus(statusEl, "正在打开项目…", "info");
        await apiRequest("POST", `/api/projects/${encodeURIComponent(projectId)}/open`);
        await refreshAll();
        setStatus(statusEl, "项目已就绪。", "info");
      },
    );
  }

  async function runAction(action) {
    await withPageBusy(
      { overlay: loadingEl, textEl: loadingTextEl, buttons: actionButtons },
      async () => {
        setStatus(statusEl, "", "info");
        try {
          if (action === "adopt-prepare") {
            await prepareAdopt();
          } else if (action === "adopt-commit-yes") {
            await commitAdopt(true);
          } else if (action === "adopt-commit-no") {
            await commitAdopt(false);
          } else if (action === "undo") {
            await undoLastAdopt();
          } else if (action === "export") {
            await exportBook();
          } else if (action === "fix-prepare") {
            await prepareFix();
          } else if (action === "fix-commit-yes") {
            await commitFix(true);
          } else if (action === "fix-commit-no") {
            await commitFix(false);
          } else if (action === "scene-prepare") {
            await prepareScene();
          } else if (action === "scene-reconcile-yes") {
            await reconcileCurrent(true);
          } else if (action === "scene-reconcile-no") {
            await reconcileCurrent(false);
          } else if (action === "scene-commit-yes") {
            await commitScene(true);
          } else if (action === "scene-commit-no") {
            await commitScene(false);
          } else if (action === "config-set") {
            await updateConfig("set");
          } else if (action === "config-reset") {
            await updateConfig("reset");
          } else if (action === "config-reset-all") {
            await updateConfig("reset", "all");
          }
        } catch (error) {
          setStatus(statusEl, error.message, "error");
          throw error;
        }
      },
    );
  }

  async function sendMessage() {
    const text = sendInput.value.trim();
    if (!text) {
      throw new Error("请输入消息内容。");
    }

    setBusy(actionButtons, true);
    setStatus(statusEl, "正在生成回复…", "info");
    sendInput.value = "";

    const userNode = appendMessage("user", text);
    const assistantNode = appendMessage("assistant", "", { streaming: true });
    let streamedText = "";
    let donePayload = null;
    let streamError = null;

    try {
      await streamPost(
        `/api/projects/${encodeURIComponent(projectId)}/send/stream`,
        { text },
        {
          onToken(token) {
            streamedText += token;
            updateMessageBody(assistantNode, streamedText);
          },
          onDone(payload) {
            donePayload = payload;
          },
          onError(message) {
            streamError = message;
          },
        },
      );
    } finally {
      setBusy(actionButtons, false);
    }

    if (streamError) {
      assistantNode.closest(".message")?.remove();
      userNode.closest(".message")?.remove();
      sendInput.value = text;
      throw new Error(streamError);
    }

    finishStreamingMessage(assistantNode, donePayload?.reply || streamedText);
    updateSceneSuggestion(donePayload?.scene_switch_suggestion);
    adoptText.value = donePayload?.last_candidate || streamedText;

    if (donePayload?.scene_switch_suggestion?.should_suggest) {
      setStatus(
        statusEl,
        `回复已返回。场景切换建议：${donePayload.scene_switch_suggestion.reason}`,
        "info",
      );
    } else {
      setStatus(statusEl, "回复已返回。", "info");
    }

    await refreshAll();
  }

  function updateSceneSuggestion(suggestion) {
    if (!sceneSuggestion || !sceneSuggestionText) {
      return;
    }
    if (suggestion?.should_suggest) {
      sceneSuggestionText.textContent = `建议切换场景：${suggestion.reason}`;
      sceneSuggestion.classList.remove("hidden");
      return;
    }
    sceneSuggestion.classList.add("hidden");
    sceneSuggestionText.textContent = "";
  }

  async function prepareAdopt() {
    const text = adoptText.value.trim();
    if (!text) {
      throw new Error("没有可预览的采纳正文。");
    }
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/adopt/prepare`,
      { text },
    );
    adoptPreview.textContent = formatJson(payload);
    adoptPreview.classList.remove("hidden");
    setStatus(statusEl, "已生成 Canon 变更预览，请确认是否接受设定。", "info");
  }

  async function commitAdopt(acceptedCanon) {
    const text = adoptText.value.trim();
    if (!text) {
      throw new Error("没有可采纳的正文。");
    }
    await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/adopt/commit`,
      { text, accepted_canon: acceptedCanon },
    );
    adoptPreview.classList.add("hidden");
    adoptPreview.textContent = "";
    setStatus(statusEl, acceptedCanon ? "正文已采纳，设定已更新。" : "正文已采纳，设定未更新。", "info");
    await refreshAll();
  }

  async function undoLastAdopt() {
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/undo`,
    );
    setStatus(statusEl, payload.message || "已撤销最后一次采纳。", "info");
    await refreshAll();
  }

  async function exportBook() {
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/export`,
    );
    downloadText(payload.filename, payload.content);
    if (exportResult) {
      exportResult.textContent = `已保存到 ${payload.path}，并已触发浏览器下载。`;
    }
    setStatus(statusEl, "导出完成。", "info");
  }

  async function prepareFix() {
    const intent = fixIntent.value.trim();
    if (!intent) {
      throw new Error("请输入修正意图。");
    }
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/fix/prepare`,
      { intent },
    );
    fixPreview.textContent = formatJson(payload);
    fixPreview.classList.remove("hidden");
    setStatus(statusEl, "已生成修正预览，请确认是否接受设定。", "info");
  }

  async function commitFix(acceptedCanon) {
    const intent = fixIntent.value.trim();
    if (!intent) {
      throw new Error("请输入修正意图。");
    }
    await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/fix/commit`,
      { intent, accepted_canon: acceptedCanon },
    );
    fixPreview.classList.add("hidden");
    fixPreview.textContent = "";
    setStatus(statusEl, acceptedCanon ? "修正已应用。" : "修正流程已完成（未更新设定）。", "info");
    await refreshAll();
  }

  async function prepareScene() {
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/scene/prepare`,
    );
    scenePrepareData = payload;
    pendingReconcileIndex = 0;
    scenePanel.classList.remove("hidden");
    if (sceneSuggestion) {
      sceneSuggestion.classList.add("hidden");
    }
    renderSceneFlow();
    setStatus(statusEl, "场景切换已准备，请依次确认 Hot Canon 与 Cold 摘要。", "info");
  }

  function renderSceneFlow() {
    if (!scenePrepareData) {
      sceneReconcile.classList.add("hidden");
      sceneCold.classList.add("hidden");
      return;
    }

    const items = scenePrepareData.reconcile_items || [];
    if (pendingReconcileIndex < items.length) {
      const item = items[pendingReconcileIndex];
      sceneReconcile.innerHTML = `
        <h3>Hot Canon 确认 (${pendingReconcileIndex + 1}/${items.length})</h3>
        <pre class="pre-block">${escapeHtml(formatJson(item.proposal))}</pre>
        <p class="hint">请选择是否接受本次设定变更。</p>
      `;
      sceneReconcile.classList.remove("hidden");
      sceneCold.classList.add("hidden");
      return;
    }

    sceneReconcile.classList.add("hidden");
    const proposal = scenePrepareData.proposal || {};
    sceneSummary.value = proposal.summary || "";
    sceneCold.innerHTML = `
      <h3>Cold 摘要确认</h3>
      <p><span class="badge">${escapeHtml(proposal.location || "")}</span>
      <span class="badge">${escapeHtml(proposal.time || "")}</span></p>
      <pre class="pre-block">${escapeHtml(formatJson(proposal.key_points || []))}</pre>
    `;
    sceneCold.classList.remove("hidden");
  }

  async function reconcileCurrent(acceptedCanon) {
    if (!scenePrepareData) {
      throw new Error("请先准备场景切换。");
    }
    const items = scenePrepareData.reconcile_items || [];
    const item = items[pendingReconcileIndex];
    if (!item) {
      throw new Error("没有待确认的 reconcile 项。");
    }
    await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/scene/reconcile`,
      { stack_index: item.stack_index, accepted_canon: acceptedCanon },
    );
    pendingReconcileIndex += 1;
    renderSceneFlow();
    setStatus(statusEl, "Hot Canon 项已处理。", "info");
  }

  async function commitScene(coldAccepted) {
    const summary = sceneSummary.value.trim();
    if (!summary) {
      throw new Error("请填写场景摘要。");
    }
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/scene/commit`,
      { cold_accepted: coldAccepted, summary },
    );
    scenePanel.classList.add("hidden");
    scenePrepareData = null;
    pendingReconcileIndex = 0;
    setStatus(statusEl, `场景已切换到 ${payload.new_scene_id}。`, "info");
    await refreshAll();
  }

  async function updateConfig(action, keyOverride) {
    const keySelect = document.getElementById("config-key");
    const valueInput = document.getElementById("config-value");
    const key = keyOverride || keySelect?.value || "";
    const body = { action, key };
    if (action === "set") {
      body.value = Number(valueInput?.value);
      if (!Number.isFinite(body.value) || body.value < 0) {
        throw new Error("配置值必须是非负整数。");
      }
    }
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/config`,
      body,
    );
    renderConfigViews(payload.config);
    setStatus(statusEl, payload.message || "配置已更新。", "info");
  }

  async function refreshAll() {
    const [session, meta, canon, synopsis, manuscript, manuscripts, config] = await Promise.all([
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/session`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/meta`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/canon`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/synopsis`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/manuscript`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/manuscripts`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/config`),
    ]);

    document.getElementById("meta-title").textContent = meta.title || projectId;
    document.getElementById("meta-style").textContent = meta.style || "";
    document.getElementById("scene-id").textContent = session.scene_id || "";
    document.getElementById("turns-since-adopt").textContent = String(
      session.turns_since_last_adopt ?? 0,
    );
    document.getElementById("budget-notice").textContent = session.budget_notice || "无";

    renderMessages(session.messages || []);
    document.getElementById("adopted-prose").textContent = session.adopted_prose || "";
    adoptText.value = session.last_candidate || "";

    document.getElementById("meta-summary").innerHTML = renderMetaSummary(meta);
    document.getElementById("canon-summary").innerHTML = renderCanonSummary(canon);
    document.getElementById("synopsis-summary").innerHTML = renderSynopsisSummary(synopsis);
    document.getElementById("manuscript-list").innerHTML = renderManuscriptList(
      manuscripts,
      session.scene_id,
    );

    document.getElementById("meta-json").textContent = formatJson(meta);
    document.getElementById("canon-json").textContent = formatJson(canon);
    document.getElementById("synopsis-json").textContent = formatJson(synopsis);
    document.getElementById("manuscript-text").textContent = manuscript.text || "";

    renderConfigViews(config);
  }

  function renderConfigViews(configPayload) {
    const summary = document.getElementById("config-summary");
    if (summary) {
      summary.innerHTML = renderConfigSummary(configPayload);
    }
    populateConfigForm(configPayload);
  }

  function renderMessages(messages) {
    const container = document.getElementById("messages");
    if (!messages.length) {
      container.innerHTML = '<p class="hint">暂无对话，发送第一条消息开始写作。</p>';
      return;
    }
    container.innerHTML = messages
      .map((message) => renderMessageHtml(message.role, message.content))
      .join("");
    container.scrollTop = container.scrollHeight;
  }

  function renderMessageHtml(role, content, options = {}) {
    const roleClass = role === "user" ? "user" : "assistant";
    const roleLabel = role === "user" ? "作者" : "助手";
    const streamingClass = options.streaming ? " streaming" : "";
    return `
      <article class="message ${roleClass}${streamingClass}">
        <div class="message-role">${escapeHtml(roleLabel)}</div>
        <div class="message-body">${escapeHtml(content)}</div>
      </article>
    `;
  }

  function appendMessage(role, content, options = {}) {
    const container = document.getElementById("messages");
    const hint = container.querySelector(".hint");
    if (hint) {
      hint.remove();
    }
    container.insertAdjacentHTML("beforeend", renderMessageHtml(role, content, options));
    const node = container.lastElementChild?.querySelector(".message-body");
    container.scrollTop = container.scrollHeight;
    return node;
  }

  function updateMessageBody(node, content) {
    if (!node) {
      return;
    }
    node.textContent = content;
    const container = document.getElementById("messages");
    container.scrollTop = container.scrollHeight;
  }

  function finishStreamingMessage(node, content) {
    if (!node) {
      return;
    }
    node.textContent = content;
    node.closest(".message")?.classList.remove("streaming");
  }
});
