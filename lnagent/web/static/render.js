function canonFieldLabel(key) {
  const labels = {
    abilities: "能力",
    status: "状态",
    relationships: "关系",
    inventory: "物品",
    location: "位置",
  };
  return labels[key] || key;
}

function formatCanonFieldValue(value, depth = 0) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return "（无）";
    }
    return value
      .map((item) => formatCanonFieldValue(item, depth + 1))
      .filter(Boolean)
      .join("；");
  }
  if (typeof value === "object") {
    if (value.summary) {
      return String(value.summary);
    }
    if (value.name && depth > 0) {
      return String(value.name);
    }
    return Object.entries(value)
      .map(([key, nested]) => `${key}: ${formatCanonFieldValue(nested, depth + 1)}`)
      .filter((line) => !line.endsWith(": "))
      .join("；");
  }
  return String(value);
}

function renderCanonAbilities(abilities) {
  if (!Array.isArray(abilities) || !abilities.length) {
    return "<span class='hint'>（无）</span>";
  }
  return `<ul class='plain-list canon-ability-list'>${abilities
    .map((ability) => {
      const title = ability.name || ability.id || "未命名能力";
      const detail = ability.summary ? `<span class='hint'> — ${escapeHtml(ability.summary)}</span>` : "";
      return `<li><strong>${escapeHtml(title)}</strong>${detail}</li>`;
    })
    .join("")}</ul>`;
}

function renderCanonCharacter(character) {
  const name = character.name || "未命名";
  const fields = Object.entries(character).filter(([key]) => key !== "name");
  const body = fields
    .map(([key, value]) => {
      if (key === "abilities" && Array.isArray(value)) {
        return `
          <div class='canon-field'>
            <span class='canon-field-key'>${escapeHtml(canonFieldLabel(key))}</span>
            ${renderCanonAbilities(value)}
          </div>
        `;
      }
      const text = formatCanonFieldValue(value);
      if (!text) {
        return "";
      }
      return `
        <div class='canon-field'>
          <span class='canon-field-key'>${escapeHtml(canonFieldLabel(key))}</span>
          <div class='canon-field-val'>${escapeHtml(text)}</div>
        </div>
      `;
    })
    .join("");
  return `<li class='canon-character'><strong>${escapeHtml(name)}</strong>${body}</li>`;
}

function renderMetaSummary(meta) {
  const rows = [
    ["书名", meta.title],
    ["文风", meta.style],
    ["体裁", meta.genre],
    ["基调", meta.tone],
    ["视角", meta.pov],
    ["时态", meta.tense],
    ["目标读者", meta.target_audience],
  ];
  const worldRules = meta.world?.rules || [];
  const scopedRules = meta.world?.scoped || [];
  const taboos = meta.taboos || [];
  const narrativeRules = meta.narrative_rules || [];

  let html = renderKeyValueRows(rows);
  if (worldRules.length) {
    html += renderBulletSection("世界规则", worldRules);
  }
  if (scopedRules.length) {
    html += scopedRules
      .map(
        (entry) =>
          `<div class='sub-block'><strong>${escapeHtml(entry.scope_type)} / ${escapeHtml(entry.scope_id)}</strong>${renderBulletList(entry.rules || [])}</div>`,
      )
      .join("");
  }
  if (taboos.length) {
    html += renderBulletSection("禁忌", taboos);
  }
  if (narrativeRules.length) {
    html += renderBulletSection("叙事规则", narrativeRules);
  }
  return html || "<p class='hint'>暂无 Meta 信息。</p>";
}

function renderCanonSummary(canon) {
  const characters = canon.characters || [];
  const plotThreads = canon.plot_threads || [];
  const worldRules = canon.world?.rules || [];
  const scopedRules = canon.world?.scoped || [];

  let html = "";
  if (characters.length) {
    html += "<div class='sub-block'><strong>角色</strong><ul class='plain-list canon-character-list'>";
    html += characters.map((character) => renderCanonCharacter(character)).join("");
    html += "</ul></div>";
  }
  if (worldRules.length) {
    html += renderBulletSection("世界规则", worldRules);
  }
  if (scopedRules.length) {
    html += scopedRules
      .map(
        (entry) =>
          `<div class='sub-block'><strong>${escapeHtml(entry.scope_type)} / ${escapeHtml(entry.scope_id)}</strong>${renderBulletList(entry.rules || [])}</div>`,
      )
      .join("");
  }
  if (plotThreads.length) {
    html += "<div class='sub-block'><strong>情节线</strong><ul class='plain-list'>";
    html += plotThreads
      .map((thread) => {
        const title = thread.title || thread.id || "未命名情节线";
        const status = thread.status ? ` · ${thread.status}` : "";
        const note = thread.note ? `<div class='canon-field-val'>${escapeHtml(thread.note)}</div>` : "";
        return `<li><strong>${escapeHtml(title)}</strong><span class='hint'>${escapeHtml(status)}</span>${note}</li>`;
      })
      .join("");
    html += "</ul></div>";
  }
  return html || "<p class='hint'>Hot Canon 为空。</p>";
}

