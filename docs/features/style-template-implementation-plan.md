# 文风与叙事模板实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 让作者在项目创建时选择预设模板、在项目运行中编辑 meta 的叙事字段，并将常用配置保存为可复用的模板文件。

**Architecture:** 模板本质就是 `meta.json`——不需要新的数据格式。模板存放在 `projects_dir/_templates/` 下，不污染项目索引（`project_exists()` 依赖 `meta.json` 不存在）。meta 编辑复用现有 `NovelMeta.from_dict/to_dict` 与 `store.save_meta()`，仅新增 API 端点和前端表单。Web 优先；CLI 暂不新增 `/meta set` 命令面。

**Tech Stack:** Python `>=3.10,<4.0`、现有 JSON 持久化 (`JsonMemoryStore`)、现有 Web WSGI 栈、`NovelMeta` 现有字段。

---

## 使用说明（进度追踪）

**状态标记规则**：

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成并通过本阶段验收
- 如有阻塞，在阶段末补充 `阻塞：...`

**追踪原则**：

- 每完成一个阶段，必须更新本文件状态与验收结果。
- 新 session 开始时，应先阅读本文件，再决定下一步。
- 若实现过程中设计发生变化，优先回写本计划，而不是只留在聊天记录里。

---

## 0. 范围与非目标

### 本计划要交付什么

- Web 端 meta 编辑：作者可在项目页直接修改 `style / pov / tense / genre / tone / target_audience / taboos / narrative_rules`
- 模板预设：作者在创建项目时可选择预定义的模板，一键填充 meta 字段
- 模板管理：作者可将当前项目的 meta 保存为命名模板、查看模板列表、删除模板
- Prompt 注入：编辑后的 meta 字段在下一次 writing / discussion 调用时立即生效（prompt 实时读取 `meta.json`）

### 本计划暂不实现什么

- CLI `/meta set` 或 `/config meta.*` 命令
- LLM 自动生成模板
- 模板在线市场或分享
- 模板版本 / diff / 历史
- 运行时覆盖（`--template` CLI 参数）
- 模板之间合并或继承
- 世界规则（`world.rules` / `world.scoped`）的编辑——当前阶段只编辑叙事字段

**阶段完成标准**：

- [ ] 范围与非目标已确认

---

## 背景调研（审计结果，2026-06-17）

### 现有 meta 字段全景

`NovelMeta` 已完整定义以下字段（`lnagent/memory/models.py:174-186`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | `str` | 书名（开书必填） |
| `style` | `str` | 文风（开书必填） |
| `pov` | `str` | 叙述人称 |
| `tense` | `str` | 叙事时态 |
| `taboos` | `list[str]` | 禁忌内容 |
| `target_audience` | `str` | 目标读者 |
| `narrative_rules` | `list[str]` | 叙事规则 |
| `genre` | `str` | 题材类型 |
| `tone` | `str` | 整体语气 |

### 现有读路径

- `JsonMemoryStore.load_meta()` / `save_meta()` — 标准读写
- `format_meta_for_prompt()` — 注入 Prompt（所有非空字段均注入）
- `renderMetaSummary()` — Web 侧栏只读展示
- `AppService.get_meta()` — Web API `GET /api/projects/<id>/meta`
- `POST /api/projects` — 创建时仅收 `title / style / world_rules`

### 现有缺口

| 缺口 | 说明 |
|------|------|
| **无 meta 写 API** | 没有 `PUT /api/projects/<id>/meta` |
| **创建表单仅 3 字段** | `home.js` 只收 `title / style / worldRules` |
| **无模板概念** | 仓库没有 `templates/` 目录，没有模板文件 |
| **CLI 无编辑命令** | `/meta` 只读，`/meta migrate` 仅迁移 |

### 模板存储策略

选择 `projects_dir/_templates/`（例如 `projects/_templates/`）：

- **不污染项目列表**：`list_projects()` 对每个子目录调用 `store.project_exists()`，它检查 `meta.json` 是否存在。模板目录不含 `meta.json`，自然被跳过。
- **随 `LNAGENT_PROJECTS_DIR` 迁移**：用户换 `projects_dir` 模板也跟着走，不用额外配置。
- **简单文件布局**：
  ```
  projects/_templates/
    ├── 轻小说-日常系.json
    ├── 轻小说-奇幻史诗.json
    └── 严肃文学.json
  ```
  每个文件就是一个 `NovelMeta.to_dict()` 的 JSON 子集（模板只需叙事字段，不必含 `world.rules`）。

---

## Phase S0：Web Meta 编辑

**目标**：让作者在项目页直接编辑 meta 叙事字段，编辑后立刻写盘。

