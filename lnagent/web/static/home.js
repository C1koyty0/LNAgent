document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("status-message");
  const form = document.getElementById("create-project-form");
  const submitButton = document.getElementById("create-project-button");
  const templateSelect = document.getElementById("project-template");

  if (!form) {
    return;
  }

  const fields = {
    title: document.getElementById("project-title"),
    style: document.getElementById("project-style"),
    pov: document.getElementById("project-pov"),
    tense: document.getElementById("project-tense"),
    genre: document.getElementById("project-genre"),
    tone: document.getElementById("project-tone"),
    target_audience: document.getElementById("project-target-audience"),
    taboos: document.getElementById("project-taboos"),
    narrative_rules: document.getElementById("project-narrative-rules"),
    world_rules: document.getElementById("project-world-rules"),
  };

  const templateState = { items: [] };

  function listTextToArray(text) {
    return String(text ?? "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function listValueToText(values) {
    if (!Array.isArray(values)) {
      return "";
    }
    return values
      .map((value) => String(value ?? "").trim())
      .filter(Boolean)
      .join("\n");
  }

  function setFieldValue(element, value) {
    if (!element) {
      return;
    }
    element.value = String(value ?? "");
  }

  function applyTemplate(template) {
    if (!template) {
      return;
    }
    setFieldValue(fields.title, template.title || "");
    setFieldValue(fields.style, template.style || "");
    setFieldValue(fields.pov, template.pov || "");
    setFieldValue(fields.tense, template.tense || "");
    setFieldValue(fields.genre, template.genre || "");
    setFieldValue(fields.tone, template.tone || "");
    setFieldValue(fields.target_audience, template.target_audience || "");
    setFieldValue(fields.taboos, listValueToText(template.taboos));
    setFieldValue(fields.narrative_rules, listValueToText(template.narrative_rules));
  }

  function renderTemplateOptions(templates) {
    if (!templateSelect) {
      return;
    }
    templateSelect.innerHTML = "";

    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "不使用模板";
    templateSelect.appendChild(emptyOption);

    for (const template of templates) {
      const option = document.createElement("option");
      option.value = template.name || "";
      option.textContent = template.name || template.style || "未命名模板";
      templateSelect.appendChild(option);
    }
  }

  async function loadTemplates() {
    if (!templateSelect) {
      return;
    }
    try {
      const payload = await apiRequest("GET", "/api/templates");
      templateState.items = Array.isArray(payload.templates) ? payload.templates : [];
      renderTemplateOptions(templateState.items);
    } catch (error) {
      setStatus(statusEl, `模板列表加载失败：${error.message}`, "error");
    }
  }

  if (templateSelect) {
    templateSelect.addEventListener("change", () => {
      const selected = templateState.items.find((item) => item.name === templateSelect.value);
      applyTemplate(selected || null);
    });
  }

  void loadTemplates();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const projectId = document.getElementById("project-id").value.trim();
    const title = fields.title.value.trim();
    const style = fields.style.value.trim();
    const pov = fields.pov.value.trim();
    const tense = fields.tense.value.trim();
    const genre = fields.genre.value.trim();
    const tone = fields.tone.value.trim();
    const targetAudience = fields.target_audience.value.trim();
    const taboos = listTextToArray(fields.taboos.value);
    const narrativeRules = listTextToArray(fields.narrative_rules.value);
    const worldRules = listTextToArray(fields.world_rules.value);

    if (!projectId || !title || !style) {
      setStatus(statusEl, "请填写 project_id、书名与文风。", "error");
      return;
    }

    setBusy([submitButton], true);
    setStatus(statusEl, "正在创建项目…", "info");
    try {
      await apiRequest("POST", "/api/projects", {
        project_id: projectId,
        meta: {
          title,
          style,
          pov,
          tense,
          genre,
          tone,
          target_audience: targetAudience,
          taboos,
          narrative_rules: narrativeRules,
          world_rules: worldRules,
        },
      });
      window.location.href = `/projects/${encodeURIComponent(projectId)}`;
    } catch (error) {
      setStatus(statusEl, error.message, "error");
      setBusy([submitButton], false);
    }
  });
});
