# 世界观文档录入与结构化设计

> **状态**：设计已确认，WK0–WK6 + WB2.1 已实现
> **范围**：LNAgent Web 优先的世界观录入、结构化与按需注入路径  
> **目标**：允许作者以“完整世界观文档”作为录入入口，经 LLM 提炼为结构化 worldbook，再按 scene / scope 选择性注入 writing prompt，同时保持 `meta` 与 Hot Canon 的职责边界清晰。

---

## 1. 背景与动机

LNAgent 当前的世界观录入入口仍以“每行一条规则”为主：

- CLI 初始化项目时按行采集 `world_rules`
- Web 创建项目页以 textarea 录入“世界规则（每行一条）”
- 项目页 meta 编辑仅允许修改叙事字段，书名与世界规则保持只读

这套入口在“小体量、规则式设定”下尚可工作，但对实际轻小说/网文作者的世界观准备方式并不自然。作者更常见的工作习惯是：

- 先写一份或多份完整的世界观文档
- 文档中混合背景说明、术语、势力设定、地点说明、制度、能力体系、禁忌与待定问题
- 需要系统在不同 scene 中只取相关部分，而不是每次整份灌入 prompt

当前 LNAgent 底层实际上已经具备部分结构化能力：

- `meta.json` 已支持 `world.rules`（全局）与 `world.scoped[]`（`faction` / `location`）
- Prompt 组装已支持按 `active_scopes` 选择性注入 scoped 世界观块
- `meta_extractor.py` 已存在“使用 LLM 产出结构化 `meta`”的基本模式

因此当前真正缺失的不是“世界观是否需要结构化”的答案，而是：

> 如何把作者手写的完整世界观文档，转化为 LNAgent 可稳定消费、可 selective injection 的结构化世界观。

---

## 2. 设计目标

### P0

- 作者可直接录入或粘贴**完整世界观文档**，而非强制改写为“一行一条规则”
- 系统可将世界观文档经 LLM 提炼为**结构化 worldbook**
- writing prompt 只注入与当前 scene 相关的世界观信息，而非整份原文
- 保持 `meta`（作者开书圣经）与 Hot Canon（正文已确认事实）的职责边界

### P1

- 原始文档与结构化结果分离保存，避免作者原文与系统提炼结果混写
- 提供 review / apply 语义：LLM 提炼结果不是直接生效，作者可先看后用
- 第一阶段尽量复用现有 `world.rules` / `world.scoped` 与 prompt 注入路径，避免一次性重构过大

### P2

- 为后续 glossary、术语检索、RAG-lite、世界观工作台 UI 预留结构位置
- 保持 Web 优先；CLI 如需兼容，仅提供最小降级路径，不扩展复杂新交互

---

## 3. 非目标（当前轮建议明确）

以下内容**不应**成为第一版实现目标：

- 直接把完整世界观文档整份注入每一轮 writing prompt
- 直接用世界观原文替代 `meta.json` / `world.rules` / `world.scoped`
- 自动把 worldbook 中的所有内容视为 Hot Canon
- 自动构建复杂知识图谱、图数据库或任意 schema 自演进机制
- 第一版就实现 embedding 检索 / 向量 RAG / 多文档全局召回
- 复杂富文本编辑器、多人协作、版本对比 UI

---

## 4. 核心产品决策（本轮已确认）

### 4.1 世界观录入改为 document-first

世界观的作者入口从“规则列表优先”调整为“文档优先”：

- 作者维护的是**原始世界观文档**
- 系统消费的是**结构化提炼结果**
- prompt 注入使用的是**针对当前场景裁剪后的投影文本**

即：

- source document = 作者真源
- structured worldbook = 系统中间层
- prompt projection = LLM 实际读取层

### 4.2 worldbook 与 meta / canon 分工

建议明确三者职责：

#### `meta`

- 开书级静态设定入口
- 包含书名、文风、叙事字段，以及世界观投影结果
- 是 writing prompt 的稳定系统层输入之一

#### `worldbook`

- 作者维护的世界观原文 + LLM 提炼出的结构化世界观
- 偏“设定源 / author bible”
- 不等于正文已确认事实
- 可包含尚未在正文显化、但作者希望系统参考的设定

#### Hot Canon

- 只表示正文中已确认、已进入叙事事实层的内容
- 仍从 adopt / fix / reconcile 等主流程进入
- 不由世界观文档自动写入

### 4.3 原始文档与结构化结果分离保存

建议引入独立的 worldbook 存储层，而不是把大段原文直接塞进 `meta.json`。

建议目录（草案）：

```text
projects/<project_id>/
├── meta.json
├── worldbook/
│   ├── source.md
│   ├── structured.json
│   └── extraction-preview.json   # 可选：未 apply 的预览结果
├── manuscript/
└── memory/
```

第一版也可以更简单：

```text
projects/<project_id>/
├── meta.json
├── worldbook/
│   ├── source.md
│   └── structured.json
```

若需要 review 后 apply，则把“当前生效结构”与“新提取预览结构”区分开。

### 4.4 本轮已确认的实现取向

本轮 review 后，以下取向已确认：

- `worldbook apply` **覆盖** `meta.world`，不做 merge
- 第一版 `source` 采用**单文档**：`worldbook/source.md`
- `overview` 可作为**可选的短摘要注入**，但不替代 `global_rules`
- **不保留**现有“每行一条世界规则”的轻量入口；世界观录入切换为 document-first

### 4.5 selective injection 以结构化 worldbook 为核心

writing prompt 不应直接读取 `source.md` 全文，而应：

1. 总是注入世界观概览 / 全局规则
2. 根据当前 `active_scopes` 注入相关势力 / 地点块
3. 在必要时补充少量相关术语 / 附加规则
4. 仅在未来增强阶段，才考虑从原文中补原段摘录

这与当前 `meta.world.scoped` + `resolve_active_scopes` 的机制一致，可以逐步演进，而不是推翻重来。

---

## 5. 建议架构

### 5.1 三层模型

#### A. Source Layer：作者原始文档层

- 形态：Markdown / 纯文本
- 内容：完整世界观说明、势力设定、地点设定、术语表、未定问题等
- 目标：作者写起来顺手，不要求先结构化

#### B. Structured Layer：系统结构化层

- 形态：JSON
- 来源：LLM 从 source 文档提炼
- 目标：供系统过滤、选择、展示、注入

#### C. Prompt Projection Layer：注入投影层

- 形态：面向 prompt 的紧凑文本块
- 来源：Structured Layer 经选择、裁剪、格式化生成
- 目标：给 writing/discussion prompt 稳定、低 token、低噪声的上下文

### 5.2 推荐数据流

```text
作者编辑 source.md
    ↓
点击“提炼世界观”
    ↓
LLM 输出 structured worldbook preview
    ↓
作者 review / apply
    ↓
系统更新 structured.json
    ↓
系统将其中可投影部分同步到 meta.world
    ↓
PromptContextBuilder 按 scope 注入
```

其中“同步到 `meta.world`”是第一阶段最务实的做法：

- 现有 prompt 注入逻辑大多可复用
- 不需要第一版就让 prompt builder 直接依赖全新 worldbook schema
- 未来若 `meta` 与 `worldbook` 明显分层，再把 prompt 改为直接消费 `structured.json`

### 5.3 source 变更后的 freshness 语义（WB2.1）

在 `source -> extract -> apply` 闭环之上，WB2.1 进一步明确了 preview 的可信度语义：

- `source.md` 是作者真源；一旦作者保存新 source，旧 structured preview 立即视为失效
- 第一版直接清理持久化的 `worldbook/structured.json`，状态回落到 `source_only`，不保留 stale preview / diff
- 只有重新执行 extract 后，状态才会回到 `preview_ready`
- apply 只允许针对“当前 source 刚提炼出的最新 preview”执行，避免旧 preview 误写入 `meta.world`

