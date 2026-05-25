"""Prompt 上下文组装。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from lnagent.memory.models import NovelMeta
from lnagent.memory.short_term import ShortTermBuffer

_WRITING_INSTRUCTIONS = """\
你是轻小说创作助手，与作者进行对话式续写。
- 作者给出启发或大致走向，你扩展丰富为具体叙事或分析。
- 你的输出默认为候选内容；只有作者显式 /adopt 采纳后才成为正文。
- 讨论设定合理性时，可直接回答，无需写成小说段落。"""


class PromptContextBuilder:
    def build(
        self,
        *,
        meta: NovelMeta,
        buffer: ShortTermBuffer,
        user_input: str,
    ) -> list[BaseMessage]:
        system_parts = [
            _WRITING_INSTRUCTIONS,
            f"书名：{meta.title}",
            f"文风：{meta.style}",
        ]
        if meta.world_rules:
            rules_text = "\n".join(f"- {rule}" for rule in meta.world_rules)
            system_parts.append(f"世界规则：\n{rules_text}")

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
