# 世界观文档录入与结构化实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 将 LNAgent 的世界观录入从“每行一条规则”切换为 document-first：作者粘贴完整世界观文档，经 LLM 提炼为结构化 worldbook，再按 scope 选择性注入 writing prompt。

**Architecture:** 在现有 `meta.world` + `PromptContextBuilder` 之上新增 worldbook 存储层。source 是作者真源，structured 是 LLM 提炼中间层，apply 时将 structured 投影到 `meta.world` 供现有 prompt 注入路径复用。Web 优先，CLI 做最小兼容降级。

**Tech Stack:** Python `>=3.10,<4.0`、现有 JSON store（`JsonMemoryStore`）、`langchain-openai`、现有 `NovelMeta` / `WorldCanon` / `ScopedWorldRules` / `PromptContextBuilder` 数据模型与注入链路。前端为原生 JS。

---

## 使用说明（进度追踪）

**状态标记规则**：

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成并通过本阶段验收
- 如有阻塞，在阶段末补充 `阻塞：...`

**追踪原则**：

- 每完成一个阶段，必须更新本文件状态与验收结果。
- 新 session 开始时，应先阅读本文件与 `worldbook-document-ingestion-design.md`，再决定下一步。
- 若实现过程中设计发生变化，优先回写设计文档与本计划，而不是只留在聊天记录里。

---

## 0. 范围与非目标

### 本计划要交付什么

- 独立的 worldbook 存储层：`projects/<id>/worldbook/source.md` + `structured.json`
- LLM 提炼路径：`source.md` → `structured.json`（extract → preview → apply）
- apply 覆盖 `meta.world`（rules + scoped），叙事字段不受影响
- Web 端 worldbook 面板：原始文档编辑、提炼按钮、预览区、应用按钮
- Web API：`GET /api/projects/{id}/worldbook`、`PUT .../worldbook/source`、`POST .../worldbook/extract`、`POST .../worldbook/apply`
- 创建项目时不再要求填写“世界规则（每行一条）”，改为可选的文档粘贴
- CLI 原有交互式世界规则采集改为最小兼容路径

### 本计划暂不实现什么

- glossary / open_questions 注入 prompt
- embedding / RAG-lite / 向量检索
- 多文档 source 管理（`sources/*.md`）
- diff / history 视图
- 多用户隔离 / 鉴权
- 复杂富文本编辑器
- worldbook 直接替换 meta 作为 prompt 主消费层（仍走 `meta.world` 投影）

**阶段完成标准**：

- [ ] 范围与非目标已确认

---

## Phase WK0：Worldbook 存储层

**目标**：为每个项目增加 `worldbook/source.md` 与 `worldbook/structured.json` 的读写能力，不改变现有项目布局的主体结构。

**做什么**：

- 在 `JsonMemoryStore` 中新增 worldbook 路径辅助方法与读写接口
- 在 `ensure_project_layout()` 中创建 `worldbook/` 根目录
- 定义 `WorldbookStructured` dataclass（对标设计文档 `structured.json` schema）
- 默认空 state 语义：`source.md` 不存在 = 空字符串；`structured.json` 不存在 = 空 `WorldbookStructured`

**预期效果**：

- 给定 `project_id`，可以定位 `worldbook/` 数据
- source 与 structured 可独立读写
- 现有 `session.json`、`canon.json`、`synopsis.json` 不受影响
- 现有测试不受影响（仅预创建空 `worldbook/` 目录，不自动生成 `source.md` / `structured.json`）

**当前已确认的 WK0 约束**：

- `source.md` 存储为纯文本 Markdown
- `structured.json` 使用设计文档 6.2 节的 schema（`overview`、`global_rules`、`scopes[]`、`glossary[]`、`open_questions[]`）
- 文件不存在时返回合理默认值（空 source、空 structured）
- store 层只做读写，不做 LLM 调用

**建议文件**：

- Modify: `lnagent/memory/models.py` — 新增 `WorldbookStructured` dataclass、`WorldbookScope` dataclass、`WorldbookGlossaryEntry` dataclass
- Modify: `lnagent/memory/store.py` — 新增 worldbook 路径与读写接口
- Modify: `lnagent/memory/protocols.py` — 如需要，可选扩展协议
- Create: `tests/test_worldbook_store.py` — worldbook store 单元测试

**任务清单**：

- [x] WK0.1 定义 `WorldbookStructured`、`WorldbookScope`、`WorldbookGlossaryEntry` 数据模型
- [x] WK0.2 在 `JsonMemoryStore` 新增 worldbook 路径与读写接口
- [x] WK0.3 在 `ensure_project_layout()` 中预创建 `worldbook/` 目录
- [x] WK0.4 编写 worldbook store 单元测试

