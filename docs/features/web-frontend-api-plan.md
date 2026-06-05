# Web 前端与 API 改造计划

> **目标**：在保留现有 CLI 工作流的前提下，为 LNAgent 增加一个 Web 启动方式与浏览器前端，改善作者交互体验，并为后续 RAG-lite 与更丰富的项目浏览能力预留接口。  
> **范围约束（当前轮已确认）**：
> - **保留 CLI 入口**，不替换 `main.py`
> - **新增 Web 入口**，且**启动时不预绑定 `project_id`**
> - 前端/API 可通过 **`project_id` 作为路径参数** 访问项目资源
> - **暂不考虑鉴权**
> - 前端仍遵守现有产品原则：**正文采纳（adopt）与场景切换（scene switch）必须由作者显式触发**

---

## 1. 为什么要单独做 Web 入口

当前 `main.py` 直接承担了：

1. 环境配置加载
2. 项目打开/创建
3. `NovelSession` 初始化
4. 交互式命令循环
5. 终端输入输出

这对 CLI 是合理的，但对 Web 前端不够友好：

- Web 启动时不应要求先传 `--project`
- Web 需要在首页浏览、选择、创建项目
- Web 不能复用 `input()` / `print()` 风格的交互函数
- Web 更适合结构化 API，而不是命令字符串驱动

因此推荐采用：

- 保留 `main.py` 作为 **CLI 入口**
- 新增单独的 **Web 入口**
- 抽出共享初始化与服务层，供 CLI 与 Web 共用

---

## 2. 当前代码的优点与可复用部分

现有代码并不需要推倒重来，核心领域层已经具备较好的复用基础：

- `lnagent/session.py`：主会话编排与大部分核心动作
- `lnagent/memory/store.py`：项目状态读写
- `lnagent/memory/prompt.py`：Prompt 上下文组装
- `lnagent/memory/canon_extractor.py`：Hot Canon 抽取/修正/迁移
- `lnagent/memory/cold_archive.py`：Cold Archive 提案与 global rollup
- `lnagent/project.py`：项目创建/打开校验

尤其是 `NovelSession` 已经暴露了多项适合 Web 复用的核心动作：

- `send()`
- `prepare_adopt()` / `commit_adopt()`
- `prepare_fix()` / `commit_fix()`
- `pending_reconcile_items()` / `apply_reconcile()`
- `prepare_cold_proposal()` / `finish_scene_switch()`

因此 Web 改造的重点不在 memory/schema 主逻辑，而在：

1. **新增项目索引能力**
2. **抽出共享初始化能力**
3. **增加应用服务层与 API 层**
4. **解决 Web 进程中的会话状态驻留问题**

---

## 3. Web 形态下新增的核心需求

### 3.1 启动时不绑定 project

CLI 目前通过 `Settings.with_project()` 在启动时绑定项目。  
Web 模式下需要先启动服务，再在首页让用户选择项目。

因此 Web 启动只需要：

- `api_key`
- `model`
- `base_url`
- `projects_dir`

而不需要：

- `project_id`

### 3.2 项目列表/项目摘要能力

当前仓库已支持“给定 `project_id` 后打开项目”，但尚不支持“浏览所有项目”。

Web 首页需要：

- 列出 `projects_dir` 下的项目
- 读取每个项目的基础信息（书名、文风、当前 scene、是否已有正文等）
- 支持创建项目

### 3.3 结构化 API，而不是 CLI 命令字符串

Web 前端不应通过提交 `/a`、`/sc`、`/f` 等命令字符串来复用 CLI 解析器。  
更合理的方式是暴露结构化动作 API，例如：

- 发送消息
- 准备 adopt
- 确认 adopt
- 准备 fix
- 确认 fix
- 准备 scene switch
- 提交 reconcile
- 提交 scene switch

### 3.4 进程内会话状态管理

当前 `session.json` 采用 **checkpoint_only** 策略：

- `send()` 不写盘
- adopt / fix / reconcile / `/sc` / 退出时写盘
- `last_candidate` 也只在内存中保留

因此 Web 不能按“每个请求现开现关一个 `NovelSession`”的方式工作，否则会丢失：

- `last_candidate`
- `last_budget_report`
- `turns_since_last_adopt`
- 尚未 checkpoint 的讨论轮次状态

Web 端需要引入**进程内 Session Registry**，按 `project_id` 维护活跃会话对象。

---

## 4. 推荐的模块改造方案

