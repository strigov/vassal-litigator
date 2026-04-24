"""Unit tests for scripts/apply_intake_plan.py."""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import apply_intake_plan as aip


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _build_case(
    tmp_path: Path,
    *,
    next_id: int = 1,
    next_bundle_id: int = 1,
    documents: list[dict] | None = None,
    bundles: list[dict] | None = None,
) -> Path:
    case_root = tmp_path / "case"
    (case_root / ".vassal" / "plans").mkdir(parents=True, exist_ok=True)
    (case_root / ".vassal" / "work").mkdir(parents=True, exist_ok=True)
    (case_root / ".vassal" / "raw").mkdir(parents=True, exist_ok=True)
    (case_root / "Входящие документы").mkdir(parents=True, exist_ok=True)

    index_payload = {
        "version": 2,
        "last_updated": "2026-04-24T00:00:00",
        "documents": documents or [],
        "bundles": bundles or [],
        "next_id": next_id,
        "next_bundle_id": next_bundle_id,
    }
    _write_yaml(case_root / ".vassal" / "index.yaml", index_payload)
    return case_root


def _write_file(path: Path, content: str = "content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_item(
    *,
    case_root: Path,
    batch: str,
    doc_id: str,
    source_name: str,
    target_name: str,
    source_inbox: Path,
    work_dir: Path,
    source_text: str = "Текст документа",
    origin_name: str | None = None,
    convert_image_to_pdf: bool = False,
    grouped_inputs: list[str] | None = None,
    archive_src: Path | None = None,
    bundle_id: str | None = None,
    role_in_bundle: str | None = None,
    parent_id: str | None = None,
    attachment_order: int | None = None,
) -> dict:
    if grouped_inputs is None:
        source_path = source_inbox / source_name
    else:
        source_path = None

    if source_path is not None:
        _write_file(source_path, source_text)
    extracted = work_dir / f"{Path(source_name).stem}.txt"
    _write_file(extracted, source_text)

    item: dict = {
        "source_path": str(source_path) if source_path is not None else None,
        "grouped_inputs": grouped_inputs,
        "archive_src": str(archive_src) if archive_src is not None else None,
        "ocr_artifacts": [
            {
                "path": str(extracted),
                "extraction_method": "pdf-text",
                "confidence": "high",
                "pages": 1,
                "total_chars": len(source_text),
            }
        ],
        "combined_text_path": str(extracted),
        "doc_id": doc_id,
        "target_file": str(case_root / "Материалы от клиента" / target_name),
        "convert_image_to_pdf": convert_image_to_pdf,
        "title": f"Документ {doc_id}",
        "type": "договор",
        "date": "2026-04-24",
        "source": "client",
        "origin": {
            "name": origin_name or source_name,
            "date": "2026-04-24",
            "received": "2026-04-24",
            "batch": batch,
            "archive_src": archive_src.name if archive_src is not None else None,
        },
        "bundle_id": bundle_id,
        "role_in_bundle": role_in_bundle,
        "parent_id": parent_id,
        "attachment_order": attachment_order,
    }
    return item


def _write_plan(
    case_root: Path,
    *,
    batch: str,
    items: list[dict],
    source_inbox: Path,
    work_dir: Path,
    raw_dest: Path,
    next_id_start: int,
    next_bundle_id_start: int = 1,
    bundles: list[dict] | None = None,
    raw_only: list[dict] | None = None,
    skipped: list[dict] | None = None,
    cleanup_set: list[str] | None = None,
) -> Path:
    plan_path = case_root / ".vassal" / "plans" / f"{batch}.yaml"
    payload = {
        "batch": batch,
        "source_inbox": str(source_inbox),
        "work_dir": str(work_dir),
        "raw_dest": str(raw_dest),
        "next_id_start": next_id_start,
        "next_bundle_id_start": next_bundle_id_start,
        "bundles": bundles or [],
        "items": items,
        "raw_only": raw_only or [],
        "skipped": skipped or [],
        "cleanup_set": cleanup_set or [],
        "already_processed": [],
    }
    _write_yaml(plan_path, payload)
    return plan_path


