#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-intake.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки intake
по контракту v1.0.0: plan → review → apply → verify + полнотекстовая сверка зеркала.
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

SMOKE_CASE="/tmp/smoke-vassal-intake-$(date +%s)"
export SMOKE_CASE
export PLUGIN_ROOT

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"
generate_large_fixture_pdf \
    "$PLUGIN_ROOT/tests/fixtures/dummy-case/_sources/большой-договор.txt" \
    "$SMOKE_CASE/Входящие документы/большой-договор.pdf"
write_fulltext_helper "$SMOKE_CASE" "$PLUGIN_ROOT"

cat <<EOF
=== SMOKE: intake (v1.0.0 — plan → review → apply → verify) ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ПРЕДУСЛОВИЯ:
- Claude Code запущен в окружении, где доступен `Task(model=haiku)`
- setup.sh прогонится автоматически внутри init-case (либо один раз запусти вручную)

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Запусти Claude Code в этой папке.
3. Выполни: /vassal-litigator:init-case
4. Заполни карточку (если init-case запросит):
   - Клиент: ООО "Ромашка" (истец)
   - Оппонент: ООО "Лютик" (ответчик)
   - Дело: А41-1234/2025
   - Суд: Арбитражный суд Московской области
   - Суть: взыскание задолженности по договору поставки
5. init-case сам запустит intake на файлах из "Входящие документы/":
   - договор.pdf, претензия.pdf, скан.jpg, большой-договор.pdf, архив.zip (внутри: акт.pdf, платёжка.pdf)
6. Фаза plan: main-Sonnet с классификацией через Haiku-subagent. Дождись, пока Claude покажет markdown-план.
7. Проверь план:
   - scan: таблица файлов с новыми именами, целевыми папками, doc-ID
   - скан.jpg помечен для конверсии в PDF
   - архив.zip помечен как "archive_failed: false", его содержимое (акт.pdf, платёжка.pdf)
     попало в таблицу как отдельные файлы с origin.archive_src = "архив"
   - секции "Комплекты", "Сироты без даты", "Конверсии изображений → PDF",
     "Не обработанные архивы", "Проверки плана"
8. Если план ок — подтверди ("apply"/"go"/"да"). Если нет — дай правки, дождись revise-плана.
9. Фаза apply: main-Sonnet применяет утверждённый план и обновляет артефакты дела. Дождись завершения.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- .vassal/raw/intake-ГГГГ-ММ-ДД/ содержит копии всех 5 исходников + содержимое архива:
  договор.pdf, претензия.pdf, скан.jpg, большой-договор.pdf, архив.zip, архив__акт.pdf, архив__платёжка.pdf
- .vassal/mirrors/ содержит doc-001.md ... doc-NNN.md (по числу проиндексированных)
- .vassal/index.yaml валиден, source: client, у каждой записи заполнены
  id/title/date/file/mirror/origin/extraction_method/confidence/mirror_stale/ocr_quality/ocr_reattempted
- Комплекты (если план их выделил) имеют bundle_id, role_in_bundle, parent_id, attachment_order
- для всех новых записей `ocr_quality: ok`, `ocr_reattempted: false`, `ocr_quality_reason: ""`
- Материалы от клиента/ содержит хронологическую раскладку:
  * одиночные файлы — без папки (например "2025-06-01 Ромашка Договор поставки.pdf")
  * комплекты — папки вида "ГГГГ-ММ-ДД Отправитель Описание/" с "Приложение NN — ...расш"
  * сироты (если есть) — в "Без даты — <Тема>/"
- Скриншот скан.jpg превращён в PDF; .jpg-оригинал остался ТОЛЬКО в .vassal/raw/
- архив.zip НЕ попал в "Материалы от клиента/" и НЕ индексируется в index.yaml
  (в raw остаётся, в index.yaml есть только его содержимое)
- Зеркало для `большой-договор.pdf` содержит полный текст OCR-артефакта, без усечения
- Входящие документы/ пустая (все 5 файлов удалены через rm после архивации в .vassal/raw/)
- .vassal/plans/intake-*.md удалён после архивации
- .vassal/codex-logs/ГГГГ-ММ-ДД-ЧЧмм-intake-plan.md — архивная копия плана
- .vassal/work/intake-*/ удалена целиком
- .vassal/history.md содержит две строки: "intake plan: ..." и "intake apply: ..."

