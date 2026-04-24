"""Unit tests for scripts/scan_case_state.py."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest
import yaml

import scan_case_state as scs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(tmp_path: Path, documents: list | None = None) -> Path:
    """Create a minimal case directory with .vassal/index.yaml."""
    vassal = tmp_path / ".vassal"
    vassal.mkdir(parents=True, exist_ok=True)
    index = vassal / "index.yaml"
    payload: dict = {}
    if documents is not None:
        payload["documents"] = documents
    index.write_text(yaml.dump(payload), encoding="utf-8")
    return tmp_path


def _touch(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


# ---------------------------------------------------------------------------
# 1. new_files — files on disk that are NOT in index.yaml
# ---------------------------------------------------------------------------

def test_new_files_detected(tmp_path: Path) -> None:
    case_root = _make_case(tmp_path, documents=[])
    doc = _touch(case_root / "contract.pdf")

    case_root_resolved = scs._resolve_case_root(str(case_root))
    _, documents = scs._load_index_documents(case_root_resolved)
    fs_files = scs._collect_files(case_root_resolved)

    indexed_paths: set[str] = set()
    for d in documents:
        p = scs._resolve_index_file(case_root_resolved, d.get("file"))
        if p:
            indexed_paths.add(p.as_posix())

    new_files = sorted(
        f.as_posix() for f in fs_files if f.as_posix() not in indexed_paths
    )

    assert doc.resolve().as_posix() in new_files


def test_new_files_empty_when_all_indexed(tmp_path: Path) -> None:
    case_root = _make_case(tmp_path, documents=[])
    doc = _touch(case_root / "indexed.pdf")

    # Add that file to the index
    _make_case(
        tmp_path,
        documents=[{"id": "D1", "file": "indexed.pdf"}],
    )

    case_root_resolved = scs._resolve_case_root(str(case_root))
    _, documents = scs._load_index_documents(case_root_resolved)
    fs_files = scs._collect_files(case_root_resolved)

    indexed_paths = set()
    for d in documents:
        p = scs._resolve_index_file(case_root_resolved, d.get("file"))
        if p:
            indexed_paths.add(p.as_posix())

    new_files = [f.as_posix() for f in fs_files if f.as_posix() not in indexed_paths]
    assert new_files == []


# ---------------------------------------------------------------------------
# 2. orphans — index.yaml lists a file that does not exist on disk
# ---------------------------------------------------------------------------

def test_orphan_when_file_missing(tmp_path: Path) -> None:
    case_root = _make_case(
        tmp_path,
        documents=[{"id": "D99", "file": "ghost.pdf"}],
    )

    case_root_resolved = scs._resolve_case_root(str(case_root))
    _, documents = scs._load_index_documents(case_root_resolved)

    orphans: list[dict] = []
    for d in documents:
        fp = scs._resolve_index_file(case_root_resolved, d.get("file"))
        if fp is None or not fp.exists():
            orphans.append({"id": scs._to_id_string(d), "file": fp.as_posix() if fp else ""})

    ids = [o["id"] for o in orphans]
    assert "D99" in ids


def test_no_orphan_when_file_present(tmp_path: Path) -> None:
    case_root = _make_case(
        tmp_path,
        documents=[{"id": "D1", "file": "present.pdf"}],
    )
    _touch(case_root / "present.pdf")

    case_root_resolved = scs._resolve_case_root(str(case_root))
    _, documents = scs._load_index_documents(case_root_resolved)

    orphans = []
    for d in documents:
        fp = scs._resolve_index_file(case_root_resolved, d.get("file"))
        if fp is None or not fp.exists():
            orphans.append(d)

    assert orphans == []


# ---------------------------------------------------------------------------
# 3. stale_mirrors — mirror file older/newer than source file
# ---------------------------------------------------------------------------

def test_stale_mirror_when_mirror_older_than_source(tmp_path: Path) -> None:
    source = _touch(tmp_path / "source.pdf")
    mirror = _touch(tmp_path / "mirror.txt")

    now = time.time()
    _set_mtime(mirror, now - 100)   # mirror is older
    _set_mtime(source, now)          # source is newer

    reason = scs._first_stale_reason(source, mirror, None)
    assert reason is not None
    assert "mirror older" in reason


def test_no_stale_mirror_when_mirror_newer_than_source(tmp_path: Path) -> None:
    source = _touch(tmp_path / "source.pdf")
    mirror = _touch(tmp_path / "mirror.txt")

    now = time.time()
    _set_mtime(source, now - 100)   # source is older
    _set_mtime(mirror, now)          # mirror is newer

    reason = scs._first_stale_reason(source, mirror, None)
    assert reason is None


# ---------------------------------------------------------------------------
# 4. stale_mirrors from last_verified
# ---------------------------------------------------------------------------

def test_stale_mirror_when_last_verified_older_than_source(tmp_path: Path) -> None:
    source = _touch(tmp_path / "source.pdf")
    mirror = _touch(tmp_path / "mirror.txt")

    now = time.time()
    # mirror is fresh (newer than source), but last_verified is stale
    _set_mtime(source, now - 50)
    _set_mtime(mirror, now)          # mirror itself is newer → no mirror-mtime issue
    last_verified_ts = now - 200     # last_verified predates source mtime → stale

    reason = scs._first_stale_reason(source, mirror, last_verified_ts)
    assert reason is not None
    assert "last_verified" in reason


def test_no_stale_when_last_verified_newer_than_source(tmp_path: Path) -> None:
    source = _touch(tmp_path / "source.pdf")
    mirror = _touch(tmp_path / "mirror.txt")

    now = time.time()
    _set_mtime(source, now - 200)
    _set_mtime(mirror, now)           # mirror is newer than source
    last_verified_ts = now - 50       # last_verified is also after source mtime

    reason = scs._first_stale_reason(source, mirror, last_verified_ts)
    assert reason is None


# ---------------------------------------------------------------------------
# 5. ignored directories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ignored_dir", [".vassal", "Входящие документы", "На удаление"])
def test_ignored_directory_files_not_in_new_files(tmp_path: Path, ignored_dir: str) -> None:
    case_root = _make_case(tmp_path, documents=[])
    _touch(case_root / ignored_dir / "secret.pdf")

    case_root_resolved = scs._resolve_case_root(str(case_root))
    fs_files = scs._collect_files(case_root_resolved)

    posix_paths = [f.as_posix() for f in fs_files]
    assert not any(ignored_dir in p for p in posix_paths), (
        f"Files inside '{ignored_dir}/' must be ignored; found: {posix_paths}"
    )


def test_tmp_directory_ignored(tmp_path: Path) -> None:
    case_root = _make_case(tmp_path, documents=[])
    _touch(case_root / "work.tmp" / "file.pdf")

    case_root_resolved = scs._resolve_case_root(str(case_root))
    fs_files = scs._collect_files(case_root_resolved)

    assert not any("work.tmp" in f.as_posix() for f in fs_files)


# ---------------------------------------------------------------------------
# 6. ignored files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ignored_name", [".DS_Store", "Thumbs.db"])
def test_ignored_filenames_not_in_new_files(tmp_path: Path, ignored_name: str) -> None:
    case_root = _make_case(tmp_path, documents=[])
    _touch(case_root / ignored_name)

    case_root_resolved = scs._resolve_case_root(str(case_root))
    fs_files = scs._collect_files(case_root_resolved)

    names = [f.name for f in fs_files]
    assert ignored_name not in names, f"'{ignored_name}' must be ignored but was found"


def test_tmp_suffix_files_ignored(tmp_path: Path) -> None:
    case_root = _make_case(tmp_path, documents=[])
    _touch(case_root / "draft.tmp")

    case_root_resolved = scs._resolve_case_root(str(case_root))
    fs_files = scs._collect_files(case_root_resolved)

    assert not any(f.name == "draft.tmp" for f in fs_files)


# ---------------------------------------------------------------------------
# 7. missing index.yaml → FileNotFoundError / SystemExit
# ---------------------------------------------------------------------------

def test_missing_index_yaml_raises(tmp_path: Path) -> None:
    # No .vassal/index.yaml created
    with pytest.raises(FileNotFoundError):
        scs._load_index_documents(tmp_path)


def test_missing_case_root_raises(tmp_path: Path) -> None:
    nonexistent = tmp_path / "no_such_dir"
    with pytest.raises(FileNotFoundError):
        scs._resolve_case_root(str(nonexistent))


# ---------------------------------------------------------------------------
# 8. empty case — empty index.yaml + empty dir → all lists empty
# ---------------------------------------------------------------------------

def test_empty_case_all_lists_empty(tmp_path: Path) -> None:
    case_root = _make_case(tmp_path, documents=[])

    case_root_resolved = scs._resolve_case_root(str(case_root))
    index_count, documents = scs._load_index_documents(case_root_resolved)
    fs_files = scs._collect_files(case_root_resolved)

    indexed_paths: set[str] = set()
    orphans: list = []
    stale_mirrors: list = []

    for d in documents:
        fp = scs._resolve_index_file(case_root_resolved, d.get("file"))
        if fp is None or not fp.exists():
            orphans.append(d)
        else:
            indexed_paths.add(fp.as_posix())

    new_files = [f.as_posix() for f in fs_files if f.as_posix() not in indexed_paths]

    assert index_count == 0
    assert new_files == []
    assert orphans == []
    assert stale_mirrors == []
