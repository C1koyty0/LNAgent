# Hot Canon Schema 演进计划（Phase 7.1+）

> **目标**：将 Hot Canon 从 MVP 的松散 `dict` + 长字符串，升级为可追踪、可合并、可按范围注入的结构化 Story Bible，支撑**长篇 + 宏大世界观**。  
> **原则**：Schema 由框架定义；LLM 仅在固定 schema 内从正文**抽取/纠错**；作者 **y/n** 后写盘。LLM **不会**自动演进 schema。  
> **设计依据**：[memory-architecture.md](./memory-architecture.md)、[memory-mvp-plan.md](./memory-mvp-plan.md) Phase 7+  
> **待决 backlog**：[open-questions.md](./open-questions.md)（S2、S3、S4）

---

## 1. 已确认决策（2026-05-29）

| 议题 | 决议 |
|------|------|
| 迁移策略 | **A + B**：读盘惰性升级（规则解析）+ 可选一次性精修（`/canon migrate` 或等价命令，LLM 转表 → diff → y/n） |
| 实施顺序 | **S3 优先**（势力/地点规则分层）→ S2（能力结构化）→ S4（伏笔生命周期）→ 按需 Prompt 注入 → 迁移命令（B） |
| `ability.id` | 抽取时 LLM **必填**；代码对 `name` 做 slug **兜底** |
| `level` | **整数**；展示格式化为 `Lv.{n}` |
| 兼容期 | **读 v1、写 v2** 至少保留一个发布周期；缺 `schema_version` 视为 v1 |
| `/c` 展示 | 自 S2 阶段起改为**人类可读摘要**（非 raw JSON dump） |
| 向量 RAG / 分卷 R3 | **不在本计划**；本计划为 R1/R3 的前置 |

---

## 2. 现状与痛点（MVP v1）

当前 `canon.json`（`schema_version` 缺省为 **1**）：

```json
{
  "characters": [{ "name": "…", "abilities": ["长字符串…"], "…": "…" }],
  "world": { "rules": ["全局平铺…"] },
  "plot_threads": [{ "id": "可选", "status": "…", "note": "…" }]
}
```

| 痛点 | 影响 |
|------|------|
| `abilities[]` 为字符串，merge 按整段去重 | 表述略变即重复（如 test1 重复「能量感知」） |
| `world.rules[]` 仅全局列表 | 多势力/多地区设定无法挂 scope，Prompt 只能全量或硬裁剪 |
| `plot_threads` 字段过少 | 长篇难以追踪「何时埋下/推进/收束」 |
| `_format_hot_canon` 整份 JSON 注入 | token 浪费，无关势力规则干扰生成 |

---

## 3. 目标 Schema（v2 概览）

```json
{
  "schema_version": 2,
  "characters": [
    {
      "name": "伽紫",
      "abilities": [
        {
          "id": "energy_sense",
          "name": "能量感知",
          "kind": "skill",
          "level": 1,
          "summary": "主动感知半径10m内能量流动…",
          "introduced_in": "scene_001",
          "constraints": ["持续消耗微量精神力"]
        }
      ],
      "status": "…",
      "relationships": {},
      "inventory": [],
      "location": "洛兰王都"
    }
  ],
  "world": {
    "rules": ["全大陆通用规则…"],
    "scoped": [
      {
        "scope_type": "faction",
        "scope_id": "洛兰分封王国",
        "rules": ["骑士守护合击…"]
      },
      {
        "scope_type": "location",
        "scope_id": "白色空间",
        "rules": ["转生准备空间内…"]
      }
    ]
  },
  "plot_threads": [
    {
      "id": "ability_selection",
      "title": "转生能力选择",
      "status": "closed",
      "introduced_in": "scene_001",
      "advanced_in": [],
      "closed_in": "scene_001",
      "related_characters": ["伽紫", "艾露娜"],
      "priority": "main",
      "note": "…"
    }
  ]
}
```

**写入规则**：checkpoint（adopt / fix / reconcile / `/sc` / 退出 save）落盘时 **`schema_version` 恒为 2**。

---

## 4. 分阶段任务

**进度标记**：`[ ]` 未开始 · `[x]` 已完成并通过验收

### Phase 7.1：S3 — 世界观规则分层（P0，优先）

> **为何先做**：长篇 + 宏大世界观下，势力/地点规则是分块注入与控制 token 的基础；与 `meta.json` 开书设定互补（meta 偏静态 bible，Hot 偏剧情中已确认事实）。

