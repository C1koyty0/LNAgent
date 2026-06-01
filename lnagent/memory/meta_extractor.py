"""meta.json LLM 迁移（迁移 B）。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.canon_extractor import CanonPatchParseError, _parse_json_object
from lnagent.memory.models import NovelMeta

_MIGRATE_META_PROMPT = """\
你是轻小说开书设定（meta）迁移器。
将输入的 meta 整理为 schema v2 JSON 对象。
JSON schema:
{
  "schema_version": 2,
  "title": "书名",
  "style": "文风",
  "world": {
    "rules": ["全大陆通用规则"],
    "scoped": [
      {
        "scope_type": "faction|location",
        "scope_id": "势力或地点名称",
        "rules": ["仅适用于该范围的设定条目"]
      }
    ]
  },
  "pov": "",
  "tense": "",
  "taboos": [],
  "target_audience": "",
  "narrative_rules": [],
  "genre": "",
  "tone": ""
}
将势力/国家/地区级设定放入 world.scoped；全局战力、货币、通用禁忌等放入 world.rules。
不要输出解释、Markdown 或代码块。"""


class MetaExtractor:
    def __init__(self, model: Any) -> None:
        self._model = model

    def migrate_full_meta(self, meta: NovelMeta) -> NovelMeta:
        messages = [
            SystemMessage(content=_MIGRATE_META_PROMPT),
            HumanMessage(
                content=(
                    "当前 meta:\n"
                    f"{json.dumps(meta.to_dict(), ensure_ascii=False, indent=2)}"
                )
            ),
        ]
        response = self._model.invoke(messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        return NovelMeta.from_dict(_parse_json_object(text))
