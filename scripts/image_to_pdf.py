#!/usr/bin/env python3
"""
image_to_pdf.py — Конвертация растровых изображений (скриншоты, сканы, фото) в PDF.

Используется apply-фазой intake/add-evidence/add-opponent: в `Материалы от клиента/`
попадает только PDF, оригинал-картинка остаётся в `.vassal/raw/<batch>/` рядом.

Поддерживает: .png, .jpg, .jpeg, .tif, .tiff, .bmp, .heic

Использование:
    python3 image_to_pdf.py --in <file> --out <file.pdf>
    python3 image_to_pdf.py --in <f1> <f2> ... --out <file.pdf>   # несколько страниц в одном PDF

Выход:
    Печатает JSON: { "pdf": "<out>", "pages": N, "source": [paths], "warnings": [...] }
    exit 0 при успехе, 1 при ошибке.
"""

import argparse
import json
import os
import sys
from pathlib import Path

SUPPORTED = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic"}


def convert(inputs: list[str], out_path: str) -> dict:
    warnings: list[str] = []

    for src in inputs:
        if not os.path.isfile(src):
            return {"error": f"Файл не найден: {src}"}
        ext = Path(src).suffix.lower()
        if ext not in SUPPORTED:
            return {"error": f"Неподдерживаемое расширение: {ext} ({src})"}

    try:
        import fitz  # pymupdf
    except ImportError:
        return {"error": "pymupdf (fitz) не установлен — запусти scripts/setup.sh"}

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    pdf = fitz.open()
    pages = 0
    try:
        for src in inputs:
            try:
                img_doc = fitz.open(src)
            except Exception as exc:
                warnings.append(f"Не удалось открыть {src}: {exc}")
                continue
            pdf_bytes = img_doc.convert_to_pdf()
            img_doc.close()
            page_doc = fitz.open("pdf", pdf_bytes)
            pdf.insert_pdf(page_doc)
            pages += page_doc.page_count
            page_doc.close()

        if pages == 0:
            pdf.close()
            return {"error": "Ни одно изображение не удалось сконвертировать", "warnings": warnings}

        pdf.save(out_path, garbage=4, deflate=True)
    finally:
        pdf.close()

    return {
        "pdf": out_path,
        "pages": pages,
        "source": [os.path.abspath(p) for p in inputs],
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert images to PDF via PyMuPDF")
    parser.add_argument("--in", dest="inputs", nargs="+", required=True,
                        help="Один или несколько путей к изображениям")
    parser.add_argument("--out", dest="output", required=True,
                        help="Путь к итоговому PDF")
    args = parser.parse_args()

    result = convert(args.inputs, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
