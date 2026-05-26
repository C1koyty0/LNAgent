"""`/fix` 设定纠错交互流。"""

from __future__ import annotations

from collections.abc import Callable

from lnagent.cli.adopt import read_yes_no
from lnagent.memory.canon_extractor import is_empty_canon_patch
from lnagent.session import NovelSession


def read_fix_intent(
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> str:
    output_func("请输入纠错意图；单独一行 EOF 结束。")

    lines: list[str] = []
    while True:
        line = input_func("")
        if line == "EOF":
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("纠错意图不能为空")
    return text


def run_fix(
    session: NovelSession,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> None:
    try:
        intent = read_fix_intent(input_func=input_func, output_func=output_func)
        proposal = session.prepare_fix(intent)
    except ValueError as exc:
        output_func(f"错误: {exc}\n")
        return

    if is_empty_canon_patch(proposal.canon_patch):
        output_func("无 Hot Canon 变更。\n")
        return

    output_func(f"{proposal.diff}\n")
    accepted = read_yes_no("是否写入 Hot Canon? (y/n): ", input_func=input_func)
    if accepted:
        session.commit_fix(proposal)
        output_func("已更新 Hot Canon。\n")
    else:
        output_func("已取消 Hot Canon 变更。\n")
