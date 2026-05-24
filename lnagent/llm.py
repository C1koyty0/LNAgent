from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from lnagent.config import Settings


def create_chat_model(settings: Settings) -> BaseChatModel:
    """根据配置创建聊天模型实例。"""
    kwargs: dict = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url

    return init_chat_model(
        settings.model,
        model_provider="openai",
        **kwargs,
    )
