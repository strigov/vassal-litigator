#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-intake.sh /path/to/vassal-litigator

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки intake.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    print_usage
    exit 0
fi

PLUGIN_ROOT="${1:-}"
if [[ -z "$PLUGIN_ROOT" ]]; then
    print_usage
    exit 1
fi

case "$PWD" in
    /tmp|/tmp/*) ;;
    *)
        echo "WARNING: smoke-скрипт можно запускать только из /tmp/. Текущий CWD: $PWD"
        exit 1
        ;;
esac

if [[ ! -d "$PLUGIN_ROOT" ]]; then
    echo "ERROR: PLUGIN_ROOT не существует: $PLUGIN_ROOT"
    exit 1
fi

if [[ ! -d "$PLUGIN_ROOT/tests/fixtures/dummy-case" ]]; then
    echo "ERROR: не найдена фикстура $PLUGIN_ROOT/tests/fixtures/dummy-case"
    exit 1
fi

SMOKE_CASE="/tmp/smoke-vassal-intake-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat <<EOF
=== SMOKE: intake ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Открой Claude Cowork в этой папке.
3. Выполни: /vassal-litigator:init-case
4. Введи данные дела:
   - Клиент: ООО "Ромашка" (истец)
   - Оппонент: ООО "Лютик" (ответчик)
   - Дело: А41-1234/2025
   - Суд: Арбитражный суд Московской области
   - Суть: взыскание задолженности по договору поставки
5. Скопируй файлы из "$SMOKE_CASE/Входящие документы/" во "Входящие документы/" созданного дела.
6. Выполни: /vassal-litigator:intake
7. Проверь preview и подтверди apply.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- Оригиналы появились в .vassal/raw/
- Созданы md-зеркала в .vassal/mirrors/
- .vassal/index.yaml содержит записи о документах
- .vassal/history.md содержит запись об intake
- Исходные файлы перемещены в "На удаление/" через copy+zero

ПРОВЕРКА:
- find . -path '*/.vassal/raw/*' -type f
- find . -path '*/.vassal/mirrors/*.md' -type f
- python3 -c "import yaml, pathlib; p=next(pathlib.Path('.').glob('**/.vassal/index.yaml')); d=yaml.safe_load(p.read_text(encoding='utf-8')); print('docs=', len(d.get('docs', d.get('documents', []))))"
- python3 -c "import pathlib; p=next(pathlib.Path('.').glob('**/.vassal/history.md')); print(p.read_text(encoding='utf-8'))"

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
