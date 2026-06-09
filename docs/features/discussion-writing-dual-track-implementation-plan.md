# 讨论 / 写作双轨实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 为 LNAgent 增加 discussion / writing 双轨能力：讨论与写作在 prompt、会话状态、持久化路径、API 语义上彻底拆分；讨论只服务当前 scene 的规划，不直接进入正文与 Canon；写作继续沿用现有 adopt / canon / manuscript 主路径。

**Architecture:** 采用增量式改造：保留现有 writing 主路径作为兼容基线，在其旁边新增 discussion 轨的数据模型、持久化与服务接口。discussion 与 writing 通过结构化 brief 桥接，writing 只读取 brief，不读取 raw discussion chat。第一版优先打通领域层 / 服务层 / API，前端 toggle 最后接入。

**Tech Stack:** Python `>=3.10,<4.0`、现有 `LangChain` / `langchain-openai`、JSON 持久化、现有 `NovelSession` / `AppService` / Web WSGI 栈。

---

## 使用说明（进度追踪）

**状态标记规则**：

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成并通过本阶段验收
- 如有阻塞，在阶段末补充 `阻塞：...`

**追踪原则**：

- 每完成一个阶段，必须更新本文件状态与验收结果。
- 新 session 开始时，应先阅读本文件与 `discussion-writing-dual-track-design.md`，再决定下一步。
- 若实现过程中设计发生变化，优先回写设计文档与本计划，而不是只留在聊天记录里。

---

## 0. 范围与非目标（当前轮已确认）

### 本计划要交付什么

- discussion / writing 两条独立轨道
- 两套 prompt
- 两套消息历史与持久化路径
- discussion raw chat + scene brief
- writing 继续走现有 `candidate -> adopt -> canon/manuscript`
- writing 只读取 discussion brief
- adopt commit 后清空 discussion raw chat，但保留 brief
- scene switch 后清空当前 scene 的 discussion raw chat 与 brief
- Web/API 暴露显式 `discussion/*` 与 `writing/*` 路由
- 前端增加讨论 / 写作 toggle（后置阶段）

### 本计划暂不实现什么

- discussion 内容直接进入 Canon / manuscript
- discussion 跨 scene 共享
- undo 恢复 discussion raw chat
- 将 discussion brief 升级为全书级 story bible
- 多用户隔离 / 鉴权
- discussion 复杂富文本编辑器

**阶段完成标准**：

- [ ] 范围与非目标与设计文档保持一致

---

## Phase D0：数据模型与存储路径设计落地

**目标**：先把 discussion 轨的数据模型和 JSON 存储路径落下来，保证后续服务层与 API 不再靠临时 dict 拼装。

**做什么**：

- 新增 discussion brief 数据模型
- 明确 discussion raw chat 的持久化格式
- 新增 scene 级 discussion store 读写接口
- 保持现有 writing 路径不变

**预期效果**：

- 项目目录中有清晰的 discussion 存储位置
- discussion 数据可独立读写，不混入现有 `session.json`
- brief 结构稳定，可供 writing prompt 注入

**建议文件**：

- Modify: `lnagent/memory/models.py`
- Modify: `lnagent/memory/store.py`
- Create: `tests/test_discussion_store.py`
- Update docs: `docs/features/discussion-writing-dual-track-design.md`

**任务清单**：

- [ ] D0.1 定义 `DiscussionBrief` / `DiscussionMessage` 数据结构
- [ ] D0.2 设计 `projects/<id>/discussion/scene_xxx/` 持久化布局
- [ ] D0.3 在 store 中增加 discussion read/write/clear 接口
- [ ] D0.4 为 discussion store 编写单元测试

**验收**：

- [ ] discussion raw chat 与 brief 能独立读写
- [ ] 不修改现有 writing / canon / synopsis 持久化格式
- [ ] 给定 scene_id，可定位 discussion 数据目录

**验收命令（建议）**：