**验收**：

- [x] `load_worldbook_source()` / `save_worldbook_source()` round trip
- [x] `load_worldbook_structured()` / `save_worldbook_structured()` round trip
- [x] 文件不存在时返回合理的默认值
- [x] `ensure_project_layout()` 创建 `worldbook/` 目录
- [x] 现有 `tests/test_memory_store.py` 全部通过

**验收结果（2026-06-19）**：

- `python -m unittest tests.test_worldbook_store -v` ✅（6 tests）
- `python -m unittest tests.test_memory_store -v` ✅（102 tests）

**验收命令（建议）**：

- `python -m unittest tests.test_worldbook_store -v`
- `python -m unittest tests.test_memory_store -v`

---

## Phase WK1：Worldbook 提炼器（Extractor）

**目标**：实现 `WorldbookExtractor` 类，将 `source.md` 经 LLM 提炼为 `WorldbookStructured`。

**做什么**：

- 新增 `lnagent/memory/worldbook_extractor.py`
- 参考 `MetaExtractor` 的实现模式（SystemMessage prompt + `_parse_json_object` 解析）
- 设计 extraction prompt：从 Markdown 世界观文档中提取 global_rules、scopes（faction/location）、glossary、open_questions
- extract 后产出 `WorldbookStructured` 实例，由调用方决定存到 `structured.json` 预览还是直接 apply

**预期效果**：

- 给定一份世界观 Markdown，可产出 schema 一致的结构化结果
- extraction prompt 明确禁止“发明原文没有的设定”
- 解析失败时有清晰的错误信息

**当前已确认的 WK1 约束**：

- extract 是纯函数式（接收 source text，返回 `WorldbookStructured`），不负责任何写盘
- LLM prompt 使用与 `MetaExtractor` 相同的系统消息 + 用户消息模式
- `parse_json_object` 复用 `_parse_json_object`（来自 `canon_extractor.py`）
- 第一版不做 async，与现有 `MetaExtractor` 风格一致
- 不需要在 extract 中处理 diff / previous structured — 那是 apply 层的职责

**建议文件**：

- Create: `lnagent/memory/worldbook_extractor.py`
- Modify: `lnagent/memory/models.py` — 如 schema 需要微调
- Create: `tests/test_worldbook_extractor.py`

**任务清单**：

- [x] WK1.1 定义 extraction prompt 与 `WorldbookStructured` schema 映射
- [x] WK1.2 实现 `WorldbookExtractor.extract(source_md: str) → WorldbookStructured`
- [x] WK1.3 编写 extractor 单元测试（mock LLM 响应）

**验收**：

- [x] 有效 Markdown → 合法 `WorldbookStructured`
- [x] 空 source → 空 structured（不调用模型）
- [x] LLM 返回非法 JSON → 明确解析错误
- [x] `glossary` / `open_questions` 可为空
- [x] `global_rules` / `scopes` 可正确填充

**验收结果（2026-06-19）**：

- `python -m unittest tests.test_worldbook_extractor -v` ✅（4 tests）
- `python -m unittest tests.test_worldbook_extractor tests.test_worldbook_store -v` ✅（10 tests）

**验收命令（建议）**：

- `python -m unittest tests.test_worldbook_extractor -v`

---

## Phase WK2：Apply 同步（structured → meta.world）

**目标**：实现 `worldbook apply` 逻辑，将 `structured.json` 投影到 `meta.world`。

**做什么**：

- 新增 `apply_worldbook_to_meta(store, project_id)` 或类似的函数
- 读取 `structured.json` → 构建新的 `WorldCanon` → 更新 `meta.world` → save meta
- 覆盖语义：每次 apply 完全替换 `meta.world`，不做 merge
- apply 只接触 `meta.world`，不动叙事字段（`style`、`pov` 等）

**预期效果**：

- apply 后 `meta.world.rules == structured.global_rules`
- apply 后 `meta.world.scoped` 反映 structured.scopes
- 叙事字段原封不动
- apply 后 writing prompt 立即可见新世界观（因为 `PromptContextBuilder` 实时读 `meta`）

**当前已确认的 WK2 约束**：

- apply 读取 `structured.json` 而非直接接收 `WorldbookStructured` 实例，确保“结构化结果已认可”的语义
- apply 后 `meta.json` 立即写盘
- 若 `structured.json` 不存在或为空，apply 应报错而非静默清空 `meta.world`
- apply 不影响 `session.json`、`canon.json`、`synopsis.json`、`config.json`
- 第一版不需要 undo apply
- 已知 follow-up：当前 `NovelMeta` / `world_rules` 仍带有旧数组入口兼容包袱；该问题暂不在 WK2 内修补，后续随 meta/world 结构化改造一并处理

