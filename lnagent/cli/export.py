"""正文导出命令处理。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from lnagent.memory.store import JsonMemoryStore


def export_manuscript(
    store: JsonMemoryStore,
    output_path: Path | None = None,
    *,
    today: date | None = None,
) -> Path:
    target_path = _resolve_output_path(store, output_path, today=today)
    content = _build_export_content(store)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return target_path


def _resolve_output_path(
    store: JsonMemoryStore,
    output_path: Path | None,
    *,
    today: date | None,
) -> Path:
    if output_path is not None:
        return output_path if output_path.is_absolute() else store.project_dir / output_path

    export_date = today or date.today()
    exports_dir = store.project_dir / "exports"
    candidate = exports_dir / f"{export_date.isoformat()}.md"
    suffix = 2
    while candidate.exists():
        candidate = exports_dir / f"{export_date.isoformat()}-{suffix}.md"
        suffix += 1
    return candidate


def _build_export_content(store: JsonMemoryStore) -> str:
    sections: list[str] = []
    for scene_path in store.list_scene_manuscript_paths():
        text = scene_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        sections.append(f"## {_format_scene_title(scene_path)}\n\n{text}")

    if not sections:
        raise ValueError("没有可导出的正文")

    return "\n\n".join(sections) + "\n"


def _format_scene_title(scene_path: Path) -> str:
    _, number = scene_path.stem.split("_", maxsplit=1)
    return f"Scene {number}"
