"""Hot Canon patch 抽取与合并。"""

from __future__ import annotations

import copy
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.models import HotCanon

class CanonPatchParseError(ValueError):
    """LLM 输出无法解析为 Hot Canon patch。"""


_V2_WORLD_SCHEMA = """\
  "world": {
    "rules": ["全大陆通用规则"],
    "scoped": [
      {
        "scope_type": "faction|location",
        "scope_id": "势力或地点名称",
        "rules": ["仅适用于该范围的规则"]
      }
    ]
  }"""

_V2_CHARACTER_SCHEMA = """\
      "name": "角色名",
      "abilities": [
        {
          "id": "稳定英文ID必填",
          "name": "能力名",
          "kind": "skill|talent|passive|unknown",
          "level": 1,
          "summary": "简短说明",
          "introduced_in": "scene_001",
          "constraints": ["限制条件"]
        }
      ],
      "status": "当前状态",
      "relationships": {"其他角色": "关系"},
      "inventory": ["持有物"],
      "location": "当前位置\""""

_V2_PLOT_SCHEMA = """\
  "plot_threads": [
    {
      "id": "稳定ID必填",
      "title": "伏笔标题",
      "status": "open|advanced|closed",
      "introduced_in": "scene_001",
      "advanced_in": ["scene_002"],
      "closed_in": "",
      "related_characters": ["角色名"],
      "priority": "main|side",
      "note": "伏笔说明"
    }
  ]"""

_EXTRACT_SYSTEM_PROMPT = f"""\
你是轻小说 Hot Canon 抽取器。
从已采纳正文中抽取需要立即生效的事实型设定，且只输出 JSON 对象。
JSON schema:
{{
  "characters": [
    {{
{_V2_CHARACTER_SCHEMA}
    }}
  ],
{_V2_WORLD_SCHEMA},
{_V2_PLOT_SCHEMA}
}}
只包含正文中明确出现或强推出的变化；没有变化则输出空结构。不要输出解释、Markdown 或代码块。"""

_FIX_SYSTEM_PROMPT = f"""\
你是轻小说 Hot Canon 纠错器。
根据作者的纠错意图修正当前 Hot Canon，且只输出 JSON 对象。
JSON schema:
{{
  "characters": [
    {{
{_V2_CHARACTER_SCHEMA}
    }}
  ],
{_V2_WORLD_SCHEMA},
{_V2_PLOT_SCHEMA}
}}
只输出为落实纠错意图所需的变更；没有变更则输出空结构。不要输出解释、Markdown 或代码块。"""

_MIGRATE_SYSTEM_PROMPT = f"""\
你是轻小说 Hot Canon 迁移器。
将输入的 Hot Canon（可能为旧 schema）整理为完整、规范的 schema v2 JSON 对象。
JSON schema:
{{
  "schema_version": 2,
  "characters": [
    {{
{_V2_CHARACTER_SCHEMA}
    }}
  ],
{_V2_WORLD_SCHEMA},
{_V2_PLOT_SCHEMA}
}}
合并重复能力（相同含义只保留一条，使用稳定 id）；势力/地点专属规则放入 world.scoped。
输出完整 canon，不要 patch。不要输出解释、Markdown 或代码块。"""


class CanonExtractor:
    def __init__(self, model: Any) -> None:
        self._model = model

    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon:
        messages = [
            SystemMessage(content=_EXTRACT_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "当前 Hot Canon:\n"
                    f"{json.dumps(canon.to_dict(), ensure_ascii=False, indent=2)}\n\n"
                    "已采纳正文:\n"
                    f"{adopted_text}"
                )
            ),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        return HotCanon.from_dict(_parse_json_object(text))

    def extract_fix_patch(self, correction_intent: str, canon: HotCanon) -> HotCanon:
        messages = [
            SystemMessage(content=_FIX_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "当前 Hot Canon:\n"
                    f"{json.dumps(canon.to_dict(), ensure_ascii=False, indent=2)}\n\n"
                    "作者纠错意图:\n"
                    f"{correction_intent}"
                )
            ),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        return HotCanon.from_dict(_parse_json_object(text))

    def migrate_full_canon(self, canon: HotCanon) -> HotCanon:
        messages = [
            SystemMessage(content=_MIGRATE_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "当前 Hot Canon:\n"
                    f"{json.dumps(canon.to_dict(), ensure_ascii=False, indent=2)}"
                )
            ),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        return HotCanon.from_dict(_parse_json_object(text))


