#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-analytical-review.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки legal-review
по ветке Ф5a: Opus-subagent -> markdown + Mermaid -> Sonnet-subagent -> arbitrum-docx.
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
    /tmp|/tmp/*|/private/tmp|/private/tmp/*) ;;
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

SMOKE_CASE="/tmp/smoke-vassal-legal-review-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat <<'EOF' | sed \
    -e "s|__SMOKE_CASE__|$SMOKE_CASE|g" \
    -e "s|__PLUGIN_ROOT__|$PLUGIN_ROOT|g"
=== SMOKE: legal-review (contract 3.1a -> 3.2) ===

РАБОЧАЯ ДИРЕКТОРИЯ:
__SMOKE_CASE__

ПРЕДУСЛОВИЯ:
- Claude Code запущен в окружении, где доступен `Task(model=opus)`
- Доступен formatter `arbitrum-docx`
- В этом каталоге уже выполнены `init-case` и intake на fixture-документах,
  либо ты сделаешь это перед запуском legal-review

ШАГИ:
1. Перейди в smoke-директорию:
   cd "__SMOKE_CASE__"
2. Запусти Claude Code в этой папке.
3. Если intake ещё не выполнен, сначала сделай init-case + intake на fixture-документах.
4. Выполни: /vassal-litigator-cc:legal-review
5. Подтверди preview/apply.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- В `.vassal/analysis/` создан markdown `legal-review-YYYY-MM-DD.md`
- В `.vassal/analysis/` создан `.docx` `legal-review-YYYY-MM-DD.docx`
- В markdown есть секция `## Схема сторон` и блок ```mermaid
- Последняя строка markdown: `READY_FOR_DOCX: analytical`
- Отдельный review-артефакт не создаётся
- В markdown нет упоминаний про удалённый внешний исполнитель и старый контрольный слой ревью

ПРОВЕРКА:
- find . -path '*/.vassal/analysis/legal-review-*.md' -type f
- find . -path '*/.vassal/analysis/legal-review-*.docx' -type f
- python3 - <<'PYEOF'
import pathlib
import sys

files = list(pathlib.Path('.').glob('**/.vassal/analysis/legal-review-*.md'))
if not files:
    print('FAIL: legal-review markdown not found')
    sys.exit(1)

path = files[0]
text = path.read_text(encoding='utf-8')
folded = text.casefold()
checks = {
    'schema_section': '## Схема сторон' in text,
    'mermaid': '```mermaid' in text,
    'ready_for_docx': text.rstrip().endswith('READY_FOR_DOCX: analytical'),
    'no_removed_executor': ("co" "dex") not in folded,
    'no_old_review_tier': ("xh" "igh") not in folded,
    'no_control_review': 'контрольное ревью' not in folded,
}
print(path)
print(checks)
if not all(checks.values()):
    sys.exit(1)
PYEOF
- python3 - <<'PYEOF'
import pathlib
import sys

reviews = list(pathlib.Path('.').glob('**/.vassal/reviews/*.md'))
print('review_files=', reviews)
if reviews:
    sys.exit(1)
PYEOF
- python3 - <<'PYEOF'
import pathlib
import sys

files = list(pathlib.Path('.').glob('**/.vassal/analysis/legal-review-*.docx'))
if not files:
    print('FAIL: legal-review docx not found')
    sys.exit(1)

path = files[0]
size = path.stat().st_size
print(path, size)
if size <= 0:
    sys.exit(1)
PYEOF

ОЧИСТКА:
rm -rf "__SMOKE_CASE__"
EOF
