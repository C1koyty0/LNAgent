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

**当前已确认的 D0 约束**：

- 复用现有 `ChatMessage`，**不新增** `DiscussionMessage`
- `DiscussionBrief` 保留 `open_questions`
- discussion 路径采用：`projects/<id>/discussion/scene_xxx/messages.json` 与 `brief.json`
- **不修改** `SceneSession` 结构，discussion 不写入 `session.json`

**建议文件**：

- Modify: `lnagent/memory/models.py`
- Modify: `lnagent/memory/store.py`
- Create: `tests/test_discussion_store.py`
- Update docs: `docs/features/discussion-writing-dual-track-design.md`

**实现清单**：

1. 在 `lnagent/memory/models.py` 新增 `DiscussionBrief` dataclass：
   - `scene_id: str`
   - `todo_items: list[str]`
   - `constraints: list[str]`
   - `open_questions: list[str]`
   - `dirty: bool`
   - `updated_at: str`
   - 需要实现 `to_dict()` / `from_dict()` / `empty(scene_id)`
2. 不新增 `DiscussionMessage`；discussion raw chat 直接复用 `ChatMessage` 的 `role/content` 结构。
3. 在 `JsonMemoryStore` 中新增 discussion 路径辅助方法：
   - `_discussion_root()`
   - `_discussion_scene_dir(scene_id)`
   - `_discussion_messages_path(scene_id)`
   - `_discussion_brief_path(scene_id)`
4. 在 `ensure_project_layout()` 中创建 `discussion/` 根目录，但**不预创建** `scene_001/` 子目录。
5. 新增 discussion messages store API：
   - `load_discussion_messages(scene_id) -> list[ChatMessage]`
   - `save_discussion_messages(scene_id, messages)`
   - `append_discussion_message(scene_id, message)`
   - `clear_discussion_messages(scene_id)`
6. 新增 discussion brief store API：
   - `load_discussion_brief(scene_id) -> DiscussionBrief`
   - `save_discussion_brief(scene_id, brief)`
   - `clear_discussion_brief(scene_id)`
7. 新增 scene 级 discussion 清理入口：
   - `clear_discussion_scene(scene_id)`
8. 明确默认行为：
   - `load_discussion_messages()` 在文件不存在时返回 `[]`
   - `load_discussion_brief()` 在文件不存在时返回 `DiscussionBrief.empty(scene_id)`
   - `clear_*()` 在目标不存在时静默成功
9. discussion 文件格式约定：
   - `messages.json` 为对象根，形如 `{ "messages": [ChatMessage.to_dict(), ...] }`
   - `brief.json` 为结构化对象，包含 `todo_items / constraints / open_questions / dirty / updated_at`
10. `updated_at` 在 D0 仅作为数据字段保存，由调用方传入；store 层不负责生成时间。
11. D0 **不涉及**：
   - `NovelSession` 语义拆轨
   - prompt builder 改造
   - API / 前端接线
   - adopt / undo / scene switch 联动

**测试清单**：

- [x] T0.1 `ensure_project_layout()` 创建 `discussion/` 根目录
- [x] T0.2 `load_discussion_messages()` 缺省返回空列表
- [x] T0.3 discussion messages round trip
- [x] T0.4 `append_discussion_message()` 保留已有消息顺序
- [x] T0.5 `load_discussion_brief()` 缺省返回空 brief
- [x] T0.6 discussion brief round trip
- [x] T0.7 `clear_discussion_messages()` 只清 raw chat，不影响 brief
- [x] T0.8 `clear_discussion_brief()` 只清 brief，不影响 messages
- [x] T0.9 `clear_discussion_scene()` 清空当前 scene 的 discussion 全部状态

**任务清单**：

- [x] D0.1 定义 `DiscussionBrief` 数据结构
- [x] D0.2 设计并实现 `projects/<id>/discussion/scene_xxx/` 持久化布局
- [x] D0.3 在 store 中增加 discussion read/write/clear 接口
- [x] D0.4 为 discussion store 编写单元测试

**验收**：

- [x] discussion raw chat 与 brief 能独立读写
- [x] `session.json` 与现有 writing / canon / synopsis 持久化格式保持不变
- [x] 给定 `scene_id`，可定位 discussion 数据目录
- [x] discussion 清理行为不影响 writing 主路径

