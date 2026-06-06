document.addEventListener("DOMContentLoaded", () => {
  const projectId = document.body.dataset.projectId;
  if (!projectId) {
    return;
  }

  const statusEl = document.getElementById("status-message");
  const sendButton = document.getElementById("send-button");
  const sendInput = document.getElementById("send-input");
  const adoptText = document.getElementById("adopt-text");
  const adoptPreview = document.getElementById("adopt-preview");
  const fixIntent = document.getElementById("fix-intent");
  const fixPreview = document.getElementById("fix-preview");
  const scenePanel = document.getElementById("scene-panel");
  const sceneReconcile = document.getElementById("scene-reconcile");
  const sceneCold = document.getElementById("scene-cold");
  const sceneSummary = document.getElementById("scene-summary");

  const actionButtons = Array.from(document.querySelectorAll("[data-action]"));
  let pendingReconcileIndex = 0;
  let scenePrepareData = null;

  actionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      handleAction(button.dataset.action).catch((error) => {
        setStatus(statusEl, error.message, "error");
      });
    });
  });

  sendInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      handleAction("send").catch((error) => {
        setStatus(statusEl, error.message, "error");
      });
    }
  });

  init().catch((error) => {
    setStatus(statusEl, error.message, "error");
  });

  async function init() {
    setBusy(actionButtons, true);
    setStatus(statusEl, "正在打开项目…", "info");
    try {
      await apiRequest("POST", `/api/projects/${encodeURIComponent(projectId)}/open`);
      await refreshAll();
      setStatus(statusEl, "项目已就绪。", "info");
    } finally {
      setBusy(actionButtons, false);
    }
  }

  async function handleAction(action) {
    setBusy(actionButtons, true);
    setStatus(statusEl, "", "info");
    try {
      if (action === "send") {
        await sendMessage();
      } else if (action === "adopt-prepare") {
        await prepareAdopt();
      } else if (action === "adopt-commit-yes") {
        await commitAdopt(true);
      } else if (action === "adopt-commit-no") {
        await commitAdopt(false);
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
      }
    } catch (error) {
      setStatus(statusEl, error.message, "error");
      throw error;
    } finally {
      setBusy(actionButtons, false);
    }
  }

  async function sendMessage() {
    const text = sendInput.value.trim();
    if (!text) {
      throw new Error("请输入消息内容。");
    }
    setStatus(statusEl, "正在生成回复…", "info");
    const payload = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/send`,
      { text },
    );
    sendInput.value = "";
    if (payload.scene_switch_suggestion?.should_suggest) {
      setStatus(
        statusEl,
        `回复已返回。场景切换建议：${payload.scene_switch_suggestion.reason}`,
        "info",
      );
    } else {
      setStatus(statusEl, "回复已返回。", "info");
    }
    await refreshAll();
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
    setStatus(
      statusEl,
      `场景已切换到 ${payload.new_scene_id}。`,
      "info",
    );
    await refreshAll();
  }

  async function refreshAll() {
    const [session, meta, canon, synopsis, manuscript] = await Promise.all([
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/session`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/meta`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/canon`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/synopsis`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/manuscript`),
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

    document.getElementById("meta-json").textContent = formatJson(meta);
    document.getElementById("canon-json").textContent = formatJson(canon);
    document.getElementById("synopsis-json").textContent = formatJson(synopsis);
    document.getElementById("manuscript-text").textContent = manuscript.text || "";
  }

  function renderMessages(messages) {
    const container = document.getElementById("messages");
    if (!messages.length) {
      container.innerHTML = '<p class="hint">暂无对话，发送第一条消息开始写作。</p>';
      return;
    }
    container.innerHTML = messages
      .map((message) => {
        const roleClass = message.role === "user" ? "user" : "assistant";
        const roleLabel = message.role === "user" ? "作者" : "助手";
        return `
          <article class="message ${roleClass}">
            <div class="message-role">${escapeHtml(roleLabel)}</div>
            <div>${escapeHtml(message.content)}</div>
          </article>
        `;
      })
      .join("");
    container.scrollTop = container.scrollHeight;
  }
});