function renderSynopsisSummary(synopsis) {
  const globalSummary = synopsis.global || "";
  const scenes = synopsis.scenes || [];
  let html = "";
  if (globalSummary) {
    html += `<div class='sub-block'><strong>全书梗概</strong><div class='canon-field-val'>${escapeHtml(globalSummary)}</div></div>`;
  }
  if (scenes.length) {
    html += scenes
      .map(
        (scene) => `
          <div class='sub-block'>
            <strong>${escapeHtml(scene.id || "scene")}</strong>
            <p class='hint'>${escapeHtml(scene.location || "")} · ${escapeHtml(scene.time || "")}</p>
            <div class='canon-field-val'>${escapeHtml(scene.summary || "")}</div>
            ${renderBulletList(scene.key_points || [])}
          </div>
        `,
      )
      .join("");
  }
  return html || "<p class='hint'>Synopsis 为空。</p>";
}

function renderManuscriptList(manuscripts, currentSceneId) {
  const scenes = manuscripts.scenes || [];
  if (!scenes.length) {
    return "<p class='hint'>尚无归档正文。</p>";
  }
  return scenes
    .map((scene) => {
      const active = scene.scene_id === currentSceneId ? " is-active" : "";
      const text = (scene.text || "").trim();
      const charCount = text.length;
      return `
        <div class='manuscript-item${active}'>
          <strong>${escapeHtml(scene.scene_id)}</strong>
          ${scene.scene_id === currentSceneId ? "<span class='badge'>当前</span>" : ""}
          <span class='badge'>${charCount} 字</span>
        </div>
      `;
    })
    .join("");
}

function deriveWritingStep(session) {
  const hasCandidate = Boolean((session.last_candidate || "").trim());
  const adoptCount = (session.adopt_stack || []).length;
  const messageCount = (session.messages || []).length;
  const adoptedProse = (session.adopted_prose || "").trim();

  if (hasCandidate) {
    return {
      label: "有待采纳的候选",
      hint: "请查看下方「候选与采纳」，确认后点击采纳按钮",
      tone: "accent",
    };
  }
  if (adoptCount === 0 && messageCount === 0) {
    return {
      label: "新场景 · 尚未开始",
      hint: "本场景还没有对话；发送第一条消息开始写作",
      tone: "muted",
    };
  }
  if (adoptCount === 0 && messageCount > 0) {
    return {
      label: "讨论中 · 尚未采纳",
      hint: "已有对话但尚未采纳正文；出现满意段落请记得采纳",
      tone: "info",
    };
  }
  return {
    label: `写作中 · 本场景已采纳 ${adoptCount} 段`,
    hint: adoptedProse
      ? "可继续发送消息生成新候选，或在合适时准备切换场景"
      : "可继续发送消息，或在合适时准备切换场景",
    tone: "success",
  };
}

function findSynopsisEntry(synopsis, sceneId) {
  return (synopsis.scenes || []).find((entry) => entry.id === sceneId) || null;
}

function renderWritingProgress(session, manuscripts, synopsis) {
  const sceneId = session.scene_id || "";
  const step = deriveWritingStep(session);
  const scenes = manuscripts.scenes || [];
  const archivedScenes = scenes.filter(
    (scene) => scene.scene_id !== sceneId && (scene.text || "").trim(),
  );
  const currentFile = scenes.find((scene) => scene.scene_id === sceneId);
  const persistedText = (currentFile?.text || "").trim();
  const sessionAdopted = (session.adopted_prose || "").trim();
  const candidate = (session.last_candidate || "").trim();
  const adoptCount = (session.adopt_stack || []).length;
  const messageCount = (session.messages || []).length;
  const turnsSinceAdopt = session.turns_since_last_adopt ?? 0;

  let html = `
    <div class='progress-header'>
      <span class='step-badge step-${escapeHtml(step.tone)}'>${escapeHtml(step.label)}</span>
      <p class='hint progress-hint'>${escapeHtml(step.hint)}</p>
    </div>
    <div class='kv-rows progress-stats'>
      <div class='kv-row'><span class='kv-key'>当前场景</span><span class='kv-val'>${escapeHtml(sceneId || "—")}</span></div>
      <div class='kv-row'><span class='kv-key'>对话轮数</span><span class='kv-val'>${messageCount}</span></div>
      <div class='kv-row'><span class='kv-key'>本场景采纳</span><span class='kv-val'>${adoptCount} 段</span></div>
      <div class='kv-row'><span class='kv-key'>距上次采纳</span><span class='kv-val'>${turnsSinceAdopt} 轮 send</span></div>
    </div>
  `;

  if (archivedScenes.length) {
    html += "<div class='progress-section'><h3>已完成场景</h3>";
    html += archivedScenes
      .map((scene) => renderArchivedSceneBlock(scene, synopsis))
      .join("");
    html += "</div>";
  }

  html += "<div class='progress-section'><h3>当前场景正文</h3>";
  const priorScene = archivedScenes.length
    ? archivedScenes[archivedScenes.length - 1]
    : null;
  html += renderCurrentSceneBlock({
    sceneId,
    sessionAdopted,
    persistedText,
    candidate,
    adoptCount,
    synopsis,
    priorSceneId: priorScene?.scene_id || "",
  });
  html += "</div>";

  return html;
}

