# Web Brief 工作空间实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 为 LNAgent 的 Web 侧建立以 `DiscussionBrief` 为中心的工作空间：先稳定 brief v2 的字符串数组 schema，再补可视化面板与人工编辑能力；RAG 暂缓。

**Architecture:** 继续沿用现有 Web/API 双轨架构，把 brief 作为 discussion 与 writing 之间的稳定桥接层。第一阶段只确认 `todo_items / constraints / open_questions` 的字符串数组 schema 与兼容策略，避免过早引入对象模型；后续再在不破坏现有接口的前提下增加 UI 面板和编辑入口。

**Tech Stack:** Python `>=3.10,<4.0`、现有 JSON 持久化、现有 Web WSGI 栈、现有 `DiscussionBrief` / `PromptContextBuilder` / `AppService`。

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

- `DiscussionBrief` 的 v2 schema 先保持字符串数组
- `todo_items / constraints / open_questions` 继续作为独立列表字段
- 为 Web 侧预留可视化 brief 面板的数据接口
- 为作者提供可控的 brief 编辑入口
- 保持 discussion / writing 双轨的现有边界不变
- 后续允许把 brief v2 逐步升级为对象数组，但不阻塞当前计划

### 本计划暂不实现什么

- 直接切换为对象数组 schema
- RAG / 向量检索
- 复杂富文本编辑器
- 改写 CLI 双轨入口
- 讨论内容直接进入 Canon / manuscript

**阶段完成标准**：

- [ ] 范围与非目标与现有双轨设计保持一致

---

## Phase B0：Brief v2 schema 定型

**目标**：先把 brief 的稳定数据契约定下来，明确短期继续用字符串数组，避免对象模型提前膨胀。

**做什么**：

- 明确 `DiscussionBrief` 的字段边界
- 确认 `todo_items / constraints / open_questions` 全部使用 `list[str]`
- 写出从旧 brief 到 v2 的兼容规则
- 补齐 brief 序列化 / 反序列化的约束说明

**预期效果**：

- brief 结构稳定，可直接供 prompt 与 Web 面板复用
- 开发时不会因为对象数组 schema 反复改动接口
- 后续对象数组升级有明确迁移路径

**当前已确认的 B0 约束**：

- `todo_items` 使用 `list[str]`
- `constraints` 使用 `list[str]`
- `open_questions` 使用 `list[str]`
- 旧数据若为单字符串，归一化为单元素数组（如 `"foo" -> ["foo"]`）
- 三个列表字段在序列化 / API / prompt 语义上始终存在，可为空数组，不省略字段
- 列表项统一做 `strip()`，丢弃空串，保留顺序，当前阶段不做去重
- `updated_at` 表示当前 brief 最近一次成功更新的时间；只要 brief 内容或状态发生变化，无论来源都要更新时间
- 不新增对象级元数据字段
- 不改变现有 discussion / writing 路由语义

**建议文件**：

- Modify: `lnagent/memory/models.py`
- Modify: `lnagent/memory/store.py`
- Modify: `lnagent/memory/prompt.py`
- Update docs: `docs/features/discussion-writing-dual-track-design.md`

**实现清单**：

1. 在设计文档中把 brief v2 的字段类型写死为字符串数组。
2. 在 `DiscussionBrief` 数据模型里维持三列字符串列表，不引入对象数组。
3. 在 store 层补充清晰的兼容注释：旧数据若含单字符串也要能安全归一。
4. 在 prompt 格式化里固定输出三个列表块，避免前端和 LLM 依赖不稳定表示。
5. 记录未来对象数组升级条件，但不在本阶段实现。

**验收**：

- [x] brief v2 schema 只有字符串数组，不含对象数组
- [x] 旧数据能平滑读入
- [x] prompt 输出与 store 序列化一致

**验收命令（建议）**：

- `python -m unittest tests.test_discussion_store -v`
- `python -m unittest tests.test_memory_store -v`

---

## Phase B1：Brief 只读面板收口

**目标**：把已经接入项目页的 Discussion Brief 面板收口为稳定、清晰、可回归验证的只读工作区，为 B2 的人工编辑入口打基础。

**做什么**：

- 对齐计划与现状：明确 brief 面板、brief 数据拉取与基础只读渲染已存在
- 收口项目页中的 brief 展示层次、状态表达与按钮归属
- 补足空态 / 脏态 / 已同步态的页面语义
- 补前端与 Web API 回归测试，确保 discussion / writing 切换行为不受影响

**预期效果**：

- 作者能稳定看见当前 brief 的三组内容与同步状态
- brief 在页面上更像“工作区”而不是隐式摘要
- B2 可以在同一面板上继续增加编辑能力，而不需要重做结构