### 4.1 保留现有 CLI 入口

继续保留：

- `main.py` — CLI 入口

CLI 仍通过：

```bash
python main.py --project <project_id>
```

运行。

### 4.2 新增 Web 入口

建议新增：

- `web_main.py` — Web 启动入口

或等价模块入口：

- `python -m lnagent.web`

Web 启动**不要求** `--project`；项目在页面中选择。

### 4.3 抽共享初始化层

建议新增：

- `lnagent/bootstrap.py`

职责：

- 从环境加载 `Settings`
- 创建模型对象
- 打开指定项目并创建 `JsonMemoryStore`
- 初始化 `NovelSession`

这样可以让 CLI 与 Web 共用初始化逻辑，而不是在 `main.py` 中复制。

### 4.4 新增项目索引层

建议新增：

- `lnagent/project_index.py`

职责：

- 扫描 `projects_dir`
- 判断目录是否为有效项目
- 读取项目摘要
- 返回项目列表

建议提供：

- `list_projects(projects_dir: Path) -> list[ProjectSummary]`
- `load_project_summary(project_dir: Path) -> ProjectSummary`

### 4.5 新增应用服务层

建议新增：

- `lnagent/app_service.py`

职责：

- 组织项目级动作与会话级动作
- 管理 Session Registry
- 为 Web API 提供稳定接口
- 避免路由层直接操作 `NovelSession`

建议封装的方法：

- `list_projects()`
- `create_project_from_meta_dict()`
- `create_project_from_meta_file()`
- `open_project(project_id)`
- `get_project_state(project_id)`
- `send_message(project_id, text)`
- `prepare_adopt(project_id, text)`
- `commit_adopt(project_id, text, accepted_canon)`
- `prepare_fix(project_id, intent)`
- `commit_fix(project_id, intent, accepted_canon)`
- `prepare_scene_switch(project_id)`
- `apply_scene_reconcile(project_id, ...)`
- `commit_scene_switch(project_id, ...)`

### 4.6 新增 Web API / UI 层

建议新增目录：

```text
lnagent/web/
├── __init__.py
├── app.py          # Web 应用与路由
├── schemas.py      # 请求/响应 DTO
├── templates/      # 若采用服务端模板
└── static/         # JS/CSS 资源
```

如采用前后端轻量一体化模式，可先服务端渲染 + 少量 JS；如采用分离式，也可先保留 API-only 后续再接前端。

---

## 5. 推荐的 API 形态（第一版）

> 当前轮已确认：`project_id` 可以作为路径参数的一部分；暂不考虑鉴权。

建议 API 以项目为核心资源，路径形态如下：

### 5.1 项目索引与打开

- `GET /api/projects`
  - 返回项目列表与摘要
- `POST /api/projects`
  - 创建新项目（表单或 JSON）
- `GET /api/projects/{project_id}`
  - 返回项目概览
- `POST /api/projects/{project_id}/open`
  - 打开项目并确保该项目在 Session Registry 中就绪

### 5.2 会话动作

- `POST /api/projects/{project_id}/send`
- `POST /api/projects/{project_id}/adopt/prepare`
- `POST /api/projects/{project_id}/adopt/commit`
- `POST /api/projects/{project_id}/fix/prepare`
- `POST /api/projects/{project_id}/fix/commit`
- `POST /api/projects/{project_id}/scene/prepare`
- `POST /api/projects/{project_id}/scene/reconcile`
- `POST /api/projects/{project_id}/scene/commit`

### 5.3 查询接口

- `GET /api/projects/{project_id}/meta`
- `GET /api/projects/{project_id}/canon`
- `GET /api/projects/{project_id}/synopsis`
- `GET /api/projects/{project_id}/manuscript`
- `GET /api/projects/{project_id}/config`
- `GET /api/projects/{project_id}/session`

这些查询接口非常适合前端侧栏、项目页初始加载与调试观察。

---

## 6. 项目创建方式的补充

当前 `lnagent/project.py` 已支持：

- 交互式 `input()` 创建
- 从 `meta.json` 文件创建

Web 第一版还需要新增一种：

- **直接从前端提交的 meta JSON/dict 创建项目**

建议新增函数：

- `create_project_from_meta_dict(store: JsonMemoryStore, data: dict) -> NovelMeta`

这样 Web 可以支持：

- 表单方式创建项目
- 粘贴 JSON 创建项目
- 上传 JSON 文件创建项目

---

## 7. 状态读取与 DTO 设计

