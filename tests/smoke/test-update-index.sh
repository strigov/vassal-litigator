#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-update-index.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки update-index
в режимах добавления нового файла и пересоздания устаревшего зеркала.
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

source "$PLUGIN_ROOT/tests/smoke/_fulltext_common.sh"

SMOKE_CASE="/tmp/smoke-vassal-update-index-$(date +%s)"
PAYLOAD_DIR="$SMOKE_CASE/.smoke-payloads"

mkdir -p "$SMOKE_CASE" "$PAYLOAD_DIR"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"
generate_large_fixture_pdf \
    "$PLUGIN_ROOT/tests/fixtures/dummy-case/_sources/большой-договор.txt" \
    "$PAYLOAD_DIR/большой-договор-update-index.pdf"
write_fulltext_helper "$SMOKE_CASE" "$PLUGIN_ROOT"

cat <<'EOF' | sed \
    -e "s|__SMOKE_CASE__|$SMOKE_CASE|g" \
    -e "s|__PAYLOAD_DIR__|$PAYLOAD_DIR|g" \
    -e "s|__PLUGIN_ROOT__|$PLUGIN_ROOT|g"
=== SMOKE: update-index ===

РАБОЧАЯ ДИРЕКТОРИЯ:
__SMOKE_CASE__

ШАГИ:
1. Перейди в smoke-директорию:
   cd "__SMOKE_CASE__"
2. Запусти Claude Code в этой папке.
3. Выполни /vassal-litigator:init-case и дождись завершения базового intake.
4. Подготовь новый файл для режима добавления:
   cp "__PAYLOAD_DIR__/большой-договор-update-index.pdf" "__SMOKE_CASE__/Материалы от клиента/2026-04-22 Большой документ для update-index.pdf"
5. Подготовь устаревшее зеркало для режима пересоздания:
   export SMOKE_CASE="__SMOKE_CASE__"; export PLUGIN_ROOT="__PLUGIN_ROOT__"
   source "\$SMOKE_CASE/.smoke-fulltext.sh"
   export STALE_ID=\$(python3 - "\$SMOKE_CASE/.vassal/index.yaml" <<'PY'
import pathlib
import sys
import yaml

idx = pathlib.Path(sys.argv[1])
data = yaml.safe_load(idx.read_text(encoding="utf-8"))
for entry in data.get("documents", []):
    if entry.get("source") == "client":
        print(entry["id"])
        break
PY
)
   export STALE_FILE=\$(source_of_id "\$STALE_ID")
   cp "__PAYLOAD_DIR__/большой-договор-update-index.pdf" "__SMOKE_CASE__/\$STALE_FILE"
   touch -m "__SMOKE_CASE__/\$STALE_FILE"
6. Выполни: /vassal-litigator:update-index
7. Проверь preview:
   - новый файл `2026-04-22 Большой документ для update-index.pdf` попал в режим добавления
   - `\$STALE_ID` попал в список устаревших зеркал
8. Подтверди apply.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- новый файл появился в `.vassal/index.yaml` с новым doc-ID и зеркалом
- для `\$STALE_ID` зеркало пересоздано и `mirror_stale: false`
- для новой записи и `\$STALE_ID` выставлены `ocr_quality: ok`, `ocr_quality_reason: ""`, `ocr_reattempted: false`
- оба зеркала содержат полный текст без усечения
- `.vassal/codex-logs/` содержит лог update-index

ПРОВЕРКА:
- export SMOKE_CASE="__SMOKE_CASE__"; export PLUGIN_ROOT="__PLUGIN_ROOT__"
- source "\$SMOKE_CASE/.smoke-fulltext.sh"
- python3 -c "import os, pathlib, yaml; p=pathlib.Path('\$SMOKE_CASE/.vassal/index.yaml'); d=yaml.safe_load(p.read_text(encoding='utf-8')); docs=d.get('documents', []); hits=[x for x in docs if x.get('file', '').endswith('2026-04-22 Большой документ для update-index.pdf')]; stale=next((x for x in docs if x.get('id') == os.environ.get('STALE_ID')), None); print('new_hits=', len(hits)); print('new_ids=', [x.get('id') for x in hits]); print('stale_found=', bool(stale)); print('stale_mirror_stale=', None if stale is None else stale.get('mirror_stale'))"
- python3 - <<'PYEOF'
import os
import pathlib
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
stale_id = os.environ["STALE_ID"]
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
docs = data.get("documents", [])
new_hits = [doc for doc in docs if doc.get("file", "").endswith("2026-04-22 Большой документ для update-index.pdf")]
stale = next((doc for doc in docs if doc.get("id") == stale_id), None)
errors = []

if len(new_hits) != 1:
    errors.append(f"expected exactly one new update-index hit, got {len(new_hits)}")

if stale is None:
    errors.append(f"stale doc id not found: {stale_id}")
elif stale.get("mirror_stale") is not False:
    errors.append(f"mirror_stale should be False in {stale_id}, got {stale.get('mirror_stale')!r}")

for doc in new_hits + ([stale] if stale is not None else []):
    doc_id = doc.get("id", "?")
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

print("update-index OCR assertions: OK")
PYEOF
- assert_mirror_full "2026-04-22 Большой документ для update-index.pdf"
- assert_mirror_full --id "\$STALE_ID"
- find "\$SMOKE_CASE/.vassal/codex-logs" -name '*update-index*.md' -type f

ОЧИСТКА:
rm -rf "__SMOKE_CASE__"
EOF
