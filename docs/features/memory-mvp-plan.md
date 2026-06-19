# 记忆功能 MVP 实现计划

> 目标：实现**最最基本的记忆能力**，使 LNAgent 从单轮 CLI 升级为「带项目、带场景、带 Canon 的多轮续写」；Phase 5 起扩展**中篇可用**与工作流。  
> 设计依据：[memory-architecture.md](./memory-architecture.md)  
> 待决事项：[open-questions.md](./open-questions.md)（实现中遇到 🔴 项再确认）

---

## 1. MVP 范围定义

### 1.1 本计划要交付什么

| 能力 | 说明 |
|------|------|
| 项目与 meta | `--project` 开书 / 打开；`meta.json` 持久化 |
| 多轮短期记忆 | 当前场景内对话 + 已 adopt 正文；退出后再进可恢复**已 adopt 部分** |
| Prompt 上下文组装 | meta + Hot Canon（若有）+ 当前场景历史 → LLM |
| `/a` adopt | 编辑候选全文 → 追加正文 → Hot diff → **y/n** |
| `/c` canon | 打印 Hot Canon 摘要 |
| `/sc` scene | 场景切换、Cold 摘要 review、`synopsis.json`、新场景 tail 衔接 |
| 基础持久化 | `canon.json`、`synopsis.json`、`session.json`、`manuscript/scene_XXX.md` |

### 1.2 本计划**暂不**实现（后续迭代）

| 能力 | 原因 |
|------|------|
| 向量 RAG | 明确不做于 MVP；见 **Phase 7+** |
| 文风 / 叙事模板 preset | Phase 6 非目标；见路线图 |
| `--template` / 运行时改 meta | Phase 6 非目标 |
| Hot Canon schema 演进（S2–S4） | 见 **Phase 7+** |

---

## 2. 目标架构（MVP 切片）

```
main.py (--project)
    └── NovelSession
            ├── MemoryStore          # canon.json, meta.json 读写
            ├── ShortTermBuffer      # messages + adopted_prose + last_candidate
            ├── PromptContextBuilder # 组装 System + 历史 + user
            └── LLM (现有 create_chat_model)
```

**文件布局**（单场景阶段可先固定 `scene_001`）：

```
projects/<novel_id>/
├── meta.json
├── manuscript/
│   └── scene_001.md
├── memory/
│   ├── canon.json          # Hot Canon
│   └── synopsis.json       # Cold Archive（global + scenes[]）
└── session.json            # 对话 + 已 adopt 正文 + scene_id
```

---

## 3. 分阶段任务

**进度标记规则**：

- `[ ]` 未开始
- `[x]` 已完成并通过对应验收
- 如果任务已部分完成，保持 `[ ]`，在任务后追加简短备注（如：`（进行中：store 已完成，测试未补）`）
- 每个 Phase 完成后，再勾选该 Phase 的验收项

### Phase 0：骨架与数据模型（无 LLM 行为变更）

- [x] **0.1 数据模型**：定义 dataclass / TypedDict：`NovelMeta`、`HotCanon`、`SceneSession`  
  产出：`lnagent/memory/models.py`
- [x] **0.2 JSON 存储**：实现 `JsonMemoryStore`：load/save meta、canon、session  
  产出：`lnagent/memory/store.py`
- [x] **0.3 存储协议**：抽象 `MemoryStore` Protocol  
  产出：`lnagent/memory/protocols.py`
- [x] **0.4 配置扩展**：`Settings` 增加 `project_id`、`projects_dir`  
  产出：`lnagent/config.py`
- [x] **0.5 项目入口**：`main.py` 解析 `--project`；不存在则交互创建 meta  
  产出：`main.py`

**验收**：

- [x] 运行 `python main.py --project test` 可创建目录与空 `canon.json` / `meta.json`。

---

### Phase 1：多轮会话 + 上下文注入

- [x] **1.1 短期缓冲**：`ShortTermBuffer` 追加 user/assistant 消息、adopted_prose、last_candidate  
  产出：`lnagent/memory/short_term.py`