**验收命令（建议）**：

- `python -m unittest tests.test_discussion_store -v`
- `python -m unittest tests.test_memory_store -v`

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

**当前已确认的 D1 约束**：

- `PromptContextBuilder.build()` 保留为兼容别名，并内部转发到 `build_writing()`
- discussion / writing 使用两套独立 instruction
- 只有 writing prompt 读取 `DiscussionBrief`
- discussion prompt **不读取** brief
- discussion prompt **不注入**当前场景 `adopted_prose`，只允许读取 `scene_tail`
- D1 只做 prompt 基础设施，不做 brief dirty 刷新或 runtime 分流

**建议文件**：

- Modify: `lnagent/memory/prompt.py`
- Modify: `tests/test_memory_store.py`
- Update docs: `docs/features/discussion-writing-dual-track-implementation-plan.md`

**实现清单**：

1. 在 `lnagent/memory/prompt.py` 中拆出两套 instruction 常量：
   - `_WRITING_INSTRUCTIONS`
   - `_DISCUSSION_INSTRUCTIONS`
2. 为 `PromptContextBuilder` 新增两个显式入口：
   - `build_writing(...)`
   - `build_discussion(...)`
3. 保留 `build(...)` 作为兼容别名，并让其内部直接调用 `build_writing(...)`。
4. 将当前 `build()` 的主拼装逻辑迁移到 `build_writing()`，尽量保持现有 budget / meta / canon / synopsis / scene_tail 行为不变。
5. 为 `build_writing()` 增加参数：
   - `discussion_brief: DiscussionBrief | None = None`
6. 新增 writing brief 格式化 helper，例如：
   - `_format_discussion_brief_for_writing(brief)`
7. 在 writing system prompt 中新增独立 brief block：
   - 标题建议为 `当前场景讨论结论（供写作参考，非 Canon）`
   - 包含 `todo_items / constraints / open_questions`
8. 明确 writing system prompt 的相对顺序：
   - instructions
   - meta
   - global summary / prior cold
   - hot canon
   - discussion brief
   - scene tail / adopted prose
9. 实现 `build_discussion()`：
   - 使用 `_DISCUSSION_INSTRUCTIONS`
   - 不接收 `discussion_brief`
   - 不注入 brief block
   - 不注入 `已采纳正文（当前场景）`
   - 可注入 `scene_tail`
10. 保持 discussion prompt 的上下文更轻：
   - 可读 `meta / canon / global / prior / scene_tail / raw history / user_input`
   - 不默认读取完整 `adopted_prose`
11. D1 **不涉及**：
   - `NovelSession` 双轨 send 分流
   - brief dirty / 自动刷新
   - API / 前端接线
   - discussion raw chat → brief 提炼逻辑

**测试清单**：

- [x] T1.1 `build()` 仍兼容走 writing 路径
- [x] T1.2 `build_writing()` 注入 brief block
- [x] T1.3 `build_writing()` 在 `discussion_brief=None` 时不注入空 brief block
- [x] T1.4 `build_discussion()` 使用 discussion instructions
- [x] T1.5 `build_discussion()` 不注入 `已采纳正文（当前场景）`
- [x] T1.6 `build_discussion()` 可注入 `scene_tail`
- [x] T1.7 `build_writing()` 保持 `meta -> global/prior -> canon -> brief -> tail/prose` 相对顺序

**任务清单**：

- [x] D1.1 拆离 discussion / writing 两套 instruction 模板
- [x] D1.2 新增 `build_writing()` / `build_discussion()` 双入口
- [x] D1.3 为 writing prompt 注入 `DiscussionBrief`
- [x] D1.4 保留 `build()` 兼容别名
- [x] D1.5 为双 prompt 行为补回归测试

**验收**：

- [x] discussion prompt 与 writing prompt 可独立构建
- [x] writing prompt 读取 brief，不读取 discussion raw chat
- [x] discussion prompt 不注入当前场景 `adopted_prose`
- [x] 现有 writing prompt 的世界观 / Canon / synopsis 注入顺序仍正确

**验收命令（建议）**：

- `python -m unittest tests.test_memory_store.PromptContextBuilderTest -v`
- `python -m unittest tests.test_memory_store -v`

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
