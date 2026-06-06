# Web/API 第一版实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 为 LNAgent 增加第一版 Web/API 能力：保留现有 CLI 入口，新增不预绑定 `project_id` 的 Web 启动方式，支持项目浏览、项目打开、基础会话交互与结构化查询接口。

**Architecture:** 采用**增量式改造**而非替换式重写：保留 `main.py` CLI，新增独立 Web 入口；抽出共享 bootstrap；在 HTTP 路由与 `NovelSession` 之间增加应用服务层；引入按 `project_id` 管理的进程内 Session Registry，保持当前 `checkpoint_only` 与 `last_candidate` 等内存语义不变。第一版仍以 `JsonMemoryStore` 为真源，SQLite 暂缓到后续查询优化阶段。

**Tech Stack:** Python `>=3.10,<4.0`、现有 `LangChain` / `langchain-openai`、现有 JSON store；Web 框架待实现阶段最终拍板（建议轻量 ASGI/WSGI 框架），本计划先按“后端 API + 轻量页面壳”拆解。

---

## 使用说明（进度追踪）

**状态标记规则**：

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成并通过本阶段验收
- 如有阻塞，在阶段末补充 `阻塞：...`

**追踪原则**：

- 每完成一个阶段，必须在本文件中更新对应状态与验收结果。
- 若重新开启 session，应先阅读本文件，再决定下一步，不依赖对话上下文记忆。
- 如果设计发生变化，直接修改本文件相应章节与修订记录，保持其为 Web/API 工作的单一事实来源。

---

## 0. 范围与非目标（本轮已确认）

### 本计划要交付什么

- 保留现有 CLI 入口：`python main.py --project <project_id>`
- 新增 Web 启动方式，启动时**不要求**传 `project_id`
- 首页可列出项目、打开项目、创建项目
- Web/API 使用 `project_id` 作为路径参数的一部分
- 提供基础查询接口与基础会话动作接口
- 保持现有产品规则：adopt 与 scene switch 必须作者显式触发
- 第一版使用 `JsonMemoryStore` 作为真源

### 本计划暂不实现什么

- 鉴权 / 用户体系
- SQLite 替换 JSON 作为主存储
- RAG-lite 检索能力
- 多用户并发隔离设计
- 前端高级视觉设计、复杂编辑器增强
- WebSocket / 流式 token 推送（第一版可先同步请求-响应）

**阶段完成标准**：

- [ ] 所有后续阶段范围与非目标与当前共识一致

---

## Phase W0：共享启动与项目索引准备

**目标**：把 CLI 独占的初始化逻辑拆出来，并补足“Web 启动后自由选项目”所必需的项目索引能力。

**做什么**：

- 抽出共享 bootstrap 模块，复用环境加载、模型创建、store/session 初始化流程
- 新增项目索引模块，支持扫描 `projects_dir`、识别有效项目、读取项目摘要
- 保持 CLI 原有启动路径可用，不因抽取 bootstrap 改变行为

**预期效果**：

- Web 启动时可以不绑定项目，只拿到 `projects_dir`
- 系统能够列出所有现有项目及其摘要
- CLI 与未来 Web 不重复维护初始化代码

**建议文件**：

- Create: `lnagent/bootstrap.py`
- Create: `lnagent/project_index.py`
- Modify: `main.py`
- Test: `tests/test_memory_store.py` 或新增 `tests/test_web_bootstrap.py`

**任务清单**：

- [x] W0.1 抽 `Settings` + model + store + session 的共享 bootstrap 函数
- [x] W0.2 保持 `main.py` 改造后 CLI 行为不变
- [x] W0.3 新增项目扫描与项目摘要读取逻辑
- [x] W0.4 为项目索引增加单元测试

**验收**：

- [x] `python main.py --project demo` 仍可像现在一样启动 CLI
- [x] 给定 `projects_dir`，代码能返回项目列表与基础摘要
- [x] 非法项目目录不会导致索引接口整体失败

**验收命令（建议）**：

- `python -m unittest tests.test_memory_store`
- 若拆新测试：`python -m unittest tests.test_web_bootstrap`

---

## Phase W1：应用服务层与 Session Registry