---

## 6. 第一版 schema 建议

### 6.1 设计原则

第一版 schema 应遵循：

- 先服务 selective injection，而不是追求百科全书式完备
- 先保留字符串 / 列表 / 扁平对象，不引入过深嵌套
- 尽量与现有 `meta.world.rules` / `meta.world.scoped` 对齐
- 为后续 glossary / open questions / source citations 预留升级空间

### 6.2 `structured.json` 草案

```json
{
  "schema_version": 1,
  "overview": "一句到一段的世界观总览",
  "global_rules": [
    "全大陆通用规则",
    "货币、能力上限、通用禁忌等"
  ],
  "scopes": [
    {
      "scope_type": "faction",
      "scope_id": "洛兰王国",
      "summary": "该势力概述",
      "rules": [
        "该势力内部适用的制度或专属规则"
      ]
    },
    {
      "scope_type": "location",
      "scope_id": "白色空间",
      "summary": "该地点概述",
      "rules": [
        "该地点内部适用的规则"
      ]
    }
  ],
  "glossary": [
    {
      "term": "圣纹",
      "definition": "术语解释"
    }
  ],
  "open_questions": [
    "作者尚未拍板的问题"
  ]
}
```

### 6.3 第一版与现有 `meta` 的映射

建议第一版 apply 时：

- `structured.overview`：暂不强制写入 `meta`
- `structured.global_rules` → `meta.world.rules`
- `structured.scopes[]` → `meta.world.scoped[]`
- `glossary` / `open_questions`：先仅存于 `structured.json`，不强制注入 prompt

这样可以让第一版收益集中在最有价值的能力上：

- 文档录入
- 结构化拆分
- 按 scope 注入

### 6.4 为什么第一版不把 `glossary` 等都塞进 prompt

原因：

- 术语表与未决问题的 token 开销不低
- 不是每轮 writing 都需要
- 先让主要世界规则结构稳定，比一次性把所有字段注入更重要

后续可以再定义：

- 术语命中时补充 glossary
- discussion 模式下显示 open questions
- Web 面板展示结构化摘要

---

## 7. LLM 提炼与 apply 语义

### 7.1 提炼不是自动生效

世界观文档提炼建议分两步：

1. **Extract / Preview**：LLM 从 source 产出结构化预览
2. **Apply**：作者确认后，才更新生效结果

这样能避免：

- 文档微调一次就直接污染 meta
- 误提取结果立即影响写作
- 系统难以解释“为什么这轮 prompt 变了”

### 7.2 LLM 的职责边界

LLM 在这里的职责应是：

- 从原文中归纳全局规则
- 识别势力 / 地点级 scope
- 把原文拆为适合 prompt 消费的结构
- 标记不确定 / 未决项

而不是：

- 发明原文没有的设定
- 自动决定复杂 schema 演进
- 把作者语义改写成完全不同的世界观

### 7.3 apply 的最小副作用

第一版 apply 建议只做以下副作用：

- 更新 `worldbook/structured.json`
- 将 `global_rules` / `scopes` 同步到 `meta.world`
- 更新项目页中的 meta 只读展示

第一版**不应**：

- 自动写 Hot Canon
- 自动修复 synopsis
- 自动批量重算所有 scene

---

## 8. Web / API 交互建议

### 8.1 Web 优先入口

建议把世界观工作台放在项目页的 Meta 区域附近，或者作为独立 panel：

- 原始文档编辑区
- “提炼世界观”按钮
- 结构化预览区
- “应用到项目”按钮
- 当前生效 worldbook 概览

### 8.2 API 草案

建议新增最小 API：

- `GET /api/projects/{id}/worldbook`
  - 返回 source / structured / preview / status
- `PUT /api/projects/{id}/worldbook/source`
  - 保存原始世界观文档
- `POST /api/projects/{id}/worldbook/extract`
  - 调 LLM 生成 preview
- `POST /api/projects/{id}/worldbook/apply`
  - 将 preview 设为生效结构，并同步 `meta.world`

