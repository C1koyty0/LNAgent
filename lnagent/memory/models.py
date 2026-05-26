"""记忆域数据模型（JSON 可序列化）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_SCENE_ID_PATTERN = re.compile(r"^scene_(\d+)$")
_TAIL_CHAR_LIMIT = 500


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        return cls(role=str(data["role"]), content=str(data["content"]))


@dataclass
class NovelMeta:
    title: str
    world_rules: list[str]
    style: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "world_rules": self.world_rules,
            "style": self.style,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NovelMeta:
        rules = data.get("world_rules", [])
        return cls(
            title=str(data["title"]),
            world_rules=[str(r) for r in rules],
            style=str(data["style"]),
        )


@dataclass
class WorldCanon:
    rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"rules": self.rules}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldCanon:
        rules = data.get("rules", [])
        return cls(rules=[str(r) for r in rules])


@dataclass
class HotCanon:
    characters: list[dict[str, Any]] = field(default_factory=list)
    world: WorldCanon = field(default_factory=WorldCanon)
    plot_threads: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": self.characters,
            "world": self.world.to_dict(),
            "plot_threads": self.plot_threads,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HotCanon:
        world_data = data.get("world", {})
        return cls(
            characters=list(data.get("characters", [])),
            world=WorldCanon.from_dict(world_data if isinstance(world_data, dict) else {}),
            plot_threads=list(data.get("plot_threads", [])),
        )

    @classmethod
    def empty(cls) -> HotCanon:
        return cls()


@dataclass
class AdoptRecord:
    text: str
    canon_before: dict[str, Any]
    canon_patch: dict[str, Any]
    accepted_canon: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "canon_before": self.canon_before,
            "canon_patch": self.canon_patch,
            "accepted_canon": self.accepted_canon,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdoptRecord:
        canon_before = data.get("canon_before", {})
        canon_patch = data.get("canon_patch", {})
        return cls(
            text=str(data.get("text", "")),
            canon_before=canon_before if isinstance(canon_before, dict) else {},
            canon_patch=canon_patch if isinstance(canon_patch, dict) else {},
            accepted_canon=bool(data.get("accepted_canon", False)),
        )


@dataclass
class SceneSynopsisEntry:
    id: str
    location: str
    time: str
    summary: str
    key_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "location": self.location,
            "time": self.time,
            "summary": self.summary,
            "key_points": self.key_points,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneSynopsisEntry:
        raw_points = data.get("key_points", [])
        return cls(
            id=str(data.get("id", "")),
            location=str(data.get("location", "")),
            time=str(data.get("time", "")),
            summary=str(data.get("summary", "")),
            key_points=[str(p) for p in raw_points] if isinstance(raw_points, list) else [],
        )


@dataclass
class ColdSynopsis:
    global_summary: str = ""
    scenes: list[SceneSynopsisEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global": self.global_summary,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColdSynopsis:
        raw_scenes = data.get("scenes", [])
        scenes = [
            SceneSynopsisEntry.from_dict(s)
            for s in raw_scenes
            if isinstance(s, dict)
        ]
        return cls(
            global_summary=str(data.get("global", "")),
            scenes=scenes,
        )

    @classmethod
    def empty(cls) -> ColdSynopsis:
        return cls()

    def find_scene(self, scene_id: str) -> SceneSynopsisEntry | None:
        for entry in self.scenes:
            if entry.id == scene_id:
                return entry
        return None


@dataclass
class ContextConfig:
    char_budget: int = 300_000
    messages_limit: int = 80_000
    adopted_prose_limit: int = 120_000
    hot_canon_limit: int = 60_000
    global_limit: int = 30_000
    prior_scene_cold_limit: int = 12_000
    scene_tail_limit: int = 2_000
    meta_limit: int = 10_000

    def to_dict(self) -> dict[str, int]:
        return {
            "char_budget": self.char_budget,
            "messages_limit": self.messages_limit,
            "adopted_prose_limit": self.adopted_prose_limit,
            "hot_canon_limit": self.hot_canon_limit,
            "global_limit": self.global_limit,
            "prior_scene_cold_limit": self.prior_scene_cold_limit,
            "scene_tail_limit": self.scene_tail_limit,
            "meta_limit": self.meta_limit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextConfig:
        default = cls()
        return cls(
            char_budget=_read_int(data, "char_budget", default.char_budget),
            messages_limit=_read_int(data, "messages_limit", default.messages_limit),
            adopted_prose_limit=_read_int(
                data,
                "adopted_prose_limit",
                default.adopted_prose_limit,
            ),
            hot_canon_limit=_read_int(data, "hot_canon_limit", default.hot_canon_limit),
            global_limit=_read_int(data, "global_limit", default.global_limit),
            prior_scene_cold_limit=_read_int(
                data,
                "prior_scene_cold_limit",
                default.prior_scene_cold_limit,
            ),
            scene_tail_limit=_read_int(data, "scene_tail_limit", default.scene_tail_limit),
            meta_limit=_read_int(data, "meta_limit", default.meta_limit),
        )


@dataclass
class SceneSwitchConfig:
    min_adopts: int = 2
    no_adopt_turns: int = 3

    def to_dict(self) -> dict[str, int]:
        return {
            "min_adopts": self.min_adopts,
            "no_adopt_turns": self.no_adopt_turns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneSwitchConfig:
        default = cls()
        return cls(
            min_adopts=_read_int(data, "min_adopts", default.min_adopts),
            no_adopt_turns=_read_int(data, "no_adopt_turns", default.no_adopt_turns),
        )


@dataclass
class ProjectConfig:
    context: ContextConfig = field(default_factory=ContextConfig)
    scene_switch: SceneSwitchConfig = field(default_factory=SceneSwitchConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "scene_switch": self.scene_switch.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        context_data = data.get("context", {})
        scene_switch_data = data.get("scene_switch", {})
        return cls(
            context=ContextConfig.from_dict(
                context_data if isinstance(context_data, dict) else {}
            ),
            scene_switch=SceneSwitchConfig.from_dict(
                scene_switch_data if isinstance(scene_switch_data, dict) else {}
            ),
        )

    @classmethod
    def default(cls) -> ProjectConfig:
        return cls()


def _read_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


DEFAULT_SCENE_ID = "scene_001"


def next_scene_id(scene_id: str) -> str:
    match = _SCENE_ID_PATTERN.match(scene_id)
    if not match:
        raise ValueError(f"无效场景 ID: {scene_id}")
    number = int(match.group(1)) + 1
    return f"scene_{number:03d}"


def previous_scene_id(scene_id: str) -> str | None:
    match = _SCENE_ID_PATTERN.match(scene_id)
    if not match:
        raise ValueError(f"无效场景 ID: {scene_id}")
    number = int(match.group(1))
    if number <= 1:
        return None
    return f"scene_{number - 1:03d}"


def extract_tail(text: str, *, limit: int = _TAIL_CHAR_LIMIT) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


@dataclass
class SceneSession:
    scene_id: str = DEFAULT_SCENE_ID
    messages: list[ChatMessage] = field(default_factory=list)
    adopted_prose: str = ""
    adopt_stack: list[AdoptRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "messages": [m.to_dict() for m in self.messages],
            "adopted_prose": self.adopted_prose,
            "adopt_stack": [r.to_dict() for r in self.adopt_stack],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneSession:
        raw_messages = data.get("messages", [])
        messages = [
            ChatMessage.from_dict(m) for m in raw_messages if isinstance(m, dict)
        ]
        raw_adopt_stack = data.get("adopt_stack", [])
        adopt_stack = [
            AdoptRecord.from_dict(r) for r in raw_adopt_stack if isinstance(r, dict)
        ]
        return cls(
            scene_id=str(data.get("scene_id", DEFAULT_SCENE_ID)),
            messages=messages,
            adopted_prose=str(data.get("adopted_prose", "")),
            adopt_stack=adopt_stack,
        )

    @classmethod
    def default(cls) -> SceneSession:
        return cls(scene_id=DEFAULT_SCENE_ID)
