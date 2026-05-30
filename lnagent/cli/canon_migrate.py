"""Hot Canon schema v2 一次性迁移（迁移 B）。"""

from __future__ import annotations

from lnagent.cli.adopt import read_yes_no
from lnagent.memory.canon_extractor import (
    CanonExtractor,
    CanonPatchParseError,
    format_canon_diff,
    is_empty_canon_patch,
)
from lnagent.memory.canon_migrate import CANON_SCHEMA_VERSION
from lnagent.memory.models import HotCanon
from lnagent.memory.store import JsonMemoryStore
def run_canon_migrate(
    store: JsonMemoryStore,
    extractor: CanonExtractor,
    *,
    force: bool = False,
) -> None:
    canon = store.load_canon()
    if canon.schema_version >= CANON_SCHEMA_VERSION and not force:
        print(
            "当前 Hot Canon 已是 schema v2。"
            "若需重新迁移，请使用 /canon migrate --force。\n"
        )
        return

    try:
        migrated = extractor.migrate_full_canon(canon)
    except CanonPatchParseError as exc:
        print(f"Hot Canon 迁移失败: {exc}。请重试。\n")
        return

    if is_empty_canon_patch(migrated) and not migrated.characters:
        print("迁移结果为空，未写入。\n")
        return

    print(
        format_canon_diff(canon, migrated, migrated)
        + "\n"
    )
    accepted = read_yes_no("是否写入迁移后的 Hot Canon? (y/n): ")
    if not accepted:
        print("已取消迁移。\n")
        return

    store.save_canon(migrated)
    print("Hot Canon 已迁移到 schema v2。\n")


def parse_migrate_flags(text: str) -> bool:
    return text.strip().lower() in {"--force", "-f", "force"}