ПРОВЕРКА:
- ls -la "\$SMOKE_CASE/Входящие документы/"                      # должна быть пустой
- find "\$SMOKE_CASE/.vassal/raw" -type f | wc -l                # >= 7 (5 исходников + 2 из архива)
- find "\$SMOKE_CASE/.vassal/mirrors" -name 'doc-*.md' | wc -l   # == число записей в index.yaml
- find "\$SMOKE_CASE/Материалы от клиента" -type f               # хронологическая раскладка
- find "\$SMOKE_CASE/.vassal/codex-logs" -name '*-intake-plan.md' -type f
- ls "\$SMOKE_CASE/.vassal/plans/" 2>/dev/null; ls "\$SMOKE_CASE/.vassal/work/" 2>/dev/null
- export SMOKE_CASE="$SMOKE_CASE"; export PLUGIN_ROOT="$PLUGIN_ROOT"
- python3 -c "import yaml, pathlib; p=pathlib.Path('\$SMOKE_CASE/.vassal/index.yaml'); d=yaml.safe_load(p.read_text(encoding='utf-8')); docs=d.get('documents', []); print('docs=', len(docs), 'next_id=', d.get('next_id')); print([d2.get('source') for d2 in docs])"
- python3 - <<'PYEOF'
import os
import pathlib
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
docs = data.get("documents", [])
errors = []

if not docs:
    errors.append("documents is empty")

for doc in docs:
    doc_id = doc.get("id", "?")
    if "ocr_quality" not in doc:
        errors.append(f"missing ocr_quality in {doc_id}")
    elif doc.get("ocr_quality") != "ok":
        errors.append(f"ocr_quality should be 'ok' in {doc_id}, got {doc.get('ocr_quality')!r}")
    if "ocr_quality_reason" not in doc:
        errors.append(f"missing ocr_quality_reason in {doc_id}")
    elif doc.get("ocr_quality_reason") != "":
        errors.append(f"ocr_quality_reason should be empty string in {doc_id}, got {doc.get('ocr_quality_reason')!r}")
    if doc.get("ocr_reattempted") is not False:
        errors.append(f"ocr_reattempted should be False in {doc_id}, got {doc.get('ocr_reattempted')!r}")

if errors:
    print("FAIL:")
    print("\\n".join(errors))
    sys.exit(1)

print("ocr_quality assertions: OK")
PYEOF
- source "\$SMOKE_CASE/.smoke-fulltext.sh"
- assert_mirror_full "большой-договор.pdf"
- grep -E '^(### )?.*intake (plan|apply):' "\$SMOKE_CASE/.vassal/history.md"

СВЕРКА С ФИКСТУРОЙ:
- python3 - <<'PYEOF'
import os
import pathlib
import re
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
plugin_root = pathlib.Path(os.environ["PLUGIN_ROOT"])
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
fixture = yaml.safe_load(
    (plugin_root / "tests/fixtures/dummy-case/expected/index-after-intake.yaml").read_text(encoding="utf-8")
)
docs = data.get("documents", [])
errors = []

checks = fixture.get("_check", [])


def get_path(obj, path):
    value = obj
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def parse_selector(field):
    match = re.fullmatch(r"documents\[(.+)\](?:\.(.+))?", field or "")
    if not match:
        return None, None
    return match.group(1), match.group(2)


def doc_matches_filter(doc, expr):
    not_null_match = re.fullmatch(r"([A-Za-z0-9_.]+)\s*!=\s*null", expr)
    if not_null_match:
        return get_path(doc, not_null_match.group(1)) is not None

    string_eq_match = re.fullmatch(r"([A-Za-z0-9_.]+)\s*==\s*'([^']*)'", expr)
    if string_eq_match:
        return get_path(doc, string_eq_match.group(1)) == string_eq_match.group(2)

    bool_eq_match = re.fullmatch(r"([A-Za-z0-9_.]+)\s*==\s*(true|false)", expr)
    if bool_eq_match:
        return get_path(doc, bool_eq_match.group(1)) is (bool_eq_match.group(2) == "true")

    regex_match = re.fullmatch(r"([A-Za-z0-9_.]+)\s*~\s*/((?:\\/|[^/])*)/([a-z]*)", expr)
    if regex_match:
        pattern = regex_match.group(2).replace(r"\/", "/")
        flags = re.IGNORECASE if "i" in regex_match.group(3) else 0
        value = get_path(doc, regex_match.group(1))
        return isinstance(value, str) and re.search(pattern, value, flags) is not None

    raise ValueError(f"unsupported selector filter: {expr}")

