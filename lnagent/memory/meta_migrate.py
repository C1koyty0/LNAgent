"""meta.json v1 → v2 惰性迁移与规则拆分。"""

from __future__ import annotations

import copy
import re
from typing import Any

META_SCHEMA_VERSION = 2

_FACTION_MARKERS = (
    "王国",
    "帝国",
    "神国",
    "联邦",
    "同盟",
    "联合体",
    "城邦",
    "疆域",
    "龙域",
    "共和国",
    "公国",
)


def upgrade_meta_dict(data: dict[str, Any]) -> dict[str, Any]:
    """将 meta 字典升级到 schema v2。"""
    result = copy.deepcopy(data)
    version = _read_schema_version(result)
    if version >= META_SCHEMA_VERSION and isinstance(result.get("world"), dict):
        result["schema_version"] = META_SCHEMA_VERSION
        _ensure_world_block(result)
        return result

    result["schema_version"] = META_SCHEMA_VERSION
    _migrate_legacy_world_rules(result)
    _ensure_world_block(result)
    return result


def _read_schema_version(data: dict[str, Any]) -> int:
    try:
        return int(data.get("schema_version", 1))
    except (TypeError, ValueError):
        return 1


def _ensure_world_block(data: dict[str, Any]) -> None:
    world = data.setdefault("world", {})
    if not isinstance(world, dict):
        world = {}
        data["world"] = world
    world.setdefault("rules", [])
    if not isinstance(world.get("rules"), list):
        world["rules"] = []
    world["rules"] = [str(rule) for rule in world["rules"]]
    if "scoped" not in world or not isinstance(world.get("scoped"), list):
        world["scoped"] = []


def _migrate_legacy_world_rules(data: dict[str, Any]) -> None:
    if isinstance(data.get("world"), dict) and data["world"].get("scoped"):
        rules = data["world"].get("rules", [])
        if isinstance(rules, list) and rules:
            return

    raw_rules = data.get("world_rules", [])
    if not isinstance(raw_rules, list):
        raw_rules = []
    if isinstance(data.get("world"), dict):
        nested = data["world"].get("rules", [])
        if isinstance(nested, list) and nested and not raw_rules:
            raw_rules = nested

    global_rules: list[str] = []
    scoped_map: dict[tuple[str, str], list[str]] = {}

    for item in raw_rules:
        text = str(item).strip()
        if not text:
            continue
        parsed = _parse_faction_rule(text)
        if parsed is None:
            global_rules.append(text)
            continue
        scope_type, scope_id, body = parsed
        key = (scope_type, scope_id)
        scoped_map.setdefault(key, []).append(body)

    scoped: list[dict[str, Any]] = [
        {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "rules": rules,
        }
        for (scope_type, scope_id), rules in scoped_map.items()
    ]

    data["world"] = {"rules": global_rules, "scoped": scoped}
    data.pop("world_rules", None)


def _parse_faction_rule(text: str) -> tuple[str, str, str] | None:
    if " - " not in text:
        return None
    head, tail = text.split(" - ", 1)
    head = head.strip()
    if not head or len(head) > 80:
        return None
    if not _looks_like_scope_name(head):
        return None
    scope_type = "faction" if _is_faction_name(head) else "location"
    body = tail.strip() or text
    return scope_type, head, body


def _looks_like_scope_name(name: str) -> bool:
    if _is_faction_name(name):
        return True
    if re.search(r"(空间|大陆|海域|山脉|沙漠|群岛)", name):
        return True
    return False


def _is_faction_name(name: str) -> bool:
    return any(marker in name for marker in _FACTION_MARKERS)


def split_rules_for_display(rules: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """将平铺规则拆为全局 + scoped（供测试与工具使用）。"""
    data = {"world_rules": rules}
    _migrate_legacy_world_rules(data)
    world = data.get("world", {})
    return (
        list(world.get("rules", [])),
        list(world.get("scoped", [])),
    )
