# 待讨论项（Open Questions）

> 记录尚未拍板的设计问题，避免实现或后续讨论中遗忘。  
> 已确认决策见 [memory-architecture.md §8.1](./memory-architecture.md#81-已确认)。

---

## 状态说明

| 状态 | 含义 |
|------|------|
| 🔴 待讨论 | 尚未有倾向或决议 |
| 🟡 有倾向 | 实现时可暂按倾向做，但仍建议确认 |
| 🟢 已决议 | 已写入 memory-architecture，从此表移除 |

---

## 1. Prompt 与 LLM

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **L4** | 🟢 | **meta 哪些字段固定注入 System Prompt？** | Phase 6：`title`、`world_rules`、`style` 及扩展字段（`pov`、`tense`、`taboos` 等）非空时注入。见 [memory-mvp-plan Phase 6](./memory-mvp-plan.md#phase-6工作流方向-b第一版)。 |
| **L1** | 🟡 | **adopt / scene 各需几次 LLM 调用？** | adopt：续写 1 次 + Hot 抽取 1 次；scene：Cold 提案 1 次 + reconcile 1 次？实现阶段按成本与延迟优化，不阻塞架构。 |
| **T8** | 🟢 | **上下文 token 预算如何分配？** | Phase 5：按**字符**分块上限 + 总预算裁剪；`/config` 可配。见 [memory-mvp-plan Phase 5](./memory-mvp-plan.md#phase-5中篇可用方向-a)。 |
| **L6** | 🟢 | **Hot / Cold 抽取用的结构化输出 schema** | Hot：JSON patch（Phase 2）。Cold：`synopsis.json` 见 [memory-mvp-plan Phase 3](./memory-mvp-plan.md#phase-3场景切换与-cold-archive记忆闭环)。 |
| **L7** | 🟢 | **System Prompt 中「写作任务」与「讨论任务」是否区分** | Phase 5：仅在 system 中加边界说明（讨论输出非正文，勿直接 adopt）；不新增讨论模式命令。 |

---

## 2. 场景与摘要

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **S6** | 🟢 | **场景元数据（location / time）** | `/sc` Cold 提案时 LLM 抽取；作者 review **仅改 summary**，`location`/`time` 以提案为准。POV 暂不单独字段。 |
| **S5** | 🟢 | **全书梗概（global synopsis）何时 rollup？** | **每次 Cold accept 写入 `scenes[]` 后**，LLM 自动更新 `synopsis.global`。 |
| **S2** | 🟡 | **能力字段粒度** | 计划已定：对象 + `id` 合并、`level` 整数；见 [canon-schema-evolution-plan](./canon-schema-evolution-plan.md) Phase 7.2。 |
| **S3** | 🟡 | **世界观 rules 是否按地点/势力拆分** | 计划已定：**优先实现** `world.scoped[]`（`faction`/`location`）；见 Phase 7.1。 |
| **S4** | 🟡 | **伏笔 plot_threads 完整字段** | 计划已定：`introduced_in`、`advanced_in`、`closed_in` 等；见 Phase 7.3。 |
| **C6** | 🟢 | **场景切换启发式具体规则** | Phase 5：`adopt_stack` 次数 ≥ 2 **或** 连续 M 轮无 `/a`（默认 M=3）；仅建议，不自动 `/sc`。`/config` 可调阈值。 |

---

## 3. CLI 与交互

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **X1** | 🟢 | **多行文本输入如何实现** | `/a` 与 **Cold review** 均：多行 + 单独一行 `EOF` 结束。 |
| **X2** | 🟢 | **`/fix` 的参数输入方式** | `/f` 后**多行 + 单独一行 `EOF` 结束**（同 `/a`、Cold review）；纠错意图不可为空。 |
| **X3** | 🟢 | **Cold review 空输入语义** | 与 `/a` 一致：仅输入 `EOF`（无 summary 正文）= 原样采纳提案 summary。 |
| **X4** | 🟡 | **命令大小写与前缀** | 是否仅支持 `/a` 小写？`/` 是否必须？ |

---

## 4. 项目与持久化

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **P3** | 🟢 | **MVP 是否支持 manuscript 合并导出？** | Phase 6：`/export [output_path]`；默认 `exports/YYYY-MM-DD.md`。 |
| **P4** | 🟡 | **projects 根路径是否可配置** | 已实现 `LNAGENT_PROJECTS_DIR` 环境变量；CLI 参数暴露暂不做（Phase 6 非目标）。 |
| **P5** | 🟢 | **`session.json` 持久化粒度** | **checkpoint_only**（Phase 5.5）：`send()` 不写盘；adopt / undo / fix / reconcile / `/sc` / 退出时写盘。纯讨论轮次异常退出可丢 `messages`；candidate 仍不恢复（P2）。见 [memory-mvp-plan Phase 5.5](./memory-mvp-plan.md#phase-5中篇可用方向-a)。 |
| **P6** | 🟡 | **开书 meta 采集交互** | Phase 6 第一版：`--meta <path>` JSON 初始化；交互式问答与模板开书暂不做。 |
| **E3** | 🟢 | **正文与 Hot 不一致时的 reconcile** | 不自动重抽；`/sc` 时**逐条** reconcile `adopt_stack` 中 `accepted_canon=false`；口头纠错走 `/f`。 |

---

## 5. 扩展项（非 MVP）

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **R1** | 🟡 | **向量 RAG 接入时机** | 已预留 `MemoryRetriever`；何时对历史 scene 做 embedding 检索？ |
| **R2** | 🟡 | **LangGraph / LangMem 接入边界** | 哪些模块可被替换而不动 `NovelSession` 对外 API？ |
| **R3** | 🔴 | **多书 / 章节级结构** | 当前一次一本、场景级；长篇分卷时 schema 如何演进？ |

---

## 6. Phase 3 已决议（2026-05-25，详见 memory-mvp-plan）

| 议题 | 决议 |
|------|------|
| `synopsis.json` 结构 | 分字段：`global` + `scenes[]{id,location,time,summary,key_points[]}` |
| 新场景 Prompt | meta + **global** + **上一场景刚归档的 Cold 条目** + Hot + tail（500 字） |
| `/r` 拒绝 Cold | 不写该场景 synopsis；**仍切换场景** |
| 「当前 scene cold」 | 指**上一场景**刚 accept 写入的 `scenes[]` 条目 |

---

## 7. Phase 4 已决议（2026-05-26，详见 memory-mvp-plan）

| 议题 | 决议 |
|------|------|
| `/f` 输入（X2） | 多行 + `EOF`（同 `/a`）；纠错意图不可为空 |
| `/f` LLM 输出 | 与 adopt **同 JSON patch schema + merge 规则**；prompt 按纠错意图修正 Hot |
| `/f` 副作用 | 仅改 Hot Canon；**不改正文、不写 `adopt_stack`** |
| `/u` 回滚范围（E2） | 栈顶 pop；`adopted_prose` + manuscript + Hot（`canon_before`）；**不动 `messages`** |
| `/u` 可撤对象 | `accepted_canon=false` 的 adopt 也可撤；允许多次连续 `/u` |
| `/u` 场景范围 | 仅当前场景（`/sc` 后栈已清空） |

---

## 8. Phase 5 已决议（2026-05-27，手工验收 2026-05-29）

| 议题 | 决议 |
|------|------|
| T8 计量与裁剪 | 字符预算；各块独立上限 + 总预算；超限时 CLI 提示，不 silent 丢块 |
| T8 配置 | `/config` 修改 `config.json`，立即生效 |
| C6 规则 | `adopt_stack ≥ 2` 或连续 M 轮无 `/a`（默认 3）；仅建议 |
| L7 边界 | system 中说明讨论输出非正文；无讨论模式命令 |
| P5 写盘 | `checkpoint_only`：`send()` 不写 `session.json` |

---

## 9. Phase 6 已决议（2026-05-27）

| 议题 | 决议 |
|------|------|
| P3 导出 | `/export`；按 `scene_XXX` 升序合并；`## Scene NNN` 分隔 |
| P6 开书 | 新 project 支持 `--meta <path>` JSON；已有 project 传入则报错 |
| L4 扩展 meta | `pov`、`tense`、`taboos` 等扩展字段非空时注入 Prompt |

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初稿：自 memory-architecture §8.2 拆出并扩充 |
| 2026-05-25 | 补充 Phase 2 默认：`/a` 使用 EOF 多行输入；Hot patch 覆盖 `characters`、`world.rules[]`、`plot_threads[]` |
| 2026-05-25 | Phase 3：S5/S6/L6 Cold、X1/X3、E3 等标 🟢；新增 §6 决议摘要 |
| 2026-05-26 | Phase 4：X2 标 🟢；新增 §7 决议摘要（`/f` 输入与 patch、`/u` 边界） |
| 2026-05-27 | Phase 5.5：P5 标 🟢，checkpoint_only session 写盘策略 |
| 2026-05-29 | Phase 5/6 决议同步：L4、T8、L7、C6、P3 标 🟢；P4/P6 标 🟡；新增 §8–§9 |
| 2026-05-29 | S2–S4 链出 canon-schema-evolution-plan；S3 优先、迁移 A+B |
