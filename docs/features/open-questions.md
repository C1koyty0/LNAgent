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
| **L4** | 🔴 | **meta 哪些字段固定注入 System Prompt？** | 待定字段可能包括：书名、简介、世界规则、文风、人称、禁忌、目标篇幅等。需定义 `meta.json` schema 与注入模板。 |
| **L1** | 🟡 | **adopt / scene 各需几次 LLM 调用？** | adopt：续写 1 次 + Hot 抽取 1 次；scene：Cold 提案 1 次 + reconcile 1 次？实现阶段按成本与延迟优化，不阻塞架构。 |
| **T8** | 🟡 | **上下文 token 预算如何分配？** | 各块上限（Hot Canon / 已确认摘要 / 当前场景 / tail）依赖**模型上下文窗口**与实测。MVP 可先全量注入短篇体量，超窗后再裁剪。 |
| **L6** | 🟡 | **Hot / Cold 抽取用的结构化输出 schema** | Phase 2 默认：Hot 抽取输出 JSON patch，覆盖 `characters`、`world.rules[]`、`plot_threads[]`；解析失败提示重试，不 silent fail。Cold 抽取 schema 后续随 Phase 3 再定。 |
| **L7** | 🔴 | **System Prompt 中「写作任务」与「讨论任务」是否区分** | L5 已允许纯讨论；是否在 system 中提示「讨论输出非正文，勿直接 adopt」？ |

---

## 2. 场景与摘要

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **S6** | 🔴 | **场景元数据（location / time / pov）如何维护？** | A) `/sc` 时 LLM 自动从正文抽取<br>B) `/sc` 时作者手动填写<br>C) 混合：自动抽取 + 作者可改 |
| **S5** | 🔴 | **全书梗概（global synopsis）何时 rollup？** | A) 每次 Cold accept 后自动更新<br>B) 每 N 个场景<br>C) 作者显式命令（如 `/synopsis`） |
| **S2** | 🔴 | **能力字段粒度** | 结构化等级（如「剑术 Lv3」）vs 自然语言；是否带 timestamp / source_scene？ |
| **S3** | 🔴 | **世界观 rules 是否按地点/势力拆分** | MVP 仅 `world.rules[]` 全局列表，还是预留 `world.locations`？ |
| **S4** | 🔴 | **伏笔 plot_threads 完整字段** | 待定：`id`、`status`、`introduced_in`、`closed_in`、`note` 等。 |
| **C6** | 🟡 | **场景切换启发式具体规则** | 已确认用启发式建议 `/sc`，规则待定。候选：已 adopt 段落数阈值、Agent 回复含完成信号词、作者连续多轮无 adopt 等。MVP 可先做简单规则或仅 system prompt 提示。 |

---

## 3. CLI 与交互

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **X1** | 🟡 | **多行文本输入如何实现** | Phase 2 默认：`/a` adopt 使用多行输入，单独一行 `EOF` 结束提交。Cold review 是否沿用 EOF 或改用编辑器，Phase 3 再定。 |
| **X2** | 🔴 | **`/fix` 的参数输入方式** | 纠错意图是 `/f` 后同一行，还是进入多轮对话再抽取？ |
| **X3** | 🔴 | **Cold review 空输入语义** | 文档写「直接回车等同 accept 原文」；多行模式下如何区分「提交编辑」与「accept 原文」？ |
| **X4** | 🟡 | **命令大小写与前缀** | 是否仅支持 `/a` 小写？`/` 是否必须？ |

---

## 4. 项目与持久化

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **P3** | 🔴 | **MVP 是否支持 manuscript 合并导出？** | 如 `export.md` 合并所有 scene；非阻塞 MVP。 |
| **P4** | 🔴 | **projects 根路径是否可配置** | 环境变量 `LNAGENT_PROJECTS_DIR` vs 固定 `./projects`？ |
| **P5** | 🔴 | **`session.json` 持久化粒度** | 每轮对话后写盘 vs 仅 adopt / exit 时写；与 P2「不恢复候选」的关系。 |
| **P6** | 🔴 | **开书 meta 采集交互** | 交互式问答逐字段 vs 一次粘贴 vs 模板文件；`meta.json` 最小必填字段列表。 |
| **E3** | 🟡 | **正文与 Hot 不一致时的 reconcile** | memory-architecture 写「以正文为准」；是否自动触发 Hot 重抽，还是仅 `/f` / `/sc` reconcile？ |

---

## 5. 扩展项（非 MVP）

| ID | 状态 | 问题 | 背景 / 选项 |
|----|------|------|-------------|
| **R1** | 🟡 | **向量 RAG 接入时机** | 已预留 `MemoryRetriever`；何时对历史 scene 做 embedding 检索？ |
| **R2** | 🟡 | **LangGraph / LangMem 接入边界** | 哪些模块可被替换而不动 `NovelSession` 对外 API？ |
| **R3** | 🔴 | **多书 / 章节级结构** | 当前一次一本、场景级；长篇分卷时 schema 如何演进？ |

---

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初稿：自 memory-architecture §8.2 拆出并扩充 |
| 2026-05-25 | 补充 Phase 2 默认：`/a` 使用 EOF 多行输入；Hot patch 覆盖 `characters`、`world.rules[]`、`plot_threads[]` |