def _run_main(
    *,
    plan_path: Path,
    case_root: Path,
    dry_run: bool = False,
    legacy: bool = False,
    fail_replace: bool = False,
    force: bool = False,
) -> tuple[int, dict | None]:
    argv = ["apply_intake_plan.py"]
    if legacy:
        argv.append(str(case_root))
        argv.extend(["--plan-yaml", str(plan_path)])
    else:
        argv.append(str(plan_path))

    if dry_run:
        argv.append("--dry-run")
    if force:
        argv.append("--force")

    def _do_run() -> int:
        buf = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            return_code = aip.main()
        output = buf.getvalue().strip()
        if return_code == 0 and output:
            return return_code, json.loads(output)
        if return_code == 0:
            return return_code, None
        return return_code, None

    if fail_replace:
        original_replace = aip._replace

        calls = {"count": 0}

        def _failing_replace(src: Path, dst: Path) -> None:
            if calls["count"] == 0:
                calls["count"] += 1
                raise RuntimeError("simulated promote failure")
            return original_replace(src, dst)

        with patch.object(aip, "_replace", _failing_replace):
            return _do_run()
    return _do_run()


def _load_index(case_root: Path) -> dict:
    return yaml.safe_load((case_root / ".vassal" / "index.yaml").read_text(encoding="utf-8"))


def _base_setup(tmp_path: Path, *, next_id: int = 42, next_bundle_id: int = 3) -> tuple[Path, Path, Path, Path, str]:
    batch = "intake-2026-04-24"
    case_root = _build_case(
        tmp_path,
        next_id=next_id,
        next_bundle_id=next_bundle_id,
    )
    source_inbox = case_root / "Входящие документы"
    work_dir = case_root / ".vassal" / "work" / batch
    raw_dest = case_root / ".vassal" / "raw" / batch
    return case_root, source_inbox, work_dir, raw_dest, batch


# ---------------------------------------------------------------------------
# Путь к плану / guardrails валидации
# ---------------------------------------------------------------------------


def test_plan_yaml_guard_rejects_path_outside_vassal_plans(tmp_path: Path) -> None:
    case_root, *_ = _base_setup(tmp_path)
    outside = tmp_path / "outside.yaml"
    _write_yaml(outside, {"batch": "x"})

    with pytest.raises(aip.ApplyError):
        aip._plan_yaml_guard(case_root, str(outside))


