#!/usr/bin/env python3
"""
render_pages.py — Рендер страниц PDF или изображения в набор PNG.

Использование:
    python3 render_pages.py <input_path> --output-dir <dir> [--dpi 200]

Поддерживает:
    - PDF через pymupdf
    - JPG/JPEG/PNG/TIFF/BMP через Pillow

Office-форматы (.docx/.xlsx) напрямую не рендерятся: вызывающая сторона
сначала конвертирует их в PDF.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
UNSUPPORTED_OFFICE = {".docx", ".xlsx"}


def _pdf_to_pngs(src: Path, dst: Path, dpi: int) -> list[str]:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pymupdf (fitz) не установлен — запусти scripts/setup.sh") from exc

    staging_dir = Path(tempfile.mkdtemp(prefix="render-pages-"))
    rendered: list[str] = []
    try:
        with fitz.open(src) as pdf:
            for index, page in enumerate(pdf, start=1):
                out_path = staging_dir / f"page-{index:03d}.png"
                pixmap = page.get_pixmap(dpi=dpi)
                pixmap.save(out_path)
                rendered.append(str(out_path.resolve()))

        if not rendered:
            raise ValueError("PDF has no pages")

        final_paths: list[str] = []
        for staged_path in sorted(staging_dir.glob("page-*.png")):
            out_path = dst / staged_path.name
            shutil.move(str(staged_path), str(out_path))
            final_paths.append(str(out_path.resolve()))
        return final_paths
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def _image_to_png(src: Path, dst: Path) -> list[str]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow не установлен — запусти scripts/setup.sh") from exc

    written: list[str] = []
    with Image.open(src) as image:
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            normalized = ImageOps.exif_transpose(image.copy())
            if normalized.mode in ("RGBA", "LA") or (
                normalized.mode == "P" and "transparency" in normalized.info
            ):
                rgba = normalized.convert("RGBA")
                base = Image.new("RGB", normalized.size, "white")
                base.paste(rgba, mask=rgba.getchannel("A"))
                normalized = base
            elif normalized.mode != "RGB":
                normalized = normalized.convert("RGB")

            out_path = dst / f"page-{index + 1:03d}.png"
            normalized.save(out_path, format="PNG")
            written.append(str(out_path.resolve()))

    return written


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render PDF/image pages to PNG files")
    parser.add_argument("input_path", help="Путь к PDF или изображению")
    parser.add_argument("--output-dir", required=True, help="Папка для PNG-страниц")
    parser.add_argument("--dpi", type=int, default=200, help="DPI для PDF-рендера")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    src = Path(args.input_path).expanduser().resolve()
    dst = Path(args.output_dir).expanduser().resolve()

    if not src.exists():
        print(f"Файл не найден: {src}", file=sys.stderr)
        return 1

    dst.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()

    if suffix in UNSUPPORTED_OFFICE:
        print(
            "office-формат не рендерится в PNG напрямую; "
            "конверсия в PDF должна быть сделана вызывающей стороной",
            file=sys.stderr,
        )
        return 2

    try:
        if suffix == ".pdf":
            files = _pdf_to_pngs(src, dst, args.dpi)
        elif suffix in SUPPORTED_IMAGES:
            files = _image_to_png(src, dst)
        else:
            print(f"Неподдерживаемый формат: {suffix or '[без расширения]'}", file=sys.stderr)
            return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "input": str(src),
                "output_dir": str(dst),
                "pages": len(files),
                "files": files,
                "dpi": args.dpi if suffix == ".pdf" else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