**建议文件**：

- Create: `lnagent/memory/worldbook_apply.py` — `apply_worldbook_to_meta()`
- Modify: `lnagent/memory/store.py` — 如需要
- Create: `tests/test_worldbook_apply.py`

**任务清单**：

- [x] WK2.1 实现 `apply_worldbook_to_meta(store)` 函数
- [x] WK2.2 验证 apply 后叙事字段未被覆盖
- [x] WK2.3 编写 apply 单元测试

**验收**：

- [x] apply 后 `meta.world.rules` 与 `structured.global_rules` 一致
- [x] apply 后 `meta.world.scoped` 与 `structured.scopes` 一致
- [x] apply 不改变 `meta.style`、`meta.pov` 等叙事字段
- [x] `structured.json` 不存在时 apply 报错
- [x] apply 后 prompt builder 注入中可见新世界观

**已完成验证**：

- `python -m unittest tests.test_worldbook_apply -v` ✅（4 tests）
- `python -m unittest tests.test_worldbook_apply tests.test_meta_schema_v2 -v` ✅（10 tests）

**验收命令（建议）**：

- `python -m unittest tests.test_worldbook_apply -v`
- `python -m unittest tests.test_meta_schema_v2 -v`

---

## Phase WK3：Web API 端点

**目标**：为 worldbook 新增完整的 Web API 面：读取、保存 source、extract（预览）、apply（生效）。

**做什么**：

- 在 `AppService` 中新增 worldbook 相关方法
- 在 `lnagent/web/app.py` 中新增路由
- API 设计对齐设计文档 8.2 节

**预期效果**：

- 前端可以通过 API 读写 source、触发 extract 和 apply
- extract 返回 `WorldbookStructured` 作为预览，不影响 `meta.world`
- apply 调用 Phase WK2 的逻辑，持久化生效

**当前已确认的 WK3 约束**：

- `GET /api/projects/{id}/worldbook` 返回 `{source, structured, status}`（status: `no_worldbook` / `source_only` / `preview_ready` / `applied`）
- `PUT /api/projects/{id}/worldbook/source` body: `{source: "..."}`
- `POST /api/projects/{id}/worldbook/extract` 调 LLM → 写 `structured.json` 为 preview 态 → 返回 structured 内容
- `POST /api/projects/{id}/worldbook/apply` 调 `apply_worldbook_to_meta()` → 返回更新后的 meta
- extract 需要 API_KEY 与 LLM 配置可用（复用现有 `create_chat_model`）
- extract 是同步调用（与现有 writing/discussion send 风格一致）

**建议文件**：

- Modify: `lnagent/app_service.py` — 新增 `get_worldbook()`、`save_worldbook_source()`、`extract_worldbook()`、`apply_worldbook()`
- Modify: `lnagent/web/app.py` — 新增 worldbook 路由
- Modify: `tests/test_web_app.py` — 新增 worldbook API 集成测试

**任务清单**：

- [x] WK3.1 在 `AppService` 新增 worldbook 服务方法
- [x] WK3.2 在 Web 路由中新增 worldbook API 端点
- [x] WK3.3 编写 worldbook API 集成测试

**验收**：

- [x] `GET /api/projects/{id}/worldbook` 返回正确 status
- [x] `PUT .../worldbook/source` 写盘成功
- [x] `POST .../worldbook/extract` 返回 structured 预览
- [x] `POST .../worldbook/apply` 返回更新后的 meta，且 meta.world 已同步
- [x] 对无 source 的项目 extract 报错
- [x] 对无 structured 的项目 apply 报错

**已完成验证**：

- `python -m unittest tests.test_worldbook_web_api -v` ✅（6 tests）
- `python -m unittest tests.test_worldbook_web_api tests.test_worldbook_apply tests.test_web_app -v` ✅（31 tests）

**验收命令（建议）**：

- `python -m unittest tests.test_worldbook_web_api -v`
- `python -m unittest tests.test_web_app -v`

---

## Phase WK4：Web 前端面板

**目标**：在项目页新增 worldbook 面板，提供文档编辑、提炼、预览、apply 的完整 UI 流程。

**做什么**：

