"""worldbook apply：将 structured worldbook 覆盖同步到 meta.world。"""

from __future__ import annotations

from typing import Any

from lnagent.memory.models import NovelMeta, ScopedWorldRules, WorldCanon, WorldbookStructured
from lnagent.memory.protocols import MemoryStore


class WorldbookApplyError(ValueError):
    """worldbook apply 失败。"""


def apply_worldbook_to_meta(store: MemoryStore) -> NovelMeta:
    """读取 structured.json 并覆盖写入 meta.world。"""
    structured = store.load_worldbook_structured()
    if not _has_projectable_world_content(structured):
        raise WorldbookApplyError("structured worldbook 不存在或没有可投影的世界规则")

    meta = store.load_meta()
    meta.world = world_canon_from_structured(structured)
    store.save_meta(meta)
    return meta


def _has_projectable_world_content(structured: WorldbookStructured) -> bool:
    if structured.global_rules:
        return True
    return any(scope.rules for scope in structured.scopes)


def world_canon_from_structured(structured: WorldbookStructured) -> WorldCanon:
    return WorldCanon(
        rules=list(structured.global_rules),
        scoped=[
            ScopedWorldRules(
                scope_type=scope.scope_type,
                scope_id=scope.scope_id,
                rules=list(scope.rules),
            )
            for scope in structured.scopes
            if scope.rules
        ],
    )


def structured_has_projectable_content(structured: Any) -> bool:
    if getattr(structured, "global_rules", None):
        return True
    return any(getattr(scope, "rules", None) for scope in getattr(structured, "scopes", []))