def test_validate_rejects_source_inbox_not_case_root(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=case_root / "неправильный-вход",
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="source_inbox must be exactly"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_work_dir_outside_vassal_work(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    bad_work = case_root / "bad-work"
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=bad_work,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="work_dir"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_source_path_outside_allowed_paths(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    external = tmp_path / "external.pdf"
    _write_file(external, "external")
    item = {
        "source_path": str(external),
        "grouped_inputs": None,
        "archive_src": None,
        "ocr_artifacts": [],
        "combined_text_path": None,
        "doc_id": "doc-042",
        "target_file": str(case_root / "Материалы от клиента" / "2026-01-01 Договор.pdf"),
        "convert_image_to_pdf": False,
        "title": "Документ doc-042",
        "type": "договор",
        "date": "2026-04-24",
        "source": "client",
        "origin": {
            "name": "external.pdf",
            "date": "2026-04-24",
            "received": "2026-04-24",
            "batch": batch,
            "archive_src": None,
        },
        "bundle_id": None,
        "role_in_bundle": None,
        "parent_id": None,
        "attachment_order": None,
    }

    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="source_path"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_cleanup_set_outside_inbox(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
        cleanup_set=[str(case_root / "outside" / "file.pdf")],
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="cleanup_set entries"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_raw_only_bad_raw_dest_name(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    for raw_dest_name in ["../pack.zip", "/tmp/pack.zip", "..", "nested/path.zip"]:
        raw_file = source_inbox / f"pack_{raw_dest_name.replace('/', '_').replace('..', 'up').replace('\\\\', 'back')}.zip"
        _write_file(raw_file, "zip")
        plan = _write_plan(
            case_root=case_root,
            batch=batch,
            items=[item],
            source_inbox=source_inbox,
            work_dir=work_dir,
            raw_dest=raw_dest,
            next_id_start=42,
            raw_only=[{"archive_src": str(raw_file), "raw_dest_name": raw_dest_name}],
        )
        raw_plan = aip._load_yaml(plan)
        index_payload = aip._load_index_payload(case_root)
        with pytest.raises(aip.ApplyError, match="raw_dest_name"):
            aip._validate_plan(case_root, raw_plan, index_payload)


@pytest.mark.parametrize(
    "batch",
    ["../evil", "/absolute", "a/b"],
)
def test_validate_rejects_dangerous_batch(tmp_path: Path, batch: str) -> None:
    case_root, source_inbox, work_dir, raw_dest, safe_batch = _base_setup(tmp_path)
    plan = _write_plan(
        case_root=case_root,
        batch=safe_batch,
        items=[],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    raw_plan["batch"] = batch
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="batch must be safe"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_duplicate_target_file_in_items(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item1 = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc1.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    item2 = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-043",
        source_name="doc2.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item1, item2],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="duplicate target_file"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_grouped_inputs_without_convert_image_to_pdf(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    first = source_inbox / "a.jpg"
    second = source_inbox / "b.jpg"
    _write_file(first, "x")
    _write_file(second, "y")
    _write_file(work_dir / "a.txt", "x")
    _write_file(work_dir / "b.txt", "y")
    extracted_a = work_dir / "a.txt"
    extracted_b = work_dir / "b.txt"
    item = {
        "source_path": None,
        "grouped_inputs": [str(first), str(second)],
        "archive_src": None,
        "ocr_artifacts": [
            {
                "path": str(extracted_a),
                "extraction_method": "ocr",
                "confidence": "high",
                "pages": 1,
                "total_chars": 10,
            },
            {
                "path": str(extracted_b),
                "extraction_method": "ocr",
                "confidence": "high",
                "pages": 1,
                "total_chars": 10,
            },
        ],
        "combined_text_path": str(extracted_a),
        "doc_id": "doc-042",
        "target_file": str(case_root / "Материалы от клиента" / "2026-01-01 Склейка.pdf"),
        "convert_image_to_pdf": False,
        "title": "Документ doc-042",
        "type": "договор",
        "date": "2026-04-24",
        "source": "client",
        "origin": {
            "name": "a.jpg",
            "date": "2026-04-24",
            "received": "2026-04-24",
            "batch": batch,
            "archive_src": None,
        },
        "bundle_id": None,
        "role_in_bundle": None,
        "parent_id": None,
        "attachment_order": None,
    }
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="grouped_inputs requires convert_image_to_pdf"):
        aip._validate_plan(case_root, raw_plan, index_payload)


def test_validate_rejects_plan_outside_vassal_plans_via_main(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    outside = case_root / "not-a-plan.yaml"
    _write_yaml(
        outside,
        {
            "batch": batch,
            "source_inbox": str(source_inbox),
            "work_dir": str(work_dir),
            "raw_dest": str(raw_dest),
            "next_id_start": 1,
            "bundles": [],
            "items": [],
            "raw_only": [],
            "skipped": [],
            "cleanup_set": [],
            "already_processed": [],
        },
    )

    code, output = _run_main(plan_path=outside, case_root=case_root, legacy=True)
    assert code == 1
    assert output is None
    assert not (case_root / ".vassal" / "plans" / f"{batch}-apply-state.json").exists()


def test_validate_rejects_bundle_id_unknown_for_item(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
        bundle_id="bundle-007",
        role_in_bundle="head",
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="unknown bundle_id"):
        aip._validate_plan(case_root, raw_plan, index_payload)


# ---------------------------------------------------------------------------
# Stage + promote + восстановление
# ---------------------------------------------------------------------------


def test_build_staging_keeps_targets_outside_case_until_promotion(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    raw_file = source_inbox / "pack.zip"
    _write_file(raw_file, "zip")
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
        raw_only=[{"archive_src": str(raw_file), "raw_dest_name": "pack.zip"}],
    )
    validated = aip._validate_plan(case_root, aip._load_yaml(plan), aip._load_index_payload(case_root))
    staging_root, staged_pairs, _agg = aip._build_staging(case_root, validated, aip._load_index_payload(case_root))

    assert staging_root.exists()
    assert (staging_root / "index.yaml.new").exists()
    assert not (case_root / "Материалы от клиента" / "2026-01-01 Договор.pdf").exists()
    assert all(Path(pair["src"]).is_relative_to(staging_root) for pair in staged_pairs)
    assert (case_root / "Материалы от клиента" / "2026-01-01 Договор.pdf") in [Path(pair["dst"]) for pair in staged_pairs]


def test_build_staging_preserves_relative_raw_source_paths(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path)
    item1 = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="folder_a/doc.pdf",
        target_name="2026-01-01 Документ A.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    item2 = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-043",
        source_name="folder_b/doc.pdf",
        target_name="2026-01-02 Документ B.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    validated = aip._validate_plan(
        case_root,
        aip._load_yaml(_write_plan(
            case_root=case_root,
            batch=batch,
            items=[item1, item2],
            source_inbox=source_inbox,
            work_dir=work_dir,
            raw_dest=raw_dest,
            next_id_start=42,
        )),
        aip._load_index_payload(case_root),
    )
    staging_root, staged_pairs, _agg = aip._build_staging(case_root, validated, aip._load_index_payload(case_root))

    raw_staged = [pair for pair in staged_pairs if pair["src"].startswith(str(staging_root / "raw"))]
    assert len(raw_staged) == 2

    dsts = {Path(pair["dst"]) for pair in raw_staged}
    assert len(dsts) == 2
    assert (raw_dest / "folder_a" / "doc.pdf") in dsts
    assert (raw_dest / "folder_b" / "doc.pdf") in dsts
    assert (staging_root / "raw" / "folder_a" / "doc.pdf").exists()
    assert (staging_root / "raw" / "folder_b" / "doc.pdf").exists()


def test_dry_run_does_not_mutate_case_state(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=10)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-010",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=10,
        cleanup_set=[str(source_inbox / "doc.pdf")],
    )
    code, output = _run_main(plan_path=plan, case_root=case_root, dry_run=True)
    assert code == 0
    assert output is not None
    assert output["applied"] is False
    assert not (case_root / "Материалы от клиента" / "2026-01-01 Договор.pdf").exists()
    assert not (case_root / ".vassal" / "plans" / "intake-2026-04-24-apply-state.json").exists()
    assert _load_index(case_root)["next_id"] == 10


def test_apply_updates_index_and_history_line(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=5)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-005",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=5,
    )
    code, output = _run_main(plan_path=plan, case_root=case_root)
    assert code == 0
    assert output is not None and output["applied"] is True

    updated = _load_index(case_root)
    assert updated["next_id"] == 6
    assert updated["documents"][-1]["id"] == "doc-005"
    assert updated["documents"][-1]["origin"]["batch"] == batch
    assert updated["documents"][-1]["origin"]["archive_src"] is None

    history = (case_root / ".vassal" / "history.md").read_text(encoding="utf-8")
    assert re.search(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} intake apply: batch=intake-2026-04-24, ", history, re.M)
    assert "план: .vassal/plans/intake-2026-04-24.md" in history


def test_apply_recovery_after_partial_promote_failure(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=7)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-007",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=7,
    )

    # one replace fails -> state должен остаться promoting
    fail_code, _ = _run_main(plan_path=plan, case_root=case_root, fail_replace=True)
    assert fail_code == 1
    state_path = case_root / ".vassal" / "plans" / f"{batch}-apply-state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "promoting"

    # повторный запуск завершает по state в idempotent-режиме
    ok_code, output = _run_main(plan_path=plan, case_root=case_root)
    assert ok_code == 0
    assert output is not None
    assert output["applied"] is True
    assert not state_path.exists()
    assert (case_root / "Материалы от клиента" / "2026-01-01 Договор.pdf").exists()


def test_apply_indexes_bundle_and_origin_fields(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=3, next_bundle_id=3)
    head = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-003",
        source_name="head.pdf",
        target_name="2026-01-01 Переписка.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
        bundle_id="bundle-003",
        role_in_bundle="head",
    )
    attach = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-004",
        source_name="attach.pdf",
        target_name="2026-01-02 Вложение.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
        bundle_id="bundle-003",
        role_in_bundle="attachment",
        parent_id="doc-003",
        attachment_order=1,
    )
    bundle = {
        "id": "bundle-003",
        "is_new": True,
        "title": "Переписка",
        "main_doc": "doc-003",
        "members": ["doc-003", "doc-004"],
    }
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[head, attach],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=3,
        next_bundle_id_start=3,
        bundles=[bundle],
    )

    code, output = _run_main(plan_path=plan, case_root=case_root)
    assert code == 0
    assert output is not None
    assert output["bundle_count"] == 1

    updated = _load_index(case_root)
    assert updated["next_bundle_id"] == 4
    assert len(updated["bundles"]) == 1
    bundle_record = updated["bundles"][0]
    assert bundle_record["id"] == "bundle-003"
    assert bundle_record["main_doc"] == "doc-003"
    assert bundle_record["members"] == ["doc-003", "doc-004"]

    by_id = {doc["id"]: doc for doc in updated["documents"]}
    assert by_id["doc-004"]["bundle_id"] == "bundle-003"
    assert by_id["doc-004"]["parent_id"] == "doc-003"
    assert by_id["doc-004"]["attachment_order"] == 1