**目标**：在 HTTP 路由和 `NovelSession` 之间增加稳定服务层，并解决 Web 每请求重建 session 会丢失内存状态的问题。

**做什么**：

- 新增 `app_service`，封装项目级与会话级动作
- 新增 Session Registry，按 `project_id` 维护活跃 `NovelSession`
- 服务层提供统一入口给 Web：打开项目、读取状态、发送消息、准备 adopt/fix/scene 等

**预期效果**：

- Web 不直接操作 CLI 函数，也不直接拼接命令文本
- `last_candidate`、`turns_since_last_adopt`、`last_budget_report` 等状态在 Web 下可连续使用
- 后续 API 设计可以围绕服务层稳定展开

**建议文件**：

- Create: `lnagent/app_service.py`
- Create: `lnagent/session_registry.py`
- Modify: `lnagent/session.py`（仅在必要时增加状态读取辅助方法）
- Test: `tests/test_web_app_service.py`

**任务清单**：

- [x] W1.1 设计 `AppService` 接口
- [x] W1.2 实现基于 `project_id` 的 Session Registry
- [x] W1.3 封装项目打开与状态读取服务
- [x] W1.4 封装 `send/adopt/fix/scene` 服务入口
- [x] W1.5 为 registry 与服务层写单元测试

**验收**：

- [x] 同一 `project_id` 的连续 API 调用可复用同一内存 session
- [x] `send()` 之后未 checkpoint 时，后续 `adopt` 仍能读取到 `last_candidate`
- [x] 不同 `project_id` 之间状态不串扰

**验收命令（建议）**：

- `python -m unittest tests.test_web_app_service`

---

## Phase W2：项目级查询 API（只读）

**目标**：先把 Web 前端最需要的只读查询接口搭起来，形成首页与项目页的基本数据面。

**做什么**：

- 新增 Web 应用骨架与 API 路由
- 提供项目列表、项目概览、meta/canon/synopsis/config/session/manuscript 等查询接口
- 统一错误响应格式

**预期效果**：

- 即使前端页面还很简陋，也能通过 API 获取项目数据
- 前端首页与项目详情页的数据来源明确
- 后续动作型 API 可在此基础上扩展

**建议文件**：

- Create: `lnagent/web/app.py`
- Create: `lnagent/web/schemas.py`
- Create: `web_main.py`
- Test: `tests/test_web_api.py`

**任务清单**：

- [x] W2.1 搭 Web 入口与应用骨架
- [x] W2.2 实现 `GET /api/projects`
- [x] W2.3 实现 `GET /api/projects/{project_id}`
- [x] W2.4 实现 `GET /api/projects/{project_id}/meta`
- [x] W2.5 实现 `GET /api/projects/{project_id}/canon`
- [x] W2.6 实现 `GET /api/projects/{project_id}/synopsis`
- [x] W2.7 实现 `GET /api/projects/{project_id}/config`
- [x] W2.8 实现 `GET /api/projects/{project_id}/session`
- [x] W2.9 实现 `GET /api/projects/{project_id}/manuscript`
- [x] W2.10 为只读 API 编写测试

**验收**：

- [x] 启动 Web 后，不传 `project_id` 也能进入首页/API
- [x] 项目列表接口可返回现有项目
- [x] 查询接口对存在项目返回结构化 JSON，对不存在项目返回明确错误

**验收命令（建议）**：

- `python -m unittest tests.test_web_api`
- 手工：启动 `python web_main.py` 后访问首页或 API

---

## Phase W3：动作型 API（send / adopt / fix / scene）

**目标**：把 CLI 的核心写作流程以结构化 API 形式暴露出来，形成完整的 Web 交互闭环。

**做什么**：

- 增加项目打开接口，确保 Session Registry 中 session 就绪
- 实现发送消息接口
- 实现 adopt 的 prepare/commit 双阶段接口
- 实现 fix 的 prepare/commit 双阶段接口
- 实现 scene switch 的 prepare/reconcile/commit 流程接口

**预期效果**：

- Web 前端不需要模拟 CLI 命令字符串
- 作者显式确认规则仍保留
- 场景切换、Hot Canon y/n、Cold review 等交互都可结构化表达

**建议文件**：

