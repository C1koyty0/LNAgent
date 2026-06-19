"""Worldbook 结构化提炼器。"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.canon_extractor import CanonPatchParseError, _parse_json_object
from lnagent.memory.models import WorldbookStructured


class WorldbookExtractParseError(ValueError):
    """LLM 输出无法解析为 WorldbookStructured。"""


class WorldbookExtractorModel(Protocol):
    def invoke(self, messages: list[Any]) -> Any: ...


_EXTRACT_SYSTEM_PROMPT = """\
你是轻小说世界观文档结构化提炼器。
根据作者提供的原始世界观文档，提炼出供系统消费的结构化 worldbook，且只输出 JSON 对象。

JSON schema:
{
  "schema_version": 1,
  "overview": "一句到一段的世界观总览",
  "global_rules": ["全局适用的世界规则"],
  "scopes": [
    {
      "scope_type": "faction|location",
      "scope_id": "势力或地点名称",
      "summary": "该 scope 的简述",
      "rules": ["仅适用于该 scope 的规则"]
    }
  ],
  "glossary": [
    {
      "term": "术语",
      "definition": "术语解释"
    }
  ],
  "open_questions": ["作者尚未拍板的问题"]
}

提炼规则：
- 只整理原文中明确出现或可直接归纳的信息
- 不要编造、补完、延展原文没有写出的设定
- 全局通用规则放入 global_rules；只适用于势力/地点的规则放入 scopes
- 原文没有的信息可留空，不要为了填满 schema 而捏造内容
- 只输出 JSON 对象，不要输出解释、Markdown 或代码块
"""


class WorldbookExtractor:
    def __init__(self, model: WorldbookExtractorModel) -> None:
        self._model = model

    def extract(self, source_md: str) -> WorldbookStructured:
        if not source_md.strip():
            return WorldbookStructured.empty()

        messages = [
            SystemMessage(content=_EXTRACT_SYSTEM_PROMPT),
            HumanMessage(content=f"原始世界观文档：\n\n{source_md}"),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        try:
            return WorldbookStructured.from_dict(_parse_json_object(text))
        except CanonPatchParseError as exc:
            raise WorldbookExtractParseError(str(exc)) from exc
