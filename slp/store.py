"""결과 저장: docs/data/searches/<id>.json + index.json (GitHub Pages가 읽는다)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def save_search(result: dict, data_dir: Path = DATA_DIR) -> Path:
    sid = result["meta"]["id"]
    path = data_dir / "searches" / f"{sid}.json"
    _write(path, result)
    index_path = data_dir / "searches" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    index = [e for e in index if e["id"] != sid]
    meta = result["meta"]
    index.insert(0, {k: meta[k] for k in ("id", "title", "created_at", "issue", "criteria", "counts")})
    index.sort(key=lambda e: e["created_at"], reverse=True)
    _write(index_path, index)
    return path
