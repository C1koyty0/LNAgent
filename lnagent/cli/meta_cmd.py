"""meta 查看与迁移命令。"""

from __future__ import annotations

import json

from lnagent.cli.adopt import read_yes_no
from lnagent.memory.meta_display import format_meta_summary
from lnagent.memory.meta_extractor import MetaExtractor
from lnagent.memory.meta_migrate import META_SCHEMA_VERSION
from lnagent.memory.canon_extractor import CanonPatchParseError
from lnagent.memory.models import NovelMeta
from lnagent.memory.store import JsonMemoryStore


def run_meta_view(store: JsonMemoryStore) -> None:
    meta = store.load_meta()
    print(format_meta_summary(meta))
    print()


def run_meta_migrate(
    store: JsonMemoryStore,
    extractor: MetaExtractor,
    *,
    force: bool = False,
) -> None:
    meta = store.load_meta()
    if meta.schema_version >= META_SCHEMA_VERSION and meta.world.scoped and not force:
        print(
            "当前 meta 已是 schema v2 且含 scoped 条目。"
            "若需重新迁移，请使用 /meta migrate --force。\n"
        )
        return

    try:
        migrated = extractor.migrate_full_meta(meta)
    except CanonPatchParseError as exc:
        print(f"meta 迁移失败: {exc}。请重试。\n")
        return

    print("meta 迁移提案:\n")
    print(json.dumps(migrated.to_dict(), ensure_ascii=False, indent=2))
    print()
    accepted = read_yes_no("是否写入迁移后的 meta.json? (y/n): ")
    if not accepted:
        print("已取消迁移。\n")
        return

    store.save_meta(migrated)
    print("meta.json 已迁移到 schema v2。\n")


def parse_meta_migrate_flags(text: str) -> bool:
    return text.strip().lower() in {"--force", "-f", "force"}
