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
| `/sc` 场景切换、Cold Archive、tail 衔接 | 依赖 scene 归档与摘要流，作为 **Phase 2** |
| `/u` undo、`/f` fix | 依赖 adopt 栈与 Canon 快照，作为 **Phase 3** |
| Hot 抽取 LLM 结构化输出 | Phase 1 可用**规则占位 / 简版 prompt**；Phase 2 完善 |
| 场景切换启发式（C6） | Phase 2 随 `/sc` 一并接入 |
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

### Phase 0：骨架与数据模型（无 LLM 行为变更）

| # | 任务 | 产出 |
|---|------|------|
| 0.1 | 定义 dataclass / TypedDict：`NovelMeta`、`HotCanon`、`SceneSession` | `lnagent/memory/models.py` |
| 0.2 | 实现 `JsonMemoryStore`：load/save meta、canon、session | `lnagent/memory/store.py` |
| 0.3 | 抽象 `MemoryStore` Protocol | `lnagent/memory/protocols.py` |
| 0.4 | `Settings` 增加 `project_id`、`projects_dir` | `lnagent/config.py` |
| 0.5 | `main.py` 解析 `--project`；不存在则交互创建 meta | `main.py` |

**验收**：运行 `python main.py --project test` 可创建目录与空 `canon.json` / `meta.json`。

---

### Phase 1：多轮会话 + 上下文注入

| # | 任务 | 产出 |
|---|------|------|
| 1.1 | `ShortTermBuffer`：追加 user/assistant 消息、adopted_prose、last_candidate | `lnagent/memory/short_term.py` |
| 1.2 | `PromptContextBuilder.build()`：按 architecture §4.3 简化版组装 messages | `lnagent/memory/prompt.py` |
| 1.3 | `NovelSession.send(user_input)`：build → invoke → 存 candidate → 持久化 session | `lnagent/session.py` |
| 1.4 | 替换 `main.py` 中 `LLMChatClient` 为 `NovelSession` 循环 | `main.py` |
| 1.5 | 退出时 save session；再进 load session（**不**恢复 candidate，符合 P2） | store + session |

**验收**：同一 project 内多轮对话，LLM 能引用上一轮内容；重启后已 adopt 正文与对话历史仍在。

**open-questions 暂按默认**：

- L4：meta 注入 `title`、`world_rules`、`style`（开书时必填此三字段）
- P5：每轮 `send` 后写 `session.json`

---

### Phase 2：`/a` adopt 与 Hot Canon（核心记忆）

| # | 任务 | 产出 |
|---|------|------|
| 2.1 | CLI 命令路由：`/a`、`/c`、`/h` 及别名；非命令走 `send()` | `lnagent/cli/commands.py` |
| 2.2 | `/a` 流程：展示 last_candidate → 读入完整文本（先 **单行/多行 EOF** 简版，见 X1） | `lnagent/cli/adopt.py` |
| 2.3 | adopt 后追加 `manuscript/scene_001.md` 与 buffer.adopted_prose | session + store |
| 2.4 | `CanonExtractor`：LLM 从 adopt 文本抽 Hot 变更 → diff 展示 | `lnagent/memory/canon_extractor.py` |
| 2.5 | y/n 确认后 merge 进 `canon.json`；拒绝则只保留正文 | store |
| 2.6 | adopt 时保存 **Hot 快照**（为 Phase 3 `/u` 预留栈） | session 内 `adopt_stack[]` |

**验收**：

1. 对话生成候选 → `/a` 采纳 → `/c` 可见新能力/状态  
2. Hot 变更 n 拒绝时，正文已写入但 canon 不变  

**简版 Hot 抽取 prompt**：要求模型输出 JSON patch（characters 增量），解析失败则提示重试、不 silent fail。

---

### Phase 3：场景切换与 Cold Archive（记忆闭环）

| # | 任务 | 产出 |
|---|------|------|
| 3.1 | `/sc`：校验至少一次 adopt；归档 scene 快照 | `lnagent/cli/scene.py` |
| 3.2 | 生成 Cold 提案 → 完整文本 review → `/r` 或提交写入 `synopsis.json` | `lnagent/memory/cold_archive.py` |
| 3.3 | 新 scene：`scene_002`、tail 500 字注入 Prompt | prompt + short_term |
| 3.4 | `/sc` 时 batch Hot reconcile（y/n） | canon_extractor |
| 3.5 | 启发式：回复末尾附加「可考虑 /sc」提示（简版 C6） | prompt 或 post-process |

**验收**：完成 scene_001 → `/sc` → 确认摘要 → scene_002 续写带 tail + 已确认 synopsis。

---

### Phase 4：纠错命令

| # | 任务 | 产出 |
|---|------|------|
| 4.1 | `/u`：pop adopt_stack，回滚正文 + Hot | `lnagent/cli/undo.py` |
| 4.2 | `/f`：读纠错意图 → Hot diff → y/n | `lnagent/cli/fix.py` |

**验收**：adopt 后 `/u` 恢复；`/f` 修正错误能力。

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
