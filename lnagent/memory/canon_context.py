"""Hot Canon Prompt 注入时的范围解析。"""

from __future__ import annotations

from lnagent.memory.models import HotCanon, SceneSynopsisEntry


def resolve_active_scopes(
    canon: HotCanon,
    *,
    prior_scene_entry: SceneSynopsisEntry | None = None,
) -> set[tuple[str, str]]:
    """根据角色位置与上一场景 Cold 元数据解析相关 scope。"""
    scopes: set[tuple[str, str]] = set()

    for character in canon.characters:
        if not isinstance(character, dict):
            continue
        location = str(character.get("location", "")).strip()
        if location:
            scopes.add(("location", location))

    if prior_scene_entry and prior_scene_entry.location.strip():
        scopes.add(("location", prior_scene_entry.location.strip()))

    return scopes
