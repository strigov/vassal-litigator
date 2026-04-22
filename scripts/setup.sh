#!/bin/bash
# setup.sh — Установка зависимостей для vassal-litigator-cc
# Запускать один раз на машине после установки плагина в Claude Code.
# Идемпотентный: проверяет, что уже установлено, и пропускает.

set -e

echo "=== vassal-litigator: Установка зависимостей ==="

# 1. Системные пакеты (OCR)
if ! command -v tesseract &> /dev/null; then
    echo "→ Устанавливаю tesseract-ocr..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-rus 2>/dev/null || {
        echo "⚠️  Не удалось установить tesseract. OCR будет работать через LLM fallback."
    }
else
    echo "✓ tesseract уже установлен"
fi

if ! command -v ocrmypdf &> /dev/null; then
    echo "→ Устанавливаю ocrmypdf..."
    pip install ocrmypdf --break-system-packages -q 2>/dev/null || {
        echo "⚠️  Не удалось установить ocrmypdf."
    }
else
    echo "✓ ocrmypdf уже установлен"
fi

# 1b. Архиваторы — нужны для распаковки клиентских пакетов .zip/.rar/.7z/.tar
missing_archivers=()
for bin in unzip 7z tar unrar; do
    if ! command -v "$bin" &> /dev/null; then
        missing_archivers+=("$bin")
    fi
done
if [ ${#missing_archivers[@]} -ne 0 ]; then
    echo "→ Устанавливаю архиваторы: ${missing_archivers[*]}..."
    sudo apt-get install -y -qq unzip p7zip-full tar unrar 2>/dev/null || {
        echo "⚠️  Не удалось установить часть архиваторов. Защищённые/битые архивы пойдут в 'Без даты — Архивы без контекста'."
    }
else
    echo "✓ архиваторы уже установлены (unzip, 7z, tar, unrar)"
fi

# 2. Python-пакеты
echo "→ Устанавливаю Python-зависимости..."
pip install --break-system-packages -q \
    PyYAML \
    openpyxl \
    python-docx \
    pymupdf \
    pillow \
    2>/dev/null || echo "⚠️  Некоторые пакеты не удалось установить."

# 2b. Опционально: LibreOffice для reocr --force docx
if [ -t 0 ]; then
    read -p "Установить LibreOffice для reocr --force docx? [y/N] " ans
    if [[ "$ans" == "y" ]]; then
        brew install --cask libreoffice 2>/dev/null || echo "LibreOffice: установи вручную"
    fi
else
    echo "→ Пропускаю установку LibreOffice: нет интерактивного TTY"
fi

# 3. Проверка
echo ""
echo "=== Статус зависимостей ==="

check_cmd() {
    if command -v "$1" &> /dev/null; then
        echo "✓ $1"
    else
        echo "✗ $1 (не установлен)"
    fi
}

check_py() {
    if python3 -c "import $1" 2>/dev/null; then
        echo "✓ python: $1"
    else
        echo "✗ python: $1 (не установлен)"
    fi
}

check_cmd tesseract
check_cmd ocrmypdf
check_cmd unzip
check_cmd 7z
check_cmd tar
check_cmd unrar
check_py yaml
check_py openpyxl
check_py docx
check_py fitz  # pymupdf (используется extract_text.py и image_to_pdf.py)
check_py PIL   # Pillow (используется render_pages.py)

echo ""
echo "=== Готово ==="
