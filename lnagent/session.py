"""多轮小说创作会话。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models import BaseChatModel

from lnagent.llm import extract_stream_chunk_content
from lnagent.memory.canon_extractor import (
    CanonExtractor,
    format_canon_diff,
    merge_hot_canon,
)
from lnagent.memory.cold_archive import (
    ColdArchiveExtractor,
    ColdProposal,
)
from lnagent.memory.context_budget import BudgetReport
from lnagent.memory.models import (
    AdoptRecord,
    ChatMessage,
    DiscussionBrief,
    HotCanon,
    NovelMeta,
    ProjectConfig,
    SceneSynopsisEntry,
    next_scene_id,
    previous_scene_id,
)
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer, build_prose_from_records
from lnagent.memory.store import JsonMemoryStore
from lnagent.memory.discussion_brief import (
    DiscussionBriefModel,
    DiscussionBriefRefreshError,
    DiscussionBriefRefresher,
)


class CanonPatchExtractor(Protocol):
    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon: ...

    def extract_fix_patch(self, correction_intent: str, canon: HotCanon) -> HotCanon: ...


class ColdArchiveGateway(Protocol):
    def propose(
        self,
        scene_id: str,
        adopted_text: str,
        *,
        meta: NovelMeta | None = None,
    ) -> ColdProposal: ...

    def rollup_global(
        self,
        old_global: str,
        scene_entry: SceneSynopsisEntry,
    ) -> str: ...


@dataclass(frozen=True)
class AdoptProposal:
    text: str
    canon_before: HotCanon
    canon_patch: HotCanon
    canon_after: HotCanon
    diff: str


@dataclass(frozen=True)
class ReconcileItem:
    stack_index: int
    proposal: AdoptProposal


def _non_empty_or_none(brief: DiscussionBrief) -> DiscussionBrief | None:
    if brief.todo_items or brief.constraints or brief.open_questions:
        return brief
    return None


class NovelSession:
    def __init__(
        self,
        store: JsonMemoryStore,
        model: BaseChatModel,
        meta: NovelMeta,
        *,
        prompt_builder: PromptContextBuilder | None = None,
        canon_extractor: CanonPatchExtractor | None = None,
        cold_extractor: ColdArchiveGateway | None = None,
        discussion_brief_refresher: DiscussionBriefRefresher | None = None,
    ) -> None:
        self._store = store
        self._model = model
        self._meta = meta
        self._config = store.load_config()
        self._prompt_builder = prompt_builder or PromptContextBuilder()
        self._canon_extractor = canon_extractor or CanonExtractor(model)
        self._cold_extractor = cold_extractor or ColdArchiveExtractor(model)
        self._brief_refresher = discussion_brief_refresher or DiscussionBriefRefresher(model)
        self._buffer = ShortTermBuffer.from_session(
            store.load_session(),
            drop_pending_candidate=True,
        )
        self._turns_since_last_adopt = 0
        self._last_budget_report = BudgetReport()
        self._scene_tail, self._prior_scene_cold = self._load_scene_prompt_context()

    @property
    def meta(self) -> NovelMeta:
        return self._meta

    @property
    def config(self) -> ProjectConfig:
        return self._config

    @property
    def scene_id(self) -> str:
        return self._buffer.scene_id

    @property
    def last_candidate(self) -> str | None:
        return self._buffer.last_candidate

    @property
    def adopt_stack(self) -> list[AdoptRecord]:
        return self._buffer.adopt_stack

    @property
    def turns_since_last_adopt(self) -> int:
        return self._turns_since_last_adopt

    @property
    def last_budget_report(self) -> BudgetReport:
        return self._last_budget_report

    def update_meta(self, meta: NovelMeta) -> None:
        self._meta = meta

    def can_switch_scene(self) -> bool:
        return len(self._buffer.adopt_stack) > 0

    def send(self, user_input: str) -> str:
        return self.send_writing(user_input)

    def send_writing(self, user_input: str) -> str:
        messages = self._prepare_writing_messages(user_input)
        return self._complete_writing_send(user_input, self._invoke_reply(messages))

    def send_discussion(self, user_input: str) -> str:
        messages = self._prepare_discussion_messages(user_input)
        return self._complete_discussion_send(user_input, self._invoke_reply(messages))

    def stream_send(self, user_input: str):
        yield from self.stream_send_writing(user_input)

    def stream_send_writing(self, user_input: str):
        """逐块产出写作回复文本，并在结束时写入会话内存状态。"""
        messages = self._prepare_writing_messages(user_input)
        yield from self._stream_with_completion(
            messages,
            lambda reply: self._complete_writing_send(user_input, reply),
        )

    def stream_send_discussion(self, user_input: str):
        """逐块产出讨论回复文本，并在结束时写入 discussion raw chat。"""
        messages = self._prepare_discussion_messages(user_input)
        yield from self._stream_with_completion(
            messages,
            lambda reply: self._complete_discussion_send(user_input, reply),
        )

    def _stream_with_completion(self, messages: list, on_complete):
        stream = getattr(self._model, "stream", None)
        if not callable(stream):
            reply = self._invoke_reply(messages)
            on_complete(reply)
            yield reply
            return

        assembled = ""
        completed = False
        try:
            for chunk in stream(messages):
                token = extract_stream_chunk_content(chunk)
                if not token:
                    continue
                if token.startswith(assembled) and len(token) > len(assembled):
                    delta = token[len(assembled) :]
                    assembled = token
                else:
                    delta = token
                    assembled += token
                if not delta:
                    continue
                yield delta
            if not assembled:
                reply = self._invoke_reply(messages)
                on_complete(reply)
                yield reply
                completed = True
                return
            on_complete(assembled)
            completed = True
        finally:
            if not completed and assembled:
                on_complete(assembled)

    def _prepare_writing_messages(self, user_input: str) -> list:
        canon = self._store.load_canon()
        synopsis = self._store.load_synopsis()
        discussion_brief = self._ensure_fresh_discussion_brief()
        messages = self._prompt_builder.build_writing(
            meta=self._meta,
            canon=canon,
            buffer=self._buffer,
            user_input=user_input,
            global_summary=synopsis.global_summary,
            prior_scene_cold=self._prior_scene_cold,
            scene_tail=self._scene_tail,
            context_config=self._config.context,
            discussion_brief=discussion_brief,
        )
        self._last_budget_report = getattr(
            self._prompt_builder,
            "last_budget_report",
            BudgetReport(),
        )
        return messages

    def _prepare_discussion_messages(self, user_input: str) -> list:
        canon = self._store.load_canon()
        synopsis = self._store.load_synopsis()
        discussion_buffer = self._build_discussion_buffer()
        messages = self._prompt_builder.build_discussion(
            meta=self._meta,
            canon=canon,
            buffer=discussion_buffer,
            user_input=user_input,
            global_summary=synopsis.global_summary,
            prior_scene_cold=self._prior_scene_cold,
            scene_tail=self._scene_tail,
            context_config=self._config.context,
        )
        self._last_budget_report = getattr(
            self._prompt_builder,
            "last_budget_report",
            BudgetReport(),
        )
        return messages

    def _build_discussion_buffer(self) -> ShortTermBuffer:
        messages = self._store.load_discussion_messages(self._buffer.scene_id)
        return ShortTermBuffer(
            scene_id=self._buffer.scene_id,
            messages=list(messages),
        )

    def _invoke_reply(self, messages: list) -> str:
        response = self._model.invoke(messages)
        content = response.content
        return content if isinstance(content, str) else str(content)

    def _ensure_fresh_discussion_brief(self) -> DiscussionBrief | None:
        """writing 前确保拿到最新可用 brief（必要时调用 refresher）。"""
        scene_id = self._buffer.scene_id
        raw = self._store.load_discussion_messages(scene_id)
        brief = self._store.load_discussion_brief(scene_id)

        if not raw:
            return _non_empty_or_none(brief)

        if not brief.dirty:
            return _non_empty_or_none(brief)

        try:
            canon = self._store.load_canon()
            synopsis = self._store.load_synopsis()
            refreshed = self._brief_refresher.refresh(
                scene_id=scene_id,
                messages=raw,
                meta=self._meta,
                canon=canon,
                global_summary=synopsis.global_summary,
                prior_scene_cold=self._prior_scene_cold,
                scene_tail=self._scene_tail,
            )
            self._store.save_discussion_brief(scene_id, refreshed)
            return _non_empty_or_none(refreshed)
        except DiscussionBriefRefreshError:
            return _non_empty_or_none(brief)

    def _complete_writing_send(self, user_input: str, reply: str) -> str:
        self._buffer.append_user(user_input)
        self._buffer.append_assistant(reply)
        self._buffer.set_candidate(reply)
        self._turns_since_last_adopt += 1
        return reply

    def _complete_discussion_send(self, user_input: str, reply: str) -> str:
        self._store.append_discussion_message(
            self._buffer.scene_id,
            ChatMessage(role="user", content=user_input),
        )
        self._store.append_discussion_message(
            self._buffer.scene_id,
            ChatMessage(role="assistant", content=reply),
        )
        brief = self._store.load_discussion_brief(self._buffer.scene_id)
        brief.dirty = True
        self._store.save_discussion_brief(self._buffer.scene_id, brief)
        return reply

    def prepare_adopt(self, text: str) -> AdoptProposal:
        if not text.strip():
            raise ValueError("采纳正文不能为空")
        canon_before = self._store.load_canon()
        canon_patch = self._canon_extractor.extract_patch(text, canon_before)
        canon_after = merge_hot_canon(canon_before, canon_patch)
        return AdoptProposal(
            text=text.strip(),
            canon_before=canon_before,
            canon_patch=canon_patch,
            canon_after=canon_after,
            diff=format_canon_diff(canon_before, canon_patch, canon_after),
        )

    def commit_adopt(self, proposal: AdoptProposal, *, accepted_canon: bool) -> None:
        self._store.append_scene_text(self._buffer.scene_id, proposal.text)
        self._buffer.append_adopted_prose(proposal.text)
        if accepted_canon:
            self._store.save_canon(proposal.canon_after)
        self._buffer.record_adopt(
            AdoptRecord(
                text=proposal.text,
                canon_before=proposal.canon_before.to_dict(),
                canon_patch=proposal.canon_patch.to_dict(),
                accepted_canon=accepted_canon,
            )
        )
        self._store.clear_discussion_messages(self._buffer.scene_id)
        self._buffer.clear_candidate()
        self._turns_since_last_adopt = 0
        self._persist_session()

    def undo_last_adopt(self) -> AdoptRecord:
        record = self._buffer.pop_last_adopt()
        rebuilt = build_prose_from_records(self._buffer.adopt_stack)
        self._store.rewrite_scene_manuscript(self._buffer.scene_id, rebuilt)
        self._store.save_canon(HotCanon.from_dict(record.canon_before))
        self._persist_session()
        return record

    def prepare_fix(self, intent: str) -> AdoptProposal:
        normalized = intent.strip()
        if not normalized:
            raise ValueError("纠错意图不能为空")
        canon_before = self._store.load_canon()
        canon_patch = self._canon_extractor.extract_fix_patch(normalized, canon_before)
        canon_after = merge_hot_canon(canon_before, canon_patch)
        return AdoptProposal(
            text=normalized,
            canon_before=canon_before,
            canon_patch=canon_patch,
            canon_after=canon_after,
            diff=format_canon_diff(canon_before, canon_patch, canon_after),
        )

    def commit_fix(self, proposal: AdoptProposal) -> None:
        self._store.save_canon(proposal.canon_after)
        self._persist_session()

    def pending_reconcile_items(self) -> list[ReconcileItem]:
        items: list[ReconcileItem] = []
        for index, record in enumerate(self._buffer.adopt_stack):
            if record.accepted_canon:
                continue
            proposal = self.prepare_adopt(record.text)
            items.append(ReconcileItem(stack_index=index, proposal=proposal))
        return items

    def apply_reconcile(self, item: ReconcileItem, *, accepted_canon: bool) -> None:
        if accepted_canon:
            self._store.save_canon(item.proposal.canon_after)
        self._buffer.mark_adopt_canon_accepted(
            item.stack_index,
            accepted=accepted_canon,
        )
        self._persist_session()

    def prepare_cold_proposal(self) -> ColdProposal:
        adopted_text = self._store.read_scene_manuscript(self._buffer.scene_id)
        if not adopted_text.strip():
            raise ValueError("当前场景尚无已采纳正文，无法生成 Cold 提案")
        return self._cold_extractor.propose(
            self._buffer.scene_id,
            adopted_text,
            meta=self._meta,
        )

    def finish_scene_switch(
        self,
        proposal: ColdProposal,
        *,
        cold_accepted: bool,
        summary: str,
    ) -> str:
        closing_scene_id = self._buffer.scene_id
        tail = self._store.read_scene_tail(
            closing_scene_id,
            limit=self._config.context.scene_tail_limit,
        )
        prior_cold: SceneSynopsisEntry | None = None

        if cold_accepted:
            entry = proposal.to_entry(closing_scene_id, summary=summary.strip())
            synopsis = self._store.load_synopsis()
            synopsis.scenes.append(entry)
            synopsis.global_summary = self._cold_extractor.rollup_global(
                synopsis.global_summary,
                entry,
            )
            self._store.save_synopsis(synopsis)
            prior_cold = entry

        new_scene_id = next_scene_id(closing_scene_id)
        self._store.ensure_scene_manuscript(new_scene_id)
        self._buffer.reset_for_new_scene(new_scene_id)
        self._turns_since_last_adopt = 0
        self._scene_tail = tail
        self._prior_scene_cold = prior_cold
        self._persist_session()
        return new_scene_id

    def save(self) -> None:
        self._persist_session()

    def update_config(self, config: ProjectConfig) -> None:
        self._config = config
        self._store.save_config(config)

    def reset_config(self) -> None:
        self.update_config(ProjectConfig.default())

    def _load_scene_prompt_context(self) -> tuple[str | None, SceneSynopsisEntry | None]:
        scene_id = self._buffer.scene_id
        prior_id = previous_scene_id(scene_id)
        if prior_id is None:
            return None, None
        tail = self._store.read_scene_tail(
            prior_id,
            limit=self._config.context.scene_tail_limit,
        )
        prior_cold = self._store.load_prior_scene_cold(scene_id)
        return (tail or None), prior_cold

    def _persist_session(self) -> None:
        self._store.save_session(self._buffer.to_session())
