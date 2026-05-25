"""命令行对话入口。"""

import argparse
import sys

from lnagent import Settings, create_chat_model
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
            reply = session.send(user_input)
            print(f"助手: {reply}\n")
        except Exception as exc:
            print(f"错误: {exc}\n")

    session.save()


if __name__ == "__main__":
    run_cli()
