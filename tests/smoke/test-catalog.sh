#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-catalog.sh /path/to/vassal-litigator

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки catalog.
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

SMOKE_CASE="/tmp/smoke-vassal-catalog-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat <<EOF
=== SMOKE: catalog ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Открой Claude Cowork в этой папке.
3. Если intake в этом каталоге ещё не выполнен:
   - запусти /vassal-litigator:init-case
   - скопируй fixture-документы во "Входящие документы/" дела
   - запусти /vassal-litigator:intake и подтверди apply
4. Выполни: /vassal-litigator:catalog
5. Проверь preview: какие записи будут обогащены и что будет перезаписана "Таблица документов.xlsx".
6. Подтверди apply.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- В корне дела создана или обновлена "Таблица документов.xlsx"
- .vassal/index.yaml обновлён: у части документов появились summary
- .vassal/codex-logs/ содержит лог catalog

ПРОВЕРКА:
- find . -name 'Таблица документов.xlsx' -type f
- python3 -c "import yaml, pathlib; p=next(pathlib.Path('.').glob('**/.vassal/index.yaml')); d=yaml.safe_load(p.read_text(encoding='utf-8')); docs=d.get('docs', d.get('documents', [])); print('docs=', len(docs)); print('with_summary=', sum(1 for x in docs if x.get('summary')))"
- find . -path '*/.vassal/codex-logs/*catalog*.md' -type f

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