- [x] **1.2 Prompt 组装**：`PromptContextBuilder.build()` 按 architecture §4.3 简化版组装 messages  
  产出：`lnagent/memory/prompt.py`
- [x] **1.3 会话发送**：`NovelSession.send(user_input)` 执行 build → invoke → 存 candidate → 持久化 session  
  产出：`lnagent/session.py`
- [x] **1.4 CLI 接入会话**：替换 `main.py` 中 `LLMChatClient` 为 `NovelSession` 循环  
  产出：`main.py`
- [x] **1.5 断点恢复**：退出时 save session；再进 load session（**不**恢复 candidate，符合 P2）  
  产出：store + session

**验收**：

- [x] 同一 project 内多轮对话，LLM 能引用上一轮内容。
- [x] 重启后已 adopt 正文与对话历史仍在。

**open-questions 暂按默认**：

- L4：meta 注入 `title`、`world.rules`、`style`（最初开书必填的是 title / style；世界观现走 `world` / worldbook 路径）
- P5：Phase 1 暂按每轮 `send` 写盘；**Phase 5.5** 改为 checkpoint_only（见 Phase 5.5）

---

### Phase 2：`/a` adopt 与 Hot Canon（核心记忆）

- [x] **2.1 命令路由**：CLI 支持 `/a`、`/c`、`/h` 及别名；非命令走 `send()`  
  产出：`lnagent/cli/commands.py`
- [x] **2.2 adopt 输入流**：`/a` 展示 `last_candidate`，读入用户修改后的完整文本；MVP 使用多行输入，单独一行 `EOF` 结束  
  产出：`lnagent/cli/adopt.py`
- [x] **2.3 正文采纳**：adopt 后追加 `manuscript/scene_001.md` 与 `buffer.adopted_prose`  
  产出：session + store
- [x] **2.4 Hot 抽取**：`CanonExtractor` 让 LLM 从 adopt 文本抽取 Hot 变更，并展示 diff  
  产出：`lnagent/memory/canon_extractor.py`
- [x] **2.5 Canon 合并**：用户 y/n 确认；确认后 merge 进 `canon.json`，拒绝则只保留正文、不更新 Canon  
  产出：store
- [x] **2.6 adopt 栈**：adopt 时保存回滚所需信息，为 Phase 4 `/u` 预留  
  产出：session 内 `adopt_stack[]`

**验收**：

- [x] 对话生成候选 → `/a` 采纳 → `/c` 可见新能力/状态。
- [x] Hot 变更 n 拒绝时，正文已写入但 canon 不变。

**Phase 2 已确认细节**：

- Hot 抽取覆盖 `characters`、`world.rules[]`、`plot_threads[]`。
- Hot patch merge：角色按 `name` 合并；数组字段追加去重；`status`、`location` 等标量字段以后来的 patch 覆盖；`plot_threads` 有 `id` 时按 `id` 合并，否则追加。
- Hot 变更被拒绝时不记录 suppression；后续 `/sc` batch reconcile 如果再次抽到，可以再次询问。
- `adopt_stack[]` 至少记录 adopt 文本、`canon_before` 快照、`canon_patch`、`accepted_canon`。
- 简版 Hot 抽取 prompt 要求模型输出 JSON patch；解析失败则提示重试，不 silent fail。

---

### Phase 3：场景切换与 Cold Archive（记忆闭环）

- [x] **3.1 场景命令**：`/sc` 校验至少一次 adopt；归档 scene 快照  
  产出：`lnagent/cli/scene.py`
- [x] **3.2 Cold 提案**：生成 Cold 提案 → 完整文本 review → `/r` 或提交写入 `synopsis.json`  
  产出：`lnagent/memory/cold_archive.py`
- [x] **3.3 新场景启动**：创建 `scene_002`，Prompt 注入 meta + global + 上一场景 Cold + Hot + tail  
  产出：prompt + short_term + store（`synopsis.json`）
