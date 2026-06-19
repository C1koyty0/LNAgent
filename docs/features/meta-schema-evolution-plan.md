# meta.json Schema 演进计划（路线 B）

> **目标**：开书设定结构化，支持 `world.rules`（全局）+ `world.scoped`（势力/地点），并按当前场景**按需注入** Prompt。  
> **与 Hot Canon 分工**：meta = 作者开书圣经（静态）；`canon.json` = 剧情中已确认事实（动态）。  
> **关联**：[canon-schema-evolution-plan.md](./canon-schema-evolution-plan.md)

---

## 1. 已确认决策

| 议题 | 决议 |
|------|------|
| 结构 | 与 Hot Canon 对齐：`world.rules` + `world.scoped[]`（`faction` / `location`） |
| 迁移 A | 读盘惰性升级；`world_rules[]` 按「名称 - 正文」启发式拆入 scoped |
| 迁移 B | `/meta migrate`（LLM 整表 → y/n → 写盘） |
| Prompt | 与 Canon 共用 `resolve_active_scopes`（角色 location + Cold location） |
| 兼容 | 读 v1、写 v2；保留 `upgrade_meta_dict()` 负责旧 `world_rules[]` 的读盘迁移 |

---

## 2. Schema v2

```json
{
  "schema_version": 2,
  "title": "书名",
  "style": "文风",
  "world": {
    "rules": ["全大陆通用…"],
    "scoped": [
      {
        "scope_type": "faction",
        "scope_id": "洛兰分封王国",
        "rules": ["政体、外交、专属能力…"]
      }
    ]
  },
  "pov": "",
  "tense": "",
  "taboos": [],
  "target_audience": "",
  "narrative_rules": [],
  "genre": "",
  "tone": ""
}
```

---

## 3. 实现清单（已完成）

- [x] `lnagent/memory/meta_migrate.py` — 惰性升级与势力规则拆分
- [x] `lnagent/memory/meta_display.py` — `/meta` 展示与 Prompt 格式化
- [x] `lnagent/memory/meta_extractor.py` — 迁移 B LLM
- [x] `lnagent/memory/models.py` — `NovelMeta.world` + `schema_version`
- [x] `lnagent/memory/prompt.py` — 按需注入 meta scoped
- [x] `lnagent/cli/meta_cmd.py` — `/meta`、`/meta migrate`
- [x] `lnagent/project.py` — 校验 `world` 结构，并允许 v1 `world_rules` 通过读盘迁移进入 v2
- [x] `tests/test_meta_schema_v2.py`

---

## 4. 使用说明（test1）

1. 启动 `python main.py --project test1` — 首次 `load_meta` 自动拆分各国条目到 `world.scoped`（内存）；保存 meta 需显式操作。
2. 执行 `/meta` 查看拆分结果。
3. 满意后 `/meta migrate` 或另存：在 migrate 确认后写入 `meta.json` v2。
4. 续写时仅注入与当前 **location** 匹配的势力/地点块 + 全局规则。

---

## 5. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-29 | 路线 B 完整实现 |
