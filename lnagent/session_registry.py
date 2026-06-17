"""进程内 NovelSession 注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from lnagent.memory.models import NovelMeta
from lnagent.memory.store import JsonMemoryStore
from lnagent.session import NovelSession


@dataclass(frozen=True)
class SessionHandle:
    project_id: str
    store: JsonMemoryStore
    meta: NovelMeta
    session: NovelSession


class SessionRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, SessionHandle] = {}

    def get(self, project_id: str) -> SessionHandle | None:
        with self._lock:
            return self._sessions.get(project_id)

    def get_or_create(self, project_id: str, factory) -> SessionHandle:
        with self._lock:
            existing = self._sessions.get(project_id)
            if existing is not None:
                return existing
            handle = factory()
            self._sessions[project_id] = handle
            return handle

    def replace(self, project_id: str, handle: SessionHandle) -> SessionHandle:
        with self._lock:
            self._sessions[project_id] = handle
            return handle

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
