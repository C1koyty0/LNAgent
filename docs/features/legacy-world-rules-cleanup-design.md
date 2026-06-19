# 旧 `world_rules` 兼容包袱收口设计

> **状态**：草案，待 review  
> **范围**：LNAgent 中 `NovelMeta` / `world_rules` 旧数组入口的兼容包袱收口  
> **目标**：在不破坏现有读盘迁移（v1 → v2）的前提下，清理已不需要的旧构造路径、旧校验逻辑和死代码，并与 WK5/WK6 移除旧录入入口的决策形成一条完整的收束线。

---

## 1. 背景与动机

LNAgent 的世界观录入经历了以下演进：

| 阶段 | 录入方式 | `meta.json` 形态 |
|------|---------|-----------------|
| v1（原始） | CLI 每行一条 `world_rules` | `{"world_rules": ["规则1", "规则2"]}` |
| v2（meta schema 演进） | `InitVar world_rules` + 惰性迁移 → `world.rules` + `world.scoped` | `{"world": {"rules": [...], "scoped": [...]}}` |
| WK5（移除旧入口） | Web 改为 optional `worldbook_source`；CLI 改为可跳过 | 同上 |
| WK6–WB2.1（收口） | source → extract → apply 覆盖 `meta.world` | 同上 |

**当前问题**：虽然录入入口已经切到 document-first，`NovelMeta` 内部仍然带着一整套旧兼容包袱：

- `InitVar world_rules` + `__post_init__` 桥接逻辑
- `@property world_rules` 向后兼容只读访问器
- `collect_novel_meta()` 仍提示“世界规则（每行一条）”
- `_validate_world_content()` 仍检查 `world_rules` 字段
- `split_rules_for_display()` 死代码
- 73 处测试仍通过 `world_rules=` 构造 `NovelMeta`

WK2 实施计划已标记为 follow-up：  
> "已知 follow-up：当前 `NovelMeta` / `world_rules` 仍带有旧数组入口兼容包袱；该问题暂不在 WK2 内修补，后续随 meta/world 结构化改造一并处理"

现在是收束这条线的时机。

---

## 2. 设计目标

### P0
- 保持对 v1 `meta.json`（含 `world_rules` 字段）的读盘兼容
- 清理不需要在运行时携带的构造路径
- 不破坏现有 195 tests 的正常运行

### P1
- 收束 CLI 旧录入提示，与 WK5 已决议保持一致
- 移除死代码
- 更新相关设计文档，消除“旧入口仍可用”的歧义

### P2
- 测试 fixture 渐进升级为 `world=WorldCanon(...)` 形态（非强制一次性迁移）

---

## 3. 非目标

- **不移除** `upgrade_meta_dict()` / `_migrate_legacy_world_rules()` —— 读盘 v1 → v2 迁移必须保留
- **不删除** `meta_migrate.py` —— 读盘惰性迁移是持久需求
- **不更改** `meta.json` 磁盘格式 —— schema v2 已稳定
- **不修改** `worldbook apply` 覆盖 `meta.world` 的语义
- **不引入** `preview_stale` 或新的状态字段

---

## 4. 当前状态审计

### 4.1 读盘路径（保留不变）

```
meta.json (v1, world_rules[]) → upgrade_meta_dict() → world.rules + world.scoped
                              → NovelMeta.from_dict() → 正常构造
```

这是稳定路径，**不纳入本次清理范围**。

### 4.2 构造路径（待清理的兼容包袱）

| 位置 | 内容 | 影响 |
|------|------|------|
| `models.py:280` | `world_rules: InitVar[list[str] \| None] = None` | 所有 `NovelMeta(...)` 构造都可在参数中传递 `world_rules=` |
| `models.py:291–298` | `__post_init__` 桥接：`world_rules → WorldCanon(rules=[...])` | 仅在 `world.rules` 和 `world.scoped` 均为空时触发 |
| `models.py:300–303` | `@property world_rules` → `self.world.rules` | 向后兼容只读访问；仅 1 处测试使用 |
| `project.py:20–28` | `collect_novel_meta()` 提示“世界规则（每行一条）” | CLI 新项目创建仍走旧交互（虽然可跳过） |
| `project.py:28` | `return NovelMeta(title=title, world_rules=world_rules, style=style)` | 唯一的**生产**调用点用 `world_rules=` 构造 |
| `project.py:113–117` | `_validate_world_content()` 检查 `world_rules` 字段 | 加载外部 meta.json 时的校验 |

