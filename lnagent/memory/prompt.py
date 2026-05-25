"""Prompt 上下文组装。"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from lnagent.memory.models import HotCanon, NovelMeta, SceneSynopsisEntry
from lnagent.memory.short_term import ShortTermBuffer

_WRITING_INSTRUCTIONS = """\
你是轻小说创作助手，与作者进行对话式续写。
- 作者给出启发或大致走向，你扩展丰富为具体叙事或分析。
- 你的输出默认为候选内容；只有作者显式 /adopt 采纳后才成为正文。
- 讨论设定合理性时，可直接回答，无需写成小说段落。
- 当一个戏剧节拍（beat）基本完成时，可建议作者使用 /sc 结束当前场景。"""


class PromptContextBuilder:
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
    ) -> list[BaseMessage]:
        system_parts = [
            _WRITING_INSTRUCTIONS,
            f"书名：{meta.title}",
            f"文风：{meta.style}",
        ]
        if meta.world_rules:
            rules_text = "\n".join(f"- {rule}" for rule in meta.world_rules)
            system_parts.append(f"世界规则：\n{rules_text}")

        if scene_tail:
            global_text = global_summary.strip()
            if global_text:
                system_parts.append(f"全书梗概（已确认）：\n{global_text}")
            prior_text = _format_prior_scene_cold(prior_scene_cold)
            if prior_text:
                system_parts.append(prior_text)

        canon_text = _format_hot_canon(canon)
        if canon_text:
            system_parts.append(canon_text)

        if scene_tail:
            system_parts.append(f"前文衔接（上一场景末尾）：\n{scene_tail}")
        else:
            adopted = buffer.adopted_prose.strip()
            if adopted:
                system_parts.append(f"已采纳正文（当前场景）：\n{adopted}")

        messages: list[BaseMessage] = [SystemMessage(content="\n\n".join(system_parts))]

        for msg in buffer.messages:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=user_input))
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


def _format_hot_canon(canon: HotCanon) -> str | None:
    data = canon.to_dict()
    if not data["characters"] and not data["world"]["rules"] and not data["plot_threads"]:
        return None

    return "Hot Canon（已确认设定）：\n" + json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )
