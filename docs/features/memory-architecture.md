# 记忆架构（Memory Architecture）

> 状态：**设计已定稿（MVP 范围）**  
> 最后更新：2026-05-25（第三轮决策）

本文档记录 LNAgent（Light Novel Agent）在**短篇、对话式续写**场景下的记忆系统设计共识，作为后续实现的依据。

---

## 1. 设计目标

| 优先级 | 目标 |
|--------|------|
| P0 | **绝对不出设定 bug**——角色能力、世界观规则、人物状态等与已确认设定一致 |
| P0 | 支持**对话式续写**：作者给出启发 / 大致走向，LLM 扩展丰富 |
| P1 | 短篇优先：**场景级**归档，而非卷 / 章级复杂结构 |
| P1 | 单次运行仅处理**一本小说** |
| P2 | LangChain 生态作为**扩展项**，核心记忆逻辑与框架解耦，避免日后大改 |

---

## 2. 核心原则

### 2.1 记忆两步走

```
┌─────────────────────────────────────────────────────────────┐
│  短期记忆：全自动归档                                         │
│  - 当前场景内对话、走向指示、生成正文                             │
│  - 场景切换时自动沉淀为「场景快照」                               │
├─────────────────────────────────────────────────────────────┤
│  长期记忆：作者确认后写入                                       │
│  - 全书 / 篇章梗概、场景摘要、伏笔状态、叙事层更新                  │
│  - 结构化 Story Bible 中的叙事类条目                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 即时 Canon 例外（能力 / 状态）

**能力变化、角色状态等「事实型」设定必须即刻生效**，不能等作者确认后才进上下文——否则会出现「刚获得能力，下一段就忘记」的问题。

因此长期记忆拆为两层：

| 层级 | 名称 | 写入方式 | 进入 Prompt |
|------|------|----------|-------------|
| L1 | **Hot Canon（即时 Canon）** | 抽取后作者 **y/n 确认**写入 | 确认后立即 |
| L2 | **Cold Archive（冷归档）** | 场景结束后生成提案，作者提交**完整文本**后写入 | 确认后 |

Hot Canon 示例：新能力、伤势、持有物（inventory）、关系变化、地点（location）。  
Cold Archive 示例：场景摘要、梗概 rollup、伏笔开闭、叙事性补充。

> **一致性保障**：记忆存储对用户**无感知**（JSON 文件，作者不直接编辑）；通过 CLI 查看（`/canon`）与命令纠错（`/undo` 等）。Hot 与 Cold 冲突时**以 Hot 为准**（Hot 反映最新事实，Cold 可能滞后于上一场景）。

### 2.3 正文与记忆优先级

| 冲突类型 | 裁决 |
|----------|------|
| Hot Canon vs Cold Archive 提案 | **以 Hot 为准**；Cold review 时作者应据此修改摘要文本 |
| 已采纳正文 vs Hot Canon | **以正文为准**，触发 reconcile 更新 Hot |
| 候选正文（未 `/adopt`） | **不进入**任何记忆层 |

---

## 3. 短期记忆

### 3.1 范围（已确认）

短期记忆**以「当前场景」为主**，不再单独维护「近几章摘要 + 指令列表」：

- **当前场景**：本场景内全部内容——作者的方向指示、多轮对话、已采纳正文。
- **前文衔接（可选 enrich）**：为保证连贯性，在场景开头附加**少量**前文材料（见 §3.3）。

近几章摘要、历史指令等叙事信息，在场景切换后沉淀到 Cold Archive；能力 / 状态类事实进入 Hot Canon。短期层不重复维护平行结构。

### 3.2 场景（Scene）定义

一个**场景**是短篇中一段连续的叙事单元，通常具备：

- 相对统一的时空（地点、时间）
- 相对统一的 POV（视点人物）
- 一条完整的戏剧节拍（beat）或节拍组

场景边界由**作者显式命令**触发（见 §5.1）；Agent 可建议切换时机，**不代为执行**。

### 3.3 前文 enrich 策略（已确认）

进入新场景时，短期上下文 = **当前场景内容** + **前文衔接块**：

| 块 | 内容 | 目的 |
|----|------|------|
| 当前场景 | 本场景对话 + 已采纳正文 | 主上下文 |
| 前文衔接 | **上一场景末尾原文（tail，约 500 字）** | 保证衔接，控制 token |

短篇体量下，**不默认加载更早的多场景摘要**；更早内容通过长期记忆（Hot Canon + 已确认 Cold Archive）注入。

### 3.4 场景切换时的自动归档

作者触发「结束当前场景 / 进入新场景」时，系统自动：

1. 将当前场景打包为**场景快照**（对话 + 正文 + 场景元数据）。
2. 从快照中**抽取 Hot Canon 更新**，经作者 **y/n 确认**后写入。
3. 生成 **Cold Archive 提案**（场景摘要、伏笔变更等），经 **完整文本 review** 后写入。
4. 清空短期「当前场景」缓冲区，新场景可携带 §3.3 的前文衔接块。

---

## 4. 长期记忆

### 4.1 结构：Story Bible + 分层摘要

长期记忆采用**结构化 Story Bible**（**JSON 存储，不对作者暴露文件编辑**），与**叙事摘要**配合：

```
projects/<novel_id>/
├── meta.json                # 世界观 / 文风等（开书时作者必填）
├── manuscript/
│   └── scene_001.md         # 已采纳正文
└── memory/
    ├── canon.json           # Hot Canon
    ├── synopsis.json        # 已确认 Cold Archive（见下）
    └── pending/             # 待确认的 Cold 提案（可选，MVP 可仅内存）
