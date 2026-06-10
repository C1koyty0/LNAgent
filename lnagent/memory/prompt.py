"""Prompt 上下文组装。"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from lnagent.memory.context_budget import (
    BudgetReport,
    clip_head,
    clip_tail,
    trim_oldest_messages,
)
from lnagent.memory.canon_context import resolve_active_scopes
from lnagent.memory.canon_display import format_hot_canon_for_prompt
from lnagent.memory.meta_display import format_meta_for_prompt
from lnagent.memory.models import (
    ContextConfig,
    DiscussionBrief,
    HotCanon,
    NovelMeta,
    SceneSynopsisEntry,
)
from lnagent.memory.short_term import ShortTermBuffer

_WRITING_INSTRUCTIONS = """\
你是轻小说创作助手，与作者进行对话式续写。
- 作者给出启发或大致走向，你扩展丰富为具体叙事。
- 你的输出是**正文候选**，供作者采纳后进入小说。
- 只有作者通过 /a 采纳的文本才视为正式正文；未采纳的候选不应被当作已发生剧情或 Canon 事实。
- 讨论区的结论是写作参考，不等于正式设定或 Canon。其中未决问题不要擅自写成强事实。
- 当一个戏剧节拍（beat）基本完成时，可建议作者使用 /sc 结束当前场景。"""

_DISCUSSION_INSTRUCTIONS = """\
你是轻小说创作助手，与作者进行场景分析与规划。
- 你的输出是**分析、建议或方案**，帮助作者理清当前场景的走向、节拍与约束。
- 不要输出可被直接采纳进小说的长段正文候选。
- 不要暗示你的分析内容已经进入 Canon、正文或手稿。
- 可以从以下角度展开：
  - 场景节拍分解
  - 角色动机与冲突
  - 写作约束与风险
  - 待写事项
  - 场景基调与节奏
