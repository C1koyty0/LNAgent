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


def extract_stream_chunk_content(chunk: object) -> str:
    """从 LangChain stream chunk 中提取文本增量。"""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if text is not None:
                    parts.append(str(text))
                    continue
                if block.get("type") in {"text", "output_text", "text_delta"}:
                    parts.append(str(block.get("text", "")))
        return "".join(parts)
    if content is None:
        additional = getattr(chunk, "additional_kwargs", None)
        if isinstance(additional, dict):
            for key in ("reasoning_content", "content"):
                value = additional.get(key)
                if isinstance(value, str) and value:
                    return value
        return ""
    return str(content)
