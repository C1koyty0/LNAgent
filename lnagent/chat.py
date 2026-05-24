from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage


class ChatClient(ABC):
    """对话客户端接口；后续可扩展为多轮会话实现。"""

    @abstractmethod
    def chat(self, message: str) -> str:
        """发送单条用户消息并返回助手回复（不保留历史）。"""


class LLMChatClient(ChatClient):
    """基于 LangChain 聊天模型的单轮对话实现。"""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    def chat(self, message: str) -> str:
        messages: list[BaseMessage] = [HumanMessage(content=message)]
        response = self._model.invoke(messages)
        content = response.content
        if isinstance(content, str):
            return content
        return str(content)


class ChatSession(ABC):
    """多轮会话接口（预留，当前未实现）。"""

    @abstractmethod
    def send(self, message: str) -> str:
        """发送消息并返回回复。"""

    @abstractmethod
    def clear(self) -> None:
        """清空会话历史。"""
