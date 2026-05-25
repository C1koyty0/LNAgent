"""小说项目初始化。"""

from __future__ import annotations

from lnagent.memory.models import NovelMeta
from lnagent.memory.store import JsonMemoryStore


def collect_novel_meta() -> NovelMeta:
    """交互式采集开书必填 meta 字段。"""
    print("\n--- 新建小说项目 ---")
    title = _prompt_required("书名")
    style = _prompt_required("文风（如：第一人称、轻松日常）")

    print("世界规则（每行一条，空行结束）：")
    world_rules: list[str] = []
    while True:
        line = input("  规则: ").strip()
        if not line:
            break
        world_rules.append(line)

    if not world_rules:
        raise ValueError("至少需要一条世界规则")

    return NovelMeta(title=title, world_rules=world_rules, style=style)


def init_project(store: JsonMemoryStore) -> NovelMeta:
    meta = collect_novel_meta()
    store.ensure_project_layout()
    store.save_meta(meta)
    return meta


def open_or_create_project(store: JsonMemoryStore) -> NovelMeta:
    if store.project_exists():
        return store.load_meta()
    return init_project(store)


def _prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} 不能为空，请重新输入。")
