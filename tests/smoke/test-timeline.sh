#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-timeline.sh /path/to/vassal-litigator

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки timeline.
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

SMOKE_CASE="/tmp/smoke-vassal-timeline-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat <<EOF
=== SMOKE: timeline ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Открой Claude Cowork в этой папке.
3. Если intake ещё не выполнен в этом каталоге, сначала выполни init-case + intake на fixture-документах.
4. Выполни: /vassal-litigator:timeline
5. В preview выбери политику extend или rebuild.
6. Подтверди apply.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- В корне дела создан или обновлён файл "Хронология дела.md"
- Внутри файла есть Mermaid-блок
- .vassal/case.yaml обновлён: заполнен timeline
- .vassal/codex-logs/ содержит лог timeline

ПРОВЕРКА:
- find . -name 'Хронология дела.md' -type f
- python3 -c "import pathlib; p=next(pathlib.Path('.').glob('**/Хронология дела.md')); t=p.read_text(encoding='utf-8'); print('mermaid=', '```mermaid' in t)"
- python3 -c "import yaml, pathlib; p=next(pathlib.Path('.').glob('**/.vassal/case.yaml')); d=yaml.safe_load(p.read_text(encoding='utf-8')); print('timeline_items=', len(d.get('timeline', [])))"
- find . -path '*/.vassal/codex-logs/*timeline*.md' -type f

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