def test_apply_merges_existing_bundle_and_keeps_next_bundle_id(tmp_path: Path) -> None:
    case_root = _build_case(
        tmp_path,
        next_id=2,
        next_bundle_id=2,
        documents=[
            {
                "id": "doc-001",
                "file": "Материалы от клиента/existing.pdf",
                "mirror": ".vassal/mirrors/doc-001.md",
                "type": "переписка",
                "title": "Старый документ",
                "date": "2026-01-01",
                "source": "client",
                "added": "2026-01-01",
                "processed_by": "haiku",
                "origin": {
                    "name": "existing.pdf",
                    "date": "2026-01-01",
                    "received": "2026-01-01",
                    "batch": "intake-prev",
                    "archive_src": None,
                },
                "mirror_stale": False,
                "pages": 1,
                "ocr_quality": "ok",
                "ocr_quality_reason": "",
                "ocr_reattempted": False,
                "last_verified": "2026-01-01",
                "bundle_id": "bundle-001",
                "parent_id": None,
                "role_in_bundle": "head",
                "attachment_order": None,
                "needs_manual_review": False,
            }
        ],
        bundles=[
            {
                "id": "bundle-001",
                "title": "Исходная переписка",
                "main_doc": "doc-001",
                "members": ["doc-001"],
            }
        ],
    )
    source_inbox = case_root / "Входящие документы"
    work_dir = case_root / ".vassal" / "work" / "intake-2026-04-24"
    raw_dest = case_root / ".vassal" / "raw" / "intake-2026-04-24"
    batch = "intake-2026-04-24"

    attachment = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-002",
        source_name="attach.pdf",
        target_name="2026-01-03 Вложение.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
        bundle_id="bundle-001",
        role_in_bundle="attachment",
        parent_id="doc-001",
        attachment_order=1,
    )
    bundle = {
        "id": "bundle-001",
        "is_new": False,
        "title": "Исходная переписка",
        "main_doc": "doc-001",
        "members": ["doc-001", "doc-002"],
    }
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[attachment],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=2,
        next_bundle_id_start=2,
        bundles=[bundle],
    )

    code, output = _run_main(plan_path=plan, case_root=case_root, force=True)
    assert code == 0
    assert output is not None
    assert output["bundle_count"] == 1

    updated = _load_index(case_root)
    assert updated["next_bundle_id"] == 2
    updated_bundle = next(b for b in updated["bundles"] if b["id"] == "bundle-001")
    assert updated_bundle["members"] == ["doc-001", "doc-002"]
    assert updated_bundle["main_doc"] == "doc-001"


