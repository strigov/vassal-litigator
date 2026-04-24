#!/usr/bin/env python3
"""
validate_opus_output.py — единый валидатор OUTPUT Opus-субагентов для контрактов 3.1a/3.1b/3.1c.

Использование:
    python3 validate_opus_output.py (--input-file <path> | --stdin) \
        --contract {3.1a,3.1b,3.1c} --skill <skill-name>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
READY_FOR_DOCX_RE = re.compile(r"^READY_FOR_DOCX:\s*(processual|analytical|letter)\s*$", re.IGNORECASE)
MOTION_RE = re.compile(r"^##\s*Ходатайство\s+(\d+):\s*(.+)$", re.MULTILINE)
MERMAID_RE = re.compile(r"```mermaid\b.*?```", re.DOTALL | re.IGNORECASE)

DOC_TYPE_EXPECTATIONS = {
    "legal-review": "analytical",
    "build-position": "analytical",
    "appeal": "processual",
    "cassation": "processual",
    "draft-judgment": "processual",
}

ALLOWED_SECTIONS_3_1A = {
    "legal-review": {
        "Квалификация",
        "Схема сторон",
        "Анализ",
        "Выводы",
    },
    "build-position": {
        "Фабула",
        "Квалификация",
        "Доказательства",
        "Схема сторон",
        "Риски",
        "Стратегия",
    },
    "appeal": {
        "Обжалуемый акт",
        "Основания",
        "Доводы",
        "Требования",
    },
    "cassation": {
        "Обжалуемый акт",
        "Существенные нарушения",
        "Доводы",
        "Требования",
    },
    "draft-judgment": {
        "Установил",
        "Оценка доказательств",
        "Правовая квалификация",
        "Постановил",
    },
}

ANALYZE_HEARING_RECOMMENDED_SECTIONS = {
    "Речевые паттерны",
    "Тактика оппонента",
    "Реакции суда",
    "Выводы",
    "Следующие шаги",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Opus OUTPUT contract format for legal skills."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-file", dest="input_file", help="Путь к markdown OUTPUT")
    source.add_argument(
        "--stdin",
        action="store_true",
        help="Читать markdown OUTPUT из stdin",
    )
    parser.add_argument(
        "--contract",
        required=True,
        choices=("3.1a", "3.1b", "3.1c"),
        help="Контракт Opus-ветки",
    )
    parser.add_argument(
        "--skill",
        required=True,
        help="Название скилла, для которого выполняется валидация",
    )
    return parser


def _read_input(input_file: str | None, use_stdin: bool) -> str:
    if use_stdin:
        return sys.stdin.read()
    path = Path(input_file or "")
    if not path.exists():
        print(f"input file not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    return path.read_text(encoding="utf-8")


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    if not matches:
        return sections
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((title, text[start:end]))
    return sections


def _title_from_sections(sections: list[tuple[str, str]]) -> str:
    if sections:
        return sections[0][0]
    return ""


def _ready_line_errors(non_empty_lines: list[str]) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    matches = []
    for line_no, line in enumerate(non_empty_lines, start=1):
        m = READY_FOR_DOCX_RE.fullmatch(line.strip())
        if m:
            matches.append((line_no, m.group(0), m.group(1).lower()))

    if not matches:
        return None, ["markdown missing READY_FOR_DOCX marker"]

    if len(matches) != 1:
        return None, [f"expected exactly 1 READY_FOR_DOCX marker, found {len(matches)}"]

    line_no, full_line, doc_type = matches[0]
    last_line_no = len(non_empty_lines)
    if line_no != last_line_no:
        return None, ["READY_FOR_DOCX must be the last non-empty line"]

    # Нормализация для downstream:
    marker = full_line.strip().split(":", 1)[1].strip().lower()
    return marker, errors


def _validate_sections_allowed(
    sections: list[tuple[str, str]],
    allowed: set[str],
    required: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    titles = {title for title, _ in sections}
    for title in titles:
        if title not in allowed:
            errors.append(f"disallowed top-level section: {title}")
    if required:
        missing = required - titles
        for missing_title in sorted(missing):
            errors.append(f"missing required section: {missing_title}")
    return errors


def _validate_ready_and_body_len(text: str) -> tuple[bool, list[str], str | None]:
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    if not non_empty_lines:
        return False, ["markdown is empty"], None
    doc_type, ready_errors = _ready_line_errors(non_empty_lines)
    return (False, ready_errors, None) if ready_errors else (True, [], doc_type)


def _validate_3_1a(text: str, skill: str) -> tuple[bool, list[str], dict]:
    valid = True
    errors: list[str] = []

    body_ok, ready_errors, doc_type = _validate_ready_and_body_len(text)
    if not body_ok:
        valid = False
        errors.extend(ready_errors)
    else:
        doc_type = doc_type  # for mypy clarity

    sections = _split_sections(text)
    title = _title_from_sections(sections)

    allowed = ALLOWED_SECTIONS_3_1A.get(skill)
    if allowed is not None:
        required = {"Схема сторон"} if skill in {"legal-review", "build-position"} else set()
        errors.extend(_validate_sections_allowed(sections, allowed, required))

    if skill in {"legal-review", "build-position"}:
        scheme_sections = [content for name, content in sections if name == "Схема сторон"]
        if not scheme_sections:
            errors.append("missing required section: Схема сторон")
        elif "```mermaid" not in "\n".join(scheme_sections):
            errors.append("Схема сторон section must contain mermaid block")

    expected_doc_type = DOC_TYPE_EXPECTATIONS.get(skill)
    if expected_doc_type and doc_type is not None and doc_type != expected_doc_type:
        errors.append(
            f"doc_type mismatch: expected {expected_doc_type} for skill {skill}, got {doc_type}"
        )

    parsed = {
        "title": title,
        "doc_type": doc_type,
        "body_len_chars": len(text),
    }

    valid = valid and not errors
    return valid, errors, parsed


def _validate_motion_blocks(text: str) -> list[tuple[int, str, str]]:
    matches = list(MOTION_RE.finditer(text))
    if not matches:
        return []

    sections = _split_sections(text)
    has_notes = any(title == "Заметки" for title, _ in sections)
    if not has_notes:
        return [("0", "", "")]

    segments = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment_text = text[start:end]
        segment_lines = [line for line in segment_text.splitlines() if line.strip()]
        ready_lines = [
            READY_FOR_DOCX_RE.fullmatch(line.strip())
            for line in segment_lines
            if READY_FOR_DOCX_RE.fullmatch(line.strip()) is not None
        ]
        if len(ready_lines) != 1:
            return [("0", "", "")]

        if segment_lines[-1].strip().lower() != "ready_for_docx: processual":
            return [("0", "", "")]

        n = int(match.group(1))
        title = match.group(2).strip()
        segments.append((n, title, segment_text))
    return segments


def _validate_3_1b(text: str, skill: str) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    non_empty = [line for line in text.splitlines() if line.strip()]
    if not non_empty:
        errors.append("markdown is empty")

    all_ready_lines = [
        line.strip().lower() for line in text.splitlines() if READY_FOR_DOCX_RE.fullmatch(line.strip())
    ]

    sections = _split_sections(text)
    if not sections or all(title != "Заметки" for title, _ in sections):
        errors.append("missing required section: Заметки")

    motion_sections = list(MOTION_RE.finditer(text))
    if not motion_sections:
        errors.append("missing required section: Ходатайство N")
    else:
        for match in motion_sections:
            if int(match.group(1)) < 1:
                errors.append("motion index must be >= 1")
                break

    parsed_segments: list[dict] = []
    if motion_sections:
        for index, match in enumerate(motion_sections):
            start = match.end()
            end = motion_sections[index + 1].start() if index + 1 < len(motion_sections) else len(text)
            segment_body = text[start:end]
            segment_lines = [line for line in segment_body.splitlines() if line.strip()]
            ready_lines = [
                line.strip().lower()
                for line in segment_lines
                if READY_FOR_DOCX_RE.fullmatch(line.strip())
            ]
            if len(ready_lines) != 1:
                errors.append(
                    "each Ходатайство segment must have exactly one READY_FOR_DOCX: processual line"
                )
                break
            if segment_lines[-1].strip().lower() != "ready_for_docx: processual":
                errors.append(
                    "READY_FOR_DOCX: processual must be the last non-empty line in each segment"
                )
                break
            parsed_segments.append(
                {
                    "index": int(match.group(1)),
                    "title": match.group(2).strip(),
                    "doc_type": "processual",
                }
            )

        if len(all_ready_lines) != len(parsed_segments):
            errors.append("found READY_FOR_DOCX lines count mismatch with motion segments")

    parsed = {
        "title": _title_from_sections(sections),
        "doc_type": None,
        "body_len_chars": len(text),
        "segments": parsed_segments,
    }
    valid = not errors and bool(motion_sections) and bool(parsed_segments)
    return valid, errors, parsed


def _extract_section_content(sections: list[tuple[str, str]], target: str) -> list[str]:
    for title, content in sections:
        if title == target:
            return content.splitlines()
    return []


def _normalize_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _parse_timeline_table(lines: list[str]) -> tuple[list[tuple[str, str, str]], list[str]]:
    errors: list[str] = []
    header_reached = False
    separator_allowed = False
    rows: list[tuple[str, str, str]] = []

    for line in lines:
        if not line.strip():
            if not header_reached:
                continue
            # Пропускаем пустые строки после таблицы:
            if rows:
                break
            continue

        cells = _normalize_table_row(line)
        if not cells:
            continue

        if not header_reached:
            if [c.lower() for c in cells] == ["дата", "источник", "событие"]:
                header_reached = True
            continue

        if all(set(cell.replace("-", "")) <= {" "} for cell in cells) and separator_allowed is False:
            separator_allowed = True
            continue

        if separator_allowed:
            if len(cells) != 3:
                errors.append("timeline table must contain exactly 3 columns")
                return [], errors
            if not all(cells):
                errors.append("timeline table row has empty cell")
                return [], errors
            rows.append((cells[0], cells[1], cells[2]))
            continue

    if not header_reached:
        errors.append("missing section table header: Дата | Источник | Событие")
    elif not rows:
        errors.append("timeline table must contain at least one data row")

    return rows, errors


def _validate_3_1c(text: str, skill: str) -> tuple[bool, list[str], dict]:
    non_empty = [line for line in text.splitlines() if line.strip()]
    errors: list[str] = []
    if not non_empty:
        errors.append("markdown is empty")

    if any(READY_FOR_DOCX_RE.fullmatch(line.strip()) for line in non_empty):
        errors.append("READY_FOR_DOCX is not allowed for 3.1c")

    sections = _split_sections(text)
    if skill == "timeline":
        if not any(title == "События" for title, _ in sections):
            errors.append("missing required section: События")
        if not any("```mermaid" in block.group(0) for block in MERMAID_RE.finditer(text)):
            errors.append("missing mermaid block")
        else:
            found_gantt = False
            for match in MERMAID_RE.finditer(text):
                if "gantt" in match.group(0).lower():
                    found_gantt = True
                    break
            if not found_gantt:
                errors.append("mermaid block is missing 'gantt'")

        rows, table_errors = _parse_timeline_table(_extract_section_content(sections, "События"))
        errors.extend(table_errors)
        if rows:
            for row in rows:
                if not all(row):
                    errors.append("timeline table row has empty value")
                    break
    elif skill == "analyze-hearing":
        if not any(title == "Ход заседания" for title, _ in sections):
            errors.append("missing required section: Ход заседания")
        if not any(title in ANALYZE_HEARING_RECOMMENDED_SECTIONS for title, _ in sections):
            errors.append(
                "analyze-hearing must contain at least one recommended section: "
                "Речевые паттерны | Тактика оппонента | Реакции суда | Выводы | Следующие шаги"
            )
    title = _title_from_sections(sections)

    parsed = {
        "title": title,
        "doc_type": None,
        "body_len_chars": len(text),
    }
    return (not errors), errors, parsed


def _build_result(contract: str, skill: str, valid: bool, errors: list[str], parsed: dict) -> dict:
    return {
        "valid": valid,
        "contract": contract,
        "skill": skill,
        "errors": errors,
        "warnings": [],
        "parsed": parsed,
    }


def main() -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        return 1

    try:
        text = _read_input(args.input_file, args.stdin)
    except SystemExit as exc:
        return exc.code

    if args.contract == "3.1a":
        valid, errors, parsed = _validate_3_1a(text, args.skill)
    elif args.contract == "3.1b":
        valid, errors, parsed = _validate_3_1b(text, args.skill)
    else:
        valid, errors, parsed = _validate_3_1c(text, args.skill)

    print(json.dumps(_build_result(args.contract, args.skill, valid, errors, parsed), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