- [x] **7.1.1 数据模型**：`WorldCanon` 增加 `scoped[]`；`ScopedWorldRules`（`scope_type`、`scope_id`、`rules[]`）  
  产出：`lnagent/memory/models.py`
- [x] **7.1.2 抽取 schema**：`CanonExtractor` prompt 支持 `world.scoped` patch；`world.rules` 仍为全局  
  产出：`lnagent/memory/canon_extractor.py`
- [x] **7.1.3 Merge**：`scoped` 按 `(scope_type, scope_id)` 合并；`rules` 数组合并去重  
  产出：`canon_extractor.py`
- [x] **7.1.4 迁移 A（惰性）**：v1 仅 `world.rules` 时原样读入；`scoped` 默认 `[]`（不做激进拆分）  
  产出：`lnagent/memory/canon_migrate.py`
- [x] **7.1.5 测试**：scoped merge、v1→v2 读盘、空 scoped  
  产出：`tests/test_canon_schema_v2.py`

**验收**：

- [x] adopt 后可将「洛兰专属规则」写入 `world.scoped`，且不与全局 `rules` 混写
- [x] 旧项目仅 `world.rules` 仍可启动；首次写盘后含 `schema_version: 2`

---

### Phase 7.2：S2 — 能力结构化（P0）

- [x] **7.2.1 数据模型**：能力对象字段（`id`、`name`、`kind`、`level`、`summary`、`introduced_in`、`constraints[]`）  
  产出：`canon_migrate.py` 归一化
- [x] **7.2.2 抽取 + Merge**：`abilities` 按 **`id`** 合并；标量覆盖、`constraints` 数组合并去重  
  产出：`canon_extractor.py`
- [x] **7.2.3 迁移 A**：v1 字符串 `abilities[]` → 启发式解析 + 同角色按 `id` 去重  
  产出：`canon_migrate.py`
- [x] **7.2.4 `/c` 摘要**：按角色列出能力（`Lv.n` + name + summary）  
  产出：`lnagent/memory/canon_display.py`
- [x] **7.2.5 测试**：merge 同 id 升级 level；字符串迁移样例  

**验收**：

- [x] test1 类 canon 迁移后「能量感知」合并为单条（同 `id`）（单测覆盖）
- [x] 新 adopt 产出带稳定 `id` 的能力对象；y/n 流程不变

---

### Phase 7.3：S4 — 伏笔生命周期（P1）

- [x] **7.3.1 数据模型**：`PlotThreadEntry` 扩展字段（见 §3）  
- [x] **7.3.2 抽取 + Merge**：`id` 抽取必填；`advanced_in` 数组合并  
- [x] **7.3.3 `/c`**：列出伏笔及 `status` / `introduced_in`  
- [x] **7.3.4 测试**：按 id 更新 status / closed_in

**验收**：

- [x] `/c` 可区分已收束 / 未收束伏笔
- [x] `/f` 与 adopt 使用**同一** v2 patch schema

---

### Phase 7.4：按需 Prompt 注入（P1）

> 依赖 7.1 `world.scoped` 与角色 `location`、Cold 条目 `location`。

- [x] **7.4.1 上下文解析**：`character.location`、上一场景 Cold `location`  
  产出：`lnagent/memory/canon_context.py`
- [x] **7.4.2 注入策略**：全局 `rules` + 匹配 `scoped` + 压缩角色/未收束伏笔  
  产出：`lnagent/memory/canon_display.py`、`prompt.py`
- [x] **7.4.3 测试**：多 scoped 时仅注入匹配块

**验收**：

- [x] 角色 location 与 scoped 通过名称片段匹配时，Prompt 含对应 scoped（单测覆盖）

---

### Phase 7.5：迁移 B — 一次性精修（P2，可选命令）

- [x] **7.5.1 `/canon migrate`**：读取当前 canon → LLM 转 v2 全表 → diff → y/n → 写盘  
  产出：`lnagent/cli/canon_migrate.py`、`commands.py`、`main.py`
- [x] **7.5.2 安全**：已为 v2 时需 `--force`；不改正文、不写 `adopt_stack`  
  产出：`lnagent/cli/canon_migrate.py`、`commands.py`、`main.py`
- [x] **7.5.3 手工**：test1 项目跑通 migrate B（作者已手工验收，待文档同步）
**验收**：

- [x] test1 经 migrate B 后结构清晰（作者已手工 spot-check）；作者可 n 拒绝（流程已实现）

---

## 5. Merge 规则摘要（v2）

