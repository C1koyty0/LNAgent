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
    html += "<div class='sub-block'><strong>角色</strong><ul class='plain-list'>";
    html += characters
      .map((character) => {
        const name = character.name || "未命名";
        const extras = Object.entries(character)
          .filter(([key]) => key !== "name")
          .map(([key, value]) => `${key}: ${value}`)
          .join(" · ");
        return `<li><strong>${escapeHtml(name)}</strong>${extras ? ` — ${escapeHtml(extras)}` : ""}</li>`;
      })
      .join("");
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
      .map((thread) => `<li>${escapeHtml(JSON.stringify(thread))}</li>`)
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
    html += `<div class='sub-block'><strong>全书梗概</strong><p>${escapeHtml(globalSummary)}</p></div>`;
  }
  if (scenes.length) {
    html += scenes
      .map(
        (scene) => `
          <div class='sub-block'>
            <strong>${escapeHtml(scene.id || "scene")}</strong>
            <p class='hint'>${escapeHtml(scene.location || "")} · ${escapeHtml(scene.time || "")}</p>
            <p>${escapeHtml(scene.summary || "")}</p>
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
      const preview = (scene.text || "").trim().slice(0, 120);
      return `
        <div class='manuscript-item${active}'>
          <strong>${escapeHtml(scene.scene_id)}</strong>
          ${scene.scene_id === currentSceneId ? "<span class='badge'>当前</span>" : ""}
          <p class='hint'>${escapeHtml(preview || "（空）")}${preview.length >= 120 ? "…" : ""}</p>
        </div>
      `;
    })
    .join("");
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
  return `<dl class='kv-list'>${rows
    .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "")
    .map(
      ([label, value]) =>
        `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`,
    )
    .join("")}</dl>`;
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