- 项目页新增 `worldbook-panel` 区域（与现有 `meta-form`、`brief-panel` 并列）
- raw source 编辑区（textarea）
- “提炼世界观”按钮 → 触发 extract API → 展示 preview
- preview 区域：展示 `global_rules`、`scopes`、`glossary`、`open_questions`（只读）
- “应用”按钮 → 触发 apply API → 更新 meta 展示
- 状态指示（未录入 / 已录入未提炼 / 已提炼待应用 / 已应用）

**当前已确认的 WK4 约束**：

- worldbook 面板放在项目页侧栏（与 meta 编辑、brief 面板同级）
- source textarea 支持粘贴完整文档
- extract 等待期间展示 loading 状态
- preview 用可折叠区域分类展示
- apply 后自动刷新 meta 只读展示（当前 meta 编辑表单的表头显示 `meta.world`）
- 第一版不做富文本编辑器

**建议文件**：

- Modify: `lnagent/web/app.py` — `_render_project()` 注入 worldbook-panel HTML
- Modify: `lnagent/web/static/project.js` — worldbook 交互逻辑
- Modify: `lnagent/web/static/render.js` — worldbook 渲染函数
- Modify: `lnagent/web/static/style.css` — worldbook 面板样式

**任务清单**：

- [x] WK4.1 新增 worldbook-panel HTML 骨架
- [x] WK4.2 实现 source 编辑与 save 逻辑
- [x] WK4.3 实现 extract → preview 渲染
- [x] WK4.4 实现 apply → meta 刷新
- [x] WK4.5 补 worldbook 前端样式

**验收**：

- [x] 项目页显示 worldbook 面板
- [x] 可粘贴文档并保存 source
- [x] 点击“提炼世界观”后展示 preview
- [x] 点击“应用”后 meta.world 展示更新
- [x] 状态指示在各步骤间正确切换
- [x] 不破坏现有 meta 编辑、discussion / writing 面板功能

**验收命令（建议）**：

- `python -m unittest tests.test_web_app.WebAppIntegrationTest.test_home_page_and_project_page_render tests.test_web_app.WebAppIntegrationTest.test_static_assets_are_served -v`
- `python -m unittest tests.test_web_app tests.test_worldbook_web_api tests.test_worldbook_apply -v`
- `python -m py_compile lnagent/web/app.py`
- `node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js`

**本阶段实际验证**：

- [x] `python -m unittest tests.test_web_app.WebAppIntegrationTest.test_home_page_and_project_page_render tests.test_web_app.WebAppIntegrationTest.test_static_assets_are_served -v`
- [x] `python -m unittest tests.test_web_app tests.test_worldbook_web_api tests.test_worldbook_apply -v`
- [x] `python -m py_compile lnagent/web/app.py`
- [x] `node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js`

---

## Phase WK5：移除旧“每行一条世界规则”入口

**目标**：将世界观录入切换为 document-first，移除旧 entry。

**做什么**：

- Web 创建表单：删除 `project-world-rules` textarea，替换为“世界观文档（可选，可在项目页补充）”的 textarea（字数更大的文档编辑区）
- 后端：放宽 `_validate_world_content()` 的必填要求——允许空 world 或 worldbook-only 项目创建
- CLI：`collect_novel_meta()` 不再强制要求“至少一条世界规则”；交互改为可选
- 项目页 meta 编辑：current 已将 title/world 标为只读，保持不变

**当前已确认的 WK5 约束**：

- 创建项目时 `world_rules` 不再必填
- Web 创建表单中原来的 `project-world-rules` textarea 改为可选的 `project-worldbook-source` textarea（不强制 LLM extract，仅保存 source.md）
- CLI `collect_novel_meta()` 的世界规则采集改为可选（输入空行 = 跳过，不再报“至少需要一条世界规则”）
- 已有项目的 `meta.world` 保持不变；不自动回填 worldbook

**建议文件**：

- Modify: `lnagent/project.py` — `collect_novel_meta()` 和 `_validate_world_content()` 放宽约束
- Modify: `lnagent/web/app.py` — `_render_home()` 表单替换，并让 create API 接收 `worldbook_source`
- Modify: `lnagent/web/static/home.js` — 移除 `world_rules` 字段、新增 optional source 字段
- Modify: `lnagent/app_service.py` — 创建项目时保存可选 `worldbook/source.md`
- Modify: `lnagent/memory/models.py` — 修正 `NovelMeta.__post_init__()` 对空 world 路径的兼容判断
- Modify: `tests/test_web_app.py` — 更新首页/静态资源/创建项目测试
- Modify: `tests/test_memory_store.py` — 更新相关测试

**任务清单**：

- [x] WK5.1 放宽后端 world 必填约束
- [x] WK5.2 替换 Web 创建表单中的世界规则输入
- [x] WK5.3 改造 CLI 交互式世界规则采集
- [x] WK5.4 更新相关测试