- `python -m unittest tests.test_discussion_store -v`

---

## Phase D1：PromptBuilder 与双 prompt 基础设施

**目标**：为 discussion / writing 建立两套 prompt 入口，停止依赖单一 `_WRITING_INSTRUCTIONS`。

**做什么**：

- 抽出 discussion prompt 与 writing prompt
- 为 writing prompt 增加 brief 注入位
- 保持现有 meta / canon / synopsis 注入顺序不被破坏

**预期效果**：

- discussion 任务明确是“规划 / 分析 / 约束整理”
- writing 任务明确是“生成可采纳正文候选”
- writing 使用 brief，而不是 raw discussion chat

**建议文件**：

- Modify: `lnagent/memory/prompt.py`
- Test: `tests/test_prompt_builder.py` 或新增 `tests/test_discussion_prompt.py`

**任务清单**：

- [ ] D1.1 抽离 discussion / writing 两套 instruction 模板
- [ ] D1.2 为 writing prompt 注入 discussion brief
- [ ] D1.3 确保 discussion prompt 不注入 candidate 语义字段
- [ ] D1.4 为 prompt builder 行为补测试

**验收**：

- [ ] discussion prompt 与 writing prompt 可独立构建
- [ ] writing prompt 读取 brief，不读取 discussion raw chat
- [ ] 现有 writing prompt 的世界观 / Canon / synopsis 注入顺序仍正确

**验收命令（建议）**：

- `python -m unittest tests.test_prompt_builder -v`

---

## Phase D2：Session 语义拆轨

**目标**：把 `NovelSession` 从“单 send 语义”升级为“discussion send + writing send”双轨语义。

**做什么**：

- 在 session 层新增 discussion send / writing send 能力
- 让 discussion 不更新 `last_candidate`
- 让 discussion 不影响 adopt stack / scene hint 计数
- 让 writing 继续沿用现有 candidate 语义

**预期效果**：

- 后端真正具备严格模式边界
- discussion 不再污染 writing 状态
- writing 仍兼容现有 adopt / fix / scene 主流程

**建议文件**：

- Modify: `lnagent/session.py`
- Modify: `lnagent/memory/short_term.py`
- Test: `tests/test_memory_store.py` 或新增 `tests/test_dual_track_session.py`

**任务清单**：

- [ ] D2.1 为 session 增加 discussion 状态读取/写入辅助方法
- [ ] D2.2 实现 `send_discussion()`
- [ ] D2.3 重命名或封装现有 `send()` 为 writing 语义入口
- [ ] D2.4 明确 discussion 不更新 `last_candidate` / `turns_since_last_adopt`
- [ ] D2.5 为 discussion / writing 边界写回归测试

**验收**：

- [ ] discussion send 后 `last_candidate` 不变
- [ ] discussion send 不写 manuscript / canon
- [ ] writing send 继续可被 adopt
- [ ] scene switch suggestion 仅由 writing 主线驱动

**验收命令（建议）**：

- `python -m unittest tests.test_dual_track_session -v`
- `python -m unittest tests.test_memory_store -v`

---

## Phase D3：brief 刷新与桥接逻辑

**目标**：打通 discussion raw chat → brief → writing prompt 的桥接闭环。

**做什么**：

- 增加 discussion brief 生成 / 刷新逻辑
- 为 brief 引入 `dirty` 语义
- writing send 前自动检查并刷新 dirty brief

**预期效果**：

- discussion 原始聊天不会直接污染 writing prompt
- writing 始终读取最新可用 brief
- brief 刷新成本可控

**建议文件**：

- Modify: `lnagent/session.py`
- Create/Modify: `lnagent/memory/discussion_brief.py`
- Test: `tests/test_discussion_brief.py`

**任务清单**：

- [ ] D3.1 设计 brief 刷新输入输出接口
- [ ] D3.2 在 discussion send 后标记 brief dirty
- [ ] D3.3 在 writing send 前自动刷新 dirty brief
- [ ] D3.4 为 brief 刷新与自动桥接补测试