def is_empty_canon_patch(patch: HotCanon) -> bool:
    data = patch.to_dict()
    if data.get("characters") or data.get("plot_threads"):
        return False
    world = data.get("world", {})
    if not isinstance(world, dict):
        return True
    if world.get("rules"):
        return False
    scoped = world.get("scoped", [])
    if isinstance(scoped, list):
        for entry in scoped:
            if isinstance(entry, dict) and entry.get("rules"):
                return False
    return True


def merge_hot_canon(base: HotCanon, patch: HotCanon) -> HotCanon:
    base_data = copy.deepcopy(base.to_dict())
    patch_data = patch.to_dict()

    base_data["characters"] = _merge_named_items(
        base_data.get("characters", []),
        patch_data.get("characters", []),
        key="name",
    )
    base_world = base_data.setdefault("world", {"rules": [], "scoped": []})
    patch_world = patch_data.get("world", {})
    if not isinstance(patch_world, dict):
        patch_world = {}
    base_world["rules"] = _merge_unique(
        base_world.get("rules", []),
        patch_world.get("rules", []),
    )
    base_world["scoped"] = _merge_scoped(
        base_world.get("scoped", []),
        patch_world.get("scoped", []),
    )
    base_data["plot_threads"] = _merge_plot_threads(
        base_data.get("plot_threads", []),
        patch_data.get("plot_threads", []),
    )
    base_data["schema_version"] = 2
    return HotCanon.from_dict(base_data)


