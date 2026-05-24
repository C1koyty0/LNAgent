"""命令行对话入口。"""

from lnagent import LLMChatClient, Settings, create_chat_model

_EXIT_COMMANDS = frozenset({"quit", "exit", "q"})


def run_cli() -> None:
    settings = Settings.from_env()
    client = LLMChatClient(create_chat_model(settings))

    print("LNAgent 对话已启动（单轮，不保留历史）")
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
            reply = client.chat(user_input)
            print(f"助手: {reply}\n")
        except Exception as exc:
            print(f"错误: {exc}\n")


if __name__ == "__main__":
    run_cli()
