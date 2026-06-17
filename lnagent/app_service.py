"""Web/HTTP 复用的应用服务层。"""

from __future__ import annotations

import queue
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any

from lnagent.bootstrap import build_project_runtime
from lnagent.config import Settings
from lnagent.llm import create_chat_model
from lnagent.memory.canon_extractor import CanonExtractor
from lnagent.memory.cold_archive import ColdArchiveExtractor, ColdProposal
from lnagent.memory.context_budget import format_budget_notice
from lnagent.memory.models import DiscussionBrief, NovelMeta
from lnagent.memory.scene_switch import SceneSwitchAdvisor
from lnagent.memory.store import JsonMemoryStore
from lnagent.cli.config import (
    ConfigCommandError,
    flatten_project_config,
    handle_config_args,
    list_config_keys,
)
from lnagent.cli.export import export_manuscript as write_export_manuscript
from lnagent.project import create_project_from_meta_dict
from lnagent.project_index import ProjectSummary, list_projects
from lnagent.session import AdoptProposal, NovelSession, ReconcileItem
from lnagent.session_registry import SessionHandle, SessionRegistry
from lnagent.template_store import JsonTemplateStore


@dataclass(frozen=True)
class ScenePrepareState:
    project_id: str
    proposal: ColdProposal


@dataclass(frozen=True)
class _QueueEvent:
    payload: dict[str, Any] | None = None
    done: bool = False


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

    def list_templates(self) -> list[dict[str, Any]]:
        return JsonTemplateStore(self._projects_dir).list_templates()

    def save_template(self, project_id: str, name: str) -> dict[str, Any]:
        handle = self.open_project(project_id)
        return JsonTemplateStore(self._projects_dir).save_template(name, handle.meta.to_dict())

    def delete_template(self, name: str) -> dict[str, Any]:
        deleted = JsonTemplateStore(self._projects_dir).delete_template(name)
        return {
            "deleted": deleted,
            "name": str(name).strip(),
        }

    def update_meta(self, project_id: str, meta_data: dict) -> dict:
        handle = self.open_project(project_id)
        if not isinstance(meta_data, dict):
            raise ValueError("meta 数据必须是对象")

        merged = handle.meta.to_dict()
        for field in (
            "style",
            "pov",
            "tense",
            "genre",
            "tone",
            "target_audience",
        ):
            if field in meta_data:
                raw_value = meta_data.get(field)
                merged[field] = "" if raw_value is None else str(raw_value).strip()

        for field in ("taboos", "narrative_rules"):
            if field in meta_data:
                merged[field] = self._normalize_meta_list(meta_data.get(field))

        if not str(merged.get("style", "")).strip():
            raise ValueError("style 不能为空")

        updated_meta = NovelMeta.from_dict(merged)
        handle.store.save_meta(updated_meta)
        handle.session.update_meta(updated_meta)
        self._registry.replace(
            handle.project_id,
            SessionHandle(
                project_id=handle.project_id,
                store=handle.store,
                meta=updated_meta,
                session=handle.session,
            ),
        )
        return updated_meta.to_dict()

    def get_canon(self, project_id: str) -> dict:
        return self.open_project(project_id).store.load_canon().to_dict()

    def get_synopsis(self, project_id: str) -> dict:
        return self.open_project(project_id).store.load_synopsis().to_dict()

    def get_config(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        config = handle.session.config.to_dict()
        return {
            **config,
            "available_keys": list_config_keys(),
            "flat": flatten_project_config(handle.session.config),
        }

    def update_config(
        self,
        project_id: str,
        *,
        action: str,
        key: str = "",
        value: int | None = None,
    ) -> dict:
        handle = self.open_project(project_id)
        normalized_action = action.strip().lower()
        if normalized_action == "set":
            if not key.strip():
                raise ValueError("set 需要 key")
            if value is None:
                raise ValueError("set 需要 value")
            args = f"set {key.strip()} {value}"
        elif normalized_action == "reset":
            if not key.strip():
                raise ValueError("reset 需要 key 或 all")
            args = f"reset {key.strip()}"
        else:
            raise ValueError(f"未知 config action: {action}")
        try:
            updated, message = handle_config_args(handle.session.config, args)
        except ConfigCommandError as exc:
            raise ValueError(str(exc)) from exc
        if updated != handle.session.config:
            handle.session.update_config(updated)
        return {
            "config": self.get_config(project_id),
            "message": message,
        }

    def undo_last_adopt(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        record = handle.session.undo_last_adopt()
        return {
            "message": "已撤销最后一次采纳",
            "undone_text": record.text,
            "session": self.get_session_state(project_id),
        }

    def export_manuscript(self, project_id: str, output_path: str | None = None) -> dict:
        handle = self.open_project(project_id)
        target = Path(output_path) if output_path else None
        written = write_export_manuscript(handle.store, target)
        content = written.read_text(encoding="utf-8")
        try:
            relative_path = str(written.relative_to(handle.store.project_dir))
        except ValueError:
            relative_path = str(written)
        return {
            "path": relative_path,
            "filename": written.name,
            "content": content,
        }

    def list_manuscripts(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        scenes: list[dict[str, str]] = []
        for scene_path in handle.store.list_scene_manuscript_paths():
            scenes.append(
                {
                    "scene_id": scene_path.stem,
                    "text": scene_path.read_text(encoding="utf-8"),
                }
            )
        return {
            "current_scene_id": handle.session.scene_id,
            "scenes": scenes,
        }

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
        return self.send_writing_message(project_id, text)

    def send_writing_message(self, project_id: str, text: str) -> dict:
        handle = self.open_project(project_id)
        reply = handle.session.send_writing(str(text))
        return self._build_send_payload(handle, reply)

    def send_discussion_message(self, project_id: str, text: str) -> dict:
        handle = self.open_project(project_id)
        reply = handle.session.send_discussion(str(text))
        return {
            "reply": reply,
            **self._build_discussion_payload(handle),
        }

    def get_discussion_state(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        return self._build_discussion_payload(handle)

    def refresh_discussion_brief(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        handle.session._ensure_fresh_discussion_brief()
        return self._build_discussion_payload(handle)

    def clear_discussion_messages(self, project_id: str) -> dict:
        handle = self.open_project(project_id)
        scene_id = handle.session.scene_id
        brief = handle.store.load_discussion_brief(scene_id)
        if brief.dirty:
            brief.dirty = False
            handle.store.save_discussion_brief(scene_id, brief)
        handle.store.clear_discussion_messages(scene_id)
        return self._build_discussion_payload(handle)

    def save_discussion_brief(
        self,
        project_id: str,
        *,
        todo_items: Any,
        constraints: Any,
        open_questions: Any,
    ) -> dict:
        handle = self.open_project(project_id)
        scene_id = handle.session.scene_id
        brief = DiscussionBrief.from_edit_payload(
            scene_id,
            todo_items=todo_items,
            constraints=constraints,
            open_questions=open_questions,
        )
        handle.store.save_discussion_brief(scene_id, brief)
        return self._build_discussion_payload(handle)

    def stream_message(self, project_id: str, text: str) -> Iterator[dict[str, Any]]:
        yield from self.stream_writing_message(project_id, text)

    def stream_writing_message(self, project_id: str, text: str) -> Iterator[dict[str, Any]]:
        try:
            handle = self.open_project(project_id)
        except ValueError as exc:
            yield {"event": "error", "data": {"error": str(exc)}}
            return

        yield from self._stream_session_reply(
            handle,
            lambda: handle.session.stream_send_writing(str(text)),
            lambda reply: self._build_send_payload(handle, reply),
        )

    def _stream_session_reply(
        self,
        handle: SessionHandle,
        stream_factory: Callable[[], Iterator[str]],
        done_payload_factory: Callable[[str], dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        event_queue: queue.SimpleQueue[_QueueEvent] = queue.SimpleQueue()

        def worker() -> None:
            try:
                for token in stream_factory():
                    event_queue.put(_QueueEvent(payload={"event": "token", "data": {"text": token}}))
                reply = handle.session.last_candidate or ""
                event_queue.put(
                    _QueueEvent(payload={"event": "done", "data": done_payload_factory(reply)})
                )
            except ValueError as exc:
                event_queue.put(_QueueEvent(payload={"event": "error", "data": {"error": str(exc)}}))
            except Exception as exc:
                event_queue.put(_QueueEvent(payload={"event": "error", "data": {"error": str(exc)}}))
            finally:
                event_queue.put(_QueueEvent(done=True))

        Thread(target=worker, daemon=True).start()

        while True:
            item = event_queue.get()
            if item.done:
                break
            if item.payload is not None:
                yield item.payload

    def _build_send_payload(self, handle: SessionHandle, reply: str) -> dict:
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

    def _build_discussion_payload(self, handle: SessionHandle) -> dict:
        scene_id = handle.session.scene_id
        messages = handle.store.load_discussion_messages(scene_id)
        brief = handle.store.load_discussion_brief(scene_id)
        return {
            "scene_id": scene_id,
            "messages": [message.to_dict() for message in messages],
            "brief": brief.to_dict(),
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

    @staticmethod
    def _normalize_meta_list(value: Any) -> list[str]:
        if isinstance(value, list):
            items = value
        elif value is None:
            items = []
        else:
            items = [value]
        normalized: list[str] = []
        for item in items:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
