"""基于 JSON 文件的 MemoryStore 实现。"""

from __future__ import annotations

import json
from pathlib import Path

from lnagent.memory.models import (
    DEFAULT_SCENE_ID,
    ColdSynopsis,
    HotCanon,
    NovelMeta,
    ProjectConfig,
    SceneSession,
    SceneSynopsisEntry,
    extract_tail,
    previous_scene_id,
)
from lnagent.memory.short_term import append_prose


class JsonMemoryStore:
    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._meta_path = project_dir / "meta.json"
        self._config_path = project_dir / "config.json"
        self._session_path = project_dir / "session.json"
        self._canon_path = project_dir / "memory" / "canon.json"
        self._synopsis_path = project_dir / "memory" / "synopsis.json"
        self._manuscript_path = project_dir / "manuscript" / f"{DEFAULT_SCENE_ID}.md"

    @property
    def project_dir(self) -> Path:
        return self._project_dir

    def project_exists(self) -> bool:
        return self._meta_path.is_file()

    def ensure_project_layout(self) -> None:
        self._project_dir.mkdir(parents=True, exist_ok=True)
        (self._project_dir / "memory").mkdir(parents=True, exist_ok=True)
        (self._project_dir / "manuscript").mkdir(parents=True, exist_ok=True)

        if not self._canon_path.is_file():
            self._write_json(self._canon_path, HotCanon.empty().to_dict())

        if not self._synopsis_path.is_file():
            self._write_json(self._synopsis_path, ColdSynopsis.empty().to_dict())

        if not self._config_path.is_file():
            self.save_config(ProjectConfig.default())

        if not self._manuscript_path.is_file():
            self._manuscript_path.write_text("", encoding="utf-8")

        if not self._session_path.is_file():
            self.save_session(SceneSession.default())

    def load_meta(self) -> NovelMeta:
        data = self._read_json(self._meta_path)
        return NovelMeta.from_dict(data)

    def save_meta(self, meta: NovelMeta) -> None:
        self._write_json(self._meta_path, meta.to_dict())

    def load_config(self) -> ProjectConfig:
        if not self._config_path.is_file():
            return ProjectConfig.default()
        data = self._read_json(self._config_path)
        return ProjectConfig.from_dict(data)

    def save_config(self, config: ProjectConfig) -> None:
        self._write_json(self._config_path, config.to_dict())

    def load_canon(self) -> HotCanon:
        if not self._canon_path.is_file():
            return HotCanon.empty()
        data = self._read_json(self._canon_path)
        return HotCanon.from_dict(data)

    def save_canon(self, canon: HotCanon) -> None:
        self._write_json(self._canon_path, canon.to_dict())

    def load_session(self) -> SceneSession:
        if not self._session_path.is_file():
            return SceneSession.default()
        data = self._read_json(self._session_path)
        return SceneSession.from_dict(data)

    def save_session(self, session: SceneSession) -> None:
        self._write_json(self._session_path, session.to_dict())

    def append_scene_text(self, scene_id: str, text: str) -> None:
        scene_path = self._scene_manuscript_path(scene_id)
        existing = scene_path.read_text(encoding="utf-8") if scene_path.is_file() else ""
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(append_prose(existing, text), encoding="utf-8")

    def rewrite_scene_manuscript(self, scene_id: str, content: str) -> None:
        scene_path = self._scene_manuscript_path(scene_id)
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(content, encoding="utf-8")

    def load_synopsis(self) -> ColdSynopsis:
        if not self._synopsis_path.is_file():
            return ColdSynopsis.empty()
        data = self._read_json(self._synopsis_path)
        return ColdSynopsis.from_dict(data)

    def save_synopsis(self, synopsis: ColdSynopsis) -> None:
        self._write_json(self._synopsis_path, synopsis.to_dict())

    def read_scene_manuscript(self, scene_id: str) -> str:
        scene_path = self._scene_manuscript_path(scene_id)
        if not scene_path.is_file():
            return ""
        return scene_path.read_text(encoding="utf-8")

    def ensure_scene_manuscript(self, scene_id: str) -> None:
        scene_path = self._scene_manuscript_path(scene_id)
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        if not scene_path.is_file():
            scene_path.write_text("", encoding="utf-8")

    def read_scene_tail(self, scene_id: str, *, limit: int | None = None) -> str:
        if limit is None:
            return extract_tail(self.read_scene_manuscript(scene_id))
        return extract_tail(self.read_scene_manuscript(scene_id), limit=limit)

    def load_prior_scene_cold(self, scene_id: str) -> SceneSynopsisEntry | None:
        prior_id = previous_scene_id(scene_id)
        if prior_id is None:
            return None
        return self.load_synopsis().find_scene(prior_id)

    def _scene_manuscript_path(self, scene_id: str) -> Path:
        return self._project_dir / "manuscript" / f"{scene_id}.md"

    @staticmethod
    def _read_json(path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"JSON 根节点必须是对象: {path}")
        return data

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