**做什么**：

- 新增 `PUT /api/projects/<id>/meta` 端点
- 在 `AppService` 增加 `update_meta()` 方法
- 在项目页侧栏把现有的 `renderMetaSummary()` 只读展示升级为可编辑表单
- 保持 `title` 只读（书名不通过此入口修改）

**预期效果**：

- 作者创建项目后，可以在 Web 端补充叙事配置
- 编辑后的 meta 字段在下一次 LLM 调用时生效

**当前已确认的 S0 约束**：

- 编辑仅覆盖叙事字段：`style / pov / tense / genre / tone / target_audience / taboos / narrative_rules`
- `title` 和 `world`（`world.rules` / `world.scoped`）保持只读
- 提交时不做字段级 diff；直接全量替换叙事字段并调用 `store.save_meta()`
- API 接受 `NovelMeta` 的叙事字段子集；缺失字段保持原值
- `style` 不可为空；验证在 API 层完成
- 编辑后 `meta.json` 立即写盘；prompt builder 在下次调用时实时读取

**建议文件**：

- Modify: `lnagent/app_service.py`（新增 `update_meta()`）
- Modify: `lnagent/web/app.py`（新增 `PUT .../meta` 路由）
- Modify: `lnagent/web/static/project.js`（表单交互）
- Modify: `lnagent/web/static/render.js`（meta 编辑表单渲染）
- Modify: `lnagent/web/static/style.css`（表单样式）
- Test: `tests/test_web_app.py`（meta 编辑回归测试）

**实现清单**：

1. 在 `AppService` 新增 `update_meta(project_id, meta_payload)` 方法：load meta → 用 payload 中的叙事字段覆盖 → save meta → 返回 `to_dict()`。
2. 在 Web 路由中新增 `PUT /api/projects/<id>/meta`。
3. 在 `render.js` 新增 `renderMetaEditForm(meta)` 函数，把 `renderMetaSummary()` 的只读行改为可编辑 input/textarea。
4. 在 `project.js` 新增编辑表单的保存逻辑（监听提交、调用 API、刷新 meta 展示）。
5. 补 CSS 样式。
6. 补测试：覆盖 meta 编辑 API 读写闭环、style 空值校验、旧项目补充叙事字段后的往返。

**任务清单**：

- [x] S0.1 实现 `AppService.update_meta()` 与 `PUT /api/projects/<id>/meta`
- [x] S0.2 实现 meta 编辑表单前端
- [x] S0.3 补 meta 编辑回归测试

**验收**：

- [x] 通过 Web 编辑 meta 叙事字段后写盘成功
- [x] 下一次 LLM 调用 prompt 中可见更新后的 meta 值
- [x] `style` 不可为空，title / world 不可通过此接口修改
- [x] 不破坏现有 project 页 / discussion / writing 功能

**验收命令（已执行）**：

- `python -m unittest tests.test_web_app -v`（20 项通过，2026-06-17）
- `python -m py_compile lnagent/app_service.py lnagent/session.py lnagent/session_registry.py lnagent/web/app.py`
- `node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js`

**阶段结果**：

- S0 已完成：项目页现支持直接编辑 `style / pov / tense / genre / tone / target_audience / taboos / narrative_rules`
- 后端新增 `PUT /api/projects/<id>/meta`，并在写盘后同步刷新进程内 `SessionHandle` 缓存，保证下一次 writing / discussion prompt 立即读取最新 meta
- 前端新增 meta 编辑表单、只读字段摘要与保存交互；`title` / `world` 保持只读

---

## Phase S1：模板存储与 CRUD

**目标**：允许作者将当前项目的 meta 叙事字段保存为命名模板，后续创建项目时可选模板。

**做什么**：

- 定义模板文件格式（`NovelMeta.to_dict()` 子集）
- 实现模板目录管理与文件读写
- 新增模板 API：列出、保存、删除

**预期效果**：

- 作者可以在 Web 端把常用配置保存为模板
- 模板文件可手动复制 / 分享

**当前已确认的 S1 约束**：

- 模板目录：`projects_dir/_templates/`
- 模板文件名：`<name>.json`（中文名直接用中文文件名）
- 模板内容：`NovelMeta` 的叙事字段子集（`style / pov / tense / genre / tone / target_audience / taboos / narrative_rules`）；可选包含 `title` 作为建议书名
- 保存模板时覆盖同名文件
- 模板不做 schema 版本管理；读取时若含 `world_rules` 旧字段则容忍
- 模板 API 不需要鉴权（与其他 API 一致）