### 4.3 测试面（73 处）

```
test_memory_store.py         58 处　NovelMeta(title=..., world_rules=..., style=...)
test_discussion_brief.py      7 处
test_web_bootstrap.py         3 处
test_meta_schema_v2.py        3 处  （其中 2 处是 v1 兼容测试，1 处用 world=WorldCanon(...)）
test_worldbook_apply.py       2 处  （1 处用 world=WorldCanon(...)，1 处用 world_rules=[]）
```

### 4.4 死代码

| 位置 | 函数 | 说明 |
|------|------|------|
| `meta_migrate.py:129` | `split_rules_for_display()` | 定义但从未被 import；注释说“供测试与工具使用”但无人调用 |

### 4.5 文档

| 文档 | 提及 `world_rules` | 需要更新? |
|------|-------------------|-----------|
| `meta-schema-evolution-plan.md` | "`InitVar world_rules` 支持旧构造方式" | 是 |
| `memory-mvp-plan.md` | L4：meta 注入 `world_rules` | 是（改为 `world.rules`） |
| `style-template-implementation-plan.md` | 模板不影响 `world_rules` | 是 |
| `worldbook-implementation-plan.md` | WK2 follow-up note | 是（勾选为已收口） |
| `open-questions.md` | L4、W7 | W7 已决议，不变 |

---

## 5. 核心设计决策（需要 review）

### D1：`InitVar world_rules` 的去留

**背景**：这是整个兼容包袱的根。`InitVar` 意味着 `world_rules` 只在构造函数中存在，不进入 `__dict__`，不被序列化。它存在的唯一目的是让调用方可以写：

```python
NovelMeta(title="书", world_rules=["魔法存在"], style="轻松")
```

而不是：

```python
NovelMeta(title="书", world=WorldCanon(rules=["魔法存在"]), style="轻松")
```

**当前使用面**：

| 类别 | 调用数 | 示例 |
|------|--------|------|
| 生产代码 | 1 处 | `collect_novel_meta()` |
| 测试代码 | ~73 处 | `NovelMeta(title="书", world_rules=["魔法存在"], style="轻松")` |

**建议（倾向 A）**：**移除 `InitVar world_rules`**。

理由：
- WK5/WK6 已决议“不保留旧入口”
- 仅剩 1 处生产调用点（`collect_novel_meta`），可以一并收束
- 测试可批量替换为 `world=WorldCanon(rules=[...])` 或保持 `world_rules=[]` → 改为 `world=WorldCanon()`（空 world）
- 消除 InitVar 的隐式行为，使 `NovelMeta` 的构造语义更清晰：world 就是 world，不存在两个入口

**替代方案 B**：保留 `InitVar world_rules` 作为永久便捷入口。
- 优点：零改动成本
- 缺点：与 WK5/WK6 决策矛盾；新开发者看到两个入口会困惑

**替代方案 C**：保留但添加 `DeprecationWarning`。
- 优点：温和过渡
- 缺点：增加噪音；74 处调用全部告警

> 🔴 **需要确认**：是否接受方案 A（移除 `InitVar world_rules`，一次改完）？

### D2：`@property world_rules` 的去留

**背景**：这是个只读属性，返回 `self.world.rules`。仅 1 处测试在使用（`test_memory_store.py:81`）。

**建议（倾向移除）**：
- 语义不精确：`world_rules` 的名字暗示“所有世界观规则”，但它只返回 `world.rules`（全局），不含 `world.scoped`
- 唯一的调用方可以改为 `meta.world.rules`

> 🔴 **需要确认**：是否移除 `@property world_rules`？如果 D1 采用方案 B/C，这个属性可以保留。

### D3：`collect_novel_meta()` 世界规则采集的去留

**背景**：WK5 已将 CLI 世界规则采集改为“可选跳过”（输入空行 = 跳过），但提示文本仍然是“世界规则（每行一条，空行结束；直接回车可跳过）”。

