#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-catalog.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/ или /private/tmp/.
Скрипт готовит smoke-окружение, запускает generate_table.py и проверяет
созданный артефакт каталога автоматически.
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

SMOKE_CASE="$(mktemp -d /tmp/smoke-vassal-catalog.XXXXXX)"
trap 'rm -rf "$SMOKE_CASE"' EXIT

run_generate_table() {
    local case_root="$1"
    python3 "$PLUGIN_ROOT/scripts/generate_table.py" --case-root "$case_root"
}

seed_happy_case() {
    local case_root="$1"
    cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/." "$case_root/"
    mkdir -p "$case_root/.vassal" "$case_root/.vassal/mirrors"

    cat > "$case_root/.vassal/index.yaml" <<'EOF'
documents:
  - id: doc-001
    date: 2026-04-01
    doc_type: договор
    title: Договор поставки
    summary: Основной договор поставки между сторонами спора.
    parties:
      from: ООО Ромашка
      to: ООО Василек
    seal: true
    signature: true
    completeness: full
    quality: good
    file: Входящие документы/договор.pdf
  - id: doc-002
    date: 2026-04-10
    doc_type: претензия
    title: Досудебная претензия
    summary: Претензия о погашении задолженности и неустойки.
    parties:
      from: ООО Василек
      to: ООО Ромашка
    seal: false
    signature: true
    completeness: full
    quality: good
    file: Входящие документы/претензия.pdf
EOF

    cat > "$case_root/.vassal/mirrors/doc-001.md" <<'EOF'
---
id: doc-001
title: Договор поставки
---

Полный текст договора поставки.
EOF

    cat > "$case_root/.vassal/mirrors/doc-002.md" <<'EOF'
---
id: doc-002
title: Досудебная претензия
---

Полный текст досудебной претензии.
EOF
}

seed_empty_documents_case() {
    local case_root="$1"
    mkdir -p "$case_root/.vassal" "$case_root/.vassal/mirrors"
    cat > "$case_root/.vassal/index.yaml" <<'EOF'
documents: []
EOF
}

assert_catalog_output() {
    local case_root="$1"
    local expected_label="$2"
    CASE_ROOT="$case_root" EXPECTED_LABEL="$expected_label" python3 - <<'PY'
import os
import pathlib
import sys

case_root = pathlib.Path(os.environ["CASE_ROOT"])
expected_label = os.environ["EXPECTED_LABEL"]
xlsx_path = case_root / "Таблица документов.xlsx"
csv_path = case_root / "Таблица документов.csv"
errors = []

if xlsx_path.exists() and csv_path.exists():
    errors.append(f"{expected_label}: unexpectedly found both XLSX and CSV outputs")

output_path = xlsx_path if xlsx_path.exists() else csv_path if csv_path.exists() else None
if output_path is None:
    errors.append(
        f"{expected_label}: expected Таблица документов.xlsx or Таблица документов.csv to exist"
    )
else:
    if output_path.stat().st_size <= 0:
        errors.append(f"{expected_label}: output file is empty: {output_path}")

if errors:
    print("FAIL:")
    print("\n".join(errors))
    sys.exit(1)

print(f"{expected_label}: OK ({output_path.name})")
PY
}

EMPTY_MIRRORS_CASE="$(mktemp -d /tmp/smoke-vassal-catalog-empty-mirrors.XXXXXX)"
EMPTY_DOCS_CASE="$(mktemp -d /tmp/smoke-vassal-catalog-empty-docs.XXXXXX)"
trap 'rm -rf "$SMOKE_CASE" "$EMPTY_MIRRORS_CASE" "$EMPTY_DOCS_CASE"' EXIT

seed_happy_case "$SMOKE_CASE"
run_generate_table "$SMOKE_CASE"
assert_catalog_output "$SMOKE_CASE" "happy-path"

seed_happy_case "$EMPTY_MIRRORS_CASE"
rm -rf "$EMPTY_MIRRORS_CASE/.vassal/mirrors"
mkdir -p "$EMPTY_MIRRORS_CASE/.vassal/mirrors"
run_generate_table "$EMPTY_MIRRORS_CASE"
assert_catalog_output "$EMPTY_MIRRORS_CASE" "empty-mirrors"

seed_empty_documents_case "$EMPTY_DOCS_CASE"
run_generate_table "$EMPTY_DOCS_CASE"
assert_catalog_output "$EMPTY_DOCS_CASE" "empty-documents"

# Проверка обогащения summary и записи в history.md требует live-сессию Claude-main,
# поэтому остаётся вне smoke и должна подтверждаться отдельным интеграционным прогоном.
