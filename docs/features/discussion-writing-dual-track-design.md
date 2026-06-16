# 讨论 / 写作双轨设计草案

> **状态**：设计讨论已收敛，待实现  
> **范围**：LNAgent 当前 scene 内的 Web / CLI 会话语义扩展  
> **目标**：将“讨论”和“写作”从 prompt、会话状态、持久化路径与 API 语义上彻底拆分，同时保留现有写作主路径的 adopt / canon / manuscript 规则。

---

## 1. 背景与动机

LNAgent 当前实现只有一条 `send` 路径：

- 同一套 prompt
- 同一套消息历史
- 同一个 `last_candidate`
- 同一个候选正文语义

这会带来两个问题：

1. **讨论与写作混流**：作者在讨论设定、节拍、人物动机时，系统仍可能把回复当作候选正文语义来处理。
2. **上下文污染**：长篇讨论原文会与写作上下文混在一起，不利于稳定生成可采纳正文。

因此需要将“讨论”和“写作”彻底拆为两条轨道：

- **讨论轨（discussion）**：用于梳理大纲、节拍、角色动机、当前场景约束、要避免的问题等
- **写作轨（writing）**：用于生成可采纳正文候选，并继续沿用现有 adopt / canon / manuscript 流程

---

## 2. 设计目标

### P0

- 讨论内容**不进入**正文、Hot Canon、Cold Archive
- 写作内容继续沿用现有路径，仍需显式 adopt 才进入正文 / canon
- 写作可读取讨论结论，但读取方式可控，不直接吃整段讨论原文

### P1

- 讨论与写作在**prompt、消息历史、状态字段、持久化路径、API** 上都可区分
- scene 内讨论可服务本 scene 写作，但不跨 scene 残留
- adopt 后可清理讨论原始聊天，降低上下文污染

### P2

- 尽量保持现有写作主流程与持久化结构兼容
- 为后续 Web 前端“讨论 / 写作 toggle”提供自然支点

---

## 3. 已确认产品决策

### 3.1 双轨完全分离

系统引入两条独立轨道：

- `discussion`
- `writing`

两者至少在以下层面区分：

- prompt
- 消息历史
- 持久化路径
- API 路由
- session 内状态字段

### 3.2 讨论轨的产物

讨论轨存两类内容：

1. **原始讨论聊天（raw chat）**
2. **结构化 brief**

brief 的定位已经确认：

- **待写事项**
- **当前场景约束**

它不是 Canon，也不是正文，更不是全书长期 Story Bible。

### 3.3 写作轨的产物

写作轨继续沿用现有语义：

- 回复可成为 `last_candidate`
- 作者可 `adopt`
- adopt 后可进入 manuscript
- Hot Canon / Cold Archive 仍只从写作主线与显式流程进入

### 3.4 讨论对写作的影响路径

写作**只读取 discussion brief**，不直接读取 discussion raw chat。

即：

- discussion raw chat → 供 discussion brief 生成使用
- discussion brief → 供 writing prompt 注入使用
- writing 不直接消费 raw discussion messages

### 3.5 adopt 后的清理规则

当写作内容 `adopt commit` 成功后：

- **清空 discussion raw chat**
- **保留 discussion brief**

这样可以避免继续把旧讨论原文塞进后续上下文，同时保留当前 scene 的待写事项与约束结论。

### 3.6 undo 规则

`undo adopt` **不恢复**被清空的 discussion raw chat。

这是一个明确的产品取舍：

- 保持实现与状态回滚简单
- 避免为讨论轨引入 adopt 级回滚耦合

### 3.7 作用域

discussion scope 为：

- **当前 scene 私有**

不跨 scene 共享，不作为全书级长期记忆。

---

## 4. 核心语义模型

### 4.1 discussion 与 writing 的职责边界

#### discussion

适用任务：

- 拆 scene 节拍
- 讨论角色动机
- 讨论当前 scene 要避免的 bug
- 讨论这一段应该出现什么信息、冲突、反转
- 梳理本 scene 待写事项

不应发生的事：

- 不生成 `last_candidate`
- 不写入 adopt stack
- 不写入 manuscript
- 不触发 Hot Canon / Cold Archive 更新

#### writing

适用任务：

- 续写正文
- 改写正文
- 生成可供 adopt 的候选文本

保持现有行为：