- [x] **3.4 Hot reconcile**：`/sc` 时逐条 reconcile `adopt_stack` 中 `accepted_canon=false`（y/n）  
  产出：canon_extractor + session
- [x] **3.5 切换建议**：启发式在回复末尾附加「可考虑 /sc」提示（简版 C6）  
  产出：prompt 或 post-process

**验收**：

- [x] 完成 scene_001 → `/sc` → 确认摘要 → scene_002 续写带 **meta + global + 上一场景 Cold + Hot + tail**（单元测试覆盖；真实 API 建议手工复验）。

**Phase 3 已确认细节**：

- **`synopsis.json` 分字段存储**：顶层 `global`（全书梗概）+ `scenes[]` 按场景条目；每条含 `id`、`location`、`time`、`summary`、`key_points[]`。
- **S5**：每次 Cold **accept 并写入** `scenes[]` 后，再调 LLM **自动 rollup 更新 `global`**。
- **场景元数据**：`location`、`time`（大致即可）由 Cold 提案 LLM 从本场景已采纳正文抽取；作者 Cold review **仅可改 `summary` 全文**，`location` / `time` **以 LLM 提案为准落盘**。
- **Cold review 交互**：与 `/a` 相同——多行输入，单独一行 `EOF` 结束；仅 `EOF`（无正文）= 原样采纳提案 `summary`。
- **`/r` 拒绝 Cold**：不写入该场景 synopsis 条目；**仍切换场景**（递增 `scene_id`、清空短期缓冲、带 tail）。
- **Hot reconcile（`/sc`）**：**逐条**处理 `adopt_stack` 中 `accepted_canon=false` 的记录，用该条 `text` 抽取 patch 并 y/n；非对全场景正文单次 bulk 抽取。
- **新场景 Prompt 注入**（进入 `scene_N+1` 时）：`meta.json` + `synopsis.global` + **上一场景刚归档的** `scenes[]` 条目（即「当前 scene cold」）+ `canon.json` + 上一场景 manuscript **tail（约 500 字，按字符）**；**不**注入更早场景的 per-scene 条目。
- **`/r` 后新场景**：无新 Cold 条目时 Prompt = meta + global（未更新）+ Hot + tail。
- **C6（MVP）**：启发式规则实现阶段细化；可先 system 提示或简单 adopt 次数阈值。

---

### Phase 4：纠错命令

- [x] **4.1 Undo**：`/u` pop adopt_stack，回滚正文 + Hot  
  产出：`lnagent/cli/undo.py`
- [x] **4.2 Fix**：`/f` 读纠错意图 → Hot diff → y/n  
  产出：`lnagent/cli/fix.py`

**验收**：

- [x] adopt 后 `/u` 恢复正文与 Hot Canon。
- [x] `/f` 修正错误能力（y/n 后写入 `canon.json`）。

**Phase 4 已确认细节**：

- **`/f` 输入（X2）**：与 `/a`、Cold review 相同——多行 + 单独一行 `EOF` 结束；**纠错意图不可为空**（仅 `EOF` 无正文则提示失败，无默认意图）。
- **`/f` LLM 语义**：与 adopt **相同 JSON patch schema**（`characters`、`world.rules[]`、`plot_threads[]`）及 **相同 merge 规则**；prompt 改为「根据纠错意图修正当前 Hot Canon」→ 展示 diff → y/n；**不改正文、不写入 `adopt_stack`**。
- **`/u` undo 范围（E2）**：pop `adopt_stack` 栈顶；回滚 `adopted_prose` + `manuscript/scene_XXX.md` + Hot Canon（恢复该条 `canon_before`）；**不修改 `messages`**。
- **`/u` 可撤对象**：`accepted_canon=false` 的 adopt **也可撤**（正文已写入即算「成功 adopt」）；允许多次连续 `/u`（栈非空即可 pop）。
- **`/u` 场景范围**：仅**当前场景**；`/sc` 切换后 `adopt_stack` 已清空，不可跨场景 undo。
- **manuscript 回滚**：pop 栈顶后按剩余 `adopt_stack` 顺序重建正文（与 `append_prose` 对称）；非单条字符串尾部剥离。
- **空 patch / 解析失败**：`/f` 与 adopt 一致——空 patch 提示「无变更」不写 canon；JSON 解析失败提示重试，不 silent fail。

