# 记忆功能 MVP 实现计划

> 目标：实现**最最基本的记忆能力**，使 LNAgent 从单轮 CLI 升级为「带项目、带场景、带 Canon 的多轮续写」。  
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
| 基础持久化 | `canon.json`、`session.json`、`manuscript/scene_XXX.md` |

### 1.2 本计划**暂不**实现（后续迭代）

| 能力 | 原因 |
|------|------|
| `/sc` 场景切换、Cold Archive、tail 衔接 | 依赖 scene 归档与摘要流，作为 **Phase 3** |
| `/u` undo、`/f` fix | 依赖 adopt 栈与 Canon 快照，作为 **Phase 4** |
| Hot 抽取 LLM 结构化输出 | Phase 2 完善 |
| 场景切换启发式（C6） | Phase 3 随 `/sc` 一并接入 |
| token 预算裁剪（T8） | 短篇先全量注入 |
| 向量 RAG | 明确不做 |

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
│   └── canon.json          # 初始可为空结构
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

- L4：meta 注入 `title`、`world_rules`、`style`（开书时必填此三字段）
- P5：每轮 `send` 后写 `session.json`

---

### Phase 2：`/a` adopt 与 Hot Canon（核心记忆）

- [ ] **2.1 命令路由**：CLI 支持 `/a`、`/c`、`/h` 及别名；非命令走 `send()`  
  产出：`lnagent/cli/commands.py`
- [ ] **2.2 adopt 输入流**：`/a` 展示 `last_candidate`，读入用户修改后的完整文本；MVP 使用多行输入，单独一行 `EOF` 结束  
  产出：`lnagent/cli/adopt.py`
- [ ] **2.3 正文采纳**：adopt 后追加 `manuscript/scene_001.md` 与 `buffer.adopted_prose`  
  产出：session + store
- [ ] **2.4 Hot 抽取**：`CanonExtractor` 让 LLM 从 adopt 文本抽取 Hot 变更，并展示 diff  
  产出：`lnagent/memory/canon_extractor.py`
- [ ] **2.5 Canon 合并**：用户 y/n 确认；确认后 merge 进 `canon.json`，拒绝则只保留正文、不更新 Canon  
  产出：store
- [ ] **2.6 adopt 栈**：adopt 时保存回滚所需信息，为 Phase 4 `/u` 预留  
  产出：session 内 `adopt_stack[]`

**验收**：

- [ ] 对话生成候选 → `/a` 采纳 → `/c` 可见新能力/状态。
- [ ] Hot 变更 n 拒绝时，正文已写入但 canon 不变。

**Phase 2 已确认细节**：

- Hot 抽取覆盖 `characters`、`world.rules[]`、`plot_threads[]`。
- Hot patch merge：角色按 `name` 合并；数组字段追加去重；`status`、`location` 等标量字段以后来的 patch 覆盖；`plot_threads` 有 `id` 时按 `id` 合并，否则追加。
- Hot 变更被拒绝时不记录 suppression；后续 `/sc` batch reconcile 如果再次抽到，可以再次询问。
- `adopt_stack[]` 至少记录 adopt 文本、`canon_before` 快照、`canon_patch`、`accepted_canon`。
- 简版 Hot 抽取 prompt 要求模型输出 JSON patch；解析失败则提示重试，不 silent fail。

---

### Phase 3：场景切换与 Cold Archive（记忆闭环）

- [ ] **3.1 场景命令**：`/sc` 校验至少一次 adopt；归档 scene 快照  
  产出：`lnagent/cli/scene.py`
- [ ] **3.2 Cold 提案**：生成 Cold 提案 → 完整文本 review → `/r` 或提交写入 `synopsis.json`  
  产出：`lnagent/memory/cold_archive.py`
- [ ] **3.3 新场景启动**：创建 `scene_002`，Prompt 注入 meta + global + 上一场景 Cold + Hot + tail  
  产出：prompt + short_term + store（`synopsis.json`）
- [ ] **3.4 Hot reconcile**：`/sc` 时逐条 reconcile `adopt_stack` 中 `accepted_canon=false`（y/n）  
  产出：canon_extractor + session
- [ ] **3.5 切换建议**：启发式在回复末尾附加「可考虑 /sc」提示（简版 C6）  
  产出：prompt 或 post-process

**验收**：

- [ ] 完成 scene_001 → `/sc` → 确认摘要 → scene_002 续写带 **meta + global + 上一场景 Cold + Hot + tail**。

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

- [ ] **4.1 Undo**：`/u` pop adopt_stack，回滚正文 + Hot  
  产出：`lnagent/cli/undo.py`
- [ ] **4.2 Fix**：`/f` 读纠错意图 → Hot diff → y/n  
  产出：`lnagent/cli/fix.py`

**验收**：

- [ ] adopt 后 `/u` 恢复。
- [ ] `/f` 修正错误能力。

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
│   ├── prompt.py           # Phase 1
│   ├── canon_extractor.py  # Phase 2
│   └── cold_archive.py     # Phase 3
├── cli/
│   ├── __init__.py
│   ├── commands.py         # Phase 2
│   ├── adopt.py            # Phase 2
│   ├── scene.py            # Phase 3
│   ├── undo.py             # Phase 4
│   └── fix.py              # Phase 4
├── session.py              # Phase 1
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
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
  │            │            │
  │            │            └── 用户可感知的核心「记忆」
  │            └── 多轮 + 持久化（最小可用）
  └── 无 LLM 变更，可单测 store/models
```

**第一批 PR 建议只做 Phase 0 + Phase 1**，跑通多轮与 meta 注入后再做 `/a`。

---

## 7. 测试策略（轻量）

| 层级 | 内容 |
|------|------|
| 单元测试 | `JsonMemoryStore` 读写、`ShortTermBuffer` adopt 栈、`PromptContextBuilder` 消息条数 |
| 集成测试 | mock LLM，走通 send → adopt(y) → canon 更新 |
| 手工 | 真实 API：两轮对话引用前序；adopt 后 `/c` 可见 Hot |

不引入额外测试框架依赖；使用 stdlib `unittest` 或 `pytest`（若项目已有则沿用）。

---

## 8. 完成标准（Definition of Done）

MVP（Phase 0–2）视为完成当：

- [ ] `python main.py --project <id>` 可创建 / 打开项目  
- [ ] 多轮对话中模型能利用当前场景历史  
- [ ] `/a` 采纳正文并可选写入 Hot Canon（y/n）  
- [ ] `/c` 查看 Canon；重启后会话与 canon 持久化  
- [ ] 未 `/a` 的候选退出后丢失  
- [ ] memory 包与 LangChain 解耦（仅 session 层调用 LLM）  

Phase 3–4 为「记忆闭环」增强，可在 MVP 之后迭代。

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初稿：Phase 0–4，最小范围 Phase 0–2 |
| 2026-05-25 | Phase 3 已确认：`synopsis.json` schema、global rollup、Prompt 注入、reconcile 与 `/r` 语义 |