前端不适合消费 `print()` 文本，更适合结构化对象。

建议新增 DTO / schema 层，定义例如：

- `ProjectSummary`
- `ProjectStateResponse`
- `ConversationState`
- `AdoptProposalView`
- `FixProposalView`
- `SceneSwitchPreview`
- `ApiErrorResponse`

这层可以放在：

- `lnagent/web/schemas.py`

用于：

- 路由输出统一化
- 减少 dict 散落在各处
- 为未来前端/RAG-lite 查询结果扩展字段留位置

---

## 8. 关于当前 JSON 文件存储与 SQLite 的讨论入口

### 8.1 当前 JSON 方案的优点

现有 `JsonMemoryStore` 的优点：

- 简单、透明、便于调试
- 与现有测试和 schema 演进方式契合
- 手工检查项目状态非常方便
- 不需要数据库迁移体系就能快速推进功能

对于当前 LNAgent 的 CLI 与单机单作者模型，这套方案是合理的。

### 8.2 当前 JSON 方案在 Web 下的压力点

但如果进入 Web 模式，问题会更明显：

- 首页列项目时需要反复读取多个项目文件
- 项目页初始加载可能要读 `meta/canon/synopsis/session/manuscript`
- 若未来加入查询接口、检索接口、排序/筛选，文件式存储会越来越笨重
- 后续 RAG-lite / 项目搜索 / 最近活动列表等能力，使用 JSON 文件遍历会越来越别扭

### 8.3 当前建议

**不建议在 Web 第一版就立刻切 SQLite 为主存储。**

原因：

- Web 改造本身已经包含入口层、服务层、会话层的新增复杂度
- 若同时切换持久化底座，会把风险叠加
- 当前最急的是把“前端 + API 交互闭环”跑通，不是先做存储迁移

更稳妥的路径是：

1. 第一版 Web 仍基于 `JsonMemoryStore`
2. 同时抽象出更明确的 store/service 边界
3. 等查询场景变多后，再评估增加 `SqliteMemoryStore` 或混合模式（JSON 为主、SQLite 为索引/查询镜像）

### 8.4 SQLite 更适合承接什么

如果后续上 SQLite，更适合优先承接：

- 项目索引（项目列表、标题、最后活动时间）
- 会话消息索引
- manuscript chunk 索引（为 RAG-lite 做准备）
- synopsis/canon 的查询镜像

而不是第一步就把所有 JSON 彻底替换掉。

---

## 9. 推荐实施顺序（Web 第一版）

### Phase W0：架构准备

- 抽 `bootstrap.py`
- 新增 `project_index.py`
- 新增 `app_service.py`
- 引入 Session Registry

### Phase W1：只做 API，不做复杂 UI

- 新增 Web 入口
- 实现项目列表 / 打开 / 查询接口
- 实现 `send` / `adopt` / `fix` / `scene` 基本 API
- 用最简页面或 API 调试工具验证闭环

### Phase W2：前端 MVP

- 首页项目列表
- 项目详情页
- 对话区
- candidate/adopt 区
- Hot Canon / Meta / Synopsis 侧栏
- scene switch 面板

### Phase W3：增强查询与 RAG-lite 预留

- 增加 manuscript/synopsis 查询能力
- 为“相关历史片段”面板预留接口
- 视需要引入 SQLite 索引层

---

## 10. 当前轮达成的具体共识

- 保留 CLI 入口，不替换 `main.py`
- 增加新的 Web 启动方式
- Web 启动时不限定 `project_id`
- `project_id` 可作为 API 路径参数的一部分
- 先不考虑鉴权
- 第一版更适合先做 API + 前端 MVP
- SQLite 值得考虑，但不建议与 Web 第一版同时切主存储

---

## 11. 下一步建议

最合适的下一步不是立刻改数据库，而是：

1. 先把 **Web/API 第一版的服务边界** 固定下来
2. 基于现有 JSON store 跑通 Web 闭环
3. 再判断哪些查询真的成为瓶颈，届时再上 SQLite

如果继续实现，建议先做：

- `bootstrap.py`
- `project_index.py`
- `app_service.py`
- `web_main.py`
- 一组最小 REST API

而不是先做持久化迁移。

---

## 12. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-04 | 初稿：整理 Web 前端与 API 改造方案；确认 Web 启动不预绑定项目、`project_id` 路径参数、暂不做鉴权；补充 JSON vs SQLite 的阶段性判断 |
