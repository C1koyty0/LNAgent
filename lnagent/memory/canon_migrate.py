"""Hot Canon v1 → v2 惰性迁移与旧格式解析。"""

from __future__ import annotations

import copy
import re
from typing import Any

CANON_SCHEMA_VERSION = 2

_LEVEL_PATTERN = re.compile(r"lv?\s*(\d+)", re.IGNORECASE)


def upgrade_canon_dict(data: dict[str, Any]) -> dict[str, Any]:
    """将 canon 字典升级到 schema v2（原地语义，返回新 dict）。"""
    result = copy.deepcopy(data)
    version = _read_schema_version(result)
    if version >= CANON_SCHEMA_VERSION:
        result["schema_version"] = CANON_SCHEMA_VERSION
        _ensure_world_v2(result)
        _normalize_characters(result.get("characters", []))
        _normalize_plot_threads(result.get("plot_threads", []))
        return result

    result["schema_version"] = CANON_SCHEMA_VERSION
    _ensure_world_v2(result)
    _normalize_characters(result.get("characters", []))
    _normalize_plot_threads(result.get("plot_threads", []))
    return result


def slugify(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        return "ability_unknown"
    normalized = re.sub(r"[\s：:]+", "_", stripped)
    normalized = re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)
    if normalized:
        return normalized[:64].lower()
    return f"ability_{abs(hash(stripped)) % 100000}"


def parse_legacy_ability_string(text: str) -> dict[str, Any]:
    raw = str(text).strip()
    level_match = _LEVEL_PATTERN.search(raw)
    level = int(level_match.group(1)) if level_match else 0

    name = raw
    for separator in ("：", ":"):
        if separator in raw:
            name = raw.split(separator, 1)[0].strip()
            break
    name = _LEVEL_PATTERN.sub("", name).strip() or raw[:32]

    kind = "unknown"
    lowered = raw.lower()
    if "天赋" in raw or "talent" in lowered:
        kind = "talent"
    elif "技能" in raw or "skill" in lowered:
        kind = "skill"
    elif "被动" in raw or "passive" in lowered:
        kind = "passive"

    return {
        "id": slugify(name),
        "name": name,
        "kind": kind,
        "level": level,
        "summary": raw,
        "introduced_in": "",
        "constraints": [],
    }


def _read_schema_version(data: dict[str, Any]) -> int:
    try:
        return int(data.get("schema_version", 1))
    except (TypeError, ValueError):
        return 1


def _ensure_world_v2(data: dict[str, Any]) -> None:
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


def _normalize_characters(characters: list[Any]) -> None:
    if not isinstance(characters, list):
        return
    for character in characters:
        if not isinstance(character, dict):
            continue
        raw_abilities = character.get("abilities", [])
        if not isinstance(raw_abilities, list):
            character["abilities"] = []
            continue
        normalized: list[dict[str, Any]] = []
        index: dict[str, dict[str, Any]] = {}
        for item in raw_abilities:
            if isinstance(item, str):
                entry = parse_legacy_ability_string(item)
            elif isinstance(item, dict):
                entry = _normalize_ability_object(item)
            else:
                continue
            ability_id = entry.get("id") or slugify(str(entry.get("name", "")))
            entry["id"] = ability_id
            if ability_id in index:
                _merge_ability_dict(index[ability_id], entry)
            else:
                index[ability_id] = entry
                normalized.append(entry)
        character["abilities"] = normalized


def _normalize_ability_object(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name", "")).strip()
    ability_id = str(item.get("id", "")).strip() or slugify(name or "ability")
    level = item.get("level", 0)
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 0
    constraints = item.get("constraints", [])
    if not isinstance(constraints, list):
        constraints = []
    return {
        "id": ability_id,
        "name": name or ability_id,
        "kind": str(item.get("kind", "unknown")),
        "level": level,
        "summary": str(item.get("summary", "")),
        "introduced_in": str(item.get("introduced_in", "")),
        "constraints": [str(value) for value in constraints],
    }


def _merge_ability_dict(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key in ("name", "kind", "summary", "introduced_in"):
        value = patch.get(key)
        if value:
            base[key] = value
    if patch.get("level") is not None:
        try:
            base["level"] = int(patch["level"])
        except (TypeError, ValueError):
            pass
    base_constraints = base.setdefault("constraints", [])
    patch_constraints = patch.get("constraints", [])
    if isinstance(patch_constraints, list):
        for item in patch_constraints:
            text = str(item)
            if text and text not in base_constraints:
                base_constraints.append(text)


def _normalize_plot_threads(threads: list[Any]) -> None:
    if not isinstance(threads, list):
        return
    normalized: list[dict[str, Any]] = []
    for item in threads:
        if isinstance(item, dict):
            normalized.append(_normalize_plot_thread_object(item))
    threads.clear()
    threads.extend(normalized)


def _normalize_plot_thread_object(item: dict[str, Any]) -> dict[str, Any]:
    advanced = item.get("advanced_in", [])
    if not isinstance(advanced, list):
        advanced = []
    related = item.get("related_characters", [])
    if not isinstance(related, list):
        related = []
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("title", "")),
        "status": str(item.get("status", "open")),
        "introduced_in": str(item.get("introduced_in", "")),
        "advanced_in": [str(value) for value in advanced],
        "closed_in": str(item.get("closed_in", "")),
        "related_characters": [str(value) for value in related],
        "priority": str(item.get("priority", "")),
        "note": str(item.get("note", "")),
    }
