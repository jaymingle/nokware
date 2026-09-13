"""The AMA's document categories, as listed on ama.gov.gh's documents centre.

Used by the AMA import (manifest category IDs) and by portal uploads, which
offer the same names so every Ledger document is filed the same way.
"""

import json
from functools import lru_cache
from pathlib import Path

CATEGORIES_FILE = Path(__file__).resolve().parent / "data" / "ama_categories.json"


@lru_cache
def categories_by_id() -> dict[int, str]:
    raw = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))["categories"]
    return {int(category_id): name for category_id, name in raw.items()}


def category_names() -> list[str]:
    return list(categories_by_id().values())
