import json
import subprocess
from pathlib import Path


def _script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "validate_opus_output.py"


def _fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "opus_outputs" / name


def _run_validator(*, contract: str, skill: str, stdin_text: str | None = None, input_file: Path | None = None):
    args = [
        "python3",
        str(_script_path()),
        "--contract",
        contract,
        "--skill",
        skill,
    ]
    if input_file is None:
        args.append("--stdin")
    else:
        args.extend(["--input-file", str(input_file)])

    result = subprocess.run(args, input=stdin_text, text=True, capture_output=True)
    return result


def _load_fixture(name: str) -> str:
    return _fixture_path(name).read_text(encoding="utf-8")


def _parse_result(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, f"CLI failed: {result.stderr!r}"
    return json.loads(result.stdout)


def test_3_1a_valid_contract_with_legal_review():
    result = _run_validator(contract="3.1a", skill="legal-review", stdin_text=_load_fixture("legal_review_valid.md"))
    data = _parse_result(result)

    assert data["valid"] is True
    assert data["contract"] == "3.1a"
    assert data["parsed"]["doc_type"] == "analytical"
    assert data["errors"] == []


def test_3_1a_invalid_when_ready_line_missing():
    result = _run_validator(contract="3.1a", skill="legal-review", stdin_text=_load_fixture("legal_review_no_ready.md"))
    data = _parse_result(result)

    assert data["valid"] is False
    assert data["parsed"]["doc_type"] is None
    assert any("READY_FOR_DOCX" in error for error in data["errors"])


def test_3_1a_invalid_when_doc_type_mismatch():
    text = (
        "## Квалификация\nКороткий текст.\n\n"
        "## Схема сторон\n```mermaid\ngraph TD\nA-->B\n```\n\n"
        "## Анализ\n...\n\n"
        "## Выводы\n...\n"
        "READY_FOR_DOCX: processual\n"
    )
    result = _run_validator(contract="3.1a", skill="legal-review", stdin_text=text)
    data = _parse_result(result)

    assert data["valid"] is False
    assert any("doc_type mismatch" in error for error in data["errors"])


def test_3_1b_valid_prepare_hearing_with_three_segments_via_stdin():
    result = _run_validator(
        contract="3.1b",
        skill="prepare-hearing",
        stdin_text=_load_fixture("prepare_hearing_3_segments.md"),
    )
    data = _parse_result(result)

    assert data["valid"] is True
    segments = data["parsed"]["segments"]
    assert isinstance(segments, list)
    assert len(segments) == 3
    assert all(item["doc_type"] == "processual" for item in segments)
    assert data["parsed"]["title"] == "Заметки"


def test_3_1b_invalid_when_segment_missing_ready_marker():
    result = _run_validator(
        contract="3.1b",
        skill="prepare-hearing",
        stdin_text=_load_fixture("prepare_hearing_bad_segment.md"),
    )
    data = _parse_result(result)

    assert data["valid"] is False
    assert any("READY_FOR_DOCX" in error for error in data["errors"])


def test_3_1c_timeline_valid_from_input_file():
    result = _run_validator(
        contract="3.1c",
        skill="timeline",
        input_file=_fixture_path("timeline_valid.md"),
    )
    data = _parse_result(result)

    assert data["valid"] is True
    assert data["parsed"]["doc_type"] is None


def test_3_1c_timeline_invalid_without_mermaid():
    result = _run_validator(
        contract="3.1c",
        skill="timeline",
        input_file=_fixture_path("timeline_no_mermaid.md"),
    )
    data = _parse_result(result)

    assert data["valid"] is False
    assert any("mermaid" in error.lower() for error in data["errors"])


def test_3_1c_analyze_hearing_positive_with_required_sections():
    result = _run_validator(
        contract="3.1c",
        skill="analyze-hearing",
        stdin_text=_load_fixture("analyze_hearing_valid.md"),
    )
    data = _parse_result(result)

    assert data["valid"] is True
    assert data["parsed"]["title"] == "Ход заседания"
    assert data["errors"] == []


def test_stdin_and_input_file_are_mutually_exclusive():
    result = subprocess.run(
        [
            "python3",
            str(_script_path()),
            "--contract",
            "3.1a",
            "--skill",
            "legal-review",
            "--stdin",
            "--input-file",
            str(_fixture_path("legal_review_valid.md")),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "not allowed" in result.stderr.lower() or "error" in result.stderr.lower()
