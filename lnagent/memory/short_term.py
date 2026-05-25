"""当前场景短期记忆缓冲。"""

from __future__ import annotations

from lnagent.memory.models import AdoptRecord, ChatMessage, SceneSession


class ShortTermBuffer:
    """场景内对话与正文缓冲；last_candidate 仅驻内存。"""

    def __init__(
        self,
        scene_id: str,
        messages: list[ChatMessage] | None = None,
        adopted_prose: str = "",
        adopt_stack: list[AdoptRecord] | None = None,
    ) -> None:
        self._scene_id = scene_id
        self._messages: list[ChatMessage] = list(messages or [])
        self._adopted_prose = adopted_prose
        self._adopt_stack: list[AdoptRecord] = list(adopt_stack or [])
        self._last_candidate: str | None = None

    @classmethod
    def from_session(
        cls,
        session: SceneSession,
        *,
        drop_pending_candidate: bool = False,
    ) -> ShortTermBuffer:
        messages = list(session.messages)
        if (
            drop_pending_candidate
            and messages
            and messages[-1].role == "assistant"
        ):
            messages = messages[:-1]

        return cls(
            scene_id=session.scene_id,
            messages=messages,
            adopted_prose=session.adopted_prose,
            adopt_stack=session.adopt_stack,
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
    def adopt_stack(self) -> list[AdoptRecord]:
        return list(self._adopt_stack)

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

    def append_adopted_prose(self, text: str) -> None:
        self._adopted_prose = append_prose(self._adopted_prose, text)

    def record_adopt(self, record: AdoptRecord) -> None:
        self._adopt_stack.append(record)

    def mark_adopt_canon_accepted(self, index: int, *, accepted: bool) -> None:
        record = self._adopt_stack[index]
        self._adopt_stack[index] = AdoptRecord(
            text=record.text,
            canon_before=record.canon_before,
            canon_patch=record.canon_patch,
            accepted_canon=accepted,
        )

    def reset_for_new_scene(self, scene_id: str) -> None:
        self._scene_id = scene_id
        self._messages.clear()
        self._adopted_prose = ""
        self._adopt_stack.clear()
        self._last_candidate = None

    def to_session(self) -> SceneSession:
        return SceneSession(
            scene_id=self._scene_id,
            messages=list(self._messages),
            adopted_prose=self._adopted_prose,
            adopt_stack=list(self._adopt_stack),
        )


def append_prose(existing: str, text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return existing
    if existing.strip():
        return existing.rstrip() + "\n\n" + normalized + "\n"
    return normalized + "\n"