如果想更保守，第一版也可以只做：

- `PUT source`
- `POST extract-and-apply`

但从产品可控性看，review / apply 两步更合理。

### 8.3 与现有 meta 编辑的关系

当前项目页中：

- 书名与世界规则只读
- 叙事字段可编辑

引入 worldbook 后，更自然的职责分工是：

- **世界观正文来源**：worldbook source / extract / apply
- **叙事字段**：继续在 meta 表单中直接编辑
- **meta.world**：由 worldbook apply 维护，而不是手工一行一条维护

这意味着当前可以直接明确：

- 世界观正文入口切换到 worldbook source / extract / apply
- `meta.world` 不再作为手工“一行一条”维护入口
- worldbook apply **覆盖** `meta.world` 的世界观投影部分；叙事字段不受影响。

---

## 9. 与当前架构的衔接方式

### 9.1 第一阶段：把 worldbook 当作 `meta.world` 的上游

这是最小改动路径：

- worldbook source / structured 是新增层
- PromptContextBuilder 仍主要消费 `meta`
- apply 时把结构化 worldbook 投影到 `meta.world`

优点：

- 复用现有测试与 prompt 逻辑
- 改动聚焦在 ingestion / Web UI / service 层
- 容易灰度验证产品价值

缺点：

- `structured.json` 中 richer fields（overview / glossary / open_questions）暂时未被 prompt 原生消费
- `meta` 仍承担一部分“投影层容器”职责

### 9.2 第二阶段：Prompt 直接消费 structured worldbook

当第一阶段稳定后，可以考虑：

- PromptBuilder 直接读取 `structured.json`
- `meta` 只保留必要的开书字段与兼容投影
- glossary / scope summary / source excerpt 进入更细粒度注入逻辑

这一步应在第一阶段价值被证实后再讨论，不作为当前设计草案的默认要求。

---

## 10. 待决问题（建议进入 backlog）

### W1. source 支持单文档还是多文档？

选项：

- 第一版仅 `source.md`
- 后续支持 `sources/*.md`

本轮结论：

- 第一版先单文档，降低 UI/API 复杂度

### W2. worldbook apply 是覆盖 `meta.world` 还是 merge？

选项：

- 全覆盖：最简单，可预测
- merge：保留手工补丁，但语义复杂

本轮结论：

- 第一版全覆盖 `meta.world`，把 worldbook 当唯一世界观投影源

### W3. 结构化 preview 是否需要 diff？

选项：

- 第一版不做 diff，只展示完整预览
- 后续再加 preview vs active 差异视图

建议倾向：

- 第一版不做 diff

### W4. `overview` 是否进入 prompt？

选项：

- 不注入，仅用于 UI 展示
- 总是注入一句摘要
- 按预算条件注入

本轮结论：

- 第一版可选注入短摘要，但不应替代 `global_rules`

### W5. discussion 是否读取 worldbook open questions？

选项：

- 不读取，仅 UI 展示
- discussion prompt 可选读取未决项

建议倾向：

- 第一版不自动注入；后续再看是否有价值

### W6. 是否需要保留“每行一条世界规则”的创建入口？

选项：

- 立即替换为文档输入
- 两者并存，文档优先

本轮结论：

- 不保留现有“每行一条世界规则”的轻量入口
- Web / 项目创建路径直接切换到 document-first 世界观录入

---

## 11. 推荐分阶段路线

### Phase WB0：文档固化与边界确认

**目标**：先把 worldbook 的产品边界写清楚，不急着进代码。

**应确认的事项**：

- worldbook 与 meta / Hot Canon 的职责边界
- 第一版 schema 最小字段集
- review / apply 是否分两步
- apply 对 `meta.world` 的覆盖语义
- Web 优先、CLI 最小兼容的产品方向

### Phase WB1：最小文档录入 + 提炼 + 应用

**目标**：先让作者可以粘贴完整世界观文档，并把它提炼为当前系统可用的 `meta.world`。

**建议范围**：