def test_apply_removes_cleanup_set_only_on_success(tmp_path: Path) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=11)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-011",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    cleanup_file = source_inbox / "doc.pdf"
    source_file = source_inbox / "doc.pdf"
    assert source_file.exists()
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=11,
        cleanup_set=[str(cleanup_file)],
    )

    code, output = _run_main(plan_path=plan, case_root=case_root)
    assert code == 0
    assert output is not None
    assert output["applied"] is True
    assert not cleanup_file.exists()


def test_build_failure_rolls_back_staging_and_skips_state_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=15)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-015",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=15,
    )

    def _fail(*_args: object, **_kwargs: object) -> dict:
        raise aip.ApplyError("simulated index payload build failure")

    monkeypatch.setattr(aip, "_build_index_payload", _fail)

    code, output = _run_main(plan_path=plan, case_root=case_root)
    assert code == 1
    assert output is None
    staging_root = case_root / ".vassal" / "tmp" / f"apply-{batch}"
    assert not staging_root.exists()
    assert not (case_root / ".vassal" / "plans" / f"{batch}-apply-state.json").exists()
    assert source_inbox.joinpath("doc.pdf").exists()
    assert not (case_root / "Материалы от клиента" / "2026-01-01 Договор.pdf").exists()


def test_build_failure_cleans_staging_on_non_applyerror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case_root, source_inbox, work_dir, raw_dest, batch = _base_setup(tmp_path, next_id=16)
    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-016",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=16,
    )

    original_copy2 = aip.shutil.copy2

    def _failing_copy2(*args: object, **_kwargs: object) -> object:
        raise OSError("simulated copy failure")

    monkeypatch.setattr(aip.shutil, "copy2", _failing_copy2)

    code, output = _run_main(plan_path=plan, case_root=case_root)
    assert code == 1
    assert output is None
    staging_root = case_root / ".vassal" / "tmp" / f"apply-{batch}"
    assert not staging_root.exists()
    assert not (case_root / ".vassal" / "plans" / f"{batch}-apply-state.json").exists()


