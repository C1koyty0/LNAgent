"""CLI 命令解析与展示。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lnagent.memory.canon_display import format_canon_summary as _format_canon_summary
from lnagent.memory.models import HotCanon


class CommandAction(str, Enum):
    ADOPT = "adopt"
    CANON = "canon"
    CANON_MIGRATE = "canon_migrate"
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
  /canon migrate  将 Hot Canon 迁移到 schema v2（LLM 精修，y/n 确认）
  /sc, /scene   结束当前场景（须至少一次 /a）；Cold 摘要 review
  /u, /undo     撤销最后一次 adopt（正文 + Hot 一并回滚）
  /f, /fix      设定纠错（多行 + EOF 输入意图），仅改 Hot Canon
  /config       查看或修改当前项目配置
  /export       导出全书纯正文，可选输出路径
  /h, /help     显示帮助
  quit/exit/q   退出

说明：未 /a 的纯讨论轮次仅在检查点（/a、/u、/f、/sc 或退出）后写入 session.json。"""

_COMMAND_ALIASES = {
    "/a": CommandAction.ADOPT,
    "/adopt": CommandAction.ADOPT,
    "/c": CommandAction.CANON,
    "/canon": CommandAction.CANON,
    "/canon migrate": CommandAction.CANON_MIGRATE,
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

    lowered = stripped.lower()
    if lowered == "/canon migrate" or lowered.startswith("/canon migrate "):
        rest = stripped[len("/canon migrate") :].strip()
        return ParsedCommand(action=CommandAction.CANON_MIGRATE, text=rest)

    first, _, rest = stripped.partition(" ")
    action = _COMMAND_ALIASES.get(first.lower())
    if action is not None:
        if action == CommandAction.CANON and rest.lower() == "migrate":
            return ParsedCommand(action=CommandAction.CANON_MIGRATE, text="")
        return ParsedCommand(action=action, text=rest.strip())
    return ParsedCommand(action=CommandAction.MESSAGE, text=stripped)


def format_canon_summary(canon: HotCanon) -> str:
    return _format_canon_summary(canon)
