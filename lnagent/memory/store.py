"""基于 JSON 文件的 MemoryStore 实现。"""

from __future__ import annotations

import json
from pathlib import Path

from lnagent.memory.models import (
    DEFAULT_SCENE_ID,
    HotCanon,
    NovelMeta,
    SceneSession,
)


class JsonMemoryStore:
    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._meta_path = project_dir / "meta.json"
        self._session_path = project_dir / "session.json"
        self._canon_path = project_dir / "memory" / "canon.json"
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

        if not self._manuscript_path.is_file():
            self._manuscript_path.write_text("", encoding="utf-8")

        if not self._session_path.is_file():
            self.save_session(SceneSession.default())

    def load_meta(self) -> NovelMeta:
        data = self._read_json(self._meta_path)
        return NovelMeta.from_dict(data)

    def save_meta(self, meta: NovelMeta) -> None:
        self._write_json(self._meta_path, meta.to_dict())

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