**API 设计**：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/templates` | 返回模板列表 `[{name, style, genre, ...}, ...]` |
| `POST` | `/api/templates` | 保存当前项目 meta 为模板（body: `{project_id, name}`） |
| `DELETE` | `/api/templates/<name>` | 删除模板 |

**建议文件**：

- Create: `lnagent/template_store.py`（模板文件读写）
- Modify: `lnagent/app_service.py`（模板 CRUD 方法）
- Modify: `lnagent/web/app.py`（模板路由）
- Test: `tests/test_template_store.py`

**实现清单**：

1. 创建 `lnagent/template_store.py`：`list_templates()` → `[{name, ...}]`、`save_template(name, meta_dict)`、`load_template(name)` → dict、`delete_template(name)`。
2. 在 `AppService` 新增 `list_templates()` / `save_template()` / `delete_template()` 方法。
3. 在 Web 路由中新增三个模板端点。
4. 确保 `list_projects()` 不被 `_templates/` 目录污染（现状已验证：`project_exists()` 检查 `meta.json`，模板目录不含该文件，自然跳过）。
5. 补模板 store 单元测试。

**任务清单**：

- [x] S1.1 实现模板 store 层
- [x] S1.2 实现模板 Web API
- [x] S1.3 补模板 store 单元测试

**验收**：

- [x] `GET /api/templates` 返回模板列表
- [x] `POST /api/templates` 保存模板并写盘为 JSON 文件
- [x] `DELETE /api/templates/<name>` 删除模板文件
- [x] 模板目录在 `_templates/` 下，不干扰项目索引
- [x] 同名保存覆盖旧文件

**验收命令（已执行）**：

- `python -m unittest tests.test_template_store tests.test_web_app.WebAppIntegrationTest.test_template_api_save_list_and_delete_round_trip tests.test_web_app.WebAppIntegrationTest.test_list_projects_and_ignore_invalid_entries tests.test_web_app.WebAppIntegrationTest.test_create_project_via_api -v`
- `python -m unittest tests.test_web_app -v`（21 项通过，2026-06-17）
- `python -m py_compile lnagent/app_service.py lnagent/template_store.py`
- `node --check lnagent/web/static/project.js`
- `node --check lnagent/web/static/render.js`

---

## Phase S2：创建项目时选择模板

**目标**：在 Web 首页创建项目的表单中增加模板选择器，选择模板后预填叙事字段。

**做什么**：

- 在首页加载时拉取模板列表
- 在创建表单中增加模板下拉选择器
- 选择模板后预填 `style / pov / tense / genre / tone / target_audience / taboos / narrative_rules`
- 不影响手动填写（选择模板后仍可修改）

**预期效果**：

- 作者创建项目时可以从常用模板起步
- 模板只做预填，所有字段仍可在创建前修改

**当前已确认的 S2 约束**：

- 模板选择是纯前端预填，不改变后端创建 API 的语义
- 若模板不含某字段，该字段保持空白
- 模板的 `title`（如有）可作为项目名建议预填，但作者可覆盖
- 模板不影响 `world_rules`——该字段仍需要作者手动填写

**建议文件**：

- Modify: `lnagent/web/app.py`（首页 HTML 注入模板列表）
- Modify: `lnagent/web/static/home.js`（模板选择与预填逻辑）
- Modify: `lnagent/web/templates/home.html`（如有）
- Modify: `lnagent/web/static/style.css`

**实现清单**：

1. 在首页 HTML 中注入模板列表（服务端渲染或通过 `GET /api/templates` 拉取）。
2. 在 `home.js` 中新增模板选择器交互：选中模板后填充表单字段。
3. 保持手动编辑不被模板覆盖（仅在用户主动选择模板时触发填充）。
4. 若模板包含 `title`，预填项目名输入框。
5. 补样式。

**任务清单**：

- [x] S2.1 首页注入模板列表
- [x] S2.2 实现模板选择与表单预填
- [x] S2.3 补前端回归测试

**验收**：

- [x] 首页创建表单中有模板下拉选项
- [x] 选择模板后 meta 字段预填
- [x] 预填后可手动修改
- [x] 不选择模板时行为与现在一致

**验收命令（建议）**：

- `python -m unittest tests.test_web_app.WebAppIntegrationTest.test_home_page_and_project_page_render tests.test_web_app.WebAppIntegrationTest.test_static_assets_are_served tests.test_web_app.WebAppIntegrationTest.test_create_project_via_api -v`
- `python -m unittest tests.test_web_app -v`
- `python -m py_compile lnagent/app_service.py lnagent/template_store.py lnagent/project.py`
- `node --check lnagent/web/static/home.js && node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js`

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-17 | 初稿：S0 meta 编辑、S1 模板存储、S2 创建时选择模板 |
