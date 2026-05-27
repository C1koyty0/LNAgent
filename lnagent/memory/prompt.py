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
from lnagent.memory.models import ContextConfig, HotCanon, NovelMeta, SceneSynopsisEntry
from lnagent.memory.short_term import ShortTermBuffer

_WRITING_INSTRUCTIONS = """\
你是轻小说创作助手，与作者进行对话式续写。
- 作者给出启发或大致走向，你扩展丰富为具体叙事或分析。
- 你需要区分“写作任务”和“讨论任务”。
- 当用户明确要求续写、改写、生成正文时，输出可以被作者采纳进小说的正文候选。
- 当用户在讨论设定、剧情、人物、风格、修改建议，或提出问题时，输出应为分析、建议或方案，不要把讨论内容写成小说正文，也不要暗示这些内容已经成为正式设定。
- 只有作者通过 /a 采纳的文本才视为正式正文；未采纳的候选、讨论回复和建议都不应被当作已发生剧情或 Canon 事实。
- 如果用户意图不明确，优先按讨论任务处理，并询问是否需要转成正文候选。
- 当一个戏剧节拍（beat）基本完成时，可建议作者使用 /sc 结束当前场景。"""


class PromptContextBuilder:
    def __init__(self) -> None:
        self.last_budget_report = BudgetReport()

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
        config = context_config or ContextConfig()
        report = BudgetReport()

        meta_parts = [
            f"书名：{meta.title}",
            f"文风：{meta.style}",
        ]
        if meta.world_rules:
            rules_text = "\n".join(f"- {rule}" for rule in meta.world_rules)
            meta_parts.append(f"世界规则：\n{rules_text}")
        if meta.pov:
            meta_parts.append(f"叙述人称：{meta.pov}")
        if meta.tense:
            meta_parts.append(f"叙事时态：{meta.tense}")
        if meta.taboos:
            taboos_text = "\n".join(f"- {rule}" for rule in meta.taboos)
            meta_parts.append(f"禁忌内容：\n{taboos_text}")
        if meta.target_audience:
            meta_parts.append(f"目标读者：{meta.target_audience}")
        if meta.narrative_rules:
            narrative_rules_text = "\n".join(f"- {rule}" for rule in meta.narrative_rules)
            meta_parts.append(f"叙事规则：\n{narrative_rules_text}")
        if meta.genre:
            meta_parts.append(f"题材类型：{meta.genre}")
        if meta.tone:
            meta_parts.append(f"整体语气：{meta.tone}")
        meta_text = clip_head("\n".join(meta_parts), config.meta_limit, report, "meta")

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
            _format_hot_canon(canon) or "",
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
            instruction_text=_WRITING_INSTRUCTIONS,
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
            _WRITING_INSTRUCTIONS,
            meta_text,
        ]

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


def _format_hot_canon(canon: HotCanon) -> str | None:
    data = canon.to_dict()
    if not data["characters"] and not data["world"]["rules"] and not data["plot_threads"]:
        return None

    return "Hot Canon（已确认设定）：\n" + json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )
