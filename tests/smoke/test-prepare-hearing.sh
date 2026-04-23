#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-prepare-hearing.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки prepare-hearing
по ветке Ф5c: Opus-subagent -> multi-document markdown -> N docx + notes.md.
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

SMOKE_CASE="/tmp/smoke-vassal-prepare-hearing-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat > "$SMOKE_CASE/.fixture-prepare-hearing-opus.md" <<'EOF'
## Заметки
### Blue team
- Подтвердить приобщение переписки и акта сверки.
- Сделать акцент на признании долга и соблюдении досудебного порядка.

### Red team
- Оппонент будет спорить о размере неустойки.
- Возможна атака на допустимость части переписки.

## Ходатайство 1: О приобщении дополнительных доказательств
Просим приобщить к материалам дела переписку сторон, акт сверки и платёжные документы,
поскольку они подтверждают признание долга, размер задолженности и соблюдение
досудебного порядка.
READY_FOR_DOCX: processual

## Ходатайство 2: Об истребовании оригиналов документов у ответчика
Просим истребовать у ответчика оригиналы товарных накладных и внутренние документы
приёмки, на которые он ссылается в возражениях, поскольку без них невозможно полно
оценить его доводы по количеству и качеству поставки.
READY_FOR_DOCX: processual
EOF

cat <<'EOF' | sed \
    -e "s|__SMOKE_CASE__|$SMOKE_CASE|g" \
    -e "s|__PLUGIN_ROOT__|$PLUGIN_ROOT|g"
=== SMOKE: prepare-hearing (contract 3.1b -> 3.2) ===

РАБОЧАЯ ДИРЕКТОРИЯ:
__SMOKE_CASE__

ПРЕДУСЛОВИЯ:
- Claude Code запущен в окружении, где доступен `Task(model=opus)`
- Доступен formatter `arbitrum-docx`
- В этом каталоге уже выполнены `init-case`, intake и желательно `build-position`

ДЕТЕРМИНИСТИЧЕСКАЯ ЗАГОТОВКА:
- В `__SMOKE_CASE__/.fixture-prepare-hearing-opus.md` записан эталонный multi-document OUTPUT
  с двумя блоками `## Ходатайство N: ...`. Используй его как проверочную форму,
  если хочешь быстро сверить парсинг ветки 3.1b.

ШАГИ:
1. Перейди в smoke-директорию:
   cd "__SMOKE_CASE__"
2. Запусти Claude Code в этой папке.
3. Если база дела ещё не подготовлена, сначала выполни init-case + intake.
4. Выполни: /vassal-litigator-cc:prepare-hearing
5. Подтверди preview/apply.
6. Сравни Opus-output со структурой из `.fixture-prepare-hearing-opus.md`:
   - `## Заметки`
   - минимум два блока `## Ходатайство N: <тема>`
   - каждый блок завершается `READY_FOR_DOCX: processual`
7. Если main не сохраняет полный multi-document markdown сам, сохрани фактический Opus-output в `__SMOKE_CASE__/.captured-prepare-hearing-opus.md`, иначе точная сверка числа ходатайств с числом `.docx` невалидна.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- В `hearings/YYYY-MM-DD/` создан `notes.md`
- В том же каталоге создано ровно `N` файлов `ходатайство-*.docx`
- Количество `.docx` равно количеству блоков `## Ходатайство N:`
- Каждый `.docx` непустой

ПРОВЕРКА:
- find . -path '*/hearings/*/notes.md' -type f
- find . -path '*/hearings/*/ходатайство-*.docx' -type f
- python3 - <<'PYEOF'
import pathlib
import re
import sys

notes = list(pathlib.Path('.').glob('**/hearings/*/notes.md'))
motions = list(pathlib.Path('.').glob('**/hearings/*/ходатайство-*.docx'))
captured = pathlib.Path('.captured-prepare-hearing-opus.md')

print('notes=', notes)
print('motions=', motions)

if not notes:
    print('FAIL: notes.md not found')
    sys.exit(1)
if not captured.is_file():
    print('FAIL: missing .captured-prepare-hearing-opus.md with actual Opus output')
    sys.exit(1)

motion_blocks = re.findall(r'^## Ходатайство \d+: .+$', captured.read_text(encoding='utf-8'), flags=re.MULTILINE)
print('captured_motion_blocks=', len(motion_blocks))

if len(motion_blocks) == 0:
    print('FAIL: no motion blocks found in captured Opus output')
    sys.exit(1)
if len(motions) != len(motion_blocks):
    print(f'FAIL: expected exactly {len(motion_blocks)} motion docx files, got {len(motions)}')
    sys.exit(1)
for path in motions:
    if path.stat().st_size <= 0:
        print('FAIL: empty docx', path)
        sys.exit(1)
PYEOF

ОЧИСТКА:
rm -rf "__SMOKE_CASE__"
EOF