**验收**：

- [x] 不填世界观也能创建项目
- [x] Web 创建表单不再要求“世界规则（每行一条）”
- [x] 旧项目（有 `world_rules` 的 `meta.json`）仍能正常加载与写作
- [x] 新项目可在项目页粘贴世界观文档并走 worldbook 流程

**验收命令（建议）**：

- `python -m unittest tests.test_web_app -v`
- `python -m unittest tests.test_memory_store -v`
- `python -m unittest tests.test_web_bootstrap -v`
- `python -m py_compile lnagent/project.py lnagent/app_service.py lnagent/web/app.py lnagent/memory/models.py`
- `node --check lnagent/web/static/home.js && node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js`

**本阶段实际验证**：

- [x] `python -m unittest tests.test_web_app.WebAppIntegrationTest.test_home_page_and_project_page_render tests.test_web_app.WebAppIntegrationTest.test_static_assets_are_served tests.test_web_app.WebAppIntegrationTest.test_create_project_via_api tests.test_memory_store.ProjectInitTest.test_load_meta_from_file_requires_required_fields tests.test_memory_store.ProjectInitTest.test_collect_novel_meta_allows_skipping_world_rules -v`
- [x] `python -m unittest tests.test_web_app tests.test_memory_store tests.test_web_bootstrap -v && python -m py_compile lnagent/project.py lnagent/app_service.py lnagent/web/app.py lnagent/memory/models.py && node --check lnagent/web/static/home.js && node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js`

---

## Phase WK6：测试覆盖与迁移收口

**目标**：保证所有现有测试通过，worldbook 新路径有充分覆盖，并做最终文档同步。

**做什么**：

- 跑全量测试，修复任何因放宽 world 约束导致的测试失败
- 如果现有 fixture 的 `meta.json` 不包含 `world_rules`，补充或调整测试
- 确保 `test_create_project_via_api` 在新的非必填约束下仍通过
- 确保模板 store 测试仍然正确隔离 world 字段
- 更新 `docs/features/README.md` 状态
- 更新 `docs/features/worldbook-document-ingestion-design.md` 修订记录

**当前已确认的 WK6 约束**：

- 如果某测试依赖“创建时必须含 world_rules”的旧行为，需要更新测试 fixture
- 允许 fixture 创建不含 world 的 meta，但已有世界的测试应继续验证正面路径

**建议文件**：

- Modify: `tests/test_web_app.py`
- Modify: `tests/test_memory_store.py`
- Modify: `tests/test_web_bootstrap.py`
- Modify: `docs/features/README.md`
- Modify: `docs/features/worldbook-document-ingestion-design.md`

**任务清单**：

- [x] WK6.1 修复因放宽 world 约束导致的测试失败
- [x] WK6.2 补全 worldbook 各路径的集成测试
- [x] WK6.3 更新 feature docs 索引与设计文档状态

**验收**：

- [x] 全量 `python -m unittest` 通过
- [x] `py_compile` 全量通过
- [x] `node --check` 全量通过
- [x] README.md 中 worldbook 条目状态更新

**验收命令（建议）**：

- `python -m unittest -v`
- `python -m py_compile lnagent/memory/worldbook_extractor.py lnagent/memory/worldbook_apply.py lnagent/app_service.py lnagent/project.py lnagent/web/app.py lnagent/bootstrap.py lnagent/template_store.py lnagent/memory/models.py`
- `node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js && node --check lnagent/web/static/home.js && node --check lnagent/web/static/common.js`

**本阶段实际验证**：

- [x] `python -m unittest tests.test_web_app.WebAppIntegrationTest.test_create_project_without_worldbook_source_keeps_worldbook_empty tests.test_web_bootstrap.BootstrapRuntimeTest.test_bootstrap_project_runtime_accepts_meta_without_world_rules tests.test_template_store.TemplateStoreTest.test_template_store_never_writes_worldbook_source -v`
- [x] `python -m unittest -v && python -m py_compile lnagent/memory/worldbook_extractor.py lnagent/memory/worldbook_apply.py lnagent/app_service.py lnagent/project.py lnagent/web/app.py lnagent/bootstrap.py lnagent/template_store.py lnagent/memory/models.py && node --check lnagent/web/static/project.js && node --check lnagent/web/static/render.js && node --check lnagent/web/static/home.js && node --check lnagent/web/static/common.js`

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-19 | 初稿：WK0 存储层、WK1 提炼器、WK2 apply、WK3 API、WK4 前端、WK5 移除旧入口、WK6 测试收口 |
