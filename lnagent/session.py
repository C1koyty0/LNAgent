"""多轮小说创作会话。"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from lnagent.memory.models import NovelMeta
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore


class NovelSession:
    def __init__(
        self,
        store: JsonMemoryStore,
        model: BaseChatModel,
        meta: NovelMeta,
        *,
        prompt_builder: PromptContextBuilder | None = None,
    ) -> None:
        self._store = store
        self._model = model
        self._meta = meta
        self._prompt_builder = prompt_builder or PromptContextBuilder()
        self._buffer = ShortTermBuffer.from_session(store.load_session())

    @property
    def meta(self) -> NovelMeta:
        return self._meta

    @property
    def scene_id(self) -> str:
        return self._buffer.scene_id

    @property
    def last_candidate(self) -> str | None:
        return self._buffer.last_candidate

    def send(self, user_input: str) -> str:
        messages = self._prompt_builder.build(
            meta=self._meta,
            buffer=self._buffer,
            user_input=user_input,
        )
        response = self._model.invoke(messages)
        content = response.content
        reply = content if isinstance(content, str) else str(content)

        self._buffer.append_user(user_input)
        self._buffer.append_assistant(reply)
        self._buffer.set_candidate(reply)
        self._persist_session()
        return reply

    def save(self) -> None:
        self._persist_session()

    def _persist_session(self) -> None:
        self._store.save_session(self._buffer.to_session())
