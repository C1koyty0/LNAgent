"""模板文件存储。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lnagent.memory.store import JsonMemoryStore

_TEMPLATE_FIELDS = (
    "title",
    "style",
    "pov",
    "tense",
    "genre",
    "tone",
    "target_audience",
    "taboos",
    "narrative_rules",
)


class JsonTemplateStore:
    def __init__(self, projects_dir: Path) -> None:
        self._projects_dir = projects_dir
        self._template_dir = projects_dir / "_templates"

    def list_templates(self) -> list[dict[str, Any]]:
        if not self._template_dir.is_dir():
            return []
        templates: list[dict[str, Any]] = []
        for path in sorted(self._template_dir.glob("*.json"), key=lambda item: item.name):
            try:
                templates.append(self._normalize_template_dict(self._read_json(path), name=path.stem))
            except (OSError, ValueError, TypeError):
                continue
        return templates

    def load_template(self, name: str) -> dict[str, Any]:
        normalized_name = self._normalize_name(name)
        path = self._template_path(normalized_name)
        if not path.is_file():
            raise ValueError("模板不存在")
        return self._normalize_template_dict(self._read_json(path), name=normalized_name)

    def save_template(self, name: str, meta_dict: dict[str, Any]) -> dict[str, Any]:
        normalized_name = self._normalize_name(name)
        normalized = self._normalize_template_dict(meta_dict, name=normalized_name)
        payload = {field: normalized[field] for field in _TEMPLATE_FIELDS if normalized[field] not in ([], "")}
        JsonMemoryStore._write_json(self._template_path(normalized_name), payload)
        return normalized

    def delete_template(self, name: str) -> bool:
        normalized_name = self._normalize_name(name)
        path = self._template_path(normalized_name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def _template_path(self, name: str) -> Path:
        return self._template_dir / f"{name}.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return JsonMemoryStore._read_json(path)

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("模板名不能为空")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("模板名不能包含路径分隔符")
        return normalized

    @staticmethod
    def _normalize_list(value: Any) -> list[str]:
        if isinstance(value, list):
            items = value
        elif value is None:
            items = []
        else:
            items = [value]
        normalized: list[str] = []
        for item in items:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized

    @classmethod
    def _normalize_template_dict(cls, data: dict[str, Any], *, name: str) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("模板数据必须是对象")
        style = str(data.get("style", "")).strip()
        if not style:
            raise ValueError("style 不能为空")
        return {
            "name": name,
            "title": str(data.get("title", "")).strip(),
            "style": style,
            "pov": str(data.get("pov", "")).strip(),
            "tense": str(data.get("tense", "")).strip(),
            "genre": str(data.get("genre", "")).strip(),
            "tone": str(data.get("tone", "")).strip(),
            "target_audience": str(data.get("target_audience", "")).strip(),
            "taboos": cls._normalize_list(data.get("taboos", [])),
            "narrative_rules": cls._normalize_list(data.get("narrative_rules", [])),
        }
