"""`/scene` 场景切换交互流。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lnagent.cli.adopt import read_yes_no
from lnagent.memory.cold_archive import ColdProposalParseError, format_cold_proposal
from lnagent.memory.store import JsonMemoryStore
from lnagent.session import NovelSession, ReconcileItem


@dataclass(frozen=True)
class ColdReviewResult:
    accepted: bool
    summary: str


def read_cold_summary(
    proposal_summary: str,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> ColdReviewResult:
    output_func("请编辑场景摘要全文；单独一行 EOF 结束。仅 EOF 表示原样采纳。")
    output_func("输入 /r 或 /reject 可拒绝本场景 Cold 归档（仍将切换场景）。")

    lines: list[str] = []
    while True:
        line = input_func("")
        lowered = line.strip().lower()
        if lowered in {"/r", "/reject"}:
            return ColdReviewResult(accepted=False, summary="")
        if line == "EOF":
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    summary = text if text else proposal_summary
    return ColdReviewResult(accepted=True, summary=summary)


def run_scene_switch(
    session: NovelSession,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> str | None:
    if not session.can_switch_scene():
        output_func("当前场景须至少一次 /a 采纳后才能 /sc。\n")
        return None

    try:
        for item in session.pending_reconcile_items():
            _run_reconcile_item(session, item, input_func=input_func, output_func=output_func)

        proposal = session.prepare_cold_proposal()
        output_func(f"{format_cold_proposal(proposal)}\n")
        review = read_cold_summary(
            proposal.summary,
            input_func=input_func,
            output_func=output_func,
        )
        new_scene_id = session.finish_scene_switch(
            proposal,
            cold_accepted=review.accepted,
            summary=review.summary,
        )
    except ColdProposalParseError as exc:
        output_func(f"Cold Archive 生成失败: {exc}。请重试 /sc。\n")
        return None
    except ValueError as exc:
        output_func(f"错误: {exc}\n")
        return None

    if review.accepted:
        output_func("已写入 Cold Archive。\n")
    else:
        output_func("已拒绝 Cold 提案，仍切换至新场景。\n")
    output_func(f"新场景: {new_scene_id}\n")
    return new_scene_id


def _run_reconcile_item(
    session: NovelSession,
    item: ReconcileItem,
    *,
    input_func: Callable[[str], str],
    output_func: Callable[[str], None],
) -> None:
    output_func(f"{item.proposal.diff}\n")
    accepted = read_yes_no(
        "是否写入 Hot Canon（场景切换前补确认）? (y/n): ",
        input_func=input_func,
    )
    session.apply_reconcile(item, accepted_canon=accepted)
