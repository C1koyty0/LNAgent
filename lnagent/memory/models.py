"""记忆域数据模型（JSON 可序列化）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


DEFAULT_SCENE_ID = "scene_001"


@dataclass
class SceneSession:
    scene_id: str = DEFAULT_SCENE_ID
    messages: list[ChatMessage] = field(default_factory=list)
    adopted_prose: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "messages": [m.to_dict() for m in self.messages],
            "adopted_prose": self.adopted_prose,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneSession:
        raw_messages = data.get("messages", [])
        messages = [
            ChatMessage.from_dict(m) for m in raw_messages if isinstance(m, dict)
        ]
        return cls(
            scene_id=str(data.get("scene_id", DEFAULT_SCENE_ID)),
            messages=messages,
            adopted_prose=str(data.get("adopted_prose", "")),
        )

    @classmethod
    def default(cls) -> SceneSession:
        return cls(scene_id=DEFAULT_SCENE_ID)
