"""Discussion brief 提炼器。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.canon_extractor import _strip_json_fence
from lnagent.memory.meta_display import format_meta_for_prompt
from lnagent.memory.models import ChatMessage, DiscussionBrief, HotCanon, NovelMeta


class DiscussionBriefRefreshError(ValueError):
    """brief 刷新失败（JSON 解析异常、根节点不对、或缺少关键字段）。"""


class DiscussionBriefModel(Protocol):
    def invoke(self, messages: list[Any]) -> Any: ...


_REFRESH_SYSTEM_PROMPT = """\
你是 light-novel discussion brief 提炼器。
根据当前场景的 discussion 原始聊天，提炼出供写作使用的结构化 brief，且只输出 JSON 对象。

JSON schema:
{
  "todo_items": ["本场景需要写的待办事项"],
  "constraints": ["写作时必须遵守的约束"],
  "open_questions": ["尚未定案但会影响写作取舍的问题"]
}

提炼规则：
- 只从讨论中选取对本场景写作有直接指导价值的内容
- 不要编造讨论中未出现的事项
- 不要把已经定案的讨论结论保留在 open_questions 中
- todo_items 用于驱动写作执行，constraints 用于约束写作方向
- 不要输出解释、Markdown 或代码块"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DiscussionBriefRefresher:
    def __init__(self, model: DiscussionBriefModel) -> None:
        self._model = model

    # ------------------------------------------------------------------  #
    #  公共入口  #
    # ------------------------------------------------------------------  #

    def refresh(
        self,
        scene_id: str,
        messages: list[ChatMessage],
        meta: NovelMeta | None = None,
        canon: HotCanon | None = None,
        global_summary: str = "",
        prior_scene_cold: Any | None = None,
        scene_tail: str | None = None,
    ) -> DiscussionBrief:
        """根据 discussion 原始聊天生成结构化 brief。"""

        # ----- 组装上下文 ----- #

        meta_block = ""
        if meta is not None:
            meta_block = format_meta_for_prompt(meta, active_scopes=None) + "\n\n"

        canon_block = ""
        if canon is not None:
            canon_str = json.dumps(canon.to_dict(), ensure_ascii=False, indent=2)
            canon_block = f"当前 Canon：\n{canon_str}\n\n"

        global_block = ""
        if global_summary:
            global_block = f"全书梗概：\n{global_summary}\n\n"

        prior_block = ""
        if prior_scene_cold is not None:
            prior_str = json.dumps(
                prior_scene_cold.to_dict(), ensure_ascii=False, indent=2
            )
            prior_block = f"前一场景 Cold Archive：\n{prior_str}\n\n"

        tail_block = ""
        if scene_tail:
            tail_block = f"前文衔接（上一场景末尾）：\n{scene_tail}\n\n"

        chat_lines: list[str] = []
        for msg in messages:
            tag = "user" if msg.role == "user" else "assistant"
            chat_lines.append(f"[{tag}] {msg.content}")
        chat_block = "\n".join(chat_lines)

        # ----- 发送给模型 ----- #

        system_content = (
            meta_block
            + canon_block
            + global_block
            + prior_block
            + tail_block
        )

        model_messages = [
            SystemMessage(content=_REFRESH_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"{system_content}"
                    f"当前场景 discussion 原始聊天：\n\n"
                    f"{chat_block}"
                )
            ),
        ]

        response = self._model.invoke(model_messages)
        content = response.content
        text = content if isinstance(content, str) else str(content)

        # ----- 解析结果 ----- #

        data = _parse_brief_object(text)
        return _brief_from_dict(data, scene_id)


# ------------------------------------------------------------------  #
#  解析与转换  #
# ------------------------------------------------------------------  #

def _parse_brief_object(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DiscussionBriefRefreshError(f"brief 不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DiscussionBriefRefreshError("brief 根节点必须是 JSON 对象")
    return data


def _brief_from_dict(data: dict[str, Any], scene_id: str) -> DiscussionBrief:
    def _str_list(key: str) -> list[str]:
        raw = data.get(key, [])
        if not isinstance(raw, list):
            return []
        result: list[str] = []
        for item in raw:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                result.append(s)
        return result

    return DiscussionBrief(
        scene_id=scene_id,
        todo_items=_str_list("todo_items"),
        constraints=_str_list("constraints"),
        open_questions=_str_list("open_questions"),
        dirty=False,
        updated_at=_now_iso(),
    )