**建议（倾向移除提示）**：
- 改为“世界规则（已由 worldbook 管理，此处跳过；直接回车继续）”
- 或直接移除采集环节，让 CLI 新项目创建只收集 title + style
- 对应的构造调用改为 `NovelMeta(title=title, style=style)`

> 🔴 **需要确认**：CLI 新项目创建要不要保留“逐行输入世界规则”的功能？还是完全移除？

### D4：`_validate_world_content()` 中 `world_rules` 校验的去留

**背景**：此函数在加载外部 meta.json 时运行，检查 `world_rules` 是否为数组。

**建议（移除校验，只保留 world 块校验）**：
- `upgrade_meta_dict()` 已经在 `NovelMeta.from_dict()` 中处理了 `world_rules` → `world` 的迁移
- 外部 JSON 如果包含 `world_rules`，迁移层会处理，不需要额外校验
- 如果外部 JSON 同时包含 `world_rules` 和 `world`，`upgrade_meta_dict` 已经处理了这种情况

> 🔴 **需要确认**：是否移除 `_validate_world_content()` 中的 `world_rules` 校验？

### D5：`split_rules_for_display()` 死代码

**事实**：定义在 `meta_migrate.py:129`，从未被 import 或调用。

**建议（移除）**：零影响。

> 此项不需要讨论，可直接移除。

---

## 6. 推荐的实施路径（Phase 1）

如果 D1–D4 全部按建议方向确认，实施可分为三个层次：

### L1：CLI 入口收束（D3）
- `collect_novel_meta()` 移除世界规则采集提示
- `NovelMeta(title=title, style=style)` 直接构造

### L2：模型层清理（D1, D2, D5）
- 移除 `NovelMeta.__post_init__` 桥接逻辑
- 将 `world_rules: InitVar[...]` 改为普通字段（或直接删除参数）
- 移除 `@property world_rules`
- 移除 `split_rules_for_display()`
- 移除 `_validate_world_content()` 中 `world_rules` 分支

### L3：测试迁移（D1 连带）
- 将 73 处 `NovelMeta(..., world_rules=[...], ...)` 替换为 `NovelMeta(..., world=WorldCanon(rules=[...]), ...)`
- 空 world 的替换为 `NovelMeta(..., world=WorldCanon(), ...)` 或直接用默认值

### L4：文档同步
- 更新 `meta-schema-evolution-plan.md`
- 更新 `memory-mvp-plan.md`
- 更新 `style-template-implementation-plan.md`
- 在 `worldbook-implementation-plan.md` 中勾选 follow-up 为已收口

---

## 7. 与现有系统的集成

- **读盘路径**：`upgrade_meta_dict()` 不受影响，v1 meta.json 仍可正常加载
- **worldbook apply**：覆盖 `meta.world`，不受影响
- **prompt 注入**：读 `meta.world.rules` + `meta.world.scoped`，不受影响
- **meta 编辑 API**：只编辑叙事字段，不涉及 `world`，不受影响
- **模板系统**：模板不持久化 `world_rules`，不受影响
- **读盘测试**：`test_meta_schema_v2.py` 中已有的 v1 → v2 迁移测试保留

---

## 8. 风险与注意事项

| 风险 | 缓解 |
|------|------|
| 测试批量迁移可能引入错误 | 分步 commit，每次替换后立即跑全量测试 |
| `collect_novel_meta()` 移除后 CLI 启动体验变化 | 在提示中说明“世界观由 worldbook 管理” |
| 外部脚本依赖 `meta.world_rules` 属性 | `git grep world_rules` 确认无外部使用 |
| `__post_init__` 移除后 `world_rules=` 参数消失导致 `TypeError` | Python 类型检查 + 全量测试会在迁移阶段捕获 |

---

## 9. 待决问题

| ID | 问题 | 建议 |
|----|------|------|
| D1 | 是否移除 `InitVar world_rules`？ | ✅ 移除 |
| D2 | 是否移除 `@property world_rules`？ | ✅ 移除 |
| D3 | CLI 世界规则提示是否移除？ | ✅ 移除（改为一行说明） |
| D4 | 是否移除 `_validate_world_content()` 中的 world_rules 校验？ | ✅ 移除 |
| D5 | 是否移除 `split_rules_for_display()`？ | ✅ 移除（死代码） |

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-19 | 初稿：审计当前状态，梳理 5 项决策，给出建议方向 |
