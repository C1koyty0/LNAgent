"""`/undo` 撤销最后一次 adopt。"""

from __future__ import annotations

from collections.abc import Callable

from lnagent.session import NovelSession


def run_undo(
    session: NovelSession,
    *,
    output_func: Callable[[str], None] = print,
) -> None:
    try:
        session.undo_last_adopt()
    except ValueError as exc:
        output_func(f"错误: {exc}\n")
        return
    output_func("已撤销最后一次采纳。\n")