- 生成 candidate
- 显式 adopt
- 进入 manuscript / canon / scene-switch 主流程

### 4.2 严格模式边界

既然产品目标是“完全区分开”，则后端语义也应严格执行：

- 在 `discussion` 轨中，即使作者输入像“直接写正文”，系统也应优先按讨论轨规则响应，而不是偷偷生成 candidate
- 在 `writing` 轨中，输出目标默认是可采纳正文候选，而不是讨论分析

前端 toggle 只是入口映射，真正的边界应由后端保证。

---

## 5. Prompt 设计

### 5.1 discussion prompt

discussion prompt 应明确：

- 当前任务是讨论，不是正式正文生成
- 输出应偏分析、规划、拆解、列要点、提出备选方案
- 可以提炼出适合写作的 scene brief
- 不要把讨论内容伪装成已经发生的剧情
- 不要把未采纳讨论当作 Canon 事实

### 5.2 writing prompt

writing prompt 应明确：

- 当前任务是生成可采纳正文候选
- 必须遵守 meta / Hot Canon / synopsis / 当前 scene brief
- brief 中的“待写事项 + 当前场景约束”是写作要求的一部分
- 输出目标是叙事正文，而不是讨论分析

### 5.3 两套 prompt 的关系

- discussion prompt 为“思考与规划”服务
- writing prompt 为“正文候选生成”服务
- 它们共享底层世界观 / Canon / synopsis 约束，但不共享任务指令模板

---

## 6. 状态与持久化设计

### 6.1 现有写作路径（保持不变）

现有写作主路径继续保留：

- `projects/<id>/session.json`
- `projects/<id>/memory/canon.json`
- `projects/<id>/memory/synopsis.json`
- `projects/<id>/manuscript/scene_XXX.md`

建议新增目录：

```text
projects/<id>/discussion/
  scene_001/
    messages.json
    brief.json
```

语义：

- `messages.json`：当前 scene 的原始 discussion 聊天
- `brief.json`：当前 scene 的结构化 brief

这里采用 scene 子目录形式，而不是 `scene_001_messages.json` / `scene_001_brief.json` 扁平文件命名，原因是：

- 更利于后续扩展 scene 级附加状态
- 便于 `clear_discussion_scene(scene_id)` 做整目录清理
- 保持 scene 私有 discussion 数据的边界清晰

### 6.3 brief 结构建议

建议第一版采用显式 JSON 结构，而不是自由文本：

```json
{
  "scene_id": "scene_001",
  "todo_items": [
    "主角进入学院后先感到格格不入",
    "本段必须交代徽章异常发热",
    "结尾埋下导师注意到主角的伏笔"
  ],
  "constraints": [
    "不要提前揭示徽章真实来源",
    "本 scene 保持第一人称近距离视角",
    "不要引入新主要角色"
  ],
  "open_questions": [
    "导师是否在本 scene 直接出场仍未决定"
  ],
  "dirty": false,
  "updated_at": "2026-06-09T12:00:00"
}
```

其中：

- `todo_items`：待写事项（`list[str]`，字段始终存在，可为空数组）
- `constraints`：当前 scene 约束（`list[str]`，字段始终存在，可为空数组）
- `open_questions`：可选，保留尚未定论点（`list[str]`，字段始终存在，可为空数组）
- `dirty`：原始讨论更新后，brief 是否需要刷新
- 兼容旧数据时，若任一列表字段是单字符串，则归一化为单元素数组
- 所有列表项在读写时统一 `strip()`，丢弃空串，保序不去重

当前版本明确采用 **字符串数组优先**：先把三栏语义（`todo_items / constraints / open_questions`）与读写边界稳定下来，再讨论是否升级为对象数组。未来若出现 item 级状态、优先级、来源、注释、排序或冲突合并需求，可再将三组列表从 `list[str]` 演进为对象数组，但该升级应满足以下约束：

- 升级目标是**增强条目字段**，不是改变三栏语义分工
- 旧 `list[str]` 数据需要有明确、单向、可回放的迁移规则
- writing prompt 仍应以稳定的纯文本条目视图读取 brief，而不是直接依赖前端对象结构
- 在真实需求明确前，不预埋对象数组兼容层，不引入半成品迁移代码

因此，当前阶段不在 schema 中加入 `id/status/source/priority` 等字段；这些 richer brief 能力仅作为后续演进出口记录在 B3 文档中。

