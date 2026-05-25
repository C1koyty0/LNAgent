"""Cold Archive 提案生成与全书梗概 rollup。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.canon_extractor import _strip_json_fence
from lnagent.memory.models import NovelMeta, SceneSynopsisEntry


class ColdProposalParseError(ValueError):
    """LLM 输出无法解析为 Cold Archive 提案。"""


@dataclass(frozen=True)
class ColdProposal:
    location: str
    time: str
    summary: str
    key_points: list[str]

    def to_entry(self, scene_id: str, *, summary: str | None = None) -> SceneSynopsisEntry:
        return SceneSynopsisEntry(
            id=scene_id,
            location=self.location,
            time=self.time,
            summary=summary if summary is not None else self.summary,
            key_points=list(self.key_points),
        )


_PROPOSE_SYSTEM_PROMPT = """\
你是轻小说 Cold Archive 抽取器。
根据本场景已采纳正文，生成本场景的叙事归档提案，且只输出 JSON 对象。
JSON schema:
{
  "location": "场景地点（大致即可）",
  "time": "大致时间",
  "summary": "本场景叙事摘要",
  "key_points": ["关键信息条目"]
}
summary 应覆盖本场景主要事件与情绪弧线；key_points 为伏笔、转折等要点。
不要输出解释、Markdown 或代码块。"""


_ROLLUP_SYSTEM_PROMPT = """\
你是轻小说全书梗概维护器。
根据既有全书梗概与本场景 newly 确认的场景摘要，输出更新后的全书梗概。
只输出纯文本梗概，不要 JSON、不要 Markdown、不要标题前缀。"""


class ColdArchiveModel(Protocol):
    def invoke(self, messages: list[Any]) -> Any: ...


class ColdArchiveExtractor:
    def __init__(self, model: ColdArchiveModel) -> None:
        self._model = model

    def propose(
        self,
        scene_id: str,
        adopted_text: str,
        *,
        meta: NovelMeta | None = None,
    ) -> ColdProposal:
        meta_block = ""
        if meta is not None:
            meta_block = (
                f"书名：{meta.title}\n文风：{meta.style}\n"
                f"世界规则：{json.dumps(meta.world_rules, ensure_ascii=False)}\n\n"
            )
        messages = [
            SystemMessage(content=_PROPOSE_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"{meta_block}"
                    f"场景 ID：{scene_id}\n\n"
                    "已采纳正文：\n"
                    f"{adopted_text}"
                )
            ),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        return _proposal_from_dict(_parse_cold_proposal_object(text))

    def rollup_global(
        self,
        old_global: str,
        scene_entry: SceneSynopsisEntry,
    ) -> str:
        entry_json = json.dumps(scene_entry.to_dict(), ensure_ascii=False, indent=2)
        messages = [
            SystemMessage(content=_ROLLUP_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "当前全书梗概：\n"
                    f"{old_global or '（尚无）'}\n\n"
                    "本场景已确认归档：\n"
                    f"{entry_json}"
                )
            ),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        return text.strip()


def format_cold_proposal(proposal: ColdProposal) -> str:
    payload = {
        "location": proposal.location,
        "time": proposal.time,
        "summary": proposal.summary,
        "key_points": proposal.key_points,
    }
    return "Cold Archive 提案:\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_cold_proposal_object(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ColdProposalParseError(f"Cold 提案不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ColdProposalParseError("Cold 提案根节点必须是 JSON 对象")
    return data


def _proposal_from_dict(data: dict[str, Any]) -> ColdProposal:
    raw_points = data.get("key_points", [])
    key_points = (
        [str(p) for p in raw_points]
        if isinstance(raw_points, list)
        else []
    )
    summary = str(data.get("summary", "")).strip()
    if not summary:
        raise ColdProposalParseError("Cold 提案缺少 summary")
    return ColdProposal(
        location=str(data.get("location", "")),
        time=str(data.get("time", "")),
        summary=summary,
        key_points=key_points,
    )
