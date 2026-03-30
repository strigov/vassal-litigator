#!/bin/bash
# setup.sh — Установка зависимостей для vassal-litigator
# Запускать один раз за сессию Cowork.
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

# 2. Python-пакеты
echo "→ Устанавливаю Python-зависимости..."
pip install --break-system-packages -q \
    PyYAML \
    openpyxl \
    python-docx \
    pymupdf \
    2>/dev/null || echo "⚠️  Некоторые пакеты не удалось установить."

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
check_py yaml
check_py openpyxl
check_py docx
check_py fitz  # pymupdf

echo ""
echo "=== Готово ==="
