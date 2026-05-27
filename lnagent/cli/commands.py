"""CLI 命令解析与展示。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from lnagent.memory.models import HotCanon


class CommandAction(str, Enum):
    ADOPT = "adopt"
    CANON = "canon"
    SCENE = "scene"
    UNDO = "undo"
    FIX = "fix"
    CONFIG = "config"
    EXPORT = "export"
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
  /sc, /scene   结束当前场景（须至少一次 /a）；Cold 摘要 review
  /u, /undo     撤销最后一次 adopt（正文 + Hot 一并回滚）
  /f, /fix      设定纠错（多行 + EOF 输入意图），仅改 Hot Canon
  /config       查看或修改当前项目配置
  /export       导出全书纯正文，可选输出路径
  /h, /help     显示帮助
  quit/exit/q   退出"""

_COMMAND_ALIASES = {
    "/a": CommandAction.ADOPT,
    "/adopt": CommandAction.ADOPT,
    "/c": CommandAction.CANON,
    "/canon": CommandAction.CANON,
    "/h": CommandAction.HELP,
    "/help": CommandAction.HELP,
    "/sc": CommandAction.SCENE,
    "/scene": CommandAction.SCENE,
    "/u": CommandAction.UNDO,
    "/undo": CommandAction.UNDO,
    "/f": CommandAction.FIX,
    "/fix": CommandAction.FIX,
    "/config": CommandAction.CONFIG,
    "/export": CommandAction.EXPORT,
}


def parse_command(text: str) -> ParsedCommand:
    stripped = text.strip()
    if not stripped:
        return ParsedCommand(action=CommandAction.MESSAGE, text="")

    first, _, rest = stripped.partition(" ")
    action = _COMMAND_ALIASES.get(first.lower())
    if action is not None:
        return ParsedCommand(action=action, text=rest.strip())
    return ParsedCommand(action=CommandAction.MESSAGE, text=stripped)


def format_canon_summary(canon: HotCanon) -> str:
    data = canon.to_dict()
    if not data["characters"] and not data["world"]["rules"] and not data["plot_threads"]:
        return "Hot Canon 为空。"
    return json.dumps(data, ensure_ascii=False, indent=2)
