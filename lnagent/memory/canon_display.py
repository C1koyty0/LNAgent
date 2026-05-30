"""Hot Canon 人类可读展示。"""

from __future__ import annotations

from lnagent.memory.models import HotCanon, ScopedWorldRules


def format_canon_summary(canon: HotCanon) -> str:
    if _is_empty_canon(canon):
        return "Hot Canon 为空。"

    sections: list[str] = ["Hot Canon（已确认设定）", f"schema_version: {canon.schema_version}"]

    world_section = _format_world_section(canon)
    if world_section:
        sections.append(world_section)

    characters_section = _format_characters_section(canon)
    if characters_section:
        sections.append(characters_section)

    threads_section = _format_plot_threads_section(canon, open_only=False)
    if threads_section:
        sections.append(threads_section)

    return "\n\n".join(sections)


def format_hot_canon_for_prompt(
    canon: HotCanon,
    *,
    active_scopes: set[tuple[str, str]] | None = None,
) -> str | None:
    if _is_empty_canon(canon):
        return None

    sections: list[str] = ["Hot Canon（已确认设定）"]
    world_section = _format_world_section(canon, active_scopes=active_scopes)
    if world_section:
        sections.append(world_section)

    characters_section = _format_characters_section(canon, compact=True)
    if characters_section:
        sections.append(characters_section)

    open_threads = _format_plot_threads_section(canon, open_only=True)
    if open_threads:
        sections.append(open_threads)

    if len(sections) == 1:
        return None
    return "\n\n".join(sections)


def _is_empty_canon(canon: HotCanon) -> bool:
    if canon.characters or canon.plot_threads:
        return False
    if canon.world.rules:
        return False
    return not any(entry.rules for entry in canon.world.scoped)


def _format_world_section(
    canon: HotCanon,
    *,
    active_scopes: set[tuple[str, str]] | None = None,
) -> str | None:
    lines: list[str] = []
    if canon.world.rules:
        lines.append("【全局规则】")
        lines.extend(f"- {rule}" for rule in canon.world.rules)

    scoped_entries = _filter_scoped(canon.world.scoped, active_scopes)
    for entry in scoped_entries:
        if not entry.rules:
            continue
        label = "势力" if entry.scope_type == "faction" else "地点"
        lines.append(f"【{label}：{entry.scope_id}】")
        lines.extend(f"- {rule}" for rule in entry.rules)

    if not lines:
        return None
    return "\n".join(lines)


def _filter_scoped(
    scoped: list[ScopedWorldRules],
    active_scopes: set[tuple[str, str]] | None,
) -> list[ScopedWorldRules]:
    if not active_scopes:
        return scoped
    filtered: list[ScopedWorldRules] = []
    for entry in scoped:
        key = (entry.scope_type, entry.scope_id)
        if key in active_scopes:
            filtered.append(entry)
            continue
        if _scope_matches_active(entry.scope_id, active_scopes):
            filtered.append(entry)
    return filtered


def _scope_matches_active(
    scope_id: str,
    active_scopes: set[tuple[str, str]],
) -> bool:
    normalized = scope_id.strip()
    if not normalized:
        return False
    for _, active_id in active_scopes:
        active = active_id.strip()
        if not active:
            continue
        if normalized == active or normalized in active or active in normalized:
            return True
        if _shared_name_fragment(normalized, active, min_len=2):
            return True
    return False


def _shared_name_fragment(left: str, right: str, *, min_len: int) -> bool:
    if min_len <= 0:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < min_len:
        return False
    for index in range(len(shorter) - min_len + 1):
        fragment = shorter[index : index + min_len]
        if fragment in longer:
            return True
    return False


def _format_characters_section(
    canon: HotCanon,
    *,
    compact: bool = False,
) -> str | None:
    if not canon.characters:
        return None
    lines = ["【角色】"]
    for character in canon.characters:
        if not isinstance(character, dict):
            continue
        name = character.get("name", "未知")
        location = character.get("location", "")
        header = f"- {name}"
        if location:
            header += f" @ {location}"
        lines.append(header)
        status = character.get("status", "")
        if status and not compact:
            lines.append(f"  状态: {status}")
        abilities = character.get("abilities", [])
        if isinstance(abilities, list):
            for ability in abilities:
                lines.append(_format_ability_line(ability, compact=compact))
    return "\n".join(lines)


def _format_ability_line(ability: object, *, compact: bool) -> str:
    if isinstance(ability, dict):
        name = ability.get("name") or ability.get("id", "能力")
        level = ability.get("level", 0)
        try:
            level_text = f"Lv.{int(level)} " if int(level) > 0 else ""
        except (TypeError, ValueError):
            level_text = ""
        summary = str(ability.get("summary", ""))
        if compact and len(summary) > 120:
            summary = summary[:120] + "…"
        line = f"  · {level_text}{name}"
        if summary:
            line += f": {summary}"
        return line
    return f"  · {ability}"


def _format_plot_threads_section(
    canon: HotCanon,
    *,
    open_only: bool,
) -> str | None:
    if not canon.plot_threads:
        return None
    lines = ["【伏笔】"]
    has_entry = False
    for thread in canon.plot_threads:
        if not isinstance(thread, dict):
            continue
        status = str(thread.get("status", "open"))
        if open_only and status == "closed":
            continue
        has_entry = True
        title = thread.get("title") or thread.get("id") or "未命名"
        introduced = thread.get("introduced_in", "")
        line = f"- [{status}] {title}"
        if introduced:
            line += f" (始于 {introduced})"
        note = thread.get("note", "")
        if note:
            line += f": {note}"
        lines.append(line)
    if not has_entry:
        return None
    return "\n".join(lines)