### 6.4 持久化原则

discussion 轨建议**按轮次持久化**：

- 每次 discussion send 后，raw chat 写盘
- brief 可在生成/刷新后写盘

原因：

- discussion 更像策划笔记
- 相比候选正文，讨论丢失的感知更差
- 不宜完全复用 writing 的 `checkpoint_only`

---

## 7. brief 刷新策略

### 7.1 默认策略

推荐策略：

1. discussion 消息写入 raw chat
2. 将 brief 标记为 `dirty=true`
3. 在进入 writing 前，如果 `dirty=true`，自动调用一次 brief 生成/刷新
4. 刷新完成后置 `dirty=false`

### 7.2 为什么不每轮都刷新

不建议每轮 discussion 都强制刷新 brief：

- 增加 LLM 调用成本
- 讨论过程中 brief 容易频繁抖动
- 有些 discussion 只是局部探索，不值得立即沉淀

### 7.4 `dirty` 的精确定义

`dirty=true` 的唯一语义是：

- 当前 scene 的 discussion raw chat 中，存在**尚未被当前 brief 摘要吸收**的信息。

因此：

- discussion 新增 user/assistant 消息后，应将 brief 标记为 `dirty=true`
- brief 刷新成功后，应保存新 brief 并置 `dirty=false`
- 若当前 scene 已无 raw discussion messages，则不应仅因为 brief 存在而继续保持 `dirty=true`

### 7.5 brief 刷新输入边界

brief 刷新时，允许读取的输入为：

- 当前 scene 的 discussion raw chat
- `NovelMeta`
- `HotCanon`
- `synopsis.global`
- `prior_scene_cold`
- `scene_tail`

但 **不读取 writing 轨的 `ShortTermBuffer.messages`**。

原因：

- writing 与 discussion 已在后端语义上拆轨
- brief 刷新应总结 discussion 轨结论，而不是重新混入 writing 主线聊天历史

### 7.6 刷新触发与失败策略

推荐流程：

1. `send_discussion()` / `stream_send_discussion()` 结束后，只写 raw chat，并将 brief 标记为 `dirty=true`
2. `send_writing()` / `stream_send_writing()` 在构建 writing prompt 前检查 brief
3. 若 `dirty=true` 且当前 scene raw discussion messages 非空，则自动刷新 brief
4. 若刷新成功：
   - 用新 brief **整体覆盖**旧 brief
   - 写入 `updated_at`
   - 置 `dirty=false`
5. 若刷新失败：
   - **不阻塞 writing**
   - 回退到旧 brief；若无旧 brief，则按无 brief 处理
   - 允许 `dirty` 继续保持 `true`，等待下一次刷新机会

### 7.7 为什么采用整份重算覆盖

brief 刷新采用**全量 raw discussion → 重新生成完整 brief**，而不是增量 merge。

原因：

- discussion 过程中常会推翻前面的中间意见
- 增量 merge 容易残留过期的 `todo_items` / `constraints`
- 全量重算更符合“当前讨论共识”的产品语义

### 7.8 `updated_at` 的语义

`updated_at` 表示：

- **该 brief 最近一次成功写回后的时间**
- 既包括自动 refresh 生成新 brief，也包括 discussion 追加后仅更新 `dirty` 状态、以及未来人工编辑等写回场景

它不表示：

- 最后一条 raw discussion message 的时间
- brief 首次创建时间

因此 B0 之后，推荐统一在 brief 持久化写回路径更新时间，而不是只在 refresher 成功时补写。

---

## 8. API 设计建议

既然目标是“完全区分”，建议 API 也做显式拆分，而不是在同一路由里加 `mode` 参数。

### 8.1 discussion API

```text
POST /api/projects/{project_id}/discussion/send
GET  /api/projects/{project_id}/discussion/get
POST /api/projects/{project_id}/discussion/refresh
POST /api/projects/{project_id}/discussion/brief/save
POST /api/projects/{project_id}/discussion/clear
```

建议语义：

- `discussion/send`：追加 discussion 原始聊天，返回 discussion 回复与最新 brief 状态
- `discussion/get`：读取 raw chat + brief
- `discussion/refresh`：显式刷新 brief（前端也可手动触发）
- `discussion/brief/save`：人工编辑并保存当前 scene 的 brief
- `clear`：清空当前 scene 的 raw discussion chat（必要时也可支持清 brief）