| 实体 | 主键 | 合并行为 |
|------|------|----------|
| `characters[]` | `name` | 与 MVP 相同；嵌套字段递归 merge |
| `abilities[]` | `id` | 同 id 覆盖 `level`、`summary` 等；`constraints` 追加去重 |
| `world.rules[]` | — | 字符串追加去重 |
| `world.scoped[]` | `(scope_type, scope_id)` | 同 scope 合并 `rules[]` |
| `plot_threads[]` | `id` | 同 id 覆盖标量；`advanced_in` 追加去重 |

**空 patch / JSON 解析失败**：与 MVP 一致，提示重试，不 silent fail。

---

## 6. 迁移策略详述（A + B）

### 6.1 迁移 A（惰性，默认）

触发：`JsonMemoryStore.load_canon()` 或 `HotCanon.from_dict()` 检测到 `schema_version` 缺省或 `< 2`。

| v1 字段 | v2 处理 |
|---------|---------|
| `world.rules` | 保留为 `world.rules` |
| （无 scoped） | `scoped: []`；可选启发式拆分（7.1.4，保守） |
| `abilities` 字符串 | 7.2.3 解析为 `AbilityEntry` |
| `plot_threads` | 补全缺省字段为空；`id` 仍可选 |

写盘：任意 checkpoint 时将内存 v2 写入，`schema_version: 2`。

### 6.2 迁移 B（一次性精修）

适用：test1 等复杂 canon、A 解析质量不足时。

流程：展示当前 canon → LLM 输出完整 v2 JSON → diff → y/n → `save_canon`。

**不替代**日常 adopt 抽取；仅结构升级。

---

## 7. LLM 与作者边界（再强调）

```
正文 adopt ──► LLM 抽 patch（schema v2）──► merge ──► diff ──► 作者 y/n ──► canon.json
/canon migrate B ──► LLM 整表转 v2 ──► diff ──► 作者 y/n ──► canon.json
```

- LLM **不**新增顶层字段、**不**改 merge 代码逻辑。  
- Schema 变更 **仅**通过本计划发版 + 迁移 A/B 完成。

---

## 8. 模块与文件（预计）

```
lnagent/memory/
├── models.py              # AbilityEntry, ScopedWorldRules, schema_version
├── canon_migrate.py       # v1→v2 惰性升级与字符串解析
├── canon_extractor.py     # prompt + merge 扩展
├── canon_display.py       # /c 人类可读（可选）
├── prompt.py              # 7.4 按需注入
└── store.py               # 版本读写

lnagent/cli/
├── canon_migrate.py       # 7.5 /canon migrate（可选）
└── commands.py            # 路由

tests/
└── test_canon_schema_v2.py  # 或并入 test_memory_store.py
```

---

## 9. 测试策略

| 层级 | 内容 |
|------|------|
| 单元 | scoped/ability/plot merge；v1 读入 v2 内存；迁移 A 样例 JSON |
| 集成 | mock LLM：adopt → scoped + ability 对象写入 |
| 手工 | test1：7.1 后写入洛兰 scoped；7.2 后重复能力合并；7.5 migrate B |

---

## 10. 完成标准（Definition of Done）

本计划（7.1–7.4 核心）视为完成当：

- [x] `canon.json` 带 `schema_version: 2`，且 v1 项目可加载并升级写盘  
- [x] `world.scoped` 支持 faction/location，merge 与抽取稳定  
- [x] `abilities` 按 `id` 合并，无「同能力多字符串」退化  
- [x] `plot_threads` 可表达引入/推进/收束场景  
- [x] Prompt 按当前 scope 注入相关 scoped rules（7.4）  
- [x] `/c` 为人类可读摘要  
- [x] adopt / fix / undo / reconcile 流程与 y/n 语义不变  

7.5 migrate B 已实现并完成 `test1` 手工 migrate spot-check。

---

## 11. 与 Phase 7+ 其他项的关系

| 项 | 关系 |
|----|------|
| R1 向量 RAG | 结构化 `id` / `scope_id` 便于日后索引；本计划不实现检索 |
| R3 分卷结构 | 独立计划；`introduced_in` 仍用 `scene_XXX` |
| meta.json | 静态开书设定；scoped 承载剧情中**已确认**的势力/地点规则 |

---

## 12. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-29 | 初稿：S3 优先；迁移 A+B；能力 id/整数 level；读 v1 写 v2 |
| 2026-05-29 | Phase 7.1–7.5 代码实现完成；单测 92 项通过 |
| 2026-06-04 | 同步 7.5 手工验收状态：`test1` migrate B 已由作者手工确认 |