- 如果作者提出具体的写作问题或意见，可针对性地给出分析，而不是代为写作。
- 如果作者意图不清，请主动追问以明确当前讨论重点。"""

_BRIEF_HEADER = "当前场景讨论结论（供写作参考，非 Canon）"


class PromptContextBuilder:
    def __init__(self) -> None:
        self.last_budget_report = BudgetReport()

    # ── 兼容别名 ──

    def build(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        global_summary: str = "",
        prior_scene_cold: SceneSynopsisEntry | None = None,
        scene_tail: str | None = None,
        context_config: ContextConfig | None = None,
    ) -> list[BaseMessage]:
        return self.build_writing(
            meta=meta,
            canon=canon,
            buffer=buffer,
            user_input=user_input,
            global_summary=global_summary,
            prior_scene_cold=prior_scene_cold,
            scene_tail=scene_tail,
            context_config=context_config,
            discussion_brief=None,
        )

    # ── writing 入口 ──

    def build_writing(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        global_summary: str = "",
        prior_scene_cold: SceneSynopsisEntry | None = None,
        scene_tail: str | None = None,
        context_config: ContextConfig | None = None,
        discussion_brief: DiscussionBrief | None = None,
    ) -> list[BaseMessage]:
        return self._build(
            instruction_text=_WRITING_INSTRUCTIONS,
            meta=meta,
            canon=canon,
            buffer=buffer,
            user_input=user_input,
            global_summary=global_summary,
            prior_scene_cold=prior_scene_cold,
            scene_tail=scene_tail,
            context_config=context_config,
            extra_system_block=_format_discussion_brief_for_writing(discussion_brief),
            include_adopted_prose=True,
        )

    # ── discussion 入口 ──

    def build_discussion(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        global_summary: str = "",
        prior_scene_cold: SceneSynopsisEntry | None = None,
        scene_tail: str | None = None,
        context_config: ContextConfig | None = None,
    ) -> list[BaseMessage]:
        return self._build(
            instruction_text=_DISCUSSION_INSTRUCTIONS,
            meta=meta,
            canon=canon,
            buffer=buffer,
            user_input=user_input,
            global_summary=global_summary,
            prior_scene_cold=prior_scene_cold,
            scene_tail=scene_tail,
            context_config=context_config,
            extra_system_block="",
            include_adopted_prose=False,
        )

    # ── 共享核心 ──

    def _build(
        self,
        *,
        instruction_text: str,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        global_summary: str = "",
        prior_scene_cold: SceneSynopsisEntry | None = None,
        scene_tail: str | None = None,
        context_config: ContextConfig | None = None,
        extra_system_block: str = "",
        include_adopted_prose: bool = True,
    ) -> list[BaseMessage]:
        config = context_config or ContextConfig()
        report = BudgetReport()

        active_scopes = resolve_active_scopes(
            canon,
            prior_scene_entry=prior_scene_cold,
        )
        meta_text = clip_head(
            format_meta_for_prompt(meta, active_scopes=active_scopes),
            config.meta_limit,
            report,
            "meta",
        )

        global_text = clip_head(
            global_summary.strip(),
            config.global_limit,
            report,
            "global",
        )
        prior_text = clip_head(
            _format_prior_scene_cold(prior_scene_cold) or "",
            config.prior_scene_cold_limit,
            report,
            "prior_scene_cold",
        )
        canon_text = clip_head(
            format_hot_canon_for_prompt(canon, active_scopes=active_scopes) or "",
            config.hot_canon_limit,
            report,
            "hot_canon",
        )
        scene_tail_text = clip_tail(
            scene_tail or "",
            config.scene_tail_limit,
            report,
            "scene_tail",
        )
        adopted_text = ""
        if include_adopted_prose:
            adopted_text = clip_tail(
                buffer.adopted_prose.strip(),
                config.adopted_prose_limit,
                report,
                "adopted_prose",
            )
        history_messages = trim_oldest_messages(
            buffer.messages,
            config.messages_limit,
            report,
        )

        history_messages, adopted_text, global_text, canon_text = _apply_total_budget(
            report=report,
            config=config,
            instruction_text=instruction_text,
            meta_text=meta_text,
            global_text=global_text,
            prior_text=prior_text,
            canon_text=canon_text,
            scene_tail_text=scene_tail_text,
            adopted_text=adopted_text,
            history_messages=history_messages,
            user_input=user_input,
        )

        system_parts = [
            instruction_text,
            meta_text,
        ]

        if scene_tail_text:
            if global_text:
                system_parts.append(f"全书梗概（已确认）：\n{global_text}")
            if prior_text:
                system_parts.append(prior_text)

        if canon_text:
            system_parts.append(canon_text)

        if extra_system_block:
            system_parts.append(extra_system_block)

        if scene_tail_text:
            system_parts.append(f"前文衔接（上一场景末尾）：\n{scene_tail_text}")
        elif adopted_text:
            system_parts.append(f"已采纳正文（当前场景）：\n{adopted_text}")

        messages: list[BaseMessage] = [SystemMessage(content="\n\n".join(system_parts))]

        for msg in history_messages:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=user_input))
        report.total_after = _count_prompt_chars(messages)
        self.last_budget_report = report
        return messages


def _format_discussion_brief_for_writing(
    brief: DiscussionBrief | None,
) -> str:
    if brief is None:
        return ""
    parts: list[str] = []
    if brief.todo_items:
        items = "\n".join(f"- {item}" for item in brief.todo_items)
        parts.append(f"待写事项：\n{items}")
    if brief.constraints:
        constraints = "\n".join(f"- {c}" for c in brief.constraints)
        parts.append(f"当前场景约束：\n{constraints}")
    if brief.open_questions:
        questions = "\n".join(f"- {q}" for q in brief.open_questions)
        parts.append(f"未决问题：\n{questions}")
    if not parts:
        return ""
    return f"{_BRIEF_HEADER}\n" + "\n".join(parts)


def _format_prior_scene_cold(entry: SceneSynopsisEntry | None) -> str | None:
    if entry is None:
        return None
    parts = [
        f"上一场景归档（{entry.id}）",
        f"地点：{entry.location}",
        f"时间：{entry.time}",
        f"摘要：{entry.summary}",
    ]
    if entry.key_points:
        points = "\n".join(f"- {point}" for point in entry.key_points)
        parts.append(f"要点：\n{points}")
    return "\n".join(parts)


def _apply_total_budget(
    *,
    report: BudgetReport,
    config: ContextConfig,
    instruction_text: str,
    meta_text: str,
    global_text: str,
    prior_text: str,
    canon_text: str,
    scene_tail_text: str,
    adopted_text: str,
    history_messages: list,
    user_input: str,
) -> tuple[list, str, str, str]:
    report.total_before = _estimate_prompt_chars(
        instruction_text=instruction_text,
        meta_text=meta_text,
        global_text=global_text,
        prior_text=prior_text,
        canon_text=canon_text,
        scene_tail_text=scene_tail_text,
        adopted_text=adopted_text,
        history_messages=history_messages,
        user_input=user_input,
    )
    if report.total_before <= config.char_budget:
        return history_messages, adopted_text, global_text, canon_text

    excess = report.total_before - config.char_budget

    if excess > 0 and history_messages:
        current = sum(len(message.content) for message in history_messages)
        next_limit = max(0, current - excess)
        history_messages = trim_oldest_messages(history_messages, next_limit, report)
        excess -= current - sum(len(message.content) for message in history_messages)

    if excess > 0 and adopted_text:
        next_limit = max(0, len(adopted_text) - excess)
        before = len(adopted_text)
        adopted_text = clip_tail(adopted_text, next_limit, report, "adopted_prose")
        excess -= before - len(adopted_text)

    if excess > 0 and global_text:
        next_limit = max(0, len(global_text) - excess)
        before = len(global_text)
        global_text = clip_head(global_text, next_limit, report, "global")
        excess -= before - len(global_text)

    if excess > 0 and canon_text:
        next_limit = max(0, len(canon_text) - excess)
        canon_text = clip_head(canon_text, next_limit, report, "hot_canon")

    return history_messages, adopted_text, global_text, canon_text


def _count_prompt_chars(messages: list[BaseMessage]) -> int:
    total = 0
    for message in messages:
        content = message.content
        total += len(content) if isinstance(content, str) else len(str(content))
    return total


def _estimate_prompt_chars(
    *,
    instruction_text: str,
    meta_text: str,
    global_text: str,
    prior_text: str,
    canon_text: str,
    scene_tail_text: str,
    adopted_text: str,
    history_messages: list,
    user_input: str,
) -> int:
    system_parts = [instruction_text, meta_text]
    if scene_tail_text:
        if global_text:
            system_parts.append(f"全书梗概（已确认）：\n{global_text}")
        if prior_text:
            system_parts.append(prior_text)
    if canon_text:
        system_parts.append(canon_text)
    if scene_tail_text:
        system_parts.append(f"前文衔接（上一场景末尾）：\n{scene_tail_text}")
    elif adopted_text:
        system_parts.append(f"已采纳正文（当前场景）：\n{adopted_text}")

    system_chars = len("\n\n".join(system_parts))
    history_chars = sum(len(message.content) for message in history_messages)
    return system_chars + history_chars + len(user_input)
