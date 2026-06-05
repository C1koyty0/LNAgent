"""小说项目初始化。"""

from __future__ import annotations

import json
from pathlib import Path

from lnagent.memory.models import NovelMeta
from lnagent.memory.store import JsonMemoryStore

_REQUIRED_META_FIELDS = ("title", "style")


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


def init_project_from_meta_file(store: JsonMemoryStore, meta_path: Path) -> NovelMeta:
    meta = load_meta_from_file(meta_path)
    store.ensure_project_layout()
    store.save_meta(meta)
    return meta


def create_project_from_meta_dict(
    store: JsonMemoryStore,
    meta_data: dict,
) -> NovelMeta:
    if store.project_exists():
        raise ValueError("项目已存在，不能重复创建")
    if not isinstance(meta_data, dict):
        raise ValueError("meta 数据必须是对象")
    meta = _load_meta_from_data(meta_data)
    store.ensure_project_layout()
    store.save_meta(meta)
    return meta


def open_or_create_project(
    store: JsonMemoryStore,
    *,
    meta_path: Path | None = None,
) -> NovelMeta:
    if store.project_exists():
        if meta_path is not None:
            raise ValueError("不能覆盖已有项目的 meta.json")
        return store.load_meta()
    if meta_path is not None:
        return init_project_from_meta_file(store, meta_path)
    return init_project(store)


def load_meta_from_file(meta_path: Path) -> NovelMeta:
    try:
        text = meta_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except OSError as exc:
        raise ValueError(f"无法读取 meta 文件: {meta_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"meta 文件不是有效 JSON: {meta_path}") from exc

    return _load_meta_from_data(data)


def _load_meta_from_data(data: object) -> NovelMeta:
    if not isinstance(data, dict):
        raise ValueError("meta JSON 根节点必须是对象")

    missing = [field for field in _REQUIRED_META_FIELDS if field not in data]
    if missing:
        raise ValueError(f"meta JSON 缺少必填字段: {', '.join(missing)}")

    if not str(data["title"]).strip():
        raise ValueError("meta JSON 字段 title 不能为空")
    if not str(data["style"]).strip():
        raise ValueError("meta JSON 字段 style 不能为空")
    _validate_world_content(data)

    return NovelMeta.from_dict(data)


def _validate_world_content(data: dict) -> None:
    world = data.get("world")
    if isinstance(world, dict):
        rules = world.get("rules", [])
        scoped = world.get("scoped", [])
        has_rules = isinstance(rules, list) and bool(rules)
        has_scoped = (
            isinstance(scoped, list)
            and any(
                isinstance(entry, dict) and entry.get("rules")
                for entry in scoped
            )
        )
        if has_rules or has_scoped:
            return

    world_rules = data.get("world_rules")
    if isinstance(world_rules, list) and world_rules:
        return

    raise ValueError(
        "meta JSON 须包含非空 world.rules、world.scoped 或旧版 world_rules"
    )


def _prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} 不能为空，请重新输入。")