- Modify: `lnagent/app_service.py`
- Modify: `lnagent/web/app.py`
- Modify: `lnagent/web/schemas.py`
- Test: `tests/test_web_api.py`

**任务清单**：

- [x] W3.1 实现 `POST /api/projects/{project_id}/open`
- [x] W3.2 实现 `POST /api/projects/{project_id}/send`
- [x] W3.3 实现 `POST /api/projects/{project_id}/adopt/prepare`
- [x] W3.4 实现 `POST /api/projects/{project_id}/adopt/commit`
- [x] W3.5 实现 `POST /api/projects/{project_id}/fix/prepare`
- [x] W3.6 实现 `POST /api/projects/{project_id}/fix/commit`
- [x] W3.7 实现 `POST /api/projects/{project_id}/scene/prepare`
- [x] W3.8 实现 `POST /api/projects/{project_id}/scene/reconcile`
- [x] W3.9 实现 `POST /api/projects/{project_id}/scene/commit`
- [x] W3.10 为动作型 API 编写回归测试

**验收**：

- [x] 可以通过 API 完成一次完整的 send → adopt → commit 流程
- [x] 可以通过 API 完成一次 fix 流程
- [x] 可以通过 API 完成一次 scene switch 流程
- [x] `checkpoint_only` 语义不被破坏

**验收命令（建议）**：

- `python -m unittest tests.test_web_api`
- 手工：使用 curl/HTTP 客户端走通一轮流程

---

## Phase W4：项目创建 API 与首页/项目页最小前端壳

**目标**：让 Web 不只是 API，还具备最小可用的页面壳：能选项目、能看状态、能发消息。

**做什么**：

- 增加创建项目 API（支持 JSON/dict 方式创建）
- 增加首页页面：项目列表 + 新建项目
- 增加项目详情页：对话区 + 状态侧栏 + 基础按钮
- 先以最小页面壳为目标，不追求复杂视觉设计

**预期效果**：

- 作者无需先知道 `project_id` 就可进入系统
- 作者能在浏览器里完成最基础的项目选择与写作交互
- 后续 RAG-lite 或 richer UI 有落点

**建议文件**：

- Modify: `lnagent/project.py`
- Create/Modify: `lnagent/web/templates/*`
- Create/Modify: `lnagent/web/static/*`
- Modify: `lnagent/web/app.py`
- Test: `tests/test_web_api.py`（后端）

**任务清单**：

- [x] W4.1 新增 `create_project_from_meta_dict()` 等非交互式创建能力
- [x] W4.2 实现 `POST /api/projects` 创建项目
- [x] W4.3 实现首页页面（项目列表 + 新建入口）
- [x] W4.4 实现项目页页面（消息、候选、状态面板）
- [x] W4.5 为创建流程与页面基础加载补测试/手工验收

**验收**：

- [x] 打开 Web 首页可见项目列表
- [x] 不预先知道 `project_id` 也可选择或创建项目
- [x] 创建项目后可直接进入项目页
- [x] 项目页至少能完成查看状态 + 发消息

**验收命令（建议）**：

- `python -m unittest tests.test_web_api`
- 手工：`python web_main.py` 后在浏览器打开首页，完成创建或进入项目页

---

## Phase W5：稳定性回归与文档收口

**目标**：确认 Web 第一版没有破坏 CLI 和现有持久化语义，并将新入口说明写回仓库文档。

**做什么**：

- 回归 CLI 行为
- 回归项目持久化行为
- 更新 README 与 features 文档
- 记录已知限制（无鉴权、JSON 真源、无 RAG、无 SQLite 主存储）

**预期效果**：

- Web 第一版可交付
- 仓库中有明确的启动方式、能力边界与后续方向说明
- 新 session 再次进入仓库时，仍可用文档追踪进度与限制

**建议文件**：

- Modify: `README.md`
- Modify: `docs/features/README.md`
- Modify: `docs/features/web-frontend-api-plan.md`
- Test: 相关回归测试文件

**任务清单**：

- [x] W5.1 回归 CLI 入口可用性
- [x] W5.2 回归 session / canon / synopsis 持久化语义
- [x] W5.3 更新 README 的启动与使用说明
- [x] W5.4 更新 features 索引与 Web 文档状态
- [x] W5.5 补充已知限制与下一阶段方向（SQLite、RAG-lite）