- `worldbook/source.md`
- `worldbook/structured.json`
- `extract` + `apply`
- apply 同步 `meta.world.rules` / `meta.world.scoped`
- Prompt 继续走现有 `meta` 注入路径

**第一阶段不做**：

- glossary 注入
- 向量检索
- diff/history
- 多文档 source 管理

### Phase WB2：世界观工作台与 richer structure

**目标**：让 structured worldbook 在 UI 上可读、可查、可理解。

**可能范围**：

- scope summary 展示
- glossary 展示
- open questions 展示
- active vs preview 状态提示

### Phase WB3：按需检索 / RAG-lite 增强

**目标**：在世界观文档很大时，做更细粒度的补充注入。

**可能范围**：

- scope 命中后补原文摘录
- glossary 命中补充
- embedding / chunk retrieval

这应放在后续增强，而不是当前版本前提。

---

## 12. 风险与注意事项

### 12.1 最大风险：作者原文与生效世界观不一致

如果没有 preview / apply 分离，作者会很难理解：

- 原文改了什么
- 提炼结果改了什么
- 为什么 prompt 行为变了

因此建议从一开始就明确：

- source 是作者真源
- structured 是系统提炼结果
- active structured 才影响 prompt

### 12.2 LLM 提炼漂移风险

同一份 source 文档反复提炼，结果可能不稳定。缓解思路：

- prompt 明确 schema 与字段职责
- apply 前人工 review
- 第一版 schema 保持简单
- 尽量避免让 LLM“自由发明分类”

### 12.3 不要模糊 worldbook 与 canon

这是产品语义上最容易混淆的一点。必须反复强调：

- worldbook = 作者设定源
- canon = 正文确认事实

否则后续会出现：

- prompt 过早把幕后设定当成已发生剧情
- UI 上作者看不懂哪些是“世界设定”、哪些是“剧情已证实”

### 12.4 不要第一版就把 schema 做太厚

第一版目标是解决：

- 录入不方便
- 难以 selective injection
- 结构化世界观没有 ingestion 路径

而不是一次性完成最终形态的 Story Bible 系统。

---

## 13. 建议的下一步

如果本草案方向成立，下一步建议是：

1. 根据 review 结果先补一轮文档收敛
2. 再单独写一份 **worldbook implementation plan**
3. 第一版只做 `source.md -> structured.json -> meta.world` 的最小闭环

我建议把第一版成功标准压缩为：

- 作者能粘贴完整世界观文档
- 系统能产出可 review 的结构化结果
- apply 后 writing prompt 能按 scope 只读到相关世界观块

做到这三点，就已经显著优于当前“每行一条规则”的入口。

---

## 14. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-19 | 首版设计草案：提出 document-first worldbook、source/structured/prompt projection 三层模型，以及 `worldbook -> meta.world` 的第一阶段衔接路径 |
| 2026-06-19 | 用户 review 后回写为已确认决策：标题从“草案”改为“设计已确认”、4.4 节补充实现取向、待决问题 W1/W2/W4/W6 从“建议倾向”改为“本轮结论”、W6 明确不保留旧入口、新增 W7 回 `open-questions.md` |
| 2026-06-19 | 拆出 WK0–WK6 实施计划文档 `worldbook-implementation-plan.md`，同步更新 README.md 索引 |
| 2026-06-19 | WK5 已实现：移除创建阶段旧 `world_rules` 入口，Web 创建表单改为可选 `worldbook_source`，CLI 世界规则采集改为可跳过，并同步 README / 计划状态 |
| 2026-06-19 | WK6 已实现：补齐空 world 新路径、bootstrap 最小 meta 路径、template store 隔离 `worldbook_source` 的收口测试，并同步 README / 设计 / 实施计划状态 |
| 2026-06-19 | WB2.1 已实现：source 保存后立即清理旧 `structured.json`、状态回落到 `source_only`、apply 仅允许针对最新 extract 结果执行，并同步 README / 设计 / 实施计划状态 |