---

### Phase 5：中篇可用（方向 A）

> **目标**：记忆 MVP（Phase 0–4）完成后，使多场景、长对话仍稳定可用——优先解决 context 超窗，再优化交互提示。  
> **不在本 Phase**：合并导出（P3）、meta 模板（P6/L4）、向量 RAG（R1）——见 Phase 6 / Phase 7+。

**任务优先级**：

| 优先级 | 任务 | open-questions |
|--------|------|----------------|
| P0 | `/config` 项目级实时配置 | T8, C6 |
| P0 | T8 Prompt 预算裁剪 | T8 |
| P1 | C6 场景切换启发式升级 | C6 |
| P1 | L7 讨论 vs 写作边界 | L7 |
| P2 | P5 session 持久化粒度（可选） | P5 |
| P2 | X4 命令解析规范化（可选） | X4 |

- [x] **5.0 `/config` 项目配置**：当前 project 内查看、修改、重置 Phase 5 配置；立即生效并持久化  
  产出：`lnagent/cli/config.py`、`projects/<id>/config.json`
- [x] **5.1 T8 预算配置**：项目配置可配各块字符上限与总预算  
  产出：`lnagent/config.py`、`lnagent/memory/context_budget.py`（或同等模块）
- [x] **5.2 T8 Prompt 裁剪**：`PromptContextBuilder` 超限时按优先级裁剪各块  
  产出：`lnagent/memory/prompt.py` + 单测
- [x] **5.3 C6 切换建议**：抽出 `SceneSwitchAdvisor`，替换 `main.py` 中 `adopt_stack >= 2` 简版规则  
  产出：`lnagent/memory/scene_switch.py`（或 `lnagent/cli/scene_hint.py`）
- [x] **5.4 L7 System Prompt**：明确「讨论输出非正文，勿直接 adopt」  
  产出：`lnagent/memory/prompt.py`
- [x] **5.5 P5 持久化（checkpoint_only）**：`send()` 不写盘；仅在 adopt / undo / fix / reconcile / `/sc` / 退出时写 `session.json`  
  产出：`lnagent/session.py`
- [x] **5.6 裁剪可感知（可选）**：超限时向作者提示已裁剪块与约略字数  
  产出：`NovelSession.send()` 或 CLI 层

**验收**：

- [x] 长对话（如 10+ 轮）或多场景项目下 `send` 仍稳定；超预算时有确定行为（裁剪或明确报错），不 silent 丢块。（手工 spot-check 已通过，2026-05-29）
- [x] 单元测试覆盖：各块独立超限、总预算超限、裁剪顺序、tail/Hot 保留优先级。
- [x] `/sc` 建议在 beat 完成附近出现；正常续写时不过度打扰（规则可配置或文档化阈值）。
- [x] System prompt 含讨论/写作边界说明；纯讨论轮次输出偏分析而非小说段落（单测覆盖边界文案；语气仍建议手工 spot-check）。

**Phase 5 已确认细节（方向 A）**：