**当前已确认的 B1 约束**：

- B1 不引入 brief 编辑能力，编辑入口留到 B2
- B1 不修改 `DiscussionBrief` 的字符串数组 schema
- B1 不改变现有 discussion / writing 模式切换与路由语义
- brief 面板继续以当前项目页为主，不新增独立页面
- 若调整按钮位置，只做同页内归属优化，不新增新的后端动作

**建议文件**：

- Modify: `docs/features/web-brief-workspace-plan.md`
- Modify: `lnagent/web/app.py`
- Modify: `lnagent/web/static/project.js`
- Modify: `lnagent/web/static/render.js`
- Modify: `lnagent/web/static/style.css`
- Test: `tests/test_web_app.py`

**实现清单**：

1. 回写计划文档，把 B1 从“面板骨架”重定义为“只读面板收口”，明确哪些部分已经具备、哪些部分仍待完成。
2. 复核项目页中 brief 面板与 discussion 操作的布局关系，决定是否把 `刷新讨论摘要` 等动作移动到更靠近 brief 面板的位置。
3. 收紧 brief 渲染语义：区分空 brief、`dirty=true` 待刷新、`dirty=false` 已同步、raw chat 已清空但 brief 保留等状态。
4. 保持 discussion / writing 双轨行为不变，只改展示层，不扩展新的编辑或提交流程。
5. 为页面 HTML、`discussion/get` / `discussion/refresh` 响应和前端静态资源补回归测试，确认 brief 面板持续存在且渲染关键字段。

**任务清单**：

- [x] B1.1 回写计划文档并记录现状
- [ ] B1.2 收口 brief 面板的布局与操作归属
- [ ] B1.3 收紧 brief 状态与空态表达
- [ ] B1.4 为 brief 面板补 Web 回归测试

**验收**：

- [ ] 项目页持续可见 brief 内容、同步状态和空态提示
- [ ] brief 面板收口后不影响现有 discussion / writing 功能
- [ ] 页面刷新、discussion refresh、discussion clear 后 brief 仍按预期显示
- [ ] 测试文件与验收命令指向实际存在的 `tests/test_web_app.py`

**验收命令（建议）**：

- `python -m unittest tests.test_web_app -v`

---

## Phase B2：Brief 人工编辑入口

**目标**：允许作者直接调整 brief 的字符串列表内容，形成“讨论结果可控修订”的闭环。

**做什么**：

- 增加 brief 编辑提交接口
- 允许对三组字符串列表逐项增删改
- 提交后同步刷新 store 与 prompt 输入
- 保持编辑权限和确认语义清晰

**预期效果**：

- 作者可以不经过重跑讨论，直接修正 brief
- Web 端可以把 brief 当成轻量工作区而不是只读摘要
- writing prompt 读取到的内容始终是最新 brief

**建议文件**：

- Modify: `lnagent/app_service.py`
- Modify: `lnagent/web/app.py`
- Modify: `lnagent/web/schemas.py`
- Modify: `lnagent/memory/store.py`
- Test: `tests/test_web_app_service.py`

**任务清单**：

- [ ] B2.1 设计 brief 编辑 payload
- [ ] B2.2 实现 brief 保存与校验
- [ ] B2.3 接入项目页编辑动作
- [ ] B2.4 补 brief 编辑回归测试

**验收**：

- [ ] brief 可通过 Web 端保存
- [ ] 保存后 prompt 与页面同步更新
- [ ] 不破坏现有 discussion / writing 路由

**验收命令（建议）**：

- `python -m unittest tests.test_web_app_service -v`
- `python -m unittest tests.test_web_api -v`

---

## Phase B3：后续升级预留

**目标**：给 brief v2 到对象数组的升级留出清晰出口，但不提前启动。

**做什么**：

- 记录对象数组可扩展点
- 明确升级后需要补的 UI 交互和兼容迁移
- 评估是否需要单独的 diff / history 视图

**预期效果**：

- 当前实现不被未来复杂化拖慢
- 需要 richer brief 时有明确迁移路径
- 讨论 / 写作双轨仍保持稳定

**建议文件**：

- Update docs: `docs/features/discussion-writing-dual-track-design.md`
- Update docs: `docs/features/open-questions.md`

**任务清单**：

- [ ] B3.1 记录对象数组升级前置条件
- [ ] B3.2 记录 brief 编辑 UX 的后续方向
- [ ] B3.3 复核开放问题并更新决议

**验收**：

- [ ] 文档中明确“先字符串数组，后对象数组”
- [ ] 升级入口不影响当前交付

**验收命令（建议）**：

- 无

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-12 | 新增 Web brief 工作空间计划：先定字符串数组 schema，再做可视化面板与人工编辑 |
