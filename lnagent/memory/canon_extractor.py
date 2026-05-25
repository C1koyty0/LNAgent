"""Hot Canon patch 抽取与合并。"""

from __future__ import annotations

import copy
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.models import HotCanon


class CanonPatchParseError(ValueError):
    """LLM 输出无法解析为 Hot Canon patch。"""


_EXTRACT_SYSTEM_PROMPT = """\
你是轻小说 Hot Canon 抽取器。
从已采纳正文中抽取需要立即生效的事实型设定，且只输出 JSON 对象。
JSON schema:
{
  "characters": [
    {
      "name": "角色名",
      "abilities": ["能力"],
      "status": "当前状态",
      "relationships": {"其他角色": "关系"},
      "inventory": ["持有物"],
      "location": "当前位置"
    }
  ],
  "world": {"rules": ["世界规则"]},
  "plot_threads": [{"id": "可选稳定ID", "status": "open|advanced|closed", "note": "伏笔说明"}]
}
只包含正文中明确出现或强推出的变化；没有变化则输出空结构。不要输出解释、Markdown 或代码块。"""


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


def merge_hot_canon(base: HotCanon, patch: HotCanon) -> HotCanon:
    base_data = copy.deepcopy(base.to_dict())
    patch_data = patch.to_dict()

    base_data["characters"] = _merge_named_items(
        base_data.get("characters", []),
        patch_data.get("characters", []),
        key="name",
    )
    base_world = base_data.setdefault("world", {})
    patch_world = patch_data.get("world", {})
    base_world["rules"] = _merge_unique(
        base_world.get("rules", []),
        patch_world.get("rules", []),
    )
    base_data["plot_threads"] = _merge_plot_threads(
        base_data.get("plot_threads", []),
        patch_data.get("plot_threads", []),
    )
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
            _merge_dict_in_place(index[patch_key], patch_item)
        else:
            merged.append(copy.deepcopy(patch_item))
            if patch_key:
                index[patch_key] = merged[-1]
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
            _merge_dict_in_place(index[patch_id], patch_item)
        elif patch_item not in merged:
            merged.append(copy.deepcopy(patch_item))
            if patch_id:
                index[patch_id] = merged[-1]
    return merged


def _merge_dict_in_place(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if value is None:
            continue
        if isinstance(value, list):
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