function renderArchivedSceneBlock(scene, synopsis) {
  const entry = findSynopsisEntry(synopsis, scene.scene_id);
  const text = (scene.text || "").trim();
  const summaryLine = entry
    ? `${entry.location || ""}${entry.time ? ` · ${entry.time}` : ""}`
    : "";
  return `
    <details class='prose-archive' open>
      <summary>
        <strong>${escapeHtml(scene.scene_id)}</strong>
        ${summaryLine ? `<span class='hint'> — ${escapeHtml(summaryLine)}</span>` : ""}
        <span class='badge'>${text.length} 字</span>
      </summary>
      ${entry?.summary ? `<p class='archive-summary'>${escapeHtml(entry.summary)}</p>` : ""}
      <pre class='pre-block prose-read'>${escapeHtml(text)}</pre>
    </details>
  `;
}

function renderCurrentSceneBlock({
  sceneId,
  sessionAdopted,
  persistedText,
  candidate,
  adoptCount,
  synopsis,
  priorSceneId,
}) {
  const entry = findSynopsisEntry(synopsis, sceneId);
  const priorEntry = priorSceneId ? findSynopsisEntry(synopsis, priorSceneId) : null;
  let html = "";

  if (priorEntry?.summary && priorSceneId && priorSceneId !== sceneId) {
    html += `<p class='archive-summary'><strong>上一场景回顾（${escapeHtml(priorSceneId)}）：</strong>${escapeHtml(priorEntry.summary)}</p>`;
  } else if (entry?.summary) {
    html += `<p class='archive-summary'><strong>本场景摘要：</strong>${escapeHtml(entry.summary)}</p>`;
  }

  if (candidate) {
    html += `
      <div class='candidate-callout'>
        <strong>待采纳候选</strong>
        <pre class='pre-block prose-read'>${escapeHtml(candidate)}</pre>
      </div>
    `;
  }

  const displayAdopted = sessionAdopted || persistedText;
  if (displayAdopted) {
    html += `
      <div class='prose-current'>
        <strong>已采纳正文${adoptCount ? `（${adoptCount} 段）` : ""}</strong>
        <pre class='pre-block prose-read'>${escapeHtml(displayAdopted)}</pre>
      </div>
    `;
  } else if (!candidate) {
    html += "<p class='hint'>本场景尚无已采纳正文。发送消息后，满意的内容请在「候选与采纳」中确认。</p>";
  }

  if (persistedText && sessionAdopted && persistedText !== sessionAdopted) {
    html += `
      <details class='prose-archive'>
        <summary>已归档到 manuscript 文件的正文</summary>
        <pre class='pre-block prose-read'>${escapeHtml(persistedText)}</pre>
      </details>
    `;
  }

  return html || "<p class='hint'>暂无内容。</p>";
}

function renderConfigSummary(configPayload) {
  const flat = configPayload.flat || {};
  const keys = configPayload.available_keys || Object.keys(flat);
  if (!keys.length) {
    return "<p class='hint'>暂无配置项。</p>";
  }
  return renderKeyValueRows(keys.map((key) => [key, flat[key]]));
}

function populateConfigForm(configPayload) {
  const keySelect = document.getElementById("config-key");
  const valueInput = document.getElementById("config-value");
  if (!keySelect || !valueInput) {
    return;
  }
  const flat = configPayload.flat || {};
  const keys = configPayload.available_keys || Object.keys(flat);
  keySelect.innerHTML = keys
    .map((key) => `<option value='${escapeHtml(key)}'>${escapeHtml(key)}</option>`)
    .join("");
  const syncValue = () => {
    const selected = keySelect.value;
    valueInput.value = flat[selected] ?? 0;
  };
  keySelect.onchange = syncValue;
  syncValue();
}

function renderKeyValueRows(rows) {
  const items = rows.filter(
    ([, value]) => value !== undefined && value !== null && String(value).trim() !== "",
  );
  if (!items.length) {
    return "";
  }
  return `<div class='kv-rows'>${items
    .map(
      ([label, value]) => `
        <div class='kv-row'>
          <span class='kv-key'>${escapeHtml(label)}</span>
          <span class='kv-val'>${escapeHtml(String(value))}</span>
        </div>
      `,
    )
    .join("")}</div>`;
}

function renderBulletSection(title, items) {
  return `<div class='sub-block'><strong>${escapeHtml(title)}</strong>${renderBulletList(items)}</div>`;
}

function renderBulletList(items) {
  if (!items.length) {
    return "";
  }
  return `<ul class='plain-list'>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
}
