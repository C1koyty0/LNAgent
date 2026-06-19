document.addEventListener("DOMContentLoaded", () => {
  const projectId = resolveProjectId();
  if (!projectId) {
    const statusEl = document.getElementById("status-message");
    setStatus(statusEl, "无法读取 project_id，请刷新页面或返回首页重试。", "error");
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
  const metaForm = document.getElementById("meta-form");
  const modeToggle = document.getElementById("mode-toggle");
  const modeDescription = document.getElementById("mode-description");
  const writingMessagesEl = document.getElementById("messages");
  const discussionMessagesEl = document.getElementById("discussion-messages");
  const discussionBriefEl = document.getElementById("discussion-brief");
  const discussionWeakHintEl = document.getElementById("discussion-weak-hint");
  const briefEditForm = document.getElementById("brief-edit-form");
  const briefEditTodo = document.getElementById("brief-edit-todo");
  const briefEditConstraints = document.getElementById("brief-edit-constraints");
  const briefEditOpenQuestions = document.getElementById("brief-edit-open-questions");
  const adoptPanel = document.getElementById("adopt-panel");
  const fixPanel = document.getElementById("fix-panel");
  const metaStyleInput = document.getElementById("meta-style-input");
  const metaPovInput = document.getElementById("meta-pov-input");
  const metaTenseInput = document.getElementById("meta-tense-input");
  const metaGenreInput = document.getElementById("meta-genre-input");
  const metaToneInput = document.getElementById("meta-tone-input");
  const metaTargetAudienceInput = document.getElementById("meta-target-audience-input");
  const metaTaboosInput = document.getElementById("meta-taboos-input");
  const metaNarrativeRulesInput = document.getElementById("meta-narrative-rules-input");
  const worldbookSourceInput = document.getElementById("worldbook-source");
  const worldbookStatusEl = document.getElementById("worldbook-status");
  const worldbookStatusNoteEl = document.getElementById("worldbook-status-note");
  const worldbookApplyButton = document.getElementById("worldbook-apply-button");
  const worldbookPreviewOverviewEl = document.getElementById("worldbook-preview-overview");
  const worldbookPreviewGlobalRulesEl = document.getElementById("worldbook-preview-global-rules");
  const worldbookPreviewScopesEl = document.getElementById("worldbook-preview-scopes");
  const worldbookPreviewGlossaryEl = document.getElementById("worldbook-preview-glossary");
  const worldbookPreviewOpenQuestionsEl = document.getElementById("worldbook-preview-open-questions");

  const actionButtons = Array.from(document.querySelectorAll("[data-action]"));
  const modeButtons = Array.from(modeToggle?.querySelectorAll("[data-mode]") || []);

  let pendingReconcileIndex = 0;
  let scenePrepareData = null;
  let currentMode = "writing";
  let writingSession = null;
  let discussionState = null;
  let metaState = null;
  let canonState = null;
  let synopsisState = null;
  let manuscriptsState = null;
  let configState = null;
  let worldbookState = null;

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

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const nextMode = button.dataset.mode || "writing";
      if (nextMode === currentMode) {
        return;
      }
      setMode(nextMode);
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

  if (metaForm) {
    metaForm.setAttribute("data-bound", "meta-form");
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
        setMode("writing");
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
          } else if (action === "discussion-refresh") {
            await refreshDiscussionBrief();
          } else if (action === "discussion-clear") {
            await clearDiscussionMessages();
          } else if (action === "discussion-edit-toggle") {
            toggleBriefEditForm(true);
          } else if (action === "discussion-edit-cancel") {
            toggleBriefEditForm(false);
          } else if (action === "discussion-brief-save") {
            await saveDiscussionBrief();
          } else if (action === "meta-save") {
            await saveMeta();
          } else if (action === "worldbook-save-source") {
            await saveWorldbookSource();
          } else if (action === "worldbook-extract") {
            await extractWorldbook();
          } else if (action === "worldbook-apply") {
            await applyWorldbook();
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
    if (currentMode === "discussion") {
      await sendDiscussionMessage(text);
      return;
    }
    await sendWritingMessage(text);
  }

  async function sendDiscussionMessage(text) {
    setBusy(actionButtons, true);
    setStatus(statusEl, "正在记录讨论…", "info");
    sendInput.value = "";

    const userNode = appendMessageToContainer(discussionMessagesEl, "user", text);
    const assistantNode = appendMessageToContainer(discussionMessagesEl, "assistant", "", { streaming: true });

    try {
      const payload = await apiRequest(
        "POST",
        `/api/projects/${encodeURIComponent(projectId)}/discussion/send`,
        { text },
      );
      finishStreamingMessage(assistantNode, payload.reply || "");
      discussionState = payload;
      renderDiscussionState(discussionState);
      setStatus(statusEl, "讨论回复已记录。", "info");
    } catch (error) {
      assistantNode.closest(".message")?.remove();
      userNode.closest(".message")?.remove();
      sendInput.value = text;
      throw error;
    } finally {
      setBusy(actionButtons, false);
    }
  }

  async function sendWritingMessage(text) {
    setBusy(actionButtons, true);
    setStatus(statusEl, "正在生成回复…", "info");
    sendInput.value = "";

    const userNode = appendMessageToContainer(writingMessagesEl, "user", text);
    const assistantNode = appendMessageToContainer(writingMessagesEl, "assistant", "", { streaming: true });
    let streamedText = "";
    let donePayload = null;
    let streamError = null;

    try {
      await streamPost(
        `/api/projects/${encodeURIComponent(projectId)}/writing/send/stream`,
        { text },
        {
          onToken(token) {
            streamedText += token;
            updateMessageBody(writingMessagesEl, assistantNode, streamedText);
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

    finishStreamingMessage(
      assistantNode,
      preferLongerText(streamedText, donePayload?.reply),
    );
    updateSceneSuggestion(donePayload?.scene_switch_suggestion);
    adoptText.value = preferLongerText(streamedText, donePayload?.last_candidate);

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

  function setMode(nextMode) {
    currentMode = nextMode === "discussion" ? "discussion" : "writing";
    modeButtons.forEach((button) => {
      const active = button.dataset.mode === currentMode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    writingMessagesEl?.classList.toggle("hidden", currentMode !== "writing");
    discussionMessagesEl?.classList.toggle("hidden", currentMode !== "discussion");
    discussionWeakHintEl?.classList.toggle("hidden", currentMode !== "discussion");
    [adoptPanel, fixPanel, scenePanel].forEach((panel) => {
      panel?.classList.toggle("is-weakened", currentMode === "discussion");
    });
    if (modeDescription) {
      modeDescription.textContent =
        currentMode === "discussion"
          ? "当前为讨论模式：消息会写入 discussion 轨，并可随时刷新 Discussion Brief。"
          : "当前为写作模式：会生成候选正文，并保持 SSE 流式体验。";
    }
    if (currentMode === "discussion") {
      renderDiscussionState(discussionState);
    } else {
      renderWritingSession(writingSession);
    }
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
    configState = payload.config;
    renderConfigViews(configState);
    setStatus(statusEl, payload.message || "配置已更新。", "info");
  }

  async function refreshDiscussionBrief() {
    discussionState = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/discussion/refresh`,
    );
    renderDiscussionState(discussionState);
    setStatus(statusEl, "Discussion Brief 已刷新。", "info");
  }

  async function clearDiscussionMessages() {
    discussionState = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/discussion/clear`,
    );
    renderDiscussionState(discussionState);
    setStatus(statusEl, "讨论原始消息已清空。", "info");
  }

  function populateBriefEditForm(brief) {
    if (!briefEditTodo || !briefEditConstraints || !briefEditOpenQuestions) {
      return;
    }
    briefEditTodo.value = briefItemsToText(brief?.todo_items);
    briefEditConstraints.value = briefItemsToText(brief?.constraints);
    briefEditOpenQuestions.value = briefItemsToText(brief?.open_questions);
  }

  function toggleBriefEditForm(show) {
    if (!briefEditForm) {
      return;
    }
    if (show) {
      populateBriefEditForm(discussionState?.brief || {});
      briefEditForm.classList.remove("hidden");
      return;
    }
    briefEditForm.classList.add("hidden");
  }

  async function saveDiscussionBrief() {
    if (!briefEditTodo || !briefEditConstraints || !briefEditOpenQuestions) {
      throw new Error("brief 编辑表单未就绪。");
    }
    discussionState = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/discussion/brief/save`,
      {
        todo_items: textToBriefItems(briefEditTodo.value),
        constraints: textToBriefItems(briefEditConstraints.value),
        open_questions: textToBriefItems(briefEditOpenQuestions.value),
      },
    );
    renderDiscussionState(discussionState);
    toggleBriefEditForm(false);
    setStatus(statusEl, "Discussion Brief 已保存，写作将读取最新内容。", "info");
  }

  function populateMetaForm(meta) {
    if (!metaStyleInput) {
      return;
    }
    metaStyleInput.value = meta?.style || "";
    metaPovInput.value = meta?.pov || "";
    metaTenseInput.value = meta?.tense || "";
    metaGenreInput.value = meta?.genre || "";
    metaToneInput.value = meta?.tone || "";
    metaTargetAudienceInput.value = meta?.target_audience || "";
    metaTaboosInput.value = metaListToText(meta?.taboos);
    metaNarrativeRulesInput.value = metaListToText(meta?.narrative_rules);
  }

  async function saveMeta() {
    if (!metaStyleInput) {
      throw new Error("meta 编辑表单未就绪。");
    }
    const payload = await apiRequest(
      "PUT",
      `/api/projects/${encodeURIComponent(projectId)}/meta`,
      {
        style: metaStyleInput.value,
        pov: metaPovInput.value,
        tense: metaTenseInput.value,
        genre: metaGenreInput.value,
        tone: metaToneInput.value,
        target_audience: metaTargetAudienceInput.value,
        taboos: textToMetaList(metaTaboosInput.value),
        narrative_rules: textToMetaList(metaNarrativeRulesInput.value),
      },
    );
    metaState = payload;
    document.getElementById("meta-title").textContent = payload.title || projectId;
    document.getElementById("meta-style").textContent = payload.style || "";
    document.getElementById("meta-summary").innerHTML = renderMetaSummary(metaState) + renderMetaEditForm(metaState);
    document.getElementById("meta-json").textContent = formatJson(metaState);
    populateMetaForm(metaState);
    setStatus(statusEl, "Meta 已保存，后续写作将读取最新叙事配置。", "info");
  }

  async function saveWorldbookSource() {
    if (!worldbookSourceInput) {
      throw new Error("worldbook 编辑器未就绪。");
    }
    worldbookState = await apiRequest(
      "PUT",
      `/api/projects/${encodeURIComponent(projectId)}/worldbook/source`,
      { source: worldbookSourceInput.value },
    );
    renderWorldbook(worldbookState);
    setStatus(statusEl, "Worldbook 文档已保存。", "info");
  }

  async function extractWorldbook() {
    worldbookState = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/worldbook/extract`,
    );
    renderWorldbook(worldbookState);
    setStatus(statusEl, "Worldbook 已提炼，可检查 preview 后决定是否应用。", "info");
  }

  async function applyWorldbook() {
    worldbookState = await apiRequest(
      "POST",
      `/api/projects/${encodeURIComponent(projectId)}/worldbook/apply`,
    );
    metaState = worldbookState.meta || metaState;
    renderWorldbook(worldbookState);
    if (metaState) {
      document.getElementById("meta-title").textContent = metaState.title || projectId;
      document.getElementById("meta-style").textContent = metaState.style || "";
      document.getElementById("meta-summary").innerHTML = renderMetaSummary(metaState) + renderMetaEditForm(metaState);
      document.getElementById("meta-json").textContent = formatJson(metaState);
      populateMetaForm(metaState);
    }
    setStatus(statusEl, "Worldbook 已应用到 Meta 世界观。", "info");
  }

  function syncWorldbookActionButtons(payload) {
    if (!worldbookApplyButton) {
      return;
    }
    const canApply = payload?.status === "preview_ready";
    worldbookApplyButton.disabled = !canApply;
    worldbookApplyButton.title = canApply
      ? ""
      : "只有最新提炼出的 preview 才能应用到 Meta 世界观。";
  }

  async function refreshAll() {
    const [session, meta, canon, synopsis, manuscripts, config, discussion, worldbook] = await Promise.all([
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/session`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/meta`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/canon`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/synopsis`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/manuscripts`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/config`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/discussion/get`),
      apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/worldbook`),
    ]);

    writingSession = session;
    discussionState = discussion;
    metaState = meta;
    canonState = canon;
    synopsisState = synopsis;
    manuscriptsState = manuscripts;
    configState = config;
    worldbookState = worldbook;

    document.getElementById("meta-title").textContent = meta.title || projectId;
    document.getElementById("meta-style").textContent = meta.style || "";
    document.getElementById("scene-id").textContent = session.scene_id || "";
    document.getElementById("turns-since-adopt").textContent = String(
      session.turns_since_last_adopt ?? 0,
    );
    document.getElementById("budget-notice").textContent = session.budget_notice || "无";

    renderWritingSession(writingSession);
    renderDiscussionState(discussionState);

    document.getElementById("meta-summary").innerHTML = renderMetaSummary(metaState) + renderMetaEditForm(metaState);
    document.getElementById("canon-summary").innerHTML = renderCanonSummary(canonState);
    document.getElementById("synopsis-summary").innerHTML = renderSynopsisSummary(synopsisState);
    document.getElementById("manuscript-list").innerHTML = renderManuscriptList(
      manuscriptsState,
      session.scene_id,
    );

    populateMetaForm(metaState);
    document.getElementById("meta-json").textContent = formatJson(metaState);
    document.getElementById("canon-json").textContent = formatJson(canonState);
    document.getElementById("synopsis-json").textContent = formatJson(synopsisState);

    renderConfigViews(configState);
    renderWorldbook(worldbookState);
  }

  function renderWritingSession(session) {
    if (!session) {
      return;
    }
    document.getElementById("writing-progress").innerHTML = renderWritingProgress(
      session,
      manuscriptsState || { scenes: [] },
      synopsisState || { scenes: [] },
    );
    renderMessagesInContainer(
      writingMessagesEl,
      session.messages || [],
      "暂无对话，发送第一条消息开始写作。",
    );
    adoptText.value = session.last_candidate || "";
  }

  function renderDiscussionState(payload) {
    if (discussionBriefEl) {
      discussionBriefEl.innerHTML = renderDiscussionBrief(payload?.brief || {}, {
        messageCount: Array.isArray(payload?.messages) ? payload.messages.length : 0,
      });
    }
    renderMessagesInContainer(
      discussionMessagesEl,
      payload?.messages || [],
      "暂无讨论消息，切到讨论模式后发送第一条消息开始梳理。",
    );
  }

  function renderConfigViews(configPayload) {
    const summary = document.getElementById("config-summary");
    if (summary) {
      summary.innerHTML = renderConfigSummary(configPayload);
    }
    populateConfigForm(configPayload);
  }

  function renderWorldbook(payload) {
    if (!payload) {
      return;
    }
    if (worldbookSourceInput) {
      worldbookSourceInput.value = payload.source || "";
    }
    const status = renderWorldbookStatus(payload.status);
    if (worldbookStatusEl) {
      worldbookStatusEl.innerHTML = `<span class='badge ${escapeHtml(status.badgeClass || `worldbook-status-badge ${status.className}`)}'>${escapeHtml(status.label)}</span>`;
    }
    if (worldbookStatusNoteEl) {
      worldbookStatusNoteEl.textContent = status.note;
    }
    syncWorldbookActionButtons(payload);
    const preview = renderWorldbookPreview(payload);
    if (worldbookPreviewOverviewEl) {
      worldbookPreviewOverviewEl.innerHTML = preview.overview;
    }
    if (worldbookPreviewGlobalRulesEl) {
      worldbookPreviewGlobalRulesEl.innerHTML = `<summary>全局规则</summary>${preview.globalRules}`;
    }
    if (worldbookPreviewScopesEl) {
      worldbookPreviewScopesEl.innerHTML = `<summary>Scope 规则</summary>${preview.scopes}`;
    }
    if (worldbookPreviewGlossaryEl) {
      worldbookPreviewGlossaryEl.innerHTML = `<summary>术语表</summary>${preview.glossary}`;
    }
    if (worldbookPreviewOpenQuestionsEl) {
      worldbookPreviewOpenQuestionsEl.innerHTML = `<summary>待解问题</summary>${preview.openQuestions}`;
    }
  }

  function renderMessagesInContainer(container, messages, emptyHint) {
    if (!container) {
      return;
    }
    if (!messages.length) {
      container.innerHTML = `<p class="hint">${escapeHtml(emptyHint)}</p>`;
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
        <div class="message-body">${renderMarkdown(content)}</div>
      </article>
    `;
  }

  function appendMessageToContainer(container, role, content, options = {}) {
    const hint = container?.querySelector(".hint");
    if (hint) {
      hint.remove();
    }
    container?.insertAdjacentHTML("beforeend", renderMessageHtml(role, content, options));
    const node = container?.lastElementChild?.querySelector(".message-body");
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
    return node;
  }

  function updateMessageBody(container, node, content) {
    setMessageBody(node, content, { markdown: false, streaming: true });
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }

  function finishStreamingMessage(node, content) {
    setMessageBody(node, content, { markdown: true, streaming: false });
    node.closest(".message")?.classList.remove("streaming");
  }
});

function resolveProjectId() {
  const fromBody = document.body.dataset.projectId;
  if (fromBody) {
    return fromBody;
  }
  const fromPage = document.querySelector("[data-project-id]");
  return fromPage?.dataset.projectId || "";
}
