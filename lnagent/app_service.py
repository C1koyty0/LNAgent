"""Web/HTTP 复用的应用服务层。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lnagent.bootstrap import build_project_runtime
from lnagent.config import Settings
from lnagent.llm import create_chat_model
from lnagent.memory.canon_extractor import CanonExtractor
from lnagent.memory.cold_archive import ColdArchiveExtractor, ColdProposal
from lnagent.memory.context_budget import format_budget_notice
from lnagent.memory.models import NovelMeta
from lnagent.memory.scene_switch import SceneSwitchAdvisor
from lnagent.memory.store import JsonMemoryStore
from lnagent.project import create_project_from_meta_dict
from lnagent.project_index import ProjectSummary, list_projects
from lnagent.session import AdoptProposal, NovelSession, ReconcileItem
from lnagent.session_registry import SessionHandle, SessionRegistry


@dataclass(frozen=True)
class ScenePrepareState:
    project_id: str
    proposal: ColdProposal


class AppService:
    def __init__(
        self,
        *,
        projects_dir: Path,
        settings_factory: Callable[[], Settings | None] | None = None,
        model_factory: Callable[[str], Any] | None = None,
        canon_extractor_factory: Callable[[Any], Any] | None = None,
        cold_extractor_factory: Callable[[Any], Any] | None = None,
        registry: SessionRegistry | None = None,
    ) -> None:
        self._projects_dir = projects_dir
        self._settings_factory = settings_factory or Settings.from_env
        self._model_factory = model_factory
        self._canon_extractor_factory = canon_extractor_factory or CanonExtractor
        self._cold_extractor_factory = cold_extractor_factory or ColdArchiveExtractor
        self._registry = registry or SessionRegistry()
        self._scene_prepare_states: dict[str, ScenePrepareState] = {}

    @property
    def projects_dir(self) -> Path:
        return self._projects_dir

    def list_projects(self) -> list[ProjectSummary]:
        return list_projects(self._projects_dir)

    def create_project(self, project_id: str, meta_data: dict) -> dict:
        normalized = project_id.strip()
        if not normalized:
            raise ValueError("project_id 不能为空")
        store = JsonMemoryStore(self._projects_dir / normalized)
        meta = create_project_from_meta_dict(store, meta_data)
        return {
            "project_id": normalized,
            "meta": meta.to_dict(),
        }

    def open_project(self, project_id: str) -> SessionHandle:
        normalized = project_id.strip()
        if not normalized:
            raise ValueError("project_id 不能为空")
        return self._registry.get_or_create(
            normalized,
            lambda: self._create_session_handle(normalized),
        )

    def get_project_overview(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        return {
            "project_id": project_id,
            "title": handle.meta.title,
            "style": handle.meta.style,
            "scene_id": handle.session.scene_id,
            "has_candidate": handle.session.last_candidate is not None,
        }

    def get_meta(self, project_id: str) -> dict:
        return self.open_project(project_id).meta.to_dict()

    def get_canon(self, project_id: str) -> dict:
        return self.open_project(project_id).store.load_canon().to_dict()

    def get_synopsis(self, project_id: str) -> dict:
        return self.open_project(project_id).store.load_synopsis().to_dict()

    def get_config(self, project_id: str) -> dict:
        return self.open_project(project_id).session.config.to_dict()

    def get_session_state(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        session = handle.session
        buffer = session._buffer
        return {
            "scene_id": session.scene_id,
            "last_candidate": session.last_candidate,
            "turns_since_last_adopt": session.turns_since_last_adopt,
            "budget_notice": format_budget_notice(session.last_budget_report),
            "adopt_stack": [record.to_dict() for record in session.adopt_stack],
            "messages": [message.to_dict() for message in buffer.messages],
            "adopted_prose": buffer.adopted_prose,
        }

    def get_manuscript(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        scene_id = handle.session.scene_id
        return {
            "scene_id": scene_id,
            "text": handle.store.read_scene_manuscript(scene_id),
        }

    def send_message(self, project_id: str, text: str) -> dict:
        handle = self.open_project(project_id)
        reply = handle.session.send(text)
        suggestion = SceneSwitchAdvisor(handle.session.config.scene_switch).suggest(
            adopt_count=len(handle.session.adopt_stack),
            turns_since_last_adopt=handle.session.turns_since_last_adopt,
        )
        return {
            "reply": reply,
            "last_candidate": handle.session.last_candidate,
            "budget_notice": format_budget_notice(handle.session.last_budget_report),
            "scene_switch_suggestion": {
                "should_suggest": suggestion.should_suggest,
                "reason": suggestion.reason,
            },
        }

    def prepare_adopt(self, project_id: str, text: str | None) -> dict:
        handle = self.open_project(project_id)
        source_text = text if text is not None else handle.session.last_candidate
        if source_text is None:
            raise ValueError("没有可采纳候选")
        proposal = handle.session.prepare_adopt(source_text)
        return self._proposal_to_dict(proposal)

    def commit_adopt(
        self,
        project_id: str,
        text: str | None,
        *,
        accepted_canon: bool,
    ) -> dict:
        handle = self.open_project(project_id)
        source_text = text if text is not None else handle.session.last_candidate
        if source_text is None:
            raise ValueError("没有可采纳候选")
        proposal = handle.session.prepare_adopt(source_text)
        handle.session.commit_adopt(proposal, accepted_canon=accepted_canon)
        return {
            "scene_id": handle.session.scene_id,
            "last_candidate": handle.session.last_candidate,
            "manuscript_text": handle.store.read_scene_manuscript(handle.session.scene_id),
            "adopt_stack": [record.to_dict() for record in handle.session.adopt_stack],
        }

    def prepare_fix(self, project_id: str, intent: str) -> dict:
        proposal = self.open_project(project_id).session.prepare_fix(intent)
        return self._proposal_to_dict(proposal)

    def commit_fix(self, project_id: str, intent: str, *, accepted_canon: bool) -> dict:
        handle = self.open_project(project_id)
        proposal = handle.session.prepare_fix(intent)
        if accepted_canon:
            handle.session.commit_fix(proposal)
        return {
            "accepted_canon": accepted_canon,
            "canon": handle.store.load_canon().to_dict(),
        }

    def prepare_scene_switch(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        if not handle.session.can_switch_scene():
            raise ValueError("当前场景须至少一次 /a 采纳后才能 /sc")
        reconcile_items = handle.session.pending_reconcile_items()
        proposal = handle.session.prepare_cold_proposal()
        self._scene_prepare_states[project_id] = ScenePrepareState(
            project_id=project_id,
            proposal=proposal,
        )
        return {
            "reconcile_items": [self._reconcile_item_to_dict(item) for item in reconcile_items],
            "proposal": self._cold_proposal_to_dict(proposal),
        }

    def apply_scene_reconcile(
        self,
        project_id: str,
        stack_index: int,
        *,
        accepted_canon: bool,
    ) -> dict:
        handle = self.open_project(project_id)
        items = handle.session.pending_reconcile_items()
        item = next(
            (candidate for candidate in items if candidate.stack_index == stack_index),
            None,
        )
        if item is None:
            raise ValueError("未找到待确认的 reconcile 项")
        handle.session.apply_reconcile(item, accepted_canon=accepted_canon)
        return {
            "stack_index": stack_index,
            "accepted_canon": accepted_canon,
        }

    def commit_scene_switch(
        self,
        project_id: str,
        *,
        cold_accepted: bool,
        summary: str,
    ) -> dict:
        handle = self.open_project(project_id)
        prepared = self._scene_prepare_states.get(project_id)
        proposal = (
            handle.session.prepare_cold_proposal()
            if prepared is None
            else prepared.proposal
        )
        new_scene_id = handle.session.finish_scene_switch(
            proposal,
            cold_accepted=cold_accepted,
            summary=summary,
        )
        self._scene_prepare_states.pop(project_id, None)
        return {
            "new_scene_id": new_scene_id,
            "cold_accepted": cold_accepted,
            "session": self.get_session_state(project_id),
        }

    def _create_session_handle(self, project_id: str) -> SessionHandle:
        settings = self._settings_factory()
        if settings is None:
            raise ValueError("未提供运行设置")
        runtime_settings = settings.with_project(project_id)
        store = JsonMemoryStore(runtime_settings.project_dir)
        if not store.project_exists():
            raise ValueError(f"项目不存在: {project_id}")
        meta = store.load_meta()
        model_factory = self._model_factory
        runtime = build_project_runtime(
            runtime_settings,
            store,
            meta,
            model_factory=(
                (lambda passed_settings: model_factory(project_id))
                if model_factory is not None
                else create_chat_model
            ),
            session_factory=self._build_session,
        )
        return SessionHandle(
            project_id=project_id,
            store=runtime.store,
            meta=runtime.meta,
            session=runtime.session,
        )

    def _build_session(
        self,
        store: JsonMemoryStore,
        model: Any,
        meta: NovelMeta,
    ) -> NovelSession:
        return NovelSession(
            store,
            model,
            meta,
            canon_extractor=self._canon_extractor_factory(model),
            cold_extractor=self._cold_extractor_factory(model),
        )

    @staticmethod
    def _proposal_to_dict(proposal: AdoptProposal) -> dict:
        return {
            "text": proposal.text,
            "diff": proposal.diff,
            "canon_before": proposal.canon_before.to_dict(),
            "canon_patch": proposal.canon_patch.to_dict(),
            "canon_after": proposal.canon_after.to_dict(),
        }

    @staticmethod
    def _cold_proposal_to_dict(proposal: ColdProposal) -> dict:
        return {
            "location": proposal.location,
            "time": proposal.time,
            "summary": proposal.summary,
            "key_points": proposal.key_points,
        }

    @classmethod
    def _reconcile_item_to_dict(cls, item: ReconcileItem) -> dict:
        return {
            "stack_index": item.stack_index,
            "proposal": cls._proposal_to_dict(item.proposal),
        }