# ---------------------------------------------------------------------------
# Проверка конфликта target_file с существующим индексом
# ---------------------------------------------------------------------------


def test_validate_rejects_target_file_already_in_index(tmp_path: Path) -> None:
    existing_file = "Материалы от клиента/2026-01-01 Договор.pdf"
    case_root = _build_case(
        tmp_path,
        next_id=42,
        documents=[
            {
                "id": "doc-001",
                "file": existing_file,
                "mirror": ".vassal/mirrors/doc-001.md",
                "type": "договор",
                "title": "Существующий документ",
                "date": "2026-01-01",
                "source": "client",
                "added": "2026-01-01",
                "processed_by": "haiku",
                "origin": {
                    "name": "existing.pdf",
                    "date": "2026-01-01",
                    "received": "2026-01-01",
                    "batch": "intake-prev",
                    "archive_src": None,
                },
                "mirror_stale": False,
                "pages": 1,
                "ocr_quality": "ok",
                "ocr_quality_reason": "",
                "ocr_reattempted": False,
                "last_verified": "2026-01-01",
                "bundle_id": None,
                "parent_id": None,
                "role_in_bundle": None,
                "attachment_order": None,
                "needs_manual_review": False,
            }
        ],
    )
    source_inbox = case_root / "Входящие документы"
    work_dir = case_root / ".vassal" / "work" / "intake-2026-04-24"
    raw_dest = case_root / ".vassal" / "raw" / "intake-2026-04-24"
    batch = "intake-2026-04-24"

    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    with pytest.raises(aip.ApplyError, match="target_file already in index"):
        aip._validate_plan(case_root, raw_plan, index_payload, force=False)


def test_validate_allows_target_file_already_in_index_with_force(tmp_path: Path) -> None:
    existing_file = "Материалы от клиента/2026-01-01 Договор.pdf"
    case_root = _build_case(
        tmp_path,
        next_id=42,
        documents=[
            {
                "id": "doc-001",
                "file": existing_file,
                "mirror": ".vassal/mirrors/doc-001.md",
                "type": "договор",
                "title": "Существующий документ",
                "date": "2026-01-01",
                "source": "client",
                "added": "2026-01-01",
                "processed_by": "haiku",
                "origin": {
                    "name": "existing.pdf",
                    "date": "2026-01-01",
                    "received": "2026-01-01",
                    "batch": "intake-prev",
                    "archive_src": None,
                },
                "mirror_stale": False,
                "pages": 1,
                "ocr_quality": "ok",
                "ocr_quality_reason": "",
                "ocr_reattempted": False,
                "last_verified": "2026-01-01",
                "bundle_id": None,
                "parent_id": None,
                "role_in_bundle": None,
                "attachment_order": None,
                "needs_manual_review": False,
            }
        ],
    )
    source_inbox = case_root / "Входящие документы"
    work_dir = case_root / ".vassal" / "work" / "intake-2026-04-24"
    raw_dest = case_root / ".vassal" / "raw" / "intake-2026-04-24"
    batch = "intake-2026-04-24"

    item = _make_item(
        case_root=case_root,
        batch=batch,
        doc_id="doc-042",
        source_name="doc.pdf",
        target_name="2026-01-01 Договор.pdf",
        source_inbox=source_inbox,
        work_dir=work_dir,
    )
    plan = _write_plan(
        case_root=case_root,
        batch=batch,
        items=[item],
        source_inbox=source_inbox,
        work_dir=work_dir,
        raw_dest=raw_dest,
        next_id_start=42,
    )
    raw_plan = aip._load_yaml(plan)
    index_payload = aip._load_index_payload(case_root)
    # Should not raise
    result = aip._validate_plan(case_root, raw_plan, index_payload, force=True)
    assert result is not None
