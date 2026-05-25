"""多轮小说创作会话。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models import BaseChatModel

from lnagent.memory.canon_extractor import (
    CanonExtractor,
    format_canon_diff,
    merge_hot_canon,
)
from lnagent.memory.cold_archive import (
    ColdArchiveExtractor,
    ColdProposal,
)
from lnagent.memory.models import (
    AdoptRecord,
    HotCanon,
    NovelMeta,
    SceneSynopsisEntry,
    next_scene_id,
    previous_scene_id,
)
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore


class CanonPatchExtractor(Protocol):
    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon: ...


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
    ) -> None:
        self._store = store
        self._model = model
        self._meta = meta
        self._prompt_builder = prompt_builder or PromptContextBuilder()
        self._canon_extractor = canon_extractor or CanonExtractor(model)
        self._cold_extractor = cold_extractor or ColdArchiveExtractor(model)
        self._buffer = ShortTermBuffer.from_session(
            store.load_session(),
            drop_pending_candidate=True,
        )
        self._scene_tail, self._prior_scene_cold = self._load_scene_prompt_context()

    @property
    def meta(self) -> NovelMeta:
        return self._meta

    @property
    def scene_id(self) -> str:
        return self._buffer.scene_id

    @property
    def last_candidate(self) -> str | None:
        return self._buffer.last_candidate

    @property
    def adopt_stack(self) -> list[AdoptRecord]:
        return self._buffer.adopt_stack

    def can_switch_scene(self) -> bool:
        return len(self._buffer.adopt_stack) > 0

    def send(self, user_input: str) -> str:
        canon = self._store.load_canon()
        synopsis = self._store.load_synopsis()
        messages = self._prompt_builder.build(
            meta=self._meta,
            canon=canon,
            buffer=self._buffer,
            user_input=user_input,
            global_summary=synopsis.global_summary,
            prior_scene_cold=self._prior_scene_cold,
            scene_tail=self._scene_tail,
        )
        response = self._model.invoke(messages)
        content = response.content
        reply = content if isinstance(content, str) else str(content)

        self._buffer.append_user(user_input)
        self._buffer.append_assistant(reply)
        self._buffer.set_candidate(reply)
        self._persist_session()
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
        self._buffer.clear_candidate()
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
        tail = self._store.read_scene_tail(closing_scene_id)
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
        self._scene_tail = tail
        self._prior_scene_cold = prior_cold
        self._persist_session()
        return new_scene_id

    def save(self) -> None:
        self._persist_session()

    def _load_scene_prompt_context(self) -> tuple[str | None, SceneSynopsisEntry | None]:
        scene_id = self._buffer.scene_id
        prior_id = previous_scene_id(scene_id)
        if prior_id is None:
            return None, None
        tail = self._store.read_scene_tail(prior_id)
        prior_cold = self._store.load_prior_scene_cold(scene_id)
        return (tail or None), prior_cold

    def _persist_session(self) -> None:
        self._store.save_session(self._buffer.to_session())
