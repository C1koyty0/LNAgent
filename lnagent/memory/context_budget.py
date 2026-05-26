"""Prompt 上下文字符预算工具。"""

from __future__ import annotations

from dataclasses import dataclass, field

from lnagent.memory.models import ChatMessage

_KNOWN_BLOCKS = (
    "meta",
    "hot_canon",
    "global",
    "prior_scene_cold",
    "scene_tail",
    "messages",
    "adopted_prose",
)


@dataclass
class BudgetReport:
    total_before: int = 0
    total_after: int = 0
    clipped_chars: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in _KNOWN_BLOCKS}
    )

    @property
    def has_clipping(self) -> bool:
        return any(value > 0 for value in self.clipped_chars.values())

    def record(self, block: str, before: int, after: int) -> None:
        clipped = max(0, before - after)
        if clipped:
            self.clipped_chars[block] = self.clipped_chars.get(block, 0) + clipped


def clip_head(text: str, limit: int, report: BudgetReport, block: str) -> str:
    if limit < 0 or len(text) <= limit:
        return text
    clipped = text[:limit]
    report.record(block, len(text), len(clipped))
    return clipped


def clip_tail(text: str, limit: int, report: BudgetReport, block: str) -> str:
    if limit < 0 or len(text) <= limit:
        return text
    clipped = text[-limit:] if limit > 0 else ""
    report.record(block, len(text), len(clipped))
    return clipped


def trim_oldest_messages(
    messages: list[ChatMessage],
    limit: int,
    report: BudgetReport,
) -> list[ChatMessage]:
    if limit < 0:
        return list(messages)

    total = sum(len(message.content) for message in messages)
    if total <= limit:
        return list(messages)

    kept_reversed: list[ChatMessage] = []
    remaining = limit
    for message in reversed(messages):
        content_len = len(message.content)
        if content_len <= remaining:
            kept_reversed.append(message)
            remaining -= content_len
        elif remaining > 0 and not kept_reversed:
            kept_reversed.append(
                ChatMessage(role=message.role, content=message.content[-remaining:])
            )
            remaining = 0
        if remaining <= 0:
            break

    kept = list(reversed(kept_reversed))
    after = sum(len(message.content) for message in kept)
    report.record("messages", total, after)
    return kept


def format_budget_notice(report: BudgetReport) -> str:
    clipped = [
        f"{block} 约 {count} 字"
        for block, count in report.clipped_chars.items()
        if count > 0
    ]
    if not clipped:
        return ""
    return "提示: 已按上下文预算裁剪 " + "、".join(clipped) + "。"