### 8.2 writing API

```text
POST /api/projects/{project_id}/writing/send
POST /api/projects/{project_id}/writing/send/stream
```

它们本质上是现有 `/send` 与 `/send/stream` 的语义升级版：

- 写作前读取 discussion brief
- 仍生成 candidate
- 仍服务 adopt / fix / scene 现有主路径

### 8.3 现有 `/send` 路由的处理

建议过渡期方案：

- 保留现有 `/send`、`/send/stream`
- 但在实现上将其视为 `writing/send` 的兼容别名
- 新前端改走显式 `discussion/*` 与 `writing/*`

这样可减少对已有测试与调用方的破坏。

---

## 9. Session 行为矩阵

### 9.1 discussion send

执行后：

- 追加 discussion raw messages
- 不更新 `last_candidate`
- 不更新 adopt stack
- 不更新 turns_since_last_adopt
- brief 标记 dirty
- 不触发 scene switch suggestion

### 9.2 writing send

执行后：

- 按现有写作主路径生成 candidate
- 更新 `last_candidate`
- 更新 messages
- 更新 turns_since_last_adopt
- 可继续触发现有 scene-switch suggestion 逻辑

### 9.3 adopt commit

执行后：

- 按现有逻辑写入 manuscript / canon
- 清空 discussion raw chat
- 保留 discussion brief

### 9.4 undo adopt

执行后：

- 仅回滚现有写作主路径数据
- 不恢复 discussion raw chat
- discussion brief 保持当前值不变

### 9.5 scene switch commit

执行后：

- 完成现有 scene switch 主逻辑
- 清空当前 scene 的 discussion raw chat
- 清空当前 scene 的 discussion brief
- 新 scene 启动时 discussion 状态为空

---

## 10. 前端映射建议

前端建议增加一个简单 toggle / button group：

- `讨论`
- `写作`

映射规则：

- 讨论模式 → `discussion/send`
- 写作模式 → `writing/send` 或 `writing/send/stream`

项目页可同时展示两个区块：

1. **Discussion Brief 面板**
   - 待写事项
   - 当前 scene 约束
2. **Writing Candidate 面板**
   - 当前 candidate
   - adopt/fix/scene 操作

这样能让“讨论结果如何进入写作”在 UI 上可见。

---

## 11. 与现有记忆架构的关系

当前 `memory-architecture.md` 中有一条既有决议：

- “纯讨论轮次不单独设模式；是否写入正文仍仅由显式 `/a` 决定”

本设计草案代表的是**下一阶段演进方向**：

- 现有 MVP：讨论与写作仅在 prompt 语义层弱区分
- 下一阶段：讨论 / 写作在 prompt、状态、存储、API 上彻底拆轨

因此实现前应同步更新：

- `memory-architecture.md`
- `open-questions.md`
- Web/API 相关计划文档

避免旧文档继续把“不单独设模式”当作最终结论。

---

## 12. 实现建议顺序

1. **数据模型与存储层**
   - discussion messages store
   - discussion brief store
2. **session / service 语义拆轨**
   - discussion send
   - writing send
3. **API 拆分**
   - `discussion/*`
   - `writing/*`
4. **测试补齐**
   - discussion 不污染 candidate / canon / manuscript
   - writing 正常读取 brief
   - adopt 后清 raw chat
   - scene switch 清空 discussion 状态
5. **前端 toggle**
   - 显式切换讨论 / 写作入口

---

## 13. 待确认但可按默认值推进的实现细节

以下细节目前没有明显分歧，可直接按默认值实施：

- discussion brief 采用 JSON 结构而非纯文本
- writing 只读取 brief，不读取 raw chat
- discussion 使用独立 endpoint，而不是 `mode` 参数
- discussion raw chat 按轮次落盘
- adopt 后保留 brief、清 raw chat
- scene switch 后清 raw chat + brief

---

## 14. 一句话总结

LNAgent 下一阶段将从“单会话、弱区分讨论/写作”演进为“当前 scene 内 discussion / writing 双轨并行”：

- discussion 负责规划，不进正文与 Canon
- writing 负责产出 candidate，继续走现有 adopt 主路径
- 两者通过结构化 brief 桥接，而不是直接共享原始聊天历史
