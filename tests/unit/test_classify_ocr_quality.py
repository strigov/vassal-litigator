import json
import subprocess
import sys

from classify_ocr_quality import classify, _coerce_confidence


def test_pdf_text_with_high_category_is_ok():
    result = classify("pdf-text", "high", 120, 1)
    assert result["ocr_quality"] == "ok"
    assert result["ocr_quality_reason"] == ""


def test_pdf_text_with_medium_category_is_ok():
    result = classify(" pdf-text ", "medium", 30, 1)
    assert result["ocr_quality"] == "ok"
    assert result["ocr_quality_reason"] == ""


def test_docx_parse_with_high_category_is_ok():
    result = classify("docx-parse", "high", 10, 1)
    assert result["ocr_quality"] == "ok"
    assert result["ocr_quality_reason"] == ""


def test_ocr_with_low_category_is_low():
    result = classify("ocr", "low", 1000, 10)
    assert result["ocr_quality"] == "low"
    assert result["ocr_quality_reason"] != ""


def test_ocr_with_medium_category_and_many_chars_is_low():
    result = classify("ocr", "medium", 300, 1)
    assert result["ocr_quality"] == "low"
    assert result["ocr_quality_reason"] != ""


def test_ocr_with_float_confidence_and_threshold_met_is_ok():
    result = classify("ocr", 0.82, 500, 2)
    assert result == {"ocr_quality": "ok", "ocr_quality_reason": ""}


def test_ocr_with_small_text_is_empty():
    result = classify("ocr", 0.82, 30, 1)
    assert result == {"ocr_quality": "empty", "ocr_quality_reason": "ocr produced <50 chars"}


def test_haiku_vision_with_good_metrics_is_ok():
    result = classify("haiku-vision", 0.80, 1000, 3)
    assert result == {"ocr_quality": "ok", "ocr_quality_reason": ""}


def test_ocr_with_missing_confidence_is_low():
    result = classify("ocr", None, 500, 2)
    assert result["ocr_quality"] == "low"
    assert result["ocr_quality_reason"] == "confidence missing or non-numeric"


def test_none_extraction_method_is_empty():
    result = classify("none", "high", 500, 2)
    assert result == {"ocr_quality": "empty", "ocr_quality_reason": "extraction failed"}


def test_unknown_method_is_ok_by_default():
    result = classify("legacy-parser", "low", 20, 1)
    assert result == {"ocr_quality": "ok", "ocr_quality_reason": ""}


# --- Fix 1: NaN / Inf confidence safety ---

def test_coerce_confidence_nan_string_returns_none():
    assert _coerce_confidence("nan") is None


def test_coerce_confidence_inf_string_returns_none():
    assert _coerce_confidence("inf") is None


def test_coerce_confidence_float_nan_returns_none():
    assert _coerce_confidence(float("nan")) is None


def test_coerce_confidence_float_inf_returns_none():
    assert _coerce_confidence(float("inf")) is None


def test_ocr_confidence_nan_string_treated_as_missing_returns_low():
    """confidence='nan' → _coerce_confidence returns None → treated as missing → low."""
    result = classify("ocr", "nan", 500, 2)
    assert result["ocr_quality"] == "low"
    assert result["ocr_quality_reason"] == "confidence missing or non-numeric"


def test_ocr_confidence_float_nan_treated_as_missing_returns_low():
    result = classify("ocr", float("nan"), 500, 2)
    assert result["ocr_quality"] == "low"
    assert result["ocr_quality_reason"] == "confidence missing or non-numeric"


def test_ocr_confidence_float_inf_treated_as_missing_returns_low():
    result = classify("ocr", float("inf"), 500, 2)
    assert result["ocr_quality"] == "low"
    assert result["ocr_quality_reason"] == "confidence missing or non-numeric"


# --- Fix 2: CLI --total-chars / --pages with None/empty/null values ---

def _run_cli(*args):
    """Run classify_ocr_quality.py as subprocess, return parsed JSON."""
    import os
    script = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "classify_ocr_quality.py"
    )
    result = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"CLI crashed: stderr={result.stderr!r}"
    return json.loads(result.stdout)


def test_cli_total_chars_empty_string_does_not_crash():
    data = _run_cli("--extraction-method", "ocr", "--confidence", "0.9", "--total-chars", "")
    assert "ocr_quality" in data


def test_cli_total_chars_null_does_not_crash():
    data = _run_cli("--extraction-method", "ocr", "--confidence", "0.9", "--total-chars", "null")
    assert "ocr_quality" in data


def test_cli_total_chars_none_string_does_not_crash():
    data = _run_cli("--extraction-method", "ocr", "--confidence", "0.9", "--total-chars", "none")
    assert "ocr_quality" in data


def test_cli_pages_null_does_not_crash():
    data = _run_cli("--extraction-method", "ocr", "--confidence", "0.9",
                    "--total-chars", "500", "--pages", "null")
    assert "ocr_quality" in data


def test_cli_pages_not_passed_works_correctly():
    """--pages omitted entirely: should default to None and not crash."""
    data = _run_cli("--extraction-method", "pdf-text")
    assert data == {"ocr_quality": "ok", "ocr_quality_reason": ""}


def test_cli_total_chars_not_passed_works_correctly():
    """--total-chars omitted entirely: pdf-text returns ok regardless."""
    data = _run_cli("--extraction-method", "pdf-text")
    assert data == {"ocr_quality": "ok", "ocr_quality_reason": ""}


# --- Fix 1 (BLOCKING): pages=0 / pages=-1 must never produce ok via chars_per_page ---

def test_ocr_pages_zero_high_confidence_many_chars_not_ok():
    """pages=0 with ocr + high confidence + many chars must NOT return ok."""
    result = classify("ocr", 0.99, 10000, 0)
    assert result["ocr_quality"] != "ok", f"Expected non-ok, got: {result}"


def test_ocr_pages_negative_high_confidence_many_chars_not_ok():
    """pages=-1 with ocr + high confidence + many chars must NOT return ok."""
    result = classify("ocr", 0.99, 10000, -1)
    assert result["ocr_quality"] != "ok", f"Expected non-ok, got: {result}"


# --- Fix 2 (NIT): extraction_method not a string must not raise AttributeError ---

def test_extraction_method_none_does_not_raise():
    """extraction_method=None must not raise, must return a valid result."""
    result = classify(None, 0.9, 500, 2)
    assert "ocr_quality" in result


def test_extraction_method_int_does_not_raise():
    """extraction_method=42 (int) must not raise, must return a valid result."""
    result = classify(42, 0.9, 500, 2)
    assert "ocr_quality" in result
