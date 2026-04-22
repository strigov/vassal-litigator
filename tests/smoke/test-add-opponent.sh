#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-add-opponent.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки add-opponent
с полнотекстовой проверкой md-зеркала.
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

source "$PLUGIN_ROOT/tests/smoke/_fulltext_common.sh"

SMOKE_CASE="/tmp/smoke-vassal-add-opponent-$(date +%s)"
PAYLOAD_DIR="$SMOKE_CASE/.smoke-payloads"

mkdir -p "$SMOKE_CASE" "$PAYLOAD_DIR"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"
generate_large_fixture_pdf \
    "$PLUGIN_ROOT/tests/fixtures/dummy-case/_sources/большой-договор.txt" \
    "$PAYLOAD_DIR/большой-отзыв-ответчика.pdf"
write_fulltext_helper "$SMOKE_CASE" "$PLUGIN_ROOT"

cat <<EOF
=== SMOKE: add-opponent ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Запусти Claude Code в этой папке.
3. Выполни /vassal-litigator:init-case и дождись завершения базового intake.
4. Добавь новую поставку оппонента:
   cp "$PAYLOAD_DIR/большой-отзыв-ответчика.pdf" "$SMOKE_CASE/Входящие документы/большой-отзыв-ответчика.pdf"
5. Выполни: /vassal-litigator:add-opponent
6. Проверь preview:
   - найден один новый файл
   - выбран оппонент из карточки дела
   - план создаёт новую процессуальную папку и doc-ID
7. Подтверди apply.
8. Если после apply будет предложен экспресс-анализ Opus, его можно подтвердить отдельно; файловая проверка на этом не зависит.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- создан raw-батч `.vassal/raw/opponent-ГГГГ-ММ-ДД/` с копией `большой-отзыв-ответчика.pdf`
- в `.vassal/index.yaml` появилась новая запись с `source: opponent`, `ocr_quality: ok`, `ocr_quality_reason: ""`, `ocr_reattempted: false`
- для новой записи создано `.vassal/mirrors/doc-NNN.md` с полным текстом
- создана процессуальная папка с головным документом оппонента
- `.vassal/codex-logs/` содержит архив плана add-opponent
- `.vassal/plans/add-opponent-*.md` и `.vassal/work/add-opponent-*/` удалены

ПРОВЕРКА:
- export SMOKE_CASE="$SMOKE_CASE"; export PLUGIN_ROOT="$PLUGIN_ROOT"
- source "\$SMOKE_CASE/.smoke-fulltext.sh"
- python3 - <<'PYEOF'
import os
import pathlib
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
docs = data.get("documents", [])
hits = [doc for doc in docs if (doc.get("origin", {}) or {}).get("name") == "большой-отзыв-ответчика.pdf"]
errors = []

if len(hits) != 1:
    errors.append(f"expected exactly one hit for большой-отзыв-ответчика.pdf, got {len(hits)}")

for doc in hits:
    doc_id = doc.get("id", "?")
    file_path = doc.get("file")
    if doc.get("source") != "opponent":
        errors.append(f"source should be 'opponent' in {doc_id}, got {doc.get('source')!r}")
    if not file_path:
        errors.append(f"missing file path in {doc_id}")
    if doc.get("ocr_quality") != "ok":
        errors.append(f"ocr_quality should be 'ok' in {doc_id}, got {doc.get('ocr_quality')!r}")
    if doc.get("ocr_quality_reason") != "":
        errors.append(f"ocr_quality_reason should be empty string in {doc_id}, got {doc.get('ocr_quality_reason')!r}")
    if doc.get("ocr_reattempted") is not False:
        errors.append(f"ocr_reattempted should be False in {doc_id}, got {doc.get('ocr_reattempted')!r}")

if errors:
    print("FAIL:")
    print("\\n".join(errors))
    sys.exit(1)

print("add-opponent OCR assertions: OK")
PYEOF
- assert_mirror_full "большой-отзыв-ответчика.pdf"
- find "\$SMOKE_CASE/.vassal/raw" -path '*opponent-*' -type f
- find "\$SMOKE_CASE/.vassal/codex-logs" -name '*add-opponent-plan.md' -type f
- ls "\$SMOKE_CASE/.vassal/plans/" 2>/dev/null; ls "\$SMOKE_CASE/.vassal/work/" 2>/dev/null

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