**验收**：

- [ ] discussion 后 brief 可标记 dirty
- [ ] writing 前可自动得到最新 brief
- [ ] writing 不直接读取 raw discussion messages

**验收命令（建议）**：

- `python -m unittest tests.test_discussion_brief -v`

---

## Phase D4：adopt / undo / scene switch 的 discussion 联动

**目标**：把 discussion 轨接入现有显式作者控制流程，明确 adopt、undo、scene switch 时的清理行为。

**做什么**：

- adopt commit 后清空 discussion raw chat
- 保留 discussion brief
- undo 不恢复 raw chat
- scene switch 完成后清空当前 scene 的 raw chat 与 brief

**预期效果**：

- discussion 生命周期与当前 scene 对齐
- adopt 后上下文更干净
- scene switch 后 discussion 不跨 scene 残留

**建议文件**：

- Modify: `lnagent/session.py`
- Modify: `lnagent/memory/store.py`
- Test: `tests/test_dual_track_session.py`

**任务清单**：

- [ ] D4.1 在 adopt commit 中接入 discussion raw clear
- [ ] D4.2 明确 undo 不恢复 discussion raw
- [ ] D4.3 在 scene switch 完成路径中清空 discussion raw + brief
- [ ] D4.4 为上述联动行为补测试

**验收**：

- [ ] adopt commit 后 raw discussion chat 为空
- [ ] adopt commit 后 brief 仍存在
- [ ] undo 后 raw discussion chat 不恢复
- [ ] scene switch 后 discussion 状态为空

**验收命令（建议）**：

- `python -m unittest tests.test_dual_track_session -v`

---

## Phase D5：AppService 与 Web/API 拆分

**目标**：将 discussion / writing 的后端能力通过显式服务接口与路由暴露出来。

**做什么**：

- AppService 新增 discussion 相关服务
- Web 路由新增 `discussion/*` 与 `writing/*`
- 保留旧 `/send` 作为 writing 兼容别名（过渡期）

**预期效果**：

- API 层语义清晰，不再靠 `mode` 参数猜测
- discussion / writing 都可独立测试
- 现有调用方有兼容迁移路径

**建议文件**：

- Modify: `lnagent/app_service.py`
- Modify: `lnagent/web/app.py`
- Test: `tests/test_web_app.py`

**任务清单**：

- [ ] D5.1 新增 `discussion/send` / `discussion/get` / `discussion/refresh` / `discussion/clear`
- [ ] D5.2 新增 `writing/send` / `writing/send/stream`
- [ ] D5.3 保留现有 `/send` 兼容映射到 writing 路径
- [ ] D5.4 为 discussion / writing API 补回归测试

**验收**：

- [ ] API 可显式区分 discussion 与 writing
- [ ] discussion API 不污染 candidate 状态
- [ ] writing API 继续支持同步与 SSE 流式发送

**验收命令（建议）**：

- `python -m unittest tests.test_web_app -v`

---

## Phase D6：前端 toggle 与项目页双轨展示

**目标**：在项目页中增加“讨论 / 写作”切换入口，并让 brief 与 candidate 在 UI 上可见分层。

**做什么**：

- 前端新增 mode toggle/button group
- discussion 发送走 discussion API
- writing 发送走 writing API / SSE
- 增加 discussion brief 面板

**预期效果**：

- 用户显式知道自己当前是在讨论还是写作
- 讨论结果如何服务写作在页面上可见
- discussion 与 writing 的心智模型一致

**建议文件**：

- Modify: `lnagent/web/static/project.js`
- Modify: `lnagent/web/static/render.js`
- Modify: `lnagent/web/app.py`（模板/页面骨架）
- Test: 后续 Playwright E2E 或扩展现有页面测试

**任务清单**：

