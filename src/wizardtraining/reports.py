"""JSON-safe values, and a saved copy of each report in the runtime folder.

Reports can hold positions, zone names and quest keys. They are kept out of version control
(`runtime/` is ignored): share an excerpt, not a whole report.
"""

from __future__ import annotations

import datetime
import enum
import json
from pathlib import Path


def plain(value):
    if all(hasattr(value, axis) for axis in ("x", "y", "z")):
        return {"x": round(value.x, 1), "y": round(value.y, 1), "z": round(value.z, 1)}
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    return repr(value)


def save_report(kind: str, report: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"{kind}-{stamp}.json"
    path.write_text(json.dumps(with_text_keys(report), indent=2, sort_keys=True, default=plain) + "\n",
                    encoding="utf-8")
    return path


def with_text_keys(value):
    """`value` with every dict key as text, so the keys can be sorted: a zone read as None during loading
    once became a key among zone names, and saving the report failed."""
    if isinstance(value, dict):
        return {str(key): with_text_keys(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [with_text_keys(item) for item in value]
    return value
