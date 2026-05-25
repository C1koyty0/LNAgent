"""当前场景短期记忆缓冲。"""

from __future__ import annotations

from lnagent.memory.models import ChatMessage, SceneSession


class ShortTermBuffer:
    """场景内对话与正文缓冲；last_candidate 仅驻内存。"""

    def __init__(
        self,
        scene_id: str,
        messages: list[ChatMessage] | None = None,
        adopted_prose: str = "",
    ) -> None:
        self._scene_id = scene_id
        self._messages: list[ChatMessage] = list(messages or [])
        self._adopted_prose = adopted_prose
        self._last_candidate: str | None = None

    @classmethod
    def from_session(cls, session: SceneSession) -> ShortTermBuffer:
        return cls(
            scene_id=session.scene_id,
            messages=list(session.messages),
            adopted_prose=session.adopted_prose,
        )

    @property
    def scene_id(self) -> str:
        return self._scene_id

    @property
    def adopted_prose(self) -> str:
        return self._adopted_prose

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    @property
    def last_candidate(self) -> str | None:
        return self._last_candidate

    def append_user(self, text: str) -> None:
        self._messages.append(ChatMessage(role="user", content=text))

    def append_assistant(self, text: str) -> None:
        self._messages.append(ChatMessage(role="assistant", content=text))

    def set_candidate(self, text: str) -> None:
        self._last_candidate = text

    def clear_candidate(self) -> None:
        self._last_candidate = None

    def to_session(self) -> SceneSession:
        return SceneSession(
            scene_id=self._scene_id,
            messages=list(self._messages),
            adopted_prose=self._adopted_prose,
        )
