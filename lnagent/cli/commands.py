"""CLI 命令解析与展示。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from lnagent.memory.models import HotCanon


class CommandAction(str, Enum):
    ADOPT = "adopt"
    CANON = "canon"
    HELP = "help"
    MESSAGE = "message"


@dataclass(frozen=True)
class ParsedCommand:
    action: CommandAction
    text: str = ""


HELP_TEXT = """\
可用命令:
  /a, /adopt    采纳上一轮候选正文，并确认 Hot Canon 变更
  /c, /canon    查看当前 Hot Canon
  /h, /help     显示帮助
  quit/exit/q   退出"""

_COMMAND_ALIASES = {
    "/a": CommandAction.ADOPT,
    "/adopt": CommandAction.ADOPT,
    "/c": CommandAction.CANON,
    "/canon": CommandAction.CANON,
    "/h": CommandAction.HELP,
    "/help": CommandAction.HELP,
}


def parse_command(text: str) -> ParsedCommand:
    stripped = text.strip()
    action = _COMMAND_ALIASES.get(stripped.lower())
    if action is not None:
        return ParsedCommand(action=action)
    return ParsedCommand(action=CommandAction.MESSAGE, text=stripped)


def format_canon_summary(canon: HotCanon) -> str:
    data = canon.to_dict()
    if not data["characters"] and not data["world"]["rules"] and not data["plot_threads"]:
        return "Hot Canon 为空。"
    return json.dumps(data, ensure_ascii=False, indent=2)
