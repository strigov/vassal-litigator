#!/usr/bin/env python3
"""Apply machine-generated intake plan deterministically."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from classify_ocr_quality import classify

DOC_ID_RE = re.compile(r"^doc-(\d+)$")
BUNDLE_ID_RE = re.compile(r"^bundle-(\d+)$")
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ApplyError(RuntimeError):
    pass


def _fatal(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply machine-approved intake/add-evidence/add-opponent plan")
    parser.add_argument(
        "path",
        help="Case root directory (legacy) or plan yaml path",
    )
    parser.add_argument(
        "--plan-yaml",
        required=False,
        default=None,
        help="Plan machine YAML in .vassal/plans/",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no filesystem writes")
    parser.add_argument("--force", action="store_true", help="Compatibility flag; currently no-op")
    return parser


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_minute() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _real_path(path: Path) -> Path:
    return Path(os.path.realpath(str(path)))


def _contains(root: Path, target: Path, *, allow_equal: bool = True) -> bool:
    root_real = _real_path(root)
    target_real = _real_path(target)
    try:
        common = Path(os.path.commonpath([str(root_real), str(target_real)]))
    except ValueError:
        return False
    if not common == root_real:
        return False
    if allow_equal:
        return True
    return str(target_real) != str(root_real)


def _safe_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _safe_write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def _resolve_case_root(raw: str) -> Path:
    case_root = Path(raw).expanduser().resolve()
    if not case_root.exists():
        raise ApplyError(f"case root does not exist: {case_root}")
    if not case_root.is_dir():
        raise ApplyError(f"case root is not a directory: {case_root}")
    return case_root


def _plan_yaml_guard(case_root: Path, plan_raw: str) -> Path:
    plans_root = (case_root / ".vassal" / "plans").resolve()
    try:
        plan_path = Path(plan_raw).expanduser().resolve(strict=True)
    except Exception as exc:
        raise ApplyError("plan-yaml must reside under <case_root>/.vassal/plans/") from exc

    if not plan_path.is_file():
        raise ApplyError("plan-yaml must reside under <case_root>/.vassal/plans/")
    if not _contains(plans_root, plan_path, allow_equal=False):
        raise ApplyError("plan-yaml must reside under <case_root>/.vassal/plans/")
    return plan_path


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ApplyError(f"failed to parse yaml: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApplyError("plan yaml must be mapping")
    return payload


def _coerce_str(value: Any, *, field: str, allow_empty: bool = False) -> str:
    if value is None:
        raise ApplyError(f"{field} must be a string")
    if not isinstance(value, str):
        raise ApplyError(f"{field} must be a string")
    value = value.strip()
    if not allow_empty and not value:
        raise ApplyError(f"{field} must be non-empty")
    return value


def _coerce_optional_str(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _coerce_str(value, field=field)


def _coerce_int(value: Any, *, field: str, allow_none: bool = False, non_negative: bool = False) -> int | None:
    if value is None:
        if allow_none:
            return None
        raise ApplyError(f"{field} must be int")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApplyError(f"{field} must be int")
    if non_negative and value < 0:
        raise ApplyError(f"{field} must be >= 0")
    return value


def _coerce_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ApplyError(f"{field} must be bool")


def _coerce_list(value: Any, *, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ApplyError(f"{field} must be list")
    return value


def _coerce_date(value: Any, *, field: str, allow_none: bool = False) -> str | None:
    if value is None:
        if allow_none:
            return None
        raise ApplyError(f"{field} must be date")
    value = _coerce_str(value, field=field, allow_empty=True)
    if value == "":
        if allow_none:
            return None
        raise ApplyError(f"{field} must be date")
    if not DATE_RE.fullmatch(value):
        raise ApplyError(f"{field} must be YYYY-MM-DD")
    return value


def _resolve_in(plan_base: Path, raw: Any, *, field: str, must_exist: bool = True) -> Path:
    if raw is None:
        raise ApplyError(f"{field} must be provided")
    if not isinstance(raw, str):
        raise ApplyError(f"{field} must be path string")
    path = Path(raw)
    if not path.is_absolute():
        path = plan_base / path
    path = path.expanduser()
    if must_exist and not path.exists():
        raise ApplyError(f"{field} does not exist: {path}")
    return path


def _resolve_optional_in(plan_base: Path, raw: Any, *, field: str, must_exist: bool = False) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ApplyError(f"{field} must be path string")
    path = Path(raw)
    if not path.is_absolute():
        path = plan_base / path
    path = path.expanduser()
    if must_exist and not path.exists():
        raise ApplyError(f"{field} does not exist: {path}")
    return path


def _bucket_confidence(raw: Any) -> str:
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"high", "medium", "low"}:
            return text
        try:
            value = float(text)
        except ValueError:
            return "low"
    elif isinstance(raw, (int, float)):
        value = float(raw)
    else:
        return "low"
    if value >= 0.75:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def _agg_ocr_artifacts(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    if not artifacts:
        return {
            "primary": "unknown",
            "pages": 0,
            "total_chars": 0,
            "confidence": "low",
            "mixed": False,
        }

    primary = artifacts[0].get("extraction_method", "unknown")
    methods = [a.get("extraction_method") for a in artifacts]
    mixed = len({m for m in methods if m}) > 1

    total_pages = 0
    total_chars = 0
    worst = "high"
    for artifact in artifacts:
        total_pages += int(artifact.get("pages") or 0)
        total_chars += int(artifact.get("total_chars") or 0)
        conf = _bucket_confidence(artifact.get("confidence"))
        if CONFIDENCE_ORDER[conf] < CONFIDENCE_ORDER[worst]:
            worst = conf

    return {
        "primary": primary,
        "pages": total_pages,
        "total_chars": total_chars,
        "confidence": worst,
        "mixed": mixed,
    }


def _load_index_payload(case_root: Path) -> dict[str, Any]:
    index_path = case_root / ".vassal" / "index.yaml"
    if not index_path.exists():
        raise ApplyError("index file not found: .vassal/index.yaml")
    payload = _load_yaml(index_path)

    documents = payload.get("documents")
    bundles = payload.get("bundles")
    if documents is None:
        documents = []
    if bundles is None:
        bundles = []
    if not isinstance(documents, list):
        raise ApplyError("index.yaml.documents must be list")
    if not isinstance(bundles, list):
        raise ApplyError("index.yaml.bundles must be list")

    next_id = _coerce_int(payload.get("next_id"), field="index.yaml.next_id", non_negative=True)
    next_bundle_id = _coerce_int(payload.get("next_bundle_id"), field="index.yaml.next_bundle_id", non_negative=True)
    if next_id is None:
        raise ApplyError("index.yaml.next_id missing")
    if next_bundle_id is None:
        raise ApplyError("index.yaml.next_bundle_id missing")

    return {
        "version": payload.get("version", 2),
        "last_updated": payload.get("last_updated", _now()),
        "documents": documents,
        "bundles": bundles,
        "next_id": next_id,
        "next_bundle_id": next_bundle_id,
        "extra": {
            k: v
            for k, v in payload.items()
            if k not in {"version", "last_updated", "documents", "bundles", "next_id", "next_bundle_id"}
        },
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_image_to_pdf(inputs: list[Path], output: Path) -> None:
    script = Path(__file__).resolve().parent / "image_to_pdf.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--out", str(output), "--in", *[str(path) for path in inputs]],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ApplyError((proc.stderr or proc.stdout or "image_to_pdf failed").strip())


def _run_extract_text(path: Path, output_dir: Path) -> dict[str, Any]:
    script = Path(__file__).resolve().parent / "extract_text.py"
    output_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(script), str(path), "--output-dir", str(output_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ApplyError((proc.stderr or proc.stdout or "extract_text failed").strip())
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception as exc:
        raise ApplyError(f"extract_text output parse error: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApplyError("extract_text returned invalid json")
    text = payload.get("text")
    if not isinstance(text, str):
        raise ApplyError("extract_text payload missing text")
    return payload


def _read_item_text(item: dict[str, Any], work_dir: Path) -> tuple[str, list[dict[str, Any]]]:
    combined_path = item.get("combined_text_path")
    if combined_path is not None:
        return _read_text(combined_path), []

    ocr_artifacts = item.get("ocr_artifacts") or []
    if ocr_artifacts:
        pieces: list[str] = []
        for artifact in ocr_artifacts:
            path = artifact.get("path")
            if path is None:
                pieces.append("")
                continue
            pieces.append(_read_text(path))
        text = "\n\n--- page N ---\n\n".join(pieces)
        return text, ocr_artifacts

    if not ocr_artifacts:
        sources = item["grouped_inputs"] if item["grouped_inputs"] is not None else [item["source_path"]]
        pieces: list[str] = []
        artifacts: list[dict[str, Any]] = []
        for source in sources:
            if source is None:
                raise ApplyError("missing source in fallback text extraction")
            payload = _run_extract_text(source, work_dir / "extracted")
            pieces.append(payload.get("text", ""))
            artifacts.append(
                {
                    "extraction_method": _coerce_str(payload.get("method"), field="extract_text.method", allow_empty=True)
                    or payload.get("extraction_method", "unknown"),
                    "pages": _coerce_int(payload.get("pages"), field="extract_text.pages", allow_none=True) or 0,
                    "total_chars": len(payload.get("text", "")),
                    "confidence": payload.get("confidence", "low"),
                }
            )
        return "\n\n--- page N ---\n\n".join(pieces), artifacts

    return None, ocr_artifacts


def _build_mirror_text(*, item: dict[str, Any], aggregate: dict[str, Any], case_root: Path, text: str) -> str:
    frontmatter: dict[str, Any] = {
        "id": item["doc_id"],
        "source": item["target_file"].relative_to(case_root).as_posix(),
        "type": item["type"],
        "title": item["title"],
        "date": item["date"],
        "pages": aggregate["pages"],
        "extraction_method": aggregate["primary"],
        "extraction_model": "haiku",
        "extraction_date": _now(),
        "confidence": aggregate["confidence"],
        "ocr_reattempted": False,
    }
    if aggregate.get("mixed"):
        frontmatter["extraction_methods_mixed"] = True

    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    body = text
    if body and not body.endswith("\n"):
        body += "\n"

    return f"---\n{fm}\n---\n\n{body}"


def _history_line(batch: str, item_count: int, bundle_count: int, orphan_count: int, plan_path: Path) -> str:
    plan_file = f".vassal/plans/{plan_path.name}"
    if plan_file.endswith(".yaml"):
        plan_file = plan_file[:-5] + ".md"
    return (
        f"{_now_minute()} intake apply: batch={batch}, "
        f"файлов: {item_count}, комплектов: {bundle_count}, сирот: {orphan_count}, "
        f"план: {plan_file}"
    )

def _append_history(case_root: Path, line: str) -> None:
    history_path = case_root / ".vassal" / "history.md"
    if not history_path.exists():
        _safe_write_text(history_path, line + "\n")
        return
    current = history_path.read_text(encoding="utf-8")
    if line in current:
        return
    _safe_write_text(history_path, current.rstrip("\n") + "\n" + line + "\n")


def _validate_plan(case_root: Path, raw_plan: dict[str, Any], index_payload: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    batch = _coerce_str(raw_plan.get("batch"), field="batch")
    if Path(batch).name != batch or "/" in batch or batch in {".", ".."}:
        raise ApplyError("batch must be safe file identifier")
    inbox = (case_root / "Входящие документы").resolve()
    source_inbox = _resolve_in(case_root, raw_plan.get("source_inbox"), field="source_inbox", must_exist=False)
    if source_inbox.resolve() != inbox:
        raise ApplyError("source_inbox must be exactly <case_root>/Входящие документы")

    work_dir = _resolve_in(case_root, raw_plan.get("work_dir"), field="work_dir", must_exist=False)
    work_root = (case_root / ".vassal" / "work").resolve()
    if not _contains(work_root, work_dir, allow_equal=False):
        raise ApplyError("work_dir must be inside <case_root>/.vassal/work/")

    raw_dest = _resolve_in(case_root, raw_plan.get("raw_dest"), field="raw_dest", must_exist=False)
    raw_root = (case_root / ".vassal" / "raw").resolve()
    if not _contains(raw_root, raw_dest):
        raise ApplyError("raw_dest must be inside <case_root>/.vassal/raw/")

    next_id_start = _coerce_int(raw_plan.get("next_id_start"), field="next_id_start", non_negative=True)
    if next_id_start != index_payload["next_id"]:
        raise ApplyError("next_id_start mismatch")
    next_bundle_id_start = _coerce_int(raw_plan.get("next_bundle_id_start"), field="next_bundle_id_start", non_negative=True)

    raw_only_raw = _coerce_list(raw_plan.get("raw_only"), field="raw_only")
    raw_only: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw_only_raw):
        if not isinstance(entry, dict):
            raise ApplyError(f"raw_only[{idx}] must be mapping")
        archive_src = _resolve_in(case_root, entry.get("archive_src"), field=f"raw_only[{idx}].archive_src")
        if not _contains(source_inbox, archive_src, allow_equal=False) and archive_src != source_inbox:
            raise ApplyError("raw_only[].archive_src must be inside source_inbox")
        raw_dest_name = _coerce_str(entry.get("raw_dest_name"), field=f"raw_only[{idx}].raw_dest_name")
        if raw_dest_name != Path(raw_dest_name).name:
            raise ApplyError(f"raw_only[{idx}].raw_dest_name must be file name")
        if raw_dest_name in {".", ".."} or "/" in raw_dest_name or "\\" in raw_dest_name:
            raise ApplyError(f"raw_only[{idx}].raw_dest_name must be safe file name")
        raw_only.append({"archive_src": archive_src, "raw_dest_name": raw_dest_name})

    skipped_raw = _coerce_list(raw_plan.get("skipped"), field="skipped")
    skipped: list[dict[str, Any]] = []
    for idx, entry in enumerate(skipped_raw):
        if not isinstance(entry, dict):
            raise ApplyError(f"skipped[{idx}] must be mapping")
        path = _resolve_in(case_root, entry.get("path"), field=f"skipped[{idx}].path")
        if not (_contains(source_inbox, path) or _contains(work_dir, path)):
            raise ApplyError("skipped[].path must be in source_inbox or work_dir")
        skipped.append({
            "path": path,
            "reason": _coerce_optional_str(entry.get("reason"), field=f"skipped[{idx}].reason"),
        })

    cleanup_set_raw = _coerce_list(raw_plan.get("cleanup_set"), field="cleanup_set")
    cleanup_set: list[Path] = []
    for idx, item in enumerate(cleanup_set_raw):
        if not isinstance(item, str):
            raise ApplyError(f"cleanup_set[{idx}] must be string")
        path = _resolve_in(case_root, item, field=f"cleanup_set[{idx}]", must_exist=False)
        if not _contains(source_inbox, path):
            raise ApplyError("cleanup_set entries must be inside source_inbox")
        cleanup_set.append(path)

    existing_bundles_by_id = {
        bundle.get("id"): dict(bundle)
        for bundle in index_payload["bundles"]
        if isinstance(bundle, dict) and isinstance(bundle.get("id"), str)
    }

    bundles_raw = _coerce_list(raw_plan.get("bundles"), field="bundles")
    bundles: list[dict[str, Any]] = []
    for idx, bundle in enumerate(bundles_raw):
        if not isinstance(bundle, dict):
            raise ApplyError(f"bundles[{idx}] must be mapping")
        bundle_id = _coerce_str(bundle.get("id"), field=f"bundles[{idx}].id")
        if not BUNDLE_ID_RE.fullmatch(bundle_id):
            raise ApplyError(f"bundles[{idx}].id must be bundle-NNN")
        is_new = _coerce_bool(bundle.get("is_new", False), field=f"bundles[{idx}].is_new")
        if is_new and bundle_id in existing_bundles_by_id:
            raise ApplyError("bundle with this id already exists")
        if not is_new and bundle_id not in existing_bundles_by_id:
            raise ApplyError("bundle not found for is_new=false")

        main_doc = _coerce_str(bundle.get("main_doc"), field=f"bundles[{idx}].main_doc")
        if not DOC_ID_RE.fullmatch(main_doc):
            raise ApplyError(f"bundles[{idx}].main_doc must be doc-NNN")
        members_raw = _coerce_list(bundle.get("members"), field=f"bundles[{idx}].members")
        members: list[str] = []
        for m_idx, member in enumerate(members_raw):
            member_id = _coerce_str(member, field=f"bundles[{idx}].members[{m_idx}]")
            if not DOC_ID_RE.fullmatch(member_id):
                raise ApplyError(f"bundles[{idx}].members[{m_idx}] must be doc-NNN")
            if member_id not in members:
                members.append(member_id)
        if main_doc not in members:
            raise ApplyError("bundles[].members must include main_doc")
        bundles.append({
            "id": bundle_id,
            "is_new": is_new,
            "title": _coerce_str(bundle.get("title"), field=f"bundles[{idx}].title"),
            "main_doc": main_doc,
            "members": members,
        })

    items_raw = _coerce_list(raw_plan.get("items"), field="items")
    items: list[dict[str, Any]] = []
    doc_ids: set[str] = set()
    target_files: set[str] = set()
    for idx, item in enumerate(items_raw):
        if not isinstance(item, dict):
            raise ApplyError(f"items[{idx}] must be mapping")

        has_source = item.get("source_path") is not None
        has_grouped = item.get("grouped_inputs") is not None
        if has_source == has_grouped:
            raise ApplyError(f"items[{idx}] must contain exactly one of source_path/grouped_inputs")

        convert_image_to_pdf = _coerce_bool(item.get("convert_image_to_pdf", False), field=f"items[{idx}].convert_image_to_pdf")
        if has_source and convert_image_to_pdf:
            raise ApplyError("convert_image_to_pdf requires grouped_inputs")
        if has_grouped and not convert_image_to_pdf:
            raise ApplyError("grouped_inputs requires convert_image_to_pdf=true")

        source_path: Path | None = None
        grouped_inputs: list[Path] | None = None

        if has_source:
            source_path = _resolve_in(case_root, item.get("source_path"), field=f"items[{idx}].source_path")
            if not (_contains(source_inbox, source_path) or _contains(work_dir, source_path)):
                raise ApplyError("source_path must be inside source_inbox or work_dir")
        else:
            grouped_raw = item.get("grouped_inputs")
            if not isinstance(grouped_raw, list) or len(grouped_raw) < 2:
                raise ApplyError("grouped_inputs must be list of at least two paths")
            grouped_inputs = []
            for g_idx, g in enumerate(grouped_raw):
                path = _resolve_in(case_root, g, field=f"items[{idx}].grouped_inputs[{g_idx}]")
                if not (_contains(source_inbox, path) or _contains(work_dir, path)):
                    raise ApplyError("grouped_inputs entries must be inside source_inbox or work_dir")
                grouped_inputs.append(path)

        target_file = _resolve_optional_in(case_root, item.get("target_file"), field=f"items[{idx}].target_file")
        if target_file is None:
            raise ApplyError(f"items[{idx}].target_file is required")
        if _contains(case_root / ".vassal", target_file):
            raise ApplyError("target_file must not be inside .vassal")
        if _contains(source_inbox, target_file):
            raise ApplyError("target_file must not be inside source_inbox")
        if not _contains(case_root, target_file, allow_equal=False):
            raise ApplyError("target_file must be inside case_root")
        target_key = str(target_file)
        if target_key in target_files:
            raise ApplyError("duplicate target_file in items")
        target_files.add(target_key)

        if not force:
            existing_files = {
                doc.get("file")
                for doc in index_payload.get("documents", [])
                if isinstance(doc, dict)
            }
            target_rel = target_file.relative_to(case_root).as_posix()
            if target_rel in existing_files:
                raise ApplyError(f"target_file already in index: {item['target_file']}")

        archive_src = _resolve_optional_in(case_root, item.get("archive_src"), field=f"items[{idx}].archive_src")
        if archive_src is not None and not _contains(source_inbox, archive_src, allow_equal=False):
            raise ApplyError("items[].archive_src must be inside source_inbox")

        ocr_artifacts_raw = _coerce_list(item.get("ocr_artifacts"), field=f"items[{idx}].ocr_artifacts")
        ocr_artifacts: list[dict[str, Any]] = []
        for a_idx, artifact in enumerate(ocr_artifacts_raw):
            if not isinstance(artifact, dict):
                raise ApplyError(f"items[{idx}].ocr_artifacts[{a_idx}] must be mapping")
            method = _coerce_str(artifact.get("extraction_method"), field=f"items[{idx}].ocr_artifacts[{a_idx}].extraction_method")
            pages = _coerce_int(artifact.get("pages"), field=f"items[{idx}].ocr_artifacts[{a_idx}].pages", allow_none=True, non_negative=True)
            total_chars = _coerce_int(artifact.get("total_chars"), field=f"items[{idx}].ocr_artifacts[{a_idx}].total_chars", allow_none=True, non_negative=True)
            combined = _coerce_optional_str(artifact.get("path"), field=f"items[{idx}].ocr_artifacts[{a_idx}].path")
            artifact_path = _resolve_optional_in(case_root / "", combined, field=f"items[{idx}].ocr_artifacts[{a_idx}].path", must_exist=False) if combined is not None else None
            if artifact_path is not None and not _contains(work_dir, artifact_path):
                raise ApplyError("ocr_artifacts[].path must be inside work_dir")
            if artifact_path is not None and not artifact_path.exists():
                raise ApplyError(f"items[{idx}].ocr_artifacts[{a_idx}].path does not exist: {artifact_path}")
            ocr_artifacts.append(
                {
                    "extraction_method": method,
                    "pages": 0 if pages is None else pages,
                    "total_chars": 0 if total_chars is None else total_chars,
                    "confidence": artifact.get("confidence"),
                    "path": artifact_path,
                }
            )

        combined_text = _resolve_optional_in(case_root, item.get("combined_text_path"), field=f"items[{idx}].combined_text_path", must_exist=False)
        if combined_text is not None:
            if not _contains(work_dir, combined_text):
                raise ApplyError("combined_text_path must be inside work_dir")
            if not combined_text.exists():
                raise ApplyError("combined_text_path does not exist")

        if grouped_inputs is not None:
            if combined_text is None:
                raise ApplyError("grouped_inputs requires combined_text_path")
            if len(ocr_artifacts) != len(grouped_inputs):
                raise ApplyError("grouped_inputs requires ocr_artifacts count equal to grouped_inputs")
        else:
            if len(ocr_artifacts) not in {0, 1}:
                raise ApplyError("single item must have 0 or 1 ocr_artifact")
            if combined_text is not None and len(ocr_artifacts) == 1 and ocr_artifacts[0]["path"] is not None:
                if os.path.realpath(str(combined_text)) != os.path.realpath(str(ocr_artifacts[0]["path"])):
                    raise ApplyError("combined_text_path should equal singular ocr_artifact.path or be null")

        date_value = _coerce_date(item.get("date"), field=f"items[{idx}].date", allow_none=True)
        origin_raw = item.get("origin")
        if not isinstance(origin_raw, dict):
            raise ApplyError("items[].origin must be mapping")
        origin_name = _coerce_str(origin_raw.get("name"), field=f"items[{idx}].origin.name")
        origin_date = _coerce_date(origin_raw.get("date"), field=f"items[{idx}].origin.date", allow_none=True)
        origin_received = _coerce_date(origin_raw.get("received"), field=f"items[{idx}].origin.received")
        origin_batch = _coerce_str(origin_raw.get("batch"), field=f"items[{idx}].origin.batch")
        if origin_batch != batch:
            raise ApplyError("origin.batch must equal plan batch")
        origin_archive = _coerce_optional_str(origin_raw.get("archive_src"), field=f"items[{idx}].origin.archive_src")
        if archive_src is not None and origin_archive is not None and archive_src.name != origin_archive:
            raise ApplyError("origin.archive_src must be basename of archive_src")

        doc_id = _coerce_str(item.get("doc_id"), field=f"items[{idx}].doc_id")
        if not DOC_ID_RE.fullmatch(doc_id):
            raise ApplyError("doc_id must be doc-NNN")
        if doc_id in doc_ids:
            raise ApplyError(f"duplicate doc_id: {doc_id}")
        doc_ids.add(doc_id)

        bundle_id = _coerce_optional_str(item.get("bundle_id"), field=f"items[{idx}].bundle_id")
        if bundle_id is not None and not BUNDLE_ID_RE.fullmatch(bundle_id):
            raise ApplyError("bundle_id must be bundle-NNN")
        role = item.get("role_in_bundle")
        parent = item.get("parent_id")
        attachment_order = item.get("attachment_order")

        if bundle_id is None:
            if role is not None:
                raise ApplyError("bundle fields must be null for non-bundled item")
            if parent is not None:
                raise ApplyError("bundle fields must be null for non-bundled item")
            if attachment_order is not None:
                raise ApplyError("bundle fields must be null for non-bundled item")
            role = None
            parent = None
            attachment_order = None
        else:
            role = _coerce_str(role, field=f"items[{idx}].role_in_bundle")
            if role not in {"head", "attachment"}:
                raise ApplyError("role_in_bundle must be head|attachment")
            if role == "head":
                if parent is not None:
                    raise ApplyError("parent_id must be null for head")
                if attachment_order is not None:
                    raise ApplyError("attachment_order must be null for head")
                parent = None
                attachment_order = None
            else:
                parent = _coerce_str(parent, field=f"items[{idx}].parent_id")
                attachment_order = _coerce_int(
                    attachment_order,
                    field=f"items[{idx}].attachment_order",
                    non_negative=True,
                )
                if attachment_order <= 0:
                    raise ApplyError("attachment_order must be positive")

        items.append(
            {
                "source_path": source_path,
                "grouped_inputs": grouped_inputs,
                "archive_src": archive_src,
                "target_file": target_file,
                "convert_image_to_pdf": convert_image_to_pdf,
                "ocr_artifacts": ocr_artifacts,
                "combined_text_path": combined_text,
                "doc_id": doc_id,
                "title": _coerce_str(item.get("title"), field=f"items[{idx}].title"),
                "type": _coerce_str(item.get("type"), field=f"items[{idx}].type"),
                "date": date_value,
                "source": _coerce_str(item.get("source"), field=f"items[{idx}].source"),
                "origin": {
                    "name": origin_name,
                    "date": origin_date,
                    "received": origin_received,
                    "batch": origin_batch,
                    "archive_src": origin_archive,
                },
                "bundle_id": bundle_id,
                "role_in_bundle": role,
                "parent_id": parent,
                "attachment_order": attachment_order,
            }
        )

    existing_docs = [doc.get("id") for doc in index_payload["documents"] if isinstance(doc, dict)]
    for item in items:
        if item["doc_id"] in existing_docs:
            raise ApplyError(f"doc_id already exists in index: {item['doc_id']}")

    existing_bundle_ids = {bundle.get("id") for bundle in index_payload["bundles"] if isinstance(bundle, dict)}
    plan_bundle_ids = {bundle["id"] for bundle in bundles}

    for item in items:
        if item["bundle_id"] is not None and item["bundle_id"] not in existing_bundle_ids and item["bundle_id"] not in plan_bundle_ids:
            raise ApplyError("items reference unknown bundle_id")

    new_bundle_ids = [
        int(BUNDLE_ID_RE.fullmatch(bundle["id"]).group(1))
        for bundle in bundles
        if bundle["is_new"]
    ]
    if new_bundle_ids:
        expected = list(range(next_bundle_id_start, next_bundle_id_start + len(new_bundle_ids)))
        if sorted(new_bundle_ids) != expected:
            raise ApplyError("new bundle ids must be contiguous")

    by_bundle: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if item["bundle_id"]:
            by_bundle.setdefault(item["bundle_id"], []).append(item)

    for bundle_id, linked_items in by_bundle.items():
        bundle = next((b for b in bundles if b["id"] == bundle_id), None)
        is_new = False
        if bundle is None:
            for existing in index_payload["bundles"]:
                if isinstance(existing, dict) and existing.get("id") == bundle_id:
                    bundle = existing
                    is_new = False
                    break
            if bundle is None:
                raise ApplyError("bundle not found")
            if not isinstance(bundle, dict):
                raise ApplyError("bundle not found")
        else:
            is_new = bool(bundle.get("is_new", False))
        if not is_new:
            existing_bundle = existing_bundles_by_id.get(bundle_id)
            if existing_bundle is None:
                raise ApplyError("bundle not found for validation")
            if existing_bundle.get("main_doc") != bundle["main_doc"]:
                raise ApplyError("bundle main_doc mismatch")
            linked_ids = {item["doc_id"] for item in linked_items}
            plan_members = set(bundle["members"])
            required_members = set(existing_bundle.get("members") or [])
            required_members.update(linked_ids)
            if plan_members != required_members:
                raise ApplyError("bundle members must equal existing members plus new linked docs")

        expected_members = set(bundle["members"])
        heads = [item for item in linked_items if item["role_in_bundle"] == "head"]
        if is_new:
            if len(heads) != 1:
                raise ApplyError("bundle must have exactly one head")
            if heads[0]["doc_id"] != bundle["main_doc"]:
                raise ApplyError("bundle head mismatch")
        else:
            if len(heads) > 1:
                raise ApplyError("bundle must have at most one head")

        attachment_orders: list[int] = []
        for item in linked_items:
            if item["role_in_bundle"] == "attachment":
                order = item["attachment_order"]
                if order is None:
                    raise ApplyError("attachment_order required for attachment")
                attachment_orders.append(order)

        if len(attachment_orders) != len(set(attachment_orders)):
            raise ApplyError("attachment_order must be unique within bundle")

        for item in linked_items:
            if item["doc_id"] not in expected_members:
                raise ApplyError("item not listed in bundle members")
            if item["role_in_bundle"] == "attachment":
                if item["parent_id"] != bundle["main_doc"]:
                    raise ApplyError("attachment must reference bundle main_doc")

    return {
        "batch": batch,
        "source_inbox": source_inbox,
        "work_dir": work_dir,
        "raw_dest": raw_dest,
        "next_id_start": next_id_start,
        "next_bundle_id_start": next_bundle_id_start,
        "raw_only": raw_only,
        "skipped": skipped,
        "cleanup_set": cleanup_set,
        "bundles": bundles,
        "items": items,
    }


def _build_staging(case_root: Path, plan: dict[str, Any], index_payload: dict[str, Any]) -> tuple[Path, list[dict[str, str]], dict[str, Any]]:
    staging_root = case_root / ".vassal" / "tmp" / f"apply-{plan['batch']}"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)

    staged_pairs: list[dict[str, str]] = []
    agg_by_doc: dict[str, dict[str, Any]] = {}

    for raw in plan["raw_only"]:
        staged_source = staging_root / "raw" / raw["raw_dest_name"]
        raw_dest_path = plan["raw_dest"] / raw["raw_dest_name"]
        if not _contains(plan["raw_dest"], raw_dest_path):
            raise ApplyError("invalid raw_dest_name")
        staged_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw["archive_src"], staged_source)
        staged_pairs.append(
            {
                "src": str(staged_source),
                "dst": str(raw_dest_path),
            }
        )

    for item in plan["items"]:
        sources = item["grouped_inputs"] if item["grouped_inputs"] is not None else [item["source_path"]]
        if not sources or sources[0] is None:
            raise ApplyError("source missing")

        raw_bucket = "raw"
        if item["archive_src"] is not None:
            raw_bucket = f"raw/{item['archive_src'].name}"

        for source in sources:
            source_root = plan["source_inbox"] if _contains(plan["source_inbox"], source, allow_equal=False) else plan["work_dir"]
            if not _contains(plan["work_dir"], source, allow_equal=False) and not _contains(plan["source_inbox"], source, allow_equal=False):
                raise ApplyError("source must be inside source_inbox or work_dir")
            resolved_source = _real_path(source)
            resolved_source_root = _real_path(source_root)
            try:
                rel_path = resolved_source.relative_to(resolved_source_root)
            except ValueError:
                raise ApplyError(f"source path escapes source_root: {source}")
            staged_raw = staging_root / raw_bucket / rel_path
            staged_raw.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged_raw)
            staged_dst = plan["raw_dest"] / rel_path
            if not _contains(plan["raw_dest"], staged_dst):
                raise ApplyError("source staging destination escapes raw_dest")
            staged_pairs.append({"src": str(staged_raw), "dst": str(staged_dst)})

        staged_target = staging_root / item["target_file"].relative_to(case_root)
        if item["convert_image_to_pdf"]:
            if item["grouped_inputs"] is None:
                raise ApplyError("convert_image_to_pdf requires grouped_inputs")
            _run_image_to_pdf(item["grouped_inputs"], staged_target)
        else:
            staged_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sources[0], staged_target)
        staged_pairs.append({"src": str(staged_target), "dst": str(item["target_file"])})

        mirror_text, fallback_artifacts = _read_item_text(item, plan["work_dir"])
        artifact_payload = fallback_artifacts if fallback_artifacts else item["ocr_artifacts"]
        aggregate = _agg_ocr_artifacts(artifact_payload)
        agg_by_doc[item["doc_id"]] = aggregate

        quality = classify(
            extraction_method=aggregate["primary"],
            confidence=aggregate["confidence"],
            total_chars=aggregate["total_chars"],
            pages=aggregate["pages"],
        )
        mirror_payload = aggregate.copy()
        mirror_payload["quality"] = quality
        mirror_path = staging_root / ".vassal" / "mirrors" / f"{item['doc_id']}.md"
        mirror_path.parent.mkdir(parents=True, exist_ok=True)

        mirror_body = _build_mirror_text(
            item=item,
            aggregate=mirror_payload,
            case_root=case_root,
            text=mirror_text,
        )
        _safe_write_text(mirror_path, mirror_body)
        staged_pairs.append(
            {
                "src": str(mirror_path),
                "dst": str(case_root / ".vassal" / "mirrors" / f"{item['doc_id']}.md"),
            }
        )

    index_candidate = _build_index_payload(case_root=case_root, plan=plan, index_payload=index_payload, aggregate_by_doc=agg_by_doc)
    _safe_write_yaml(staging_root / "index.yaml.new", index_candidate)

    return staging_root, staged_pairs, agg_by_doc


def _build_index_payload(
    *,
    case_root: Path,
    plan: dict[str, Any],
    index_payload: dict[str, Any],
    aggregate_by_doc: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    documents = [dict(document) for document in index_payload["documents"] if isinstance(document, dict)]
    existing_bundles_by_id = {bundle.get("id"): dict(bundle) for bundle in index_payload["bundles"] if isinstance(bundle, dict)}

    for item in plan["items"]:
        aggregate = aggregate_by_doc[item["doc_id"]]
        quality = classify(
            extraction_method=aggregate["primary"],
            confidence=aggregate["confidence"],
            total_chars=aggregate["total_chars"],
            pages=aggregate["pages"],
        )

        documents.append(
            {
                "id": item["doc_id"],
                "file": item["target_file"].relative_to(case_root).as_posix(),
                "mirror": f".vassal/mirrors/{item['doc_id']}.md",
                "type": item["type"],
                "title": item["title"],
                "date": item["date"],
                "source": item["source"],
                "added": _now(),
                "processed_by": "haiku",
                "origin": {
                    "name": item["origin"]["name"],
                    "date": item["origin"].get("date"),
                    "received": item["origin"]["received"],
                    "batch": item["origin"]["batch"],
                    "archive_src": item["origin"].get("archive_src"),
                },
                "mirror_stale": False,
                "pages": aggregate["pages"],
                "ocr_quality": quality.get("ocr_quality", "ok"),
                "ocr_quality_reason": quality.get("ocr_quality_reason", ""),
                "ocr_reattempted": False,
                "last_verified": _now(),
                "bundle_id": item["bundle_id"],
                "parent_id": item["parent_id"],
                "role_in_bundle": item["role_in_bundle"],
                "attachment_order": item["attachment_order"],
                "needs_manual_review": quality.get("ocr_quality") != "ok",
            }
        )

    added_new_bundles = 0
    for bundle in plan["bundles"]:
        if bundle["id"] not in existing_bundles_by_id:
            if not bundle["is_new"]:
                raise ApplyError(f"bundle {bundle['id']} missing in index")
            if bundle["is_new"]:
                added_new_bundles += 1
                existing_bundles_by_id[bundle["id"]] = {
                    "id": bundle["id"],
                    "title": bundle["title"],
                    "main_doc": bundle["main_doc"],
                    "members": list(bundle["members"]),
                }
        else:
            existing = existing_bundles_by_id[bundle["id"]]
            if not bundle["is_new"]:
                expected = list(existing.get("members") or [])
                for member in bundle["members"]:
                    if member not in expected:
                        expected.append(member)
                existing["members"] = expected

    next_id = index_payload["next_id"] + len(plan["items"])
    next_bundle_id = index_payload["next_bundle_id"]
    if added_new_bundles:
        next_bundle_id = max(next_bundle_id, plan["next_bundle_id_start"] + added_new_bundles)

    payload = {
        "version": index_payload.get("version", 2),
        "last_updated": _now(),
        "documents": documents,
        "bundles": list(existing_bundles_by_id.values()),
        "next_id": next_id,
        "next_bundle_id": next_bundle_id,
    }
    payload.update(index_payload.get("extra", {}))
    return payload


def _replace(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)


def _promote_pairs(state: dict[str, Any], state_path: Path) -> None:
    staged = state.get("staged")
    if not isinstance(staged, list):
        raise ApplyError("state.staged must be list")
    promoted = set(state.get("promoted", []))
    for entry in staged:
        if not isinstance(entry, dict):
            raise ApplyError("state.staged must contain mappings")
        src = Path(entry.get("src", ""))
        dst = Path(entry.get("dst", ""))
        if not src or not dst:
            raise ApplyError("state.staged item missing src/dst")
        if str(dst) in promoted:
            continue
        if dst.exists() and not src.exists():
            promoted.add(str(dst))
            state["promoted"] = sorted(promoted)
            _safe_write_json(state_path, state)
            continue
        if not src.exists():
            raise ApplyError(f"staged source missing: {src}")
        _replace(src, dst)
        promoted.add(str(dst))
        state["promoted"] = sorted(promoted)
        _safe_write_json(state_path, state)


def _promote_index(plan_batch: str, case_root: Path, state: dict[str, Any], state_path: Path) -> None:
    index_staged = Path(state.get("index_staged", f".vassal/tmp/apply-{plan_batch}/index.yaml.new"))
    index_target = Path(state.get("index_target", ".vassal/index.yaml"))
    index_staged = (case_root / index_staged) if not index_staged.is_absolute() else index_staged
    index_target = (case_root / index_target) if not index_target.is_absolute() else index_target

    if not index_staged.exists():
        if index_target.exists():
            return
        raise ApplyError("index staged artifact missing")
    _replace(index_staged, index_target)


def _cleanup_paths(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except Exception as exc:
            errors.append(f"failed to remove {path}: {exc}")
    return errors


def _complete_after_state(
    case_root: Path,
    plan: dict[str, Any],
    plan_path: Path,
    state: dict[str, Any],
    state_path: Path,
) -> dict[str, Any]:
    if state.get("status") not in {"promoting", "done"}:
        raise ApplyError("unexpected state status")

    _promote_pairs(state, state_path)
    _promote_index(plan["batch"], case_root, state, state_path)

    state["status"] = "done"
    state["cleanup_set"] = [str(p) for p in plan["cleanup_set"]]
    _safe_write_json(state_path, state)

    cleanup_errors = _cleanup_paths(plan["cleanup_set"])

    _append_history(
        case_root,
        _history_line(
            plan["batch"],
            len(plan["items"]),
            len({item["bundle_id"] for item in plan["items"] if item["bundle_id"]}),
            len([item for item in plan["items"] if item["date"] is None]),
            plan_path,
        ),
    )

    return _build_result(
        plan=plan,
        case_root=case_root,
        plan_path=plan_path,
        applied=True,
        cleanup_errors=cleanup_errors,
    )


def _build_result(
    *,
    plan: dict[str, Any],
    case_root: Path,
    plan_path: Path,
    applied: bool,
    cleanup_errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "applied": applied,
        "batch": plan["batch"],
        "added_doc_ids": [item["doc_id"] for item in plan["items"]],
        "converted_images": sum(1 for item in plan["items"] if item["convert_image_to_pdf"]),
        "bundle_count": len({item["bundle_id"] for item in plan["items"] if item["bundle_id"]}),
        "orphan_count": sum(1 for item in plan["items"] if item["date"] is None),
        "raw_batch_path": str(plan["raw_dest"]),
        "history_line": _history_line(
            plan["batch"],
            len(plan["items"]),
            len({item["bundle_id"] for item in plan["items"] if item["bundle_id"]}),
            sum(1 for item in plan["items"] if item["date"] is None),
            plan_path,
        ),
        "state_file": f".vassal/plans/{plan['batch']}-apply-state.json",
        "cleanup_errors": cleanup_errors or [],
    }


def _state_path(case_root: Path, batch: str) -> Path:
    return case_root / ".vassal" / "plans" / f"{batch}-apply-state.json"


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _final_cleanup(case_root: Path, batch: str, plan_path: Path, work_dir: Path) -> list[str]:
    errors: list[str] = []

    with contextlib.suppress(Exception):
        shutil.rmtree((case_root / ".vassal" / "tmp" / f"apply-{batch}").resolve())

    try:
        if work_dir.exists():
            shutil.rmtree(work_dir)
    except Exception as exc:
        errors.append(f"failed to remove work_dir {work_dir}: {exc}")

    for suffix in (".md", ".yaml"):
        sibling = plan_path.with_suffix(suffix)
        if suffix == ".yaml" and sibling != plan_path:
            continue
        with contextlib.suppress(FileNotFoundError):
            sibling.unlink()

    return errors


def main() -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args()
    except SystemExit:
        return 1

    try:
        first_arg = Path(args.path).expanduser()
        if args.plan_yaml is None:
            if first_arg.is_dir():
                raise ApplyError("plan-yaml must be provided via --plan-yaml when first argument is a case root")
            if not first_arg.is_file():
                raise ApplyError("plan-yaml must be provided via --plan-yaml when first argument is a case root")
            case_root = _resolve_case_root(str(first_arg.parents[2]))
            plan_path = _plan_yaml_guard(case_root, str(first_arg))
        else:
            case_root = _resolve_case_root(args.path)
            plan_path = _plan_yaml_guard(case_root, args.plan_yaml)

        raw_plan = _load_yaml(plan_path)
        index_payload = _load_index_payload(case_root)
        validated = _validate_plan(case_root, raw_plan, index_payload, force=args.force)

        state_path = _state_path(case_root, validated["batch"])
        existing_state = _load_state(state_path)
        if existing_state is not None:
            existing_state["batch"] = validated["batch"]
            existing_state["index_target"] = str((case_root / ".vassal" / "index.yaml"))
            existing_state["index_staged"] = f".vassal/tmp/apply-{validated['batch']}/index.yaml.new"
            result = _complete_after_state(case_root, validated, plan_path, existing_state, state_path)
            extra_errors = _final_cleanup(case_root, validated["batch"], plan_path, validated["work_dir"])
            if extra_errors:
                result["cleanup_errors"].extend(extra_errors)

            with contextlib.suppress(Exception):
                state_path.unlink(missing_ok=True)
            print(json.dumps(result, ensure_ascii=False))
            return 0

        if args.dry_run:
            result = _build_result(plan=validated, case_root=case_root, plan_path=plan_path, applied=False, cleanup_errors=[])
            print(json.dumps(result, ensure_ascii=False))
            return 0

        try:
            staging_root, staged_pairs, _ = _build_staging(case_root, validated, index_payload)
        except Exception as exc:
            with contextlib.suppress(Exception):
                staging_root = case_root / ".vassal" / "tmp" / f"apply-{validated['batch']}"
                if staging_root.exists():
                    shutil.rmtree(staging_root)
            with contextlib.suppress(Exception):
                work_dir_extracted = case_root / ".vassal" / "work" / validated["batch"] / "extracted"
                shutil.rmtree(work_dir_extracted, ignore_errors=True)
            if isinstance(exc, ApplyError):
                return _fatal(str(exc))
            return _fatal(f"internal error: {exc}")

        state = {
            "status": "promoting",
            "batch": validated["batch"],
            "staged": staged_pairs,
            "promoted": [],
            "index_staged": f".vassal/tmp/apply-{validated['batch']}/index.yaml.new",
            "index_target": ".vassal/index.yaml",
            "cleanup_set": [str(path) for path in validated["cleanup_set"]],
            "plan_yaml": str(plan_path),
        }
        _safe_write_json(state_path, state)

        try:
            result = _complete_after_state(case_root, validated, plan_path, state, state_path)
            extra_errors = _final_cleanup(case_root, validated["batch"], plan_path, validated["work_dir"])
            result["cleanup_errors"].extend(extra_errors)
        except Exception as exc:
            return _fatal(str(exc))

        state_path.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ApplyError as exc:
        return _fatal(str(exc))
    except Exception:
        return _fatal("internal error")


if __name__ == "__main__":
    sys.exit(main())
