"""项目索引：为 Web 首页提供项目列表与摘要。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lnagent.memory.store import JsonMemoryStore


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    title: str
    style: str
    current_scene_id: str


def list_projects(projects_dir: Path) -> list[ProjectSummary]:
    if not projects_dir.is_dir():
        return []

    summaries: list[ProjectSummary] = []
    for entry in sorted(projects_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        summary = _load_project_summary(entry)
        if summary is not None:
            summaries.append(summary)
    return summaries


def _load_project_summary(project_dir: Path) -> ProjectSummary | None:
    store = JsonMemoryStore(project_dir)
    if not store.project_exists():
        return None

    try:
        meta = store.load_meta()
        session = store.load_session()
    except (OSError, ValueError):
        return None

    return ProjectSummary(
        project_id=project_dir.name,
        title=meta.title,
        style=meta.style,
        current_scene_id=session.scene_id,
    )
