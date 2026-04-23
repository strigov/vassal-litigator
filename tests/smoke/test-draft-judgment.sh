#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-draft-judgment.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки draft-judgment
по ветке Ф5d: Opus-subagent -> single-document markdown -> Sonnet-subagent -> docx.
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

SMOKE_CASE="/tmp/smoke-vassal-draft-judgment-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat > "$SMOKE_CASE/.fixture-draft-judgment-opus.md" <<'EOF'
## Установил
Суд установил наличие договора поставки, факт передачи товара и наличие задолженности,
подтверждённой перепиской сторон и платёжными документами.

## Оценка доказательств
Представленные истцом документы взаимно согласуются, а возражения ответчика не подтверждены
надлежащими доказательствами.

## Правовая квалификация
К спорным отношениям подлежат применению положения главы 30 Гражданского кодекса
Российской Федерации о договоре поставки и общие положения об обязательствах.

## Постановил
Иск удовлетворить частично, взыскать основной долг и уменьшенную неустойку,
распределив судебные расходы пропорционально удовлетворённым требованиям.
READY_FOR_DOCX: processual
EOF

cat <<'EOF' | sed \
    -e "s|__SMOKE_CASE__|$SMOKE_CASE|g" \
    -e "s|__PLUGIN_ROOT__|$PLUGIN_ROOT|g"
=== SMOKE: draft-judgment (contract 3.1a -> 3.2) ===

РАБОЧАЯ ДИРЕКТОРИЯ:
__SMOKE_CASE__

ПРЕДУСЛОВИЯ:
- Claude Code запущен в окружении, где доступен `Task(model=opus)`
- Доступен formatter `arbitrum-docx`
- В этом каталоге уже выполнены `init-case`, intake и хотя бы базовая аналитика дела

ДЕТЕРМИНИСТИЧЕСКАЯ ЗАГОТОВКА:
- В `__SMOKE_CASE__/.fixture-draft-judgment-opus.md` записан эталонный single-document OUTPUT
  с допустимыми секциями и финальной строкой `READY_FOR_DOCX: processual`.

ШАГИ:
1. Перейди в smoke-директорию:
   cd "__SMOKE_CASE__"
2. Запусти Claude Code в этой папке.
3. Если база дела ещё не подготовлена, сначала выполни init-case + intake.
4. Выполни: /vassal-litigator-cc:draft-judgment
5. Подтверди preview/apply.
6. При необходимости сверяй форму Opus-output с `.fixture-draft-judgment-opus.md`.
7. Если main не сохраняет markdown-артефакт сам, сохрани фактический Opus-output в `__SMOKE_CASE__/.captured-draft-judgment-opus.md`, иначе проверка маркера `READY_FOR_DOCX` не считается пройденной.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- В корне дела создан `YYYY-MM-DD draft-judgment.docx`
- Файл `.docx` непустой
- `READY_FOR_DOCX: processual` присутствует либо в промежуточном markdown-артефакте,
  если main его сохраняет, либо в захваченном subagent-output

ПРОВЕРКА:
- find . -name '*draft-judgment.docx' -type f
- python3 - <<'PYEOF'
import pathlib
import sys

files = list(pathlib.Path('.').glob('**/*draft-judgment.docx'))
if not files:
    print('FAIL: draft-judgment docx not found')
    sys.exit(1)

path = files[0]
size = path.stat().st_size
print(path, size)
if size <= 0:
    sys.exit(1)
PYEOF
- python3 - <<'PYEOF'
import pathlib
import sys

candidate_markdown_files = [
    path for path in pathlib.Path('.').glob('**/*draft-judgment*.md')
    if path.name != '.fixture-draft-judgment-opus.md'
]
captured = pathlib.Path('.captured-draft-judgment-opus.md')
print('candidate_markdown_files=', candidate_markdown_files)
print('captured_file=', captured if captured.exists() else None)

source = candidate_markdown_files[0] if candidate_markdown_files else (captured if captured.is_file() else None)
if source is None:
    print('FAIL: neither persisted markdown nor .captured-draft-judgment-opus.md found')
    sys.exit(1)

text = source.read_text(encoding='utf-8')
has_ready = text.rstrip().endswith('READY_FOR_DOCX: processual')
print('ready_source=', source)
print('has_ready_for_docx=', has_ready)
if not has_ready:
    print('FAIL: READY_FOR_DOCX: processual missing in Opus output')
    sys.exit(1)
PYEOF

ОЧИСТКА:
rm -rf "__SMOKE_CASE__"
EOF
