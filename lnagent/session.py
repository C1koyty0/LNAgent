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
from lnagent.memory.models import AdoptRecord, HotCanon, NovelMeta
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore


class CanonPatchExtractor(Protocol):
    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon: ...


@dataclass(frozen=True)
class AdoptProposal:
    text: str
    canon_before: HotCanon
    canon_patch: HotCanon
    canon_after: HotCanon
    diff: str


class NovelSession:
    def __init__(
        self,
        store: JsonMemoryStore,
        model: BaseChatModel,
        meta: NovelMeta,
        *,
        prompt_builder: PromptContextBuilder | None = None,
        canon_extractor: CanonPatchExtractor | None = None,
    ) -> None:
        self._store = store
        self._model = model
        self._meta = meta
        self._prompt_builder = prompt_builder or PromptContextBuilder()
        self._canon_extractor = canon_extractor or CanonExtractor(model)
        self._buffer = ShortTermBuffer.from_session(
            store.load_session(),
            drop_pending_candidate=True,
        )

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
        canon = self._store.load_canon()
        messages = self._prompt_builder.build(
            meta=self._meta,
            canon=canon,
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

    def save(self) -> None:
        self._persist_session()

    def _persist_session(self) -> None:
        self._store.save_session(self._buffer.to_session())