- **T8 计量单位**：**字符**（与 tail 500 字一致）；MVP 不引入 tokenizer 依赖。
- **T8 默认预算**：总预算 `300000` 字符；分块默认值为 `messages=80000`、`adopted_prose=120000`、`hot_canon=60000`、`global=30000`、`prior_scene_cold=12000`、`scene_tail=2000`、`meta=10000`。
- **T8 裁剪对象**（各块可独立上限 + 总预算）：Hot Canon、`synopsis.global`、上一场景 Cold、`scene_tail`、当前场景 `messages`、当前场景 `adopted_prose`。
- **T8 裁剪顺序**（总预算仍超则按序裁到达标）：**最旧 `messages` → `adopted_prose` 头部 → 压缩 `global` 文本 → Hot Canon 角色/数组字段**；`meta`（title/style/world.rules）、本轮 `user_input`、**tail 优先保留**（tail 可先截断至上限，但不整段丢弃除非配置允许）。
- **T8 配置入口**：`/config` 修改当前项目的 `config.json`，立即生效并持久化；启动级 `Settings` 仍只负责 API/model/project 路径。
- **T8 作者感知**：发生裁剪时 **CLI 提示**（如「已裁剪历史对话约 N 字」）；不 silent fail。
- **C6 规则（MVP 组合，OR）**：保留「`adopt_stack` 次数 ≥ 2」；增加「连续 M 轮无 `/a`」（M 默认 3，通过 `/config` 可调）；暂不做完成/收束信号词和冷却；仍 **仅建议**，不自动 `/sc`。
- **C6 模块边界**：逻辑独立于 `main.py`；`main.py` 在 `send` 回复后调用 advisor。
- **L7**：**不**新增「讨论模式」命令；仅在 system 中加边界说明（与 L5 纯讨论共存）。
- **P5（5.5 已确认）**：策略 **`checkpoint_only`**——`send()` 不写 `session.json`；检查点：`commit_adopt`、`undo_last_adopt`、`commit_fix`、`apply_reconcile`、`finish_scene_switch`、CLI 退出 `session.save()`。保持 P2「不恢复 candidate」。自上次检查点以来的纯讨论 `messages` 在异常退出时可能丢失；已 adopt 正文在 manuscript + 检查点 session 中不丢。
- **X4（若做）**：维持 `/` 前缀 + 小写别名；大小写兼容为低优先级。

---

### Phase 6：工作流（方向 B，第一版）

> **目标**：日常写作工具化——优先交付正文导出、JSON meta 开书、扩展 meta 注入；**依赖 Phase 5 稳定后再做**。

| 优先级 | 能力 | open-questions |
|--------|------|----------------|
| P0 | P3 manuscript 合并导出（CLI 命令 `/export [output_path]`） | P3 |
| P1 | P6 开书 meta 采集改进（第一版仅支持 `--meta <path>` JSON 文件） | P6 |
| P1 | L4 meta 字段扩展与人称/禁忌等注入 | L4 |
| P2 | 文风 / 叙事模板 preset（暂不实现） | README 路线图 |
| P2 | P4 projects 路径 CLI 暴露（暂不实现，`LNAGENT_PROJECTS_DIR` 已有） | P4 |

- [x] **6.1 文档固化**：明确 Phase 6 第一版范围、非目标与验收项
  产出：`docs/features/memory-mvp-plan.md`
- [x] **6.2 `/export` 导出**：CLI 支持 `/export [output_path]`；纯正文导出；默认写入项目根目录 `exports/YYYY-MM-DD.md`，同名文件自动追加数字后缀
  产出：`lnagent/cli/export.py`、`main.py`、`lnagent/cli/commands.py`
- [x] **6.3 场景合并规则**：严格按 `manuscript/scene_XXX.md` 编号升序合并；每个场景使用 `## Scene 001` 分隔；空场景跳过
  产出：`lnagent/memory/store.py` 或导出模块
- [x] **6.4 `--meta` JSON 开书**：新 project 创建时可通过 `--meta <path>` 初始化；已有 project 传入 `--meta` 直接报错，不覆盖 `meta.json`
  产出：`main.py`、`lnagent/project.py`
- [x] **6.5 meta 字段扩展**：`NovelMeta` 增加 `pov`、`tense`、`taboos`、`target_audience`、`narrative_rules`、`genre`、`tone`；旧项目缺字段时保持空值
  产出：`lnagent/memory/models.py`