**验收**：

- [x] CLI 与 Web 均有明确启动说明
- [x] Web 第一版的已知限制有文档记录
- [x] 本文件各阶段状态已同步到真实完成情况

**验收命令（建议）**：

- `python -m unittest`
- 手工：CLI 与 Web 各走一条最短流程

---

## 推荐实现顺序（执行提示）

```text
W0 共享 bootstrap / 项目索引
  -> W1 服务层 / Session Registry
  -> W2 查询 API
  -> W3 动作 API
  -> W4 最小前端壳
  -> W5 回归与文档收口
```

优先保证：

1. 不破坏 CLI
2. 不破坏 `checkpoint_only`
3. 不丢失 `last_candidate` 等内存语义
4. 先跑通 API，再丰富页面

---

## 风险与注意事项

### 风险 1：每请求重建 `NovelSession`

若 Web 每次请求都重新创建 `NovelSession`，会破坏当前产品语义：

- `last_candidate` 丢失
- `turns_since_last_adopt` 丢失
- 未 checkpoint 的对话态丢失

**应对**：必须引入 Session Registry。

### 风险 2：把 CLI `input()/print()` 直接复用到 Web

CLI 交互函数适合终端，不适合 HTTP。

**应对**：Web 仅复用领域层与服务层，不经由命令文本或终端输入函数驱动。

### 风险 3：Web 与 SQLite 改造同时进行

同时变更交互层与存储层，会显著提高调试难度。

**应对**：第一版保留 JSON 真源；SQLite 放到下一阶段再评估。

---

## Phase W6：MVP 完善（CLI parity + 体验 polish）

**目标**：补齐 Web 与 CLI 的能力差距，并改善项目页的基础可用性。

**做什么**：

- 新增 `undo` / `export` / `config` 更新 API
- 新增 `manuscripts` 列表查询
- 项目页增加撤销、导出、配置编辑入口
- 侧栏结构化展示 Meta / Canon / Synopsis / 多场景正文
- 请求 loading 状态与场景切换建议引导

**任务清单**：

- [x] W6.1 `POST /undo`、`POST /export`、`POST /config`、`GET /manuscripts`
- [x] W6.2 AppService 封装与 CLI 共用 export/config 逻辑
- [x] W6.3 项目页 UI 与静态资源更新
- [x] W6.4 回归测试与文档状态同步

**验收**：

- [x] Web 可撤销 adopt、导出 Markdown、修改项目配置
- [x] 侧栏可读性优于纯 JSON 展示
- [x] `python -m unittest` 通过

---

## Phase W7：流式输出（SSE）

**目标**：Web 发消息时逐 token 展示模型回复，改善长回复等待体验。

**做什么**：

- `NovelSession.stream_send()` 基于 LangChain `model.stream()`
- `POST /api/projects/{id}/send/stream` 返回 SSE（`token` / `done` / `error` 事件）
- WSGI 支持 chunked 流式响应
- 项目页默认走流式发送并实时更新对话区

**任务清单**：

- [x] W7.1 会话层 stream_send 与 chunk 提取
- [x] W7.2 AppService + SSE API + web_main 流式 WSGI
- [x] W7.3 前端 streamPost 与逐字展示
- [x] W7.4 回归测试

**验收**：

- [x] 流式接口完成后 session 状态与同步 `send` 一致
- [x] 保留原 `POST /send` 供 API 客户端使用
- [x] `python -m unittest` 通过

---

## 下一阶段（不在本计划内）

Web/API 第一版完成后，再考虑：

- SQLite 索引/查询层
- RAG-lite 检索接口
- 更完整的 manuscript 浏览/检索
- WebSocket / 流式输出
- 鉴权与用户隔离

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-06 | W7：Web 流式 send（SSE） |
| 2026-06-06 | W6：MVP 完善（CLI parity API + 项目页体验 polish） |
| 2026-06-04 | 初稿：将 Web/API 第一版拆成 W0–W5，要求每阶段包含目标、效果、验收与可追踪状态；用于跨 session 持续追踪进度 |
