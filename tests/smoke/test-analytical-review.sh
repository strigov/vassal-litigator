#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-analytical-review.sh /path/to/vassal-litigator

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки legal-review + Codex xhigh review.
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

SMOKE_CASE="/tmp/smoke-vassal-analytical-review-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat <<EOF
=== SMOKE: legal-review + xhigh review ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Открой Claude Cowork в этой папке.
3. Если intake ещё не выполнен в этом каталоге, сначала выполни init-case + intake на fixture-документах.
4. Для более стабильного smoke желательно сначала выполнить /vassal-litigator:catalog.
5. Выполни: /vassal-litigator:legal-review
6. Проверь preview правового анализа и подтверди apply.
7. Дождись контрольного ревью Codex xhigh.
8. Если verdict = REVIEW_BLOCKING, проверь что Сюзерену показаны 3 опции:
   - принять как есть
   - один раунд Opus фикса
   - ручная правка

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- Либо создаётся итоговый файл "{дата} Предварительный анализ документов.md"
- Либо создаётся review-артефакт в .vassal/reviews/
- При REVIEW_OK заключение и секции анализа сохранены в .vassal/analysis/
- При REVIEW_BLOCKING есть аудируемый review-отчёт с BLOCKING/NITS

ПРОВЕРКА:
- find . -path '*/.vassal/reviews/*.md' -type f
- find . -path '*/.vassal/analysis/*.md' -type f
- find . -name '*Предварительный анализ документов.md' -type f
- python3 -c "import pathlib; files=list(pathlib.Path('.').glob('**/.vassal/reviews/*.md')); print('reviews=', len(files)); print(files[0].read_text(encoding='utf-8')[:400] if files else 'NO_REVIEWS')"

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
