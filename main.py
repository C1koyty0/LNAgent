"""命令行对话入口。"""

import argparse
import sys

from lnagent import Settings, create_chat_model
from lnagent.cli.adopt import read_adopt_text, read_yes_no
from lnagent.cli.commands import (
    HELP_TEXT,
    CommandAction,
    format_canon_summary,
    parse_command,
)
from lnagent.memory.canon_extractor import CanonPatchParseError
from lnagent.memory.store import JsonMemoryStore
from lnagent.project import open_or_create_project
from lnagent.session import NovelSession

_EXIT_COMMANDS = frozenset({"quit", "exit", "q"})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LNAgent CLI")
    parser.add_argument(
        "--project",
        required=True,
        metavar="ID",
        help="novel project id (projects/<ID>/)",
    )
    return parser.parse_args(argv)


def run_cli(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = Settings.from_env().with_project(args.project)
    store = JsonMemoryStore(settings.project_dir)

    try:
        meta = open_or_create_project(store)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    model = create_chat_model(settings)
    session = NovelSession(store, model, meta)

    print("LNAgent 对话已启动（多轮，当前场景）")
    print(f"项目: {args.project}")
    print(f"书名: {meta.title}")
    print(f"场景: {session.scene_id}")
    print(f"模型: {settings.model}")
    print("输入 quit / exit / q 退出\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in _EXIT_COMMANDS:
            break

        try:
            command = parse_command(user_input)
            if command.action == CommandAction.ADOPT:
                if session.last_candidate is None:
                    print("没有可采纳候选。请先输入创作指令生成候选。\n")
                    continue
                adopted_text = read_adopt_text(session.last_candidate)
                proposal = session.prepare_adopt(adopted_text)
                print(f"{proposal.diff}\n")
                accepted = read_yes_no("是否写入 Hot Canon? (y/n): ")
                session.commit_adopt(proposal, accepted_canon=accepted)
                print("已采纳正文。\n")
            elif command.action == CommandAction.CANON:
                print(format_canon_summary(store.load_canon()))
                print()
            elif command.action == CommandAction.HELP:
                print(HELP_TEXT)
                print()
            else:
                reply = session.send(command.text)
                print(f"助手: {reply}\n")
        except CanonPatchParseError as exc:
            print(f"Hot Canon 抽取失败: {exc}。请重试 /a。\n")
        except Exception as exc:
            print(f"错误: {exc}\n")

    session.save()


if __name__ == "__main__":
    run_cli()
