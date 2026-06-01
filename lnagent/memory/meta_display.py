"""meta.json 人类可读展示与 Prompt 注入。"""

from __future__ import annotations

from lnagent.memory.canon_display import _filter_scoped
from lnagent.memory.models import NovelMeta, ScopedWorldRules


def format_meta_summary(meta: NovelMeta) -> str:
    lines = [
        f"meta（开书设定） schema_version: {meta.schema_version}",
        f"书名：{meta.title}",
        f"文风：{meta.style}",
    ]
    world_text = _format_meta_world(meta, active_scopes=None)
    if world_text:
        lines.append(world_text)
    if meta.pov:
        lines.append(f"叙述人称：{meta.pov}")
    if meta.tense:
        lines.append(f"叙事时态：{meta.tense}")
    if meta.taboos:
        lines.append("禁忌内容：\n" + "\n".join(f"- {rule}" for rule in meta.taboos))
    if meta.target_audience:
        lines.append(f"目标读者：{meta.target_audience}")
    if meta.narrative_rules:
        lines.append(
            "叙事规则：\n" + "\n".join(f"- {rule}" for rule in meta.narrative_rules)
        )
    if meta.genre:
        lines.append(f"题材类型：{meta.genre}")
    if meta.tone:
        lines.append(f"整体语气：{meta.tone}")
    return "\n".join(lines)


def format_meta_for_prompt(
    meta: NovelMeta,
    *,
    active_scopes: set[tuple[str, str]] | None = None,
) -> str:
    lines = [
        f"书名：{meta.title}",
        f"文风：{meta.style}",
    ]
    world_text = _format_meta_world(meta, active_scopes=active_scopes)
    if world_text:
        lines.append(world_text)
    if meta.pov:
        lines.append(f"叙述人称：{meta.pov}")
    if meta.tense:
        lines.append(f"叙事时态：{meta.tense}")
    if meta.taboos:
        lines.append("禁忌内容：\n" + "\n".join(f"- {rule}" for rule in meta.taboos))
    if meta.target_audience:
        lines.append(f"目标读者：{meta.target_audience}")
    if meta.narrative_rules:
        lines.append(
            "叙事规则：\n" + "\n".join(f"- {rule}" for rule in meta.narrative_rules)
        )
    if meta.genre:
        lines.append(f"题材类型：{meta.genre}")
    if meta.tone:
        lines.append(f"整体语气：{meta.tone}")
    return "\n".join(lines)


def _format_meta_world(
    meta: NovelMeta,
    *,
    active_scopes: set[tuple[str, str]] | None,
) -> str | None:
    lines: list[str] = []
    if meta.world.rules:
        lines.append("【开书·全局规则】")
        lines.extend(f"- {rule}" for rule in meta.world.rules)

    scoped_entries = _filter_scoped(meta.world.scoped, active_scopes)
    for entry in scoped_entries:
        if not entry.rules:
            continue
        label = "势力" if entry.scope_type == "faction" else "地点"
        lines.append(f"【开书·{label}：{entry.scope_id}】")
        lines.extend(f"- {rule}" for rule in entry.rules)

    if not lines:
        return None
    return "\n".join(lines)


def meta_has_world_content(meta: NovelMeta) -> bool:
    if meta.world.rules:
        return True
    return any(entry.rules for entry in meta.world.scoped)