- [x] **6.6 Prompt 注入**：扩展字段仅在非空时进入 Prompt；`taboos`、`narrative_rules` 以列表形式注入
  产出：`lnagent/memory/prompt.py`

**Phase 6 第一版暂不实现**：

- `--template` / 模板文件开书。
- 一次性粘贴 meta 或自然语言 meta 抽取。
- 文风 / 叙事 preset；后续实现时如与 meta 不一致应在初始化时报错。
- `/meta` 或 `/config meta.*` 修改已有项目 meta。
- 使用 `--meta` 覆盖已有 project 的 `meta.json`。

**验收**：

- [x] `/export` 可一条命令导出全书纯正文；默认路径在项目 `exports/` 下；显式路径可用。
- [x] 导出内容严格按 `scene_XXX` 编号升序排列，并以 `## Scene 001` 等标题分隔。
- [x] 新 project 可通过 `--meta <path>` JSON 初始化；已有 project 携带 `--meta` 启动时报错且不覆盖 meta。
- [x] 旧 project 的 `meta.json` 缺新增字段时仍可正常启动，新增字段为空。
- [x] 非空扩展 meta 字段进入 Prompt，空字段不注入。

---

### Phase 7+：扩展架构（方向 C，规划）

> **目标**：长篇与检索；改动面大，**不与 Phase 5/6 混排**。  
> **Hot Canon schema 演进**已拆独立计划：[canon-schema-evolution-plan.md](./canon-schema-evolution-plan.md)（实施顺序 **S3 → S2 → S4**，迁移 A+B）。

| 优先级 | 能力 | 文档 / open-questions |
|--------|------|------------------------|
| P0 | S3 → S2 → S4 Hot Canon schema v2 | [canon-schema-evolution-plan.md](./canon-schema-evolution-plan.md) |
| P1 | R1 向量 RAG（`MemoryRetriever`） | R1 |
| P2 | R3 分卷 / 章节结构 | R3 |
| P3 | R2 LangGraph / LangMem 接入边界 | R2 |

---

## 4. 模块与文件清单

```
lnagent/
├── memory/
│   ├── __init__.py
│   ├── models.py           # Phase 0
│   ├── protocols.py        # Phase 0
│   ├── store.py            # Phase 0
│   ├── short_term.py       # Phase 1
│   ├── prompt.py           # Phase 1；Phase 5 T8/L7
│   ├── context_budget.py   # Phase 5（T8 预算与裁剪）
│   ├── scene_switch.py     # Phase 5（C6 切换建议，名称可调整）
│   ├── canon_extractor.py  # Phase 2
│   └── cold_archive.py     # Phase 3
├── cli/
│   ├── __init__.py
│   ├── commands.py         # Phase 2
│   ├── adopt.py            # Phase 2
│   ├── scene.py            # Phase 3
│   ├── undo.py             # Phase 4
│   ├── fix.py              # Phase 4
│   ├── config.py           # Phase 5
│   └── export.py           # Phase 6
├── session.py              # Phase 1
├── project.py              # Phase 6（--meta 开书）
├── chat.py                 # 保留 LLMChatClient；NovelSession 新入口
├── config.py               # Phase 0 扩展
└── llm.py                  # 不变
```

---

## 5. 接口草案（便于扩展、少重构）

```python
# protocols.py 概念签名

class MemoryStore(Protocol):
    def load_meta(self) -> NovelMeta: ...
    def save_meta(self, meta: NovelMeta) -> None: ...
    def load_canon(self) -> HotCanon: ...
    def save_canon(self, canon: HotCanon) -> None: ...
    def load_session(self) -> SceneSession: ...
    def save_session(self, session: SceneSession) -> None: ...

class PromptContextBuilder(Protocol):
    def build(self, *, meta, canon, short_term, user_input: str) -> list[BaseMessage]: ...

class CanonExtractor(Protocol):
    def extract_patch(self, adopted_text: str, canon: HotCanon) -> CanonPatch: ...
```

LangChain 仅出现在 `session.py` 的 `model.invoke()`；memory 包**不 import langchain**。