for check in checks:
    field = check.get("field")
    expected = check.get("expected")
    kind = check.get("kind")

    if field == "version":
        if "version" not in data:
            errors.append("missing top-level field: version")
        elif expected is not None and data.get("version") != expected:
            errors.append(f"version should be {expected!r}, got {data.get('version')!r}")
    elif field == "next_id":
        if "next_id" not in data:
            errors.append("missing top-level field: next_id")
        elif kind == "integer >= 7":
            next_id = data.get("next_id")
            if not isinstance(next_id, int) or next_id < 7:
                errors.append(f"next_id should be integer >= 7, got {next_id!r}")
    elif field == "documents":
        if "documents" not in data:
            errors.append("missing top-level field: documents")
        elif kind == "non-empty list" and (not isinstance(docs, list) or not docs):
            errors.append("documents must be a non-empty list")
    elif field == "documents[*].id":
        for doc in docs:
            doc_id = doc.get("id")
            if not isinstance(doc_id, str) or not re.fullmatch(r"doc-\d+", doc_id):
                errors.append(f"documents[*].id must match /^doc-\\\\d+$/, got {doc_id!r}")
    elif field == "documents[*].source":
        for doc in docs:
            doc_id = doc.get("id", "?")
            if doc.get("source") != expected:
                errors.append(f"source should be {expected!r} in {doc_id}, got {doc.get('source')!r}")
    elif field == "documents[*].origin.batch":
        for doc in docs:
            doc_id = doc.get("id", "?")
            origin = doc.get("origin")
            batch = origin.get("batch") if isinstance(origin, dict) else None
            if not isinstance(origin, dict):
                errors.append(f"origin must be an object in {doc_id}")
            elif kind == "starts with 'intake-'" and (not isinstance(batch, str) or not batch.startswith("intake-")):
                errors.append(f"origin.batch should start with 'intake-' in {doc_id}, got {batch!r}")
    elif field == "documents[*].mirror_stale":
        for doc in docs:
            doc_id = doc.get("id", "?")
            if doc.get("mirror_stale") is not expected:
                errors.append(f"mirror_stale should be {expected!r} in {doc_id}, got {doc.get('mirror_stale')!r}")
    elif field == "documents[*].mirror":
        for doc in docs:
            doc_id = doc.get("id", "?")
            mirror = doc.get("mirror")
            if kind == "matches /^\\.vassal/mirrors/doc-\\d+\\.md$/" and (
                not isinstance(mirror, str) or not re.fullmatch(r"\.vassal/mirrors/doc-\d+\.md", mirror)
            ):
                errors.append(f"mirror has unexpected format in {doc_id}: {mirror!r}")
    elif field == "documents[*].file":
        for doc in docs:
            doc_id = doc.get("id", "?")
            file_path = doc.get("file")
            if kind == "starts with 'Материалы от клиента/'" and (
                not isinstance(file_path, str) or not file_path.startswith("Материалы от клиента/")
            ):
                errors.append(f"file should start with 'Материалы от клиента/' in {doc_id}, got {file_path!r}")
    elif field == "documents[*].ocr_quality":
        for doc in docs:
            doc_id = doc.get("id", "?")
            if doc.get("ocr_quality") != expected:
                errors.append(f"ocr_quality should be {expected!r} in {doc_id}, got {doc.get('ocr_quality')!r}")
    elif field == "documents[*].ocr_quality_reason":
        for doc in docs:
            doc_id = doc.get("id", "?")
            if doc.get("ocr_quality_reason") != expected:
                errors.append(
                    f"ocr_quality_reason should be {expected!r} in {doc_id}, got {doc.get('ocr_quality_reason')!r}"
                )
    elif field == "documents[*].ocr_reattempted":
        for doc in docs:
            doc_id = doc.get("id", "?")
            if doc.get("ocr_reattempted") is not expected:
                errors.append(
                    f"ocr_reattempted should be {expected!r} in {doc_id}, got {doc.get('ocr_reattempted')!r}"
                )
    elif field.startswith("documents["):
        try:
            filter_expr, selected_field = parse_selector(field)
            if filter_expr is None:
                raise ValueError(f"invalid selector field: {field}")
            selected_docs = [doc for doc in docs if doc_matches_filter(doc, filter_expr)]
        except ValueError as exc:
            print(str(exc))
            sys.exit(1)

        if kind == "not present":
            if selected_docs:
                errors.append(f"{field} should be absent, got {len(selected_docs)} matching document(s)")
        elif kind == "present exactly once":
            if len(selected_docs) != 1:
                errors.append(f"{field} should match exactly once, got {len(selected_docs)}")
        elif kind == "not empty":
            if not selected_docs:
                errors.append(f"_check '{field}': selector matched 0 documents (expected at least 1 for '{kind}' check)")
                continue
            for doc in selected_docs:
                doc_id = doc.get("id", "?")
                value = get_path(doc, selected_field) if selected_field else doc
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{field} should be a non-empty string in {doc_id}, got {value!r}")
        elif kind == "ends with '.pdf'":
            if not selected_docs:
                errors.append(f"_check '{field}': selector matched 0 documents (expected at least 1 for '{kind}' check)")
                continue
            for doc in selected_docs:
                doc_id = doc.get("id", "?")
                value = get_path(doc, selected_field) if selected_field else doc
                if not isinstance(value, str) or not value.endswith(".pdf"):
                    errors.append(f"{field} should end with '.pdf' in {doc_id}, got {value!r}")
        elif kind == "matches /^\\.vassal/mirrors/doc-\\d+\\.md$/":
            if not selected_docs:
                errors.append(f"_check '{field}': selector matched 0 documents (expected at least 1 for '{kind}' check)")
                continue
            for doc in selected_docs:
                doc_id = doc.get("id", "?")
                value = get_path(doc, selected_field) if selected_field else doc
                if not isinstance(value, str) or not re.fullmatch(r"\.vassal/mirrors/doc-\d+\.md", value):
                    errors.append(f"{field} has unexpected format in {doc_id}: {value!r}")
        elif kind == "matches /^doc-\\d+$/":
            if not selected_docs:
                errors.append(f"_check '{field}': selector matched 0 documents (expected at least 1 for '{kind}' check)")
                continue
            for doc in selected_docs:
                doc_id = doc.get("id", "?")
                value = get_path(doc, selected_field) if selected_field else doc
                if not isinstance(value, str) or not re.fullmatch(r"doc-\d+", value):
                    errors.append(f"{field} should match /^doc-\\\\d+$/ in {doc_id}, got {value!r}")
        elif kind == "integer >= 1":
            if not selected_docs:
                errors.append(f"_check '{field}': selector matched 0 documents (expected at least 1 for '{kind}' check)")
                continue
            for doc in selected_docs:
                doc_id = doc.get("id", "?")
                value = get_path(doc, selected_field) if selected_field else doc
                if not isinstance(value, int) or value < 1:
                    errors.append(f"{field} should be integer >= 1 in {doc_id}, got {value!r}")
        elif kind == "starts with 'Материалы от клиента/Без даты — '":
            if not selected_docs:
                errors.append(f"_check '{field}': selector matched 0 documents (expected at least 1 for '{kind}' check)")
                continue
            for doc in selected_docs:
                doc_id = doc.get("id", "?")
                value = get_path(doc, selected_field) if selected_field else doc
                if not isinstance(value, str) or not value.startswith("Материалы от клиента/Без даты — "):
                    errors.append(
                        f"{field} should start with 'Материалы от клиента/Без даты — ' in {doc_id}, got {value!r}"
                    )
        else:
            print(f"unknown selector _check kind: {kind} for field {field}")
            sys.exit(1)
    else:
        print(f"unknown _check field: {field}")
        sys.exit(1)

if errors:
    print("FAIL:")
    print("\\n".join(errors))
    sys.exit(1)

print("fixture contract checks: OK")
PYEOF
- grep -Eq '^.*intake plan: \\.vassal/plans/intake-.*\\.md, файлов в плане: [0-9]+' "\$SMOKE_CASE/.vassal/history.md"
- grep -Eq '^.*intake apply: batch=intake-.*файлов: [0-9]+, комплектов: [0-9]+, сирот: [0-9]+, план: \\.vassal/plans/intake-.*\\.md' "\$SMOKE_CASE/.vassal/history.md"

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