```

**`synopsis.json`（Phase 3 已确认）**：

```json
{
  "global": "全书梗概（每次 Cold accept 后 LLM 自动 rollup 更新）",
  "scenes": [
    {
      "id": "scene_001",
      "location": "场景地点（LLM 提案为准）",
      "time": "大致时间（LLM 提案为准）",
      "summary": "本场景叙事摘要（作者 review 可改全文）",
      "key_points": ["关键信息条目"]
    }
  ]
}
```

- 作者 Cold review **仅编辑 `summary` 全文**；`location`、`time` 以 Cold 提案 LLM 输出为准落盘。
- `/r` 拒绝时不写入该场景条目；**仍切换场景**。

**Hot Canon 角色字段（MVP）**：

| 字段 | 说明 |
|------|------|
| `name` | 角色名 |
| `abilities[]` | 能力列表 |
| `status` | 当前状态（伤势、情绪等） |
| `relationships` | 与其他角色关系 |
| `inventory[]` | 持有物 |
| `location` | 当前所在位置 |

另含 `world.rules[]`、`plot_threads[]`（伏笔）。

### 4.2 字段原则

- **事实型**（能力、规则、状态）→ `canon/`，变更走 Hot Canon 流程。
- **叙事型**（发生了什么、情绪弧线）→ `synopsis/`，变更走 Cold Archive 确认流程。
- 未确认的场景摘要**不得**作为设定依据注入 Prompt（避免草稿污染 Canon）。

### 4.3 Prompt 注入顺序（已确认，Phase 3）

**同场景续写**（未 `/sc`）：

1. System：`meta.json`（世界观、文风等）
2. Hot Canon：`canon.json`
3. 短期：当前场景已采纳正文 + 对话历史
4. User：本轮作者输入

**进入新场景后**（`/sc` 完成，短篇 MVP）：

1. System：`meta.json`
2. Cold：`synopsis.global` + **上一场景刚归档的** `scenes[]` 条目（summary、location、time、key_points；即「当前 scene cold」）
3. Hot Canon：`canon.json`
4. 短期：上一场景 manuscript **tail（约 500 字，按字符）** + 新场景对话（初始为空）
5. User：本轮作者输入

- **不**注入更早场景的 per-scene 条目；更早叙事依赖 `global` + Hot。
- Cold **`/r` 拒绝**时无新场景条目：新场景 Prompt = meta + global（未 rollup）+ Hot + tail。

按需加载相关角色 / 伏笔，**禁止**在未控 token 的情况下整本 bible 全量塞入。

### 4.4 上下文 token 预算

> **TODO**：各块（Hot Canon / 已确认摘要 / 当前场景 / tail）上限待实现阶段根据**模型上下文窗口**与实测效果确定。

---

## 5. 创作模式与 CLI 命令

### 5.1 对话式续写

- 作者：启发、约束、大致走向（可短、可模糊）。
- LLM：在 Canon + 当前场景约束下扩展、丰富、具体化。
- 输出：候选正文 / 对话回复；**仅经 `/adopt` 采纳**的内容写入当前场景正文区。
- **历史候选**：作者让 LLM 重写时，旧候选**直接丢弃**；仅最后一轮输出可被 `/adopt`。
- **纯讨论轮次（已确认）**：作者可提问、讨论设定合理性等，**不单独设模式**；是否写入正文仍仅由显式 `/a` 决定。

短期记忆中的「指令」不作为独立层维护，而是**当前场景对话历史的一部分**。

未采纳的候选正文**不进入任何记忆层**。退出后再进**不恢复**未 adopt 的候选（见 §7）。

### 5.2 开书与场景前置（已确认）

| 阶段 | 说明 |
|------|------|
| **初始化** | 作者**必须**提供世界观 / meta（书名、风格、世界规则等）；Hot Canon **可为空** |
| **首个叙事单元** | meta 就绪后进入 scene_001；**不允许空场景** |
| **`/scene` 前置** | 当前场景须至少有 **一次成功 `/adopt`**，否则拒绝切换 |

启动方式：`python main.py --project <novel_id>`；项目不存在则进入交互式创建并采集 meta。

### 5.3 显式命令与快捷别名（已确认）

作者通过 CLI 命令控制记忆写入，**不做 Agent 意图识别**。命令均提供**短别名**：

| 命令 | 别名 | 作用 |
|------|------|------|
| `/adopt` | `/a` | 进入采纳流（见 §5.5） |
| `/scene` | `/sc` | 结束当前场景并归档（见 §5.4） |
| `/undo` | `/u` | 撤销本场景最后一次 `/adopt`（正文 + Hot **一并回滚**） |
| `/fix` | `/f` | 设定纠错：修改 Hot Canon（见 §5.6） |
| `/canon` | `/c` | 查看当前 Hot Canon 摘要 |
| `/help` | `/h` | 显示命令帮助 |
| `quit` / `exit` / `q` | — | 退出 |

**场景切换决策权**：

- Agent 通过**启发式**判断 beat 是否完成，在回复中**建议**切换（如提示 `/sc`）。
- **仅作者输入 `/scene`（或 `/sc`）时**才执行归档；Agent 不得自动调用。
- 启发式规则在实现阶段细化（如：已 adopt 段落数、Agent 回复中的完成信号等）。

### 5.4 场景切换与 Cold Archive 确认流

作者输入 `/scene` 后：

1. 校验当前场景至少有一次 `/adopt`（否则拒绝）。
2. **Hot reconcile**：**逐条**处理 `adopt_stack` 中 `accepted_canon=false` 的记录，用该条 adopt 文本抽取 patch，y/n 确认后 merge 进 `canon.json`。
3. 生成 **Cold Archive 提案**（`summary`、`key_points[]`、`location`、`time`；LLM 从已采纳正文抽取）。
4. **Review 交互（已确认）**——与 `/adopt` 对齐：
   - 展示提案（含 location、time、summary、key_points）；
   - 作者多行编辑 **`summary` 全文**，单独一行 `EOF` 结束；仅 `EOF` = 原样采纳提案 summary；
   - `location`、`time` **不以作者编辑为准**，以 LLM 提案落盘；
   - 输入 `/reject`（或 `/r`）**丢弃提案且不写入**该场景 synopsis；**仍执行步骤 5–6**。
5. Cold **accept** 后：写入 `synopsis.scenes[]`；再调 LLM **自动 rollup 更新 `synopsis.global`**。
6. 清空当前场景缓冲；递增 `scene_id`；新场景 Prompt 见 §4.3；携带 §3.3 的前文 tail。

Hot 与 Cold 提案冲突时，**以 Hot 为准**；作者 editing Cold summary 时应自行对齐 Hot。

### 5.5 `/adopt` 采纳流（已确认）

1. 展示上一轮 LLM **候选全文**。
2. 作者输入**修改后的完整文本**（可原样采纳，也可编辑任意部分后再提交）；MVP CLI 使用多行输入，以单独一行 `EOF` 结束提交。
3. 将最终文本追加到当前场景正文区。
4. LLM **抽取 Hot Canon 变更**，以 diff 形式展示。
5. 作者 **y / n** 确认是否写入 Hot Canon。
6. 确认后立即进入后续 Prompt；拒绝则仅保留正文，不更新 Hot。
7. 系统记录本次 adopt 的回滚信息：adopt 文本、`canon_before` 快照、`canon_patch`、`accepted_canon`。

| 时机 | Hot Canon 行为 |
|------|----------------|
| `/adopt` 确认后 | 抽取 + **y/n 确认**写入 |
| `/scene` 时 | 对 `adopt_stack` 中 **`accepted_canon=false`** 的条目**逐条** reconcile（变更同样 y/n 确认） |
| 每轮生成后 | **不抽取** |
| 未 `/adopt` 的候选 | **不抽取、不写入** |

**Phase 2 Hot patch 与合并规则**：

- Hot 抽取输出 JSON patch，覆盖 `characters`、`world.rules[]`、`plot_threads[]`。
- 角色按 `name` 合并；数组字段追加去重；`status`、`location` 等标量字段以后来的 patch 覆盖。
- `plot_threads` 有 `id` 时按 `id` 合并，否则追加。
- Hot 变更被拒绝时不记录 suppression；后续 `/scene` batch reconcile 如果再次抽到，可以再次询问。
- JSON patch 解析失败时提示重试，不 silent fail。

### 5.6 `/undo` 与 `/fix`（已确认）

**`/undo`（`/u`）**——撤销本场景**最后一次成功 adopt**：

1. 从当前场景正文移除该次 adopt 追加的文本。
2. **Hot Canon 回滚**至该次 adopt 之前的状态（与正文一并撤销）。
3. 若无 adopt 可撤，提示失败。

**`/fix`（`/f`）**——设定纠错，**只改 Hot Canon，不动正文**：

1. 作者输入纠错意图（如「主角并未获得暗属性能力」）：**多行 + 单独一行 `EOF` 结束**（同 `/a`、Cold review）；纠错意图不可为空。
2. LLM 按纠错意图生成 Hot Canon **JSON patch**（与 adopt **同 schema**：`characters`、`world.rules[]`、`plot_threads[]`；**同 merge 规则**）。
3. 展示变更 diff；作者 **y / n** 确认写入。空 patch 提示「无变更」；JSON 解析失败提示重试。**不写入 `adopt_stack`**。

口头发现设定错误时走 **`/fix`**，而非 `/undo`（除非要连该段正文一起撤销）。

**`/undo` 补充约定（Phase 4）**：

- 每次撤销 **栈顶** 一条 adopt；栈非空时可**连续** `/u`。
- **`accepted_canon=false` 的 adopt 也可撤**（正文已写入即视为成功 adopt；Hot 恢复为该条 `canon_before`）。
- **不修改** `messages` 对话历史；仅回滚 `adopted_prose`、`manuscript` 与 Hot Canon。
- 仅**当前场景**有效；`/scene` 切换后 `adopt_stack` 已清空。

---

## 6. 范围与约束

| 项 | 决定 |
|----|------|
| 作品体量 | 先考虑**短篇** |
| 归档粒度 | **场景** |
| 能力 / 状态 | **即刻生效**（Hot Canon） |
| 并发项目 | **一次一本小说** |
| 设定一致性 | **P0**；Hot 变更 y/n 确认；`/undo` 纠错 |
| 存储格式 | **JSON**；记忆对用户**无感知**，不直接编辑文件 |
| 向量 RAG | **MVP 不实现**；架构预留扩展点（见 §6.1） |

### 6.1 扩展预留（避免大伤筋骨）

核心记忆通过**抽象接口**与 LangChain / 存储实现解耦，便于后续接入 LangGraph、LangMem 等，而无需重写业务逻辑：

| 接口（概念） | 职责 |
|--------------|------|
| `MemoryStore` | 读写 Hot Canon、Cold Archive（文件 / DB 可替换） |
| `ShortTermBuffer` | 当前场景 + 前文衔接 |
| `MemoryUpdater` | 场景归档、抽取、提案生成 |
| `PromptContextBuilder` | 按 §4.3 组装上下文 |
| `ChatModelGateway` | 对 `BaseChatModel` 的薄封装（现有 `create_chat_model`） |

向量 RAG 预留为可选的 `MemoryRetriever` 接口，MVP 提供空实现或 NoOp。

LangChain 仅作为 **LLM 调用层** 与可选 **Agent 运行时**；记忆域模型与持久化格式由 LNAgent 自有 schema 定义。

---

## 7. 项目布局

```
projects/<novel_id>/
├── meta.json                # 世界观 / 文风（开书必填，JSON）
├── manuscript/
│   └── scene_001.md         # 已采纳正文
├── memory/
│   ├── canon.json           # Hot Canon
│   ├── synopsis.json        # 已确认 Cold Archive
│   └── pending/             # 待确认提案（JSON）
└── session.json             # 当前场景进度（已 adopt 正文 + 对话；不含未 adopt 候选）
```

记忆文件由系统读写；作者通过 CLI（`/c`、`/a`、`/sc` 等）交互，**不直接编辑 JSON**。

**断点策略（已确认）**：退出后再进**不恢复**未 `/adopt` 的 LLM 候选；已 adopt 正文随场景持久化。MVP 不做候选恢复。`session.json` 采用 **checkpoint_only**（Phase 5.5）：`send()` 不写盘，仅在 adopt / 命令 / 正常退出时落盘；自上次检查点以来的纯讨论对话在异常退出时可能丢失。

---

## 8. 决策记录

### 8.1 已确认

| # | 议题 | 决定 |
|---|------|------|
| T1 | 场景切换如何触发？ | **作者显式 `/scene`（`/sc`）**；Agent 启发式建议，不代为执行 |
| T2 | 前文衔接块用什么？ | **上一场景末尾原文 tail（约 500 字）** |
| T3 | Hot Canon 抽取时机？ | **仅 `/adopt` 后** + **`/scene` 时批量 reconcile** |
| T4 | Cold Archive 如何确认？ | 展示全文 → 作者提交**修改后的完整文本**；`/reject`（`/r`）丢弃 |
| T5 | 候选正文未采纳是否进记忆？ | **否**；须 `/adopt`（`/a`） |
| T6 | Hot 与 Cold 提案冲突？ | **以 Hot 为准** |
| T7 | 存储格式 | **JSON**；记忆对用户无感知，不直接编辑文件 |
| T8 | 上下文 token 预算 | **TODO**；实现时按模型上下文窗口与实测确定 |
| T9 | 初始 Canon 来源 | 开书时作者**必填 meta**；Hot Canon **可为空** |
| C1 | `/adopt` 采纳范围 | 展示候选全文，作者可**编辑后提交完整文本** |
| X1 | `/adopt` 多行输入 | MVP CLI 使用多行输入，单独一行 `EOF` 结束提交 |
| C2 | 历史候选 | **丢弃**；仅最后一轮可 adopt |
| C3 | Cold review 交互 | 同 C1：**完整文本 in/out**，便于后续接前端 |
| C4 | 空场景 | **不允许**；`/scene` 须至少一次 `/adopt` |
| C5 | 扩展命令 | `/undo`（`/u`）、`/canon`（`/c`）、`/help`（`/h`）+ 短别名 |
| C6 | 场景切换建议 | **启发式**（实现阶段细化规则） |
| L3 | Hot 抽取确认 | 展示 diff，作者 **y/n** |
| L6 | Hot patch schema | Phase 2 输出 JSON patch，覆盖 `characters`、`world.rules[]`、`plot_threads[]`；解析失败提示重试 |
| S1 | Hot Canon 字段 | 含 **inventory**、**location** |
| P1 | 项目启动 | `python main.py --project <novel_id>` |
| E1 | 口头纠错 | 走 **`/fix`（`/f`）** 改 Hot Canon |
| E2 | `/undo` 范围 | 正文 + Hot **一并回滚**；**不动** `messages` |
| E4 | `/undo` 可撤对象 | 栈顶 pop；`accepted_canon=false` 也可撤；可连续 `/u`；仅当前场景 |
| F1 | `/fix` 输入 | 多行 + `EOF`（同 `/a`）；纠错意图不可为空 |
| F2 | `/fix` patch | 与 adopt **同 JSON patch schema + merge**；不改正文、不写 `adopt_stack` |
| L5 | 纯讨论轮次 | **允许**；不单独设模式，是否 adopt 仍靠显式 `/a` |
| P2 | 断点恢复 | **不恢复**未 adopt 候选；退出即丢弃 |
| S5 | 全书梗概 rollup | **每次 Cold accept 后** LLM 自动更新 `synopsis.global` |
| S6 | 场景元数据 | `/sc` Cold 提案时 LLM 抽取 `location`、`time`；作者仅改 `summary`，元数据以提案为准 |
| L6-C | Cold 提案 schema | `synopsis.json`：`global` + `scenes[]{id,location,time,summary,key_points[]}` |
| X3 | Cold review 空输入 | 多行 + `EOF`；仅 `EOF` = 采纳提案 summary（同 `/a`） |
| P3-SC | `/r` 后是否切场景 | **仍切换**；不写该场景 synopsis |
| P3-PR | 新场景 Prompt | meta + **global** + **上一场景 Cold 条目** + Hot + tail |

### 8.2 仍待确认

完整列表及新增讨论项见 **[open-questions.md](./open-questions.md)**。

| # | 问题 | 状态 |
|---|------|------|
| L4 | meta 哪些字段固定注入 System Prompt？ | 🔴 待讨论 |
| L1 | adopt / scene 各几次 LLM 调用？ | 🟡 实现时优化 |
| T8 | 上下文 token 预算 | 🟡 依模型窗口 |
| P3 | MVP 是否合并导出 manuscript？ | 🔴 待讨论 |

---

## 9. 与现有代码的关系

当前 `lnagent/chat.py` 中：

- `LLMChatClient`：单轮，无记忆（将被会话层替代或包装）。
- `ChatSession`（预留）：应对齐为 `NovelSession`，组合 `ShortTermBuffer` + `MemoryStore` + `PromptContextBuilder`。

**实现计划**见 [memory-mvp-plan.md](./memory-mvp-plan.md)（Phase 0–4 分阶段交付）。

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初稿：短期场景化、长期 Story Bible、Hot/Cold 分层、扩展接口 |
| 2026-05-25 | 确认 T1–T5：`/adopt`、`/scene` 显式命令；Agent 仅建议场景切换 |
| 2026-05-25 | 第二轮：T6–T9、C1–C6、L3、S1、P1；JSON 无感知存储；y/n Hot 确认；CLI 短别名 |
| 2026-05-25 | 第三轮：E1 `/fix`、E2 undo 连带 Hot、L5 纯讨论、P2 不恢复候选 |
| 2026-05-25 | 待讨论项拆至 open-questions.md；新增 memory-mvp-plan.md |
| 2026-05-25 | 补充 Phase 2：`/adopt` EOF 输入、Hot patch schema、merge 规则、拒绝策略与 adopt 栈 |
| 2026-05-26 | Phase 4：`/f` 多行+EOF、同 schema patch；`/u` 栈顶回滚、不动 messages、仅当前场景 |
| 2026-05-25 | Phase 3：`synopsis.json` schema、global rollup、Prompt 注入、逐条 reconcile、`/r` 仍切场景 |