---

## 6. 建议实施顺序（给开发者）

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
  │            │            │                              │
  │            │            └── 用户可感知的核心「记忆」      └── 中篇可用（T8/C6/L7）
  │            └── 多轮 + 持久化（最小可用）
  └── 无 LLM 变更，可单测 store/models

Phase 5 ──► Phase 6（工作流：导出/模板）──► Phase 7+（RAG / schema / 分卷）
```

**第一批 PR 建议只做 Phase 0 + Phase 1**，跑通多轮与 meta 注入后再做 `/a`。

---

## 7. 测试策略（轻量）

| 层级 | 内容 |
|------|------|
| 单元测试 | `JsonMemoryStore` 读写、`ShortTermBuffer` adopt 栈、`PromptContextBuilder`（含 tail/Cold、**Phase 5 预算裁剪**）、`synopsis.json`、`/sc` 流程 mock |
| 集成测试 | mock LLM，走通 send → adopt(y) → canon 更新；finish_scene_switch accept/reject |
| 手工 | 真实 API：多轮对话；`/a` + `/c`；`scene_001` → `/sc` → `scene_002` 续写 |

不引入额外测试框架依赖；使用 stdlib `unittest` 或 `pytest`（若项目已有则沿用）。

---

## 8. 完成标准（Definition of Done）

MVP（Phase 0–2）视为完成当：

- [x] `python main.py --project <id>` 可创建 / 打开项目  
- [x] 多轮对话中模型能利用当前场景历史  
- [x] `/a` 采纳正文并可选写入 Hot Canon（y/n）  
- [x] `/c` 查看 Canon；重启后会话与 canon 持久化  
- [x] 未 `/a` 的候选退出后丢失  
- [x] memory 包与 LangChain 解耦（仅 session 层调用 LLM）  

Phase 3（场景切换与 Cold Archive）视为完成当：

- [x] `/sc` 在至少一次 `/a` 后可切换场景；Cold accept 写入 `synopsis.json` 并 rollup `global`  
- [x] `/r` 拒绝 Cold 仍切换场景；新场景 Prompt 含 meta + global + 上一场景 Cold（若有）+ Hot + tail  
- [x] `/sc` 时逐条 reconcile `adopt_stack` 中 `accepted_canon=false`  

Phase 4（`/u`、`/f`）视为完成当：

- [x] `/u` 撤销最后一次 adopt；正文 + Hot 回滚；`accepted_canon=false` 可撤；不动 `messages`
- [x] `/f` 多行纠错意图 → patch diff → y/n；不改正文、不写 `adopt_stack`

Phase 5（中篇可用，方向 A）已完成（含长对话/多场景手工 spot-check，2026-05-29）。

Phase 6 第一版（`/export`、`--meta`、扩展 meta 注入）已完成；Phase 7+ 为规划项，实现前再拆任务与验收。

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初稿：Phase 0–4，最小范围 Phase 0–2 |
| 2026-05-25 | Phase 3 已确认：`synopsis.json` schema、global rollup、Prompt 注入、reconcile 与 `/r` 语义 |
| 2026-05-25 | Phase 2–3 实现完成：勾选任务与验收；补充 Phase 3 DoD |
| 2026-05-26 | Phase 4 已确认并实现：`/f` 多行+EOF、同 schema patch；`/u` 栈顶回滚与默认边界 |
| 2026-05-26 | 新增 Phase 5（方向 A：T8/C6/L7）及 Phase 6/7+ 路线规划 |
| 2026-05-27 | Phase 6 第一版实现完成：`/export`、`--meta` JSON 开书、扩展 meta Prompt 注入 |
| 2026-05-27 | Phase 5.5：`session.json` checkpoint_only 写盘策略实现 |
| 2026-05-29 | Phase 5 手工验收通过；同步 §1.2、§4 模块清单与 DoD |
| 2026-05-29 | Phase 7+ 链出 canon-schema-evolution-plan（S3 优先） |
