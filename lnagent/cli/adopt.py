"""`/adopt` 交互输入流。"""

from __future__ import annotations

from collections.abc import Callable


def read_adopt_text(
    candidate: str,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> str:
    output_func("上一轮候选全文：")
    output_func(candidate)
    output_func("\n请输入采纳后的完整文本；单独一行 EOF 结束。直接 EOF 表示原样采纳。")

    lines: list[str] = []
    while True:
        line = input_func("")
        if line == "EOF":
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    return text if text else candidate


def read_yes_no(
    prompt: str,
    *,
    input_func: Callable[[str], str] = input,
) -> bool:
    while True:
        answer = input_func(prompt).strip().lower()
        if answer == "y":
            return True
        if answer == "n":
            return False
        print("请输入 y 或 n。")
