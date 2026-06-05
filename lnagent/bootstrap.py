"""CLI 与 Web 共享的运行时初始化。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from langchain_core.language_models import BaseChatModel

from lnagent.config import Settings
from lnagent.llm import create_chat_model
from lnagent.memory.models import NovelMeta
from lnagent.memory.store import JsonMemoryStore
from lnagent.project import open_or_create_project
from lnagent.session import NovelSession


class SessionFactory(Protocol):
    def __call__(
        self,
        store: JsonMemoryStore,
        model: BaseChatModel,
        meta: NovelMeta,
    ) -> NovelSession: ...


@dataclass(frozen=True)
class ProjectRuntime:
    settings: Settings
    store: JsonMemoryStore
    meta: NovelMeta
    model: BaseChatModel
    session: NovelSession


def bootstrap_project_runtime(
    project_id: str,
    *,
    meta_path: Path | None = None,
    settings: Settings | None = None,
    model_factory: Callable[[Settings], BaseChatModel] = create_chat_model,
    session_factory: SessionFactory = NovelSession,
) -> ProjectRuntime:
    runtime_settings = (settings or Settings.from_env()).with_project(project_id)
    store = JsonMemoryStore(runtime_settings.project_dir)
    meta = open_or_create_project(store, meta_path=meta_path)
    return build_project_runtime(
        runtime_settings,
        store,
        meta,
        model_factory=model_factory,
        session_factory=session_factory,
    )


def build_project_runtime(
    settings: Settings,
    store: JsonMemoryStore,
    meta: NovelMeta,
    *,
    model_factory: Callable[[Settings], BaseChatModel] = create_chat_model,
    session_factory: SessionFactory = NovelSession,
) -> ProjectRuntime:
    model = model_factory(settings)
    session = session_factory(store, model, meta)
    return ProjectRuntime(
        settings=settings,
        store=store,
        meta=meta,
        model=model,
        session=session,
    )
