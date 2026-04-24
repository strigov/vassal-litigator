#!/usr/bin/env python3
"""prepare_intake_workdir.py — подготовка рабочего каталога intake.

Собирает файлы из inbox, распаковывает архивы безопасно и выполняет
предварительное извлечение текста через extract_text.

Выход:
{
  "work_dir": "...",
  "files": [...],
  "archives_unpacked": [{"archive": "...", "extracted_to": "..."}],
  "unsupported": [{"archive": "...", "reason": "..."}]
}
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util as _importlib_util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic"}
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".rar", ".7z")
MAX_PREVIEW_DEFAULT = 500


def _fatal(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Подготовка work_dir для intake: распаковка архивов + preview OCR."
    )
    parser.add_argument("inbox_dir", help="Путь к Входящие документы")
    parser.add_argument("--work-dir", required=True, help="Каталог для артефактов intake")
    parser.add_argument(
        "--max-preview-chars",
        type=int,
        default=MAX_PREVIEW_DEFAULT,
        help="Сколько символов префикса текста вернуть для preview",
    )
    return parser


def _resolve_existing_dir(raw: str, *, must_exist: bool = True, ensure_is_dir: bool = True) -> Path:
    path = Path(raw).expanduser().resolve()
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if ensure_is_dir and path.exists() and not path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    return path


def _safe_filename(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return sanitized[:160] or "file"


def _archive_kind(path: Path) -> str | None:
    lower = path.name.lower()
    if lower.endswith(".tar.gz"):
        return "tar.gz"
    if lower.endswith(".tgz"):
        return "tgz"
    for suffix in (".zip", ".tar", ".rar", ".7z"):
        if lower.endswith(suffix):
            return suffix[1:]
    return None


def _archive_stem(path: Path) -> str:
    lowered = path.name.lower()
    for suffix in (".tar.gz", ".tgz"):
        if lowered.endswith(suffix):
            return path.name[:-len(suffix)]
    return path.stem


def _iter_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(dirs)
        for name in sorted(files):
            candidate = Path(current, name)
            if candidate.is_file():
                results.append(candidate)
    return results


def _is_archive(path: Path) -> bool:
    lower = path.name.lower()
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return True
    return any(lower.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _root_prefix(root: Path) -> str:
    value = str(root.resolve())
    return value if value.endswith(os.sep) else value + os.sep


def _within_root(root: Path, target: Path) -> bool:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    return (
        target_resolved == root_resolved
        or str(target_resolved).startswith(_root_prefix(root_resolved))
    )


_DRIVE_LETTER_RE = re.compile(r"^[a-zA-Z]:[\\/]")


def _member_name_is_bad(member_name: str) -> bool:
    if not member_name:
        return True
    if member_name.startswith(("/", "\\")):
        return True
    normalized = member_name.replace("\\", "/")
    if _DRIVE_LETTER_RE.match(normalized):
        return True
    if any(part == ".." for part in normalized.split("/")):
        return True
    return False


def _link_target_is_inside(root: Path, member_name: str, link_target: str) -> bool:
    if not link_target:
        return False
    if link_target.startswith(("/", "\\")) or _DRIVE_LETTER_RE.match(link_target):
        target = root / link_target
    else:
        target = (root / member_name).parent / link_target
    return _within_root(root, target)


def _recreate_dir_clean(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _validate_and_unpack_zip(archive_path: Path, extract_root: Path) -> tuple[bool, str | None]:
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            infos = zf.infolist()
            for info in infos:
                name = info.filename
                if _member_name_is_bad(name):
                    return False, f"zip member rejected: {name}"

                member_path = extract_root / name
                if not _within_root(extract_root, member_path):
                    return False, f"zip slip detected: {name}"

                mode = (info.external_attr >> 16) & 0o177777
                if stat.S_ISLNK(mode):
                    try:
                        target_bytes = zf.read(name)
                    except Exception:
                        return False, f"failed to read symlink target: {name}"
                    try:
                        link_target = target_bytes.decode("utf-8", "strict")
                    except UnicodeDecodeError:
                        try:
                            link_target = target_bytes.decode("cp1251", "strict")
                        except Exception:
                            return False, f"symlink target decode failed: {name}"
                    if not _link_target_is_inside(extract_root, name, link_target):
                        return False, f"unsafe zip symlink target: {name}"

            zf.extractall(extract_root)
        return True, None
    except Exception as exc:  # pragma: no cover - defensive runtime failures
        return False, str(exc)


def _validate_and_unpack_tar(
    archive_path: Path,
    extract_root: Path,
    *,
    mode: str,
) -> tuple[bool, str | None]:
    try:
        with tarfile.open(archive_path, mode=mode) as tf:
            for member in tf.getmembers():
                name = member.name
                if _member_name_is_bad(name):
                    return False, f"tar member rejected: {name}"

                member_path = extract_root / name
                if not _within_root(extract_root, member_path):
                    return False, f"tar slip detected: {name}"

                if member.issym() or member.islnk():
                    if not _link_target_is_inside(extract_root, name, member.linkname):
                        return False, f"unsafe tar link target: {name}"

            tf.extractall(extract_root)
        return True, None
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def _post_validate_paths(extract_root: Path, reason_path: str | None = None) -> list[Path]:
    removed: list[Path] = []
    root_real = extract_root.resolve().resolve()
    for current, _, files in os.walk(extract_root):
        for name in files:
            file_path = Path(current) / name
            try:
                file_real = file_path.resolve()
            except OSError as exc:
                print(f"cannot resolve extracted file {file_path}: {exc}", file=sys.stderr)
                continue
            if not _within_root(root_real, file_real):
                removed.append(file_path)
                try:
                    file_path.unlink()
                except OSError:
                    pass
    return removed


def _prelist_7z_members(archive_path: Path) -> tuple[list[str] | None, str | None]:
    """Return (member_paths, error). On failure returns (None, error_message)."""
    try:
        proc = subprocess.run(
            ["7z", "l", "-slt", str(archive_path)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None, "7z command not found"
    if proc.returncode != 0:
        return None, proc.stderr.strip() or "7z l failed"
    members: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("Path = "):
            members.append(line[len("Path = "):])
    return members, None


def _prelist_rar_members(archive_path: Path) -> tuple[list[str] | None, str | None]:
    """Return (member_paths, error). On failure returns (None, error_message)."""
    try:
        proc = subprocess.run(
            ["unrar", "l", str(archive_path)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None, "unrar command not found"
    if proc.returncode != 0:
        return None, proc.stderr.strip() or "unrar l failed"
    members: list[str] = []
    in_listing = False
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        # The listing starts after a separator line of dashes and ends at the next one
        if re.match(r"^-{5,}$", stripped):
            if not in_listing:
                in_listing = True
                continue
            else:
                break
        if in_listing and stripped:
            # First whitespace-delimited token on attribute lines is file attributes,
            # the last token is the filename. Columns: Attr Size ... Date Time Name
            # Use a heuristic: the path is the last column.
            parts = stripped.split()
            if len(parts) >= 1:
                members.append(parts[-1])
    return members, None


def _check_members_safe(members: list[str]) -> str | None:
    """Return an error string if any member path is unsafe, else None."""
    for name in members:
        if _member_name_is_bad(name):
            return f"unsafe member path: {name}"
    return None


def _extract_7z_archive(archive_path: Path, scratch_dir: Path, extract_root: Path) -> tuple[bool, str | None]:
    # Pre-list members before extraction to detect path escapes early
    members, list_err = _prelist_7z_members(archive_path)
    if members is None:
        return False, list_err or "failed to list 7z members"
    safety_err = _check_members_safe(members)
    if safety_err:
        return False, safety_err

    _recreate_dir_clean(scratch_dir)
    cmd = ["7z", "x", "-y", f"-o{scratch_dir}", str(archive_path)]
    try:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            return False, "7z command not found"
        if proc.returncode != 0:
            return False, proc.stderr.strip() or "failed to unpack with 7z"

        scratch_real = scratch_dir.resolve()
        for current, dirs, files in os.walk(scratch_dir):
            for name in files + dirs:
                entry = Path(current) / name
                if not _within_root(scratch_real, entry.resolve()):
                    return False, "path escape after extraction"
                if entry.is_symlink():
                    if not _within_root(scratch_real, entry.resolve()):
                        return False, "path escape after extraction"

        _recreate_dir_clean(extract_root)
        for current, _, files in os.walk(scratch_dir):
            for name in sorted(files):
                source = Path(current) / name
                relative = source.relative_to(scratch_dir)
                destination = extract_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), destination)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return True, None


def _extract_rar_archive(archive_path: Path, scratch_dir: Path, extract_root: Path) -> tuple[bool, str | None]:
    # Pre-list members before extraction to detect path escapes early
    members, list_err = _prelist_rar_members(archive_path)
    if members is None:
        return False, list_err or "failed to list rar members"
    safety_err = _check_members_safe(members)
    if safety_err:
        return False, safety_err

    _recreate_dir_clean(scratch_dir)
    cmd = ["unrar", "x", "-y", "-inul", str(archive_path), f"{scratch_dir}/"]
    try:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            return False, "unrar command not found"
        if proc.returncode != 0:
            return False, proc.stderr.strip() or "failed to unpack with unrar"

        scratch_real = scratch_dir.resolve()
        for current, dirs, files in os.walk(scratch_dir):
            for name in files + dirs:
                entry = Path(current) / name
                if not _within_root(scratch_real, entry.resolve()):
                    return False, "path escape after extraction"
                if entry.is_symlink():
                    if not _within_root(scratch_real, entry.resolve()):
                        return False, "path escape after extraction"

        _recreate_dir_clean(extract_root)
        for current, _, files in os.walk(scratch_dir):
            for name in sorted(files):
                source = Path(current) / name
                relative = source.relative_to(scratch_dir)
                destination = extract_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), destination)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return True, None


def _ensure_extracted_text_module():
    script_dir = Path(__file__).resolve().parent
    script_path = script_dir / "extract_text.py"
    spec = _importlib_util.spec_from_file_location("extract_text_script", script_path)
    if spec is None or spec.loader is None:
        return None
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.extract


def _write_text_artifact(text: str, source_path: Path, output_root: Path) -> tuple[str, int]:
    output_root.mkdir(parents=True, exist_ok=True)
    candidate = output_root / f"{source_path.name}.txt"
    if candidate.exists():
        digest = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:10]
        candidate = output_root / f"{source_path.name}.{digest}.txt"

    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_extract_", suffix=".txt", dir=str(output_root))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp_name, candidate)
    return str(candidate.resolve()), len(text)


def _extract_text_payload(
    source_path: Path,
    output_root: Path,
    extractor,
) -> dict[str, object]:
    try:
        result = extractor(str(source_path))
    except Exception as exc:
        print(f"extract_text failed for {source_path}: {exc}", file=sys.stderr)
        result = {
            "text": "",
            "method": "none",
            "confidence": "low",
            "pages": 0,
        }
    if not isinstance(result, dict):
        raise RuntimeError(f"extract_text returned invalid payload for {source_path}")

    text = result.get("text", "")
    if not isinstance(text, str):
        text = ""

    saved_to = None
    total_chars = len(text)
    if text:
        saved_to, total_chars = _write_text_artifact(text, source_path, output_root)

    return {
        "text": text,
        "saved_to": saved_to,
        "method": result.get("method", "none"),
        "confidence": result.get("confidence", "low"),
        "pages": result.get("pages", 0),
        "total_chars": total_chars,
    }


def _iter_final_files_from_directory(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, _, names in os.walk(root):
        for name in sorted(names):
            candidate = Path(current, name)
            if candidate.is_file() and not _is_archive(candidate):
                files.append(candidate)
    return files


def _add_file_entry(
    file_path: Path,
    output_root: Path,
    max_preview_chars: int,
    extractor,
    archive_src: Path | None,
    files: list[dict[str, object]],
) -> None:
    payload = _extract_text_payload(file_path, output_root, extractor)
    text = payload["text"]
    assert isinstance(text, str)
    preview = text[:max_preview_chars] if max_preview_chars >= 0 else ""
    pages = payload.get("pages", 0)
    if not isinstance(pages, int):
        try:
            pages = int(pages)
        except (TypeError, ValueError):
            pages = 0

    files.append(
        {
            "source_path": str(file_path.resolve()),
            "extracted_text_preview": preview,
            "extraction_method": payload["method"],
            "confidence": payload["confidence"],
            "pages": pages,
            "total_chars": payload["total_chars"],
            "needs_image_to_pdf": _is_image(file_path),
            "archive_src": str(archive_src.resolve()) if archive_src is not None else None,
            "ocr_artifact_path": payload["saved_to"],
        }
    )


def _unpack_archive(
    archive_path: Path,
    archive_type: str,
    work_dir: Path,
    extracted_root: Path,
    extractor,
    max_preview_chars: int,
    unsupported: list[dict[str, str]],
    archives_unpacked: list[dict[str, str]],
    files: list[dict[str, object]],
) -> None:
    archive_stem = _archive_stem(archive_path)
    extract_root = work_dir / archive_stem
    _recreate_dir_clean(extract_root)

    kind = archive_type
    success = False
    reason: str | None = None
    if kind in {"zip"}:
        success, reason = _validate_and_unpack_zip(archive_path, extract_root)
    elif kind in {"tar", "tar.gz", "tgz"}:
        mode = "r:gz" if kind in {"tar.gz", "tgz"} else "r:"
        success, reason = _validate_and_unpack_tar(archive_path, extract_root, mode=mode)
    elif kind == "7z":
        scratch_root = work_dir / ".scratch" / archive_stem
        success, reason = _extract_7z_archive(archive_path, scratch_root, extract_root)
    elif kind == "rar":
        scratch_root = work_dir / ".scratch" / archive_stem
        success, reason = _extract_rar_archive(archive_path, scratch_root, extract_root)
    else:
        success = False
        reason = f"Unsupported archive type: {kind}"

    if not success:
        unsupported.append({"archive": str(archive_path.resolve()), "reason": reason or "unsupported archive"})
        shutil.rmtree(extract_root, ignore_errors=True)
        return

    escaped = _post_validate_paths(extract_root)
    if escaped:
        shutil.rmtree(extract_root, ignore_errors=True)
        unsupported.append(
            {
                "archive": str(archive_path.resolve()),
                "reason": "escaped paths detected",
            }
        )
        return

    final_files = _iter_final_files_from_directory(extract_root)
    if final_files:
        archives_unpacked.append(
            {
                "archive": str(archive_path.resolve()),
                "extracted_to": str(extract_root.resolve()),
            }
        )

    for final_path in sorted(final_files, key=lambda p: str(p)):
        _add_file_entry(final_path, extracted_root, max_preview_chars, extractor, archive_path, files)


def main() -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args()
    except SystemExit:
        return 1

    try:
        inbox_dir = _resolve_existing_dir(args.inbox_dir)
        work_dir = _resolve_existing_dir(args.work_dir, must_exist=False)
    except Exception as exc:
        return _fatal(str(exc))

    work_dir.mkdir(parents=True, exist_ok=True)
    extracted_root = work_dir / "extracted"
    extracted_root.mkdir(parents=True, exist_ok=True)

    extractor = _ensure_extracted_text_module()
    if extractor is None:
        return _fatal("Не удалось загрузить scripts/extract_text.py")

    files: list[dict[str, object]] = []
    archives_unpacked: list[dict[str, str]] = []
    unsupported: list[dict[str, str]] = []

    for path in sorted(_iter_files(inbox_dir), key=lambda p: str(p)):
        if not path.is_file():
            continue
        kind = _archive_kind(path)
        if kind:
            _unpack_archive(
                archive_path=path,
                archive_type=kind,
                work_dir=work_dir,
                extracted_root=extracted_root,
                extractor=extractor,
                max_preview_chars=max(0, args.max_preview_chars),
                unsupported=unsupported,
                archives_unpacked=archives_unpacked,
                files=files,
            )
            continue

        _add_file_entry(
            file_path=path,
            output_root=extracted_root,
            max_preview_chars=max(0, args.max_preview_chars),
            extractor=extractor,
            archive_src=None,
            files=files,
        )

    files.sort(key=lambda item: item["source_path"])

    result = {
        "work_dir": str(work_dir.resolve()),
        "files": files,
        "archives_unpacked": archives_unpacked,
        "unsupported": unsupported,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
