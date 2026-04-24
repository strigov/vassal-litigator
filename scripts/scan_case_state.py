#!/usr/bin/env python3
"""scan_case_state.py — сравнение файловой системы и index.yaml для update-index.

Использование:
    python3 scan_case_state.py <case_root>

Выход: единый JSON:
{
    "case_root": "/abs/path",
    "index_count": 12,
    "fs_count": 13,
    "new_files": [...],
    "orphans": [...],
    "stale_mirrors": [...],
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

IGNORE_DIRS = {".vassal", "Входящие документы", "На удаление"}
IGNORE_FILES = {".DS_Store", "Thumbs.db", "Таблица документов.xlsx"}
TMP_SUFFIX = ".tmp"


def _fatal(message: str) -> int:
    print(f"{message}", file=sys.stderr)
    return 1


def _is_ignored_dir(name: str) -> bool:
    return name in IGNORE_DIRS or name.endswith(TMP_SUFFIX)


def _is_ignored_file(name: str) -> bool:
    return name in IGNORE_FILES or name.endswith(TMP_SUFFIX)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Сканирует состояние дела: file system vs index.yaml"
    )
    parser.add_argument("case_root", help="Путь к корню дела")
    return parser


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_case_root(raw: str) -> Path:
    case_root = Path(raw).expanduser().resolve()
    if not case_root.exists():
        raise FileNotFoundError(f"case root not found: {case_root}")
    if not case_root.is_dir():
        raise NotADirectoryError(f"case root is not a directory: {case_root}")
    return case_root


def _load_index_documents(case_root: Path) -> tuple[int, list[dict[str, object]]]:
    index_path = case_root / ".vassal" / "index.yaml"
    if not index_path.is_file():
        raise FileNotFoundError(f"index.yaml not found: {index_path}")

    try:
        data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"failed to parse index.yaml: {exc}") from exc

    documents = data.get("documents")
    if documents is None:
        documents = []
    if not isinstance(documents, list):
        raise ValueError("index.yaml: documents must be a list")

    normalized: list[dict[str, object]] = [
        document for document in documents if isinstance(document, dict)
    ]
    return len(documents), normalized


def _resolve_index_file(case_root: Path, value: object) -> Path | None:
    if not isinstance(value, str):
        return None

    file_value = value.strip()
    if not file_value:
        return None

    path = Path(file_value)
    if not path.is_absolute():
        path = case_root / path
    return path.resolve(strict=False)


def _parse_last_verified(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.timestamp()
        except ValueError:
            pass

    try:
        dt = datetime.fromisoformat(normalized)
        return dt.timestamp()
    except ValueError:
        return None


def _collect_files(case_root: Path) -> list[Path]:
    collected: list[Path] = []

    for root, dirs, files in os.walk(case_root):
        dirs[:] = [name for name in dirs if not _is_ignored_dir(name)]

        for name in files:
            if _is_ignored_file(name):
                continue
            file_path = Path(root, name)
            if file_path.is_file():
                resolved = file_path.resolve()
                if not _is_within(resolved, case_root):
                    continue
                collected.append(resolved)

    return collected


def _first_stale_reason(file_path: Path, mirror_path: Path, last_verified: object) -> str | None:
    try:
        file_mtime = file_path.stat().st_mtime
    except OSError:
        return None

    try:
        mirror_mtime = mirror_path.stat().st_mtime
    except OSError:
        return None

    if mirror_mtime < file_mtime:
        return "mirror older than file mtime"

    verified_timestamp = _parse_last_verified(last_verified)
    if verified_timestamp is not None and verified_timestamp < file_mtime:
        return "index last_verified older than file mtime"

    return None


def _to_id_string(document: dict[str, object]) -> str:
    doc_id = document.get("id")
    return str(doc_id) if doc_id is not None else ""


def main() -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args()
    except SystemExit:
        return 1

    try:
        case_root = _resolve_case_root(args.case_root)
        index_count, documents = _load_index_documents(case_root)
    except Exception as exc:
        return _fatal(str(exc))

    fs_files = _collect_files(case_root)

    indexed_by_path: dict[str, tuple[str, str | None, object]] = {}
    orphans: list[dict[str, str]] = []
    stale_mirrors: list[dict[str, str]] = []

    for document in documents:
        file_path = _resolve_index_file(case_root, document.get("file"))
        if file_path is None or not _is_within(file_path, case_root):
            orphans.append({"id": _to_id_string(document), "file": ""})
            continue

        abs_file = str(file_path.as_posix())
        indexed_by_path[abs_file] = (
            _to_id_string(document),
            document.get("mirror"),
            document.get("last_verified"),
        )

        if not file_path.exists():
            orphans.append({"id": _to_id_string(document), "file": abs_file})
            continue

        mirror_path = _resolve_index_file(case_root, document.get("mirror"))
        if mirror_path is not None and _is_within(mirror_path, case_root) and mirror_path.is_file():
            reason = _first_stale_reason(file_path, mirror_path, document.get("last_verified"))
            if reason:
                stale_mirrors.append({"id": _to_id_string(document), "reason": reason})

    new_files = sorted(
        path.as_posix() for path in fs_files if str(path.as_posix()) not in indexed_by_path
    )

    result = {
        "case_root": str(case_root),
        "index_count": index_count,
        "fs_count": len(fs_files),
        "new_files": new_files,
        "orphans": orphans,
        "stale_mirrors": stale_mirrors,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