def format_canon_diff(before: HotCanon, patch: HotCanon, after: HotCanon) -> str:
    return "\n\n".join(
        [
            "Hot Canon 变更提案:",
            json.dumps(patch.to_dict(), ensure_ascii=False, indent=2),
            "合并后 Hot Canon:",
            json.dumps(after.to_dict(), ensure_ascii=False, indent=2),
        ]
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise CanonPatchParseError(f"Hot Canon patch 不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CanonPatchParseError("Hot Canon patch 根节点必须是 JSON 对象")
    return data


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _merge_scoped(
    base_items: list[Any],
    patch_items: list[Any],
) -> list[dict[str, Any]]:
    merged = copy.deepcopy(
        [entry for entry in base_items if isinstance(entry, dict)]
    )
    index = {
        (str(item.get("scope_type", "")), str(item.get("scope_id", ""))): item
        for item in merged
        if item.get("scope_id")
    }
    for patch_item in patch_items:
        if not isinstance(patch_item, dict):
            continue
        scope_type = str(patch_item.get("scope_type", "location"))
        scope_id = str(patch_item.get("scope_id", ""))
        if not scope_id:
            continue
        key = (scope_type, scope_id)
        if key in index:
            index[key]["rules"] = _merge_unique(
                index[key].get("rules", []),
                patch_item.get("rules", []),
            )
        else:
            merged.append(
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "rules": [
                        str(rule)
                        for rule in patch_item.get("rules", [])
                        if isinstance(patch_item.get("rules"), list)
                    ],
                }
            )
            index[key] = merged[-1]
    return merged


def _merge_named_items(
    base_items: list[dict[str, Any]],
    patch_items: list[dict[str, Any]],
    *,
    key: str,
) -> list[dict[str, Any]]:
    merged = copy.deepcopy(base_items)
    index = {
        item.get(key): item
        for item in merged
        if isinstance(item, dict) and item.get(key)
    }
    for patch_item in patch_items:
        if not isinstance(patch_item, dict):
            continue
        patch_key = patch_item.get(key)
        if patch_key and patch_key in index:
            _merge_character_in_place(index[patch_key], patch_item)
        else:
            merged.append(copy.deepcopy(patch_item))
            if patch_key:
                index[patch_key] = merged[-1]
    return merged


def _merge_character_in_place(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for field, value in patch.items():
        if value is None:
            continue
        if field == "abilities":
            base["abilities"] = _merge_abilities_by_id(
                base.get("abilities", []),
                value if isinstance(value, list) else [],
            )
        elif field == "relationships" and isinstance(value, dict):
            current = base.get("relationships", {})
            if isinstance(current, dict):
                nested = copy.deepcopy(current)
                nested.update(value)
                base["relationships"] = nested
            else:
                base["relationships"] = copy.deepcopy(value)
        elif isinstance(value, list):
            base[field] = _merge_unique(base.get(field, []), value)
        elif isinstance(value, dict):
            current = base.get(field, {})
            if isinstance(current, dict):
                nested = copy.deepcopy(current)
                nested.update(value)
                base[field] = nested
            else:
                base[field] = copy.deepcopy(value)
        else:
            base[field] = value


def _merge_abilities_by_id(
    base_items: list[Any],
    patch_items: list[Any],
) -> list[dict[str, Any]]:
    from lnagent.memory.canon_migrate import parse_legacy_ability_string

    merged: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}

    def add_entry(raw: Any) -> None:
        if isinstance(raw, str):
            entry = parse_legacy_ability_string(raw)
        elif isinstance(raw, dict):
            entry = copy.deepcopy(raw)
            if not entry.get("id"):
                from lnagent.memory.canon_migrate import slugify

                entry["id"] = slugify(str(entry.get("name", "ability")))
        else:
            return
        ability_id = str(entry.get("id", ""))
        if not ability_id:
            return
        if ability_id in index:
            _merge_dict_in_place(index[ability_id], entry, skip_abilities=True)
        else:
            index[ability_id] = entry
            merged.append(entry)

    for item in base_items:
        add_entry(item)
    for item in patch_items:
        add_entry(item)
    return merged


def _merge_plot_threads(
    base_items: list[dict[str, Any]],
    patch_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = copy.deepcopy(base_items)
    index = {
        item.get("id"): item
        for item in merged
        if isinstance(item, dict) and item.get("id")
    }
    for patch_item in patch_items:
        if not isinstance(patch_item, dict):
            continue
        patch_id = patch_item.get("id")
        if patch_id and patch_id in index:
            _merge_plot_thread_in_place(index[patch_id], patch_item)
        elif patch_item not in merged:
            merged.append(copy.deepcopy(patch_item))
            if patch_id:
                index[patch_id] = merged[-1]
    return merged


def _merge_plot_thread_in_place(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if value is None:
            continue
        if key == "advanced_in" and isinstance(value, list):
            base[key] = _merge_unique(base.get(key, []), value)
        elif isinstance(value, list) and key == "related_characters":
            base[key] = _merge_unique(base.get(key, []), value)
        elif isinstance(value, list):
            base[key] = _merge_unique(base.get(key, []), value)
        else:
            base[key] = value


def _merge_dict_in_place(
    base: dict[str, Any],
    patch: dict[str, Any],
    *,
    skip_abilities: bool = False,
) -> None:
    for key, value in patch.items():
        if value is None:
            continue
        if key == "abilities" and not skip_abilities:
            base[key] = _merge_abilities_by_id(base.get(key, []), value)
            continue
        if isinstance(value, list):
            if key == "advanced_in" or key == "related_characters" or key == "constraints":
                base[key] = _merge_unique(base.get(key, []), value)
            else:
                base[key] = _merge_unique(base.get(key, []), value)
        elif isinstance(value, dict):
            current = base.get(key, {})
            if isinstance(current, dict):
                nested = copy.deepcopy(current)
                nested.update(value)
                base[key] = nested
            else:
                base[key] = copy.deepcopy(value)
        else:
            base[key] = value


def _merge_unique(base: list[Any], patch: list[Any]) -> list[Any]:
    merged = list(base)
    for item in patch:
        if item not in merged:
            merged.append(item)
    return merged
