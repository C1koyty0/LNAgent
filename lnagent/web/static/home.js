document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("status-message");
  const form = document.getElementById("create-project-form");
  const submitButton = document.getElementById("create-project-button");

  if (!form) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const projectId = document.getElementById("project-id").value.trim();
    const title = document.getElementById("project-title").value.trim();
    const style = document.getElementById("project-style").value.trim();
    const worldRulesText = document.getElementById("project-world-rules").value;
    const worldRules = worldRulesText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

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
