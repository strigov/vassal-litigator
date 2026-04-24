#!/usr/bin/env python3
"""
classify_ocr_quality.py — единый классификатор качества OCR.

Использование:
    python3 scripts/classify_ocr_quality.py --extraction-method <method> \
        [--confidence <confidence>] [--total-chars <int>] [--pages <int>]

Выход: JSON {"ocr_quality": "...", "ocr_quality_reason": "..."}.
"""

from __future__ import annotations

import argparse
import json
import math
import sys


KNOWN_METHODS = {"pdf-text", "docx-parse", "text-read", "ocr", "haiku-vision", "none"}
CATEGORY_TO_CONFIDENCE = {
    "high": 0.9,
    "medium": 0.65,
    "low": 0.3,
}


def _normalize_method(method: str | None) -> str | None:
    if not isinstance(method, str):
        return None
    return method.strip().lower()


def _coerce_confidence(confidence: float | str | None) -> float | None:
    if confidence is None:
        return None

    if isinstance(confidence, (int, float)):
        try:
            result = float(confidence)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    if not isinstance(confidence, str):
        return None

    value = confidence.strip().lower()
    if not value:
        return None

    if value in CATEGORY_TO_CONFIDENCE:
        return CATEGORY_TO_CONFIDENCE[value]

    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _format_reason(method: str, confidence: float | None, total_chars: int | None, pages: int | None) -> str:
    pages_valid = isinstance(pages, int) and pages > 0
    chars_per_page = (total_chars or 0) / pages if pages_valid else float("nan")
    chars_str = f"{chars_per_page:.2f}" if pages_valid else "n/a"
    return (
        f"method={method}; confidence={confidence:.3f}"
        f"; total_chars={total_chars or 0}; pages={pages or 0}; chars_per_page={chars_str}"
    )


def classify(
    extraction_method: str | None,
    confidence: float | str | None,
    total_chars: int | None,
    pages: int | None,
) -> dict[str, str]:
    normalized_method = _normalize_method(extraction_method)
    if normalized_method in {"pdf-text", "docx-parse", "text-read"}:
        return {"ocr_quality": "ok", "ocr_quality_reason": ""}

    if normalized_method == "ocr":
        if total_chars is None or total_chars < 50:
            return {"ocr_quality": "empty", "ocr_quality_reason": "ocr produced <50 chars"}

        coerced = _coerce_confidence(confidence)
        if coerced is None:
            return {
                "ocr_quality": "low",
                "ocr_quality_reason": "confidence missing or non-numeric",
            }

        pages_valid = isinstance(pages, int) and pages > 0
        chars_per_page = (total_chars or 0) / pages if pages_valid else None
        if coerced >= 0.75 and pages_valid and chars_per_page >= 200:
            return {"ocr_quality": "ok", "ocr_quality_reason": ""}

        return {
            "ocr_quality": "low",
            "ocr_quality_reason": f"ocr below threshold ({_format_reason('ocr', coerced, total_chars, pages)})",
        }

    if normalized_method == "haiku-vision":
        coerced = _coerce_confidence(confidence)
        if coerced is None:
            return {
                "ocr_quality": "low",
                "ocr_quality_reason": "confidence missing or non-numeric",
            }

        pages_valid = isinstance(pages, int) and pages > 0
        chars_per_page = (total_chars or 0) / pages if pages_valid else None
        if coerced >= 0.75 and pages_valid and chars_per_page >= 200:
            return {"ocr_quality": "ok", "ocr_quality_reason": ""}

        return {
            "ocr_quality": "low",
            "ocr_quality_reason": (
                f"haiku-vision below threshold ({_format_reason('haiku-vision', coerced, total_chars, pages)})"
            ),
        }

    if normalized_method == "none":
        return {"ocr_quality": "empty", "ocr_quality_reason": "extraction failed"}

    if normalized_method in KNOWN_METHODS or normalized_method is None:
        return {"ocr_quality": "ok", "ocr_quality_reason": ""}

    return {"ocr_quality": "ok", "ocr_quality_reason": ""}


def _int_or_none(value: str) -> int | None:
    """Custom argparse type: returns None for empty/null/none/non-integer strings, int otherwise."""
    if not value or value.strip().lower() in {"null", "none"}:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify OCR extraction quality.")
    parser.add_argument(
        "--extraction-method",
        required=True,
        help="Extraction method from extract_text.py",
    )
    parser.add_argument(
        "--confidence",
        help="Confidence from extract_text.py (float|high|medium|low)",
    )
    parser.add_argument("--total-chars", type=_int_or_none, default=None)
    parser.add_argument("--pages", type=_int_or_none, default=None)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    result = classify(
        extraction_method=args.extraction_method,
        confidence=args.confidence,
        total_chars=args.total_chars,
        pages=args.pages,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