- [ ] D6.1 新增讨论 / 写作 toggle
- [ ] D6.2 discussion brief 面板展示
- [ ] D6.3 writing candidate 面板与 adopt 操作保持可用
- [ ] D6.4 为页面行为补验收测试

**验收**：

- [ ] 前端可显式切换 discussion / writing
- [ ] discussion 返回不覆盖 writing candidate
- [ ] writing 仍可走通 send -> adopt -> commit

**验收命令（建议）**：

- `python -m unittest tests.test_web_app -v`
- 后续补充 Playwright E2E

---

## Phase D7：CLI 兼容策略与文档收口

**目标**：明确 CLI 是否继续维持单轨 MVP 行为，或逐步接入双轨；并把仓库文档统一收口。

**做什么**：

- 决定 CLI 第一阶段是否保持原语义不变
- 更新 README / memory-architecture / feature 索引
- 记录兼容别名、限制与迁移说明

**预期效果**：

- 新旧入口边界清楚
- 后续 session 不需要从聊天记录恢复设计意图
- 仓库文档对“当前 MVP”和“下一阶段双轨”区分明确

**建议文件**：

- Modify: `README.md`
- Modify: `docs/features/README.md`
- Modify: `docs/features/memory-architecture.md`
- Modify: `docs/features/open-questions.md`

**任务清单**：

- [ ] D7.1 决定 CLI 是否接入双轨或暂保持旧行为
- [ ] D7.2 更新仓库 README 与特性说明
- [ ] D7.3 记录 API / CLI 兼容策略
- [ ] D7.4 记录已知限制与后续方向

**验收**：

- [ ] 文档能解释 discussion / writing 双轨的边界
- [ ] API 与 CLI 的当前语义清晰可查
- [ ] 新 session 可仅依靠文档继续推进

**验收命令（建议）**：

- 手工审阅文档一致性
- `python -m unittest`

---

## 推荐实现顺序

```text
D0 discussion 数据模型 / store
  -> D1 双 prompt
  -> D2 session 语义拆轨
  -> D3 brief 刷新桥接
  -> D4 adopt/undo/scene 联动
  -> D5 AppService / Web API
  -> D6 前端 toggle
  -> D7 文档收口
```

优先保证：

1. discussion 不污染 candidate / canon / manuscript
2. writing 主路径尽量保持兼容
3. writing 只读取 brief，不读取 raw discussion chat
4. scene 级生命周期边界明确

---

## 风险与注意事项

### 风险 1：把 discussion 状态塞回 `session.json`

这样会导致双轨边界重新模糊，并增加与现有 `checkpoint_only` 语义冲突的概率。

**应对**：discussion 使用独立路径与独立 store 接口。

### 风险 2：writing 直接读取 raw discussion chat

会导致 prompt 污染、token 不稳定、讨论冗余渗入正文生成。

**应对**：writing 只读取结构化 brief。

### 风险 3：discussion 与 writing 只是前端按钮区分，后端仍单路径

这会造成“视觉分离、语义未分离”的假象，风险比不做更大。

**应对**：先完成领域层 / 服务层拆轨，再接前端 toggle。

### 风险 4：adopt / scene switch 对 discussion 生命周期处理不清

若不明确 adopt 后与 scene switch 后的清理行为，discussion 数据会长期滞留，影响写作上下文。

**应对**：在 D4 阶段通过测试锁定 raw chat / brief 的生命周期矩阵。

---

## 下一阶段（不在本计划内）

双轨基础完成后，再考虑：

- discussion brief 人工编辑
- discussion brief 的更细 schema（角色、伏笔、冲突、节拍分栏）
- CLI 是否也显式支持 discussion / writing 模式
- discussion 的更强可视化面板
- 基于 brief 的 RAG-lite 检索 / scene planning

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-09 | 初稿：将 discussion / writing 双轨拆成 D0–D7，可跨 session 跟踪实现进度 |
