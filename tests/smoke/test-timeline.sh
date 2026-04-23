#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-timeline.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение и выводит шаги для ручной проверки timeline
по контракту 3.1c: Opus-subagent -> markdown-only + Mermaid Gantt.
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

SMOKE_CASE="/tmp/smoke-vassal-timeline-$(date +%s)"

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"

cat <<'EOF' | sed \
    -e "s|__SMOKE_CASE__|$SMOKE_CASE|g" \
    -e "s|__PLUGIN_ROOT__|$PLUGIN_ROOT|g"
=== SMOKE: timeline (contract 3.1c) ===

РАБОЧАЯ ДИРЕКТОРИЯ:
__SMOKE_CASE__

ПРЕДУСЛОВИЯ:
- Claude Code запущен в окружении, где доступен \`Task(model=opus)\`
- В этом каталоге уже выполнены \`init-case\` и intake на fixture-документах,
  либо ты сделаешь это перед запуском timeline

ШАГИ:
1. Перейди в smoke-директорию:
   cd "__SMOKE_CASE__"
2. Запусти Claude Code в этой папке.
3. Если intake ещё не выполнен в этом каталоге, сначала выполни init-case + intake на fixture-документах.
4. Выполни: /vassal-litigator-cc:timeline
5. В preview выбери политику extend или rebuild.
6. Подтверди apply.

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- В корне дела создан или обновлён файл "*Хронология дела.md"
- Файл создан по markdown-only ветке 3.1c: без \`READY_FOR_DOCX\`
- Внутри файла есть блок \`\`\`mermaid\` и ключевое слово \`gantt\`
- .vassal/case.yaml обновлён: заполнен timeline
- Никакие .docx для timeline не создаются

ПРОВЕРКА:
- find . -name '*Хронология дела.md' -type f
- python3 - <<'PYEOF'
import pathlib
import sys

files = list(pathlib.Path('.').glob('**/*Хронология дела.md'))
if not files:
    print('FAIL: timeline markdown not found')
    sys.exit(1)

path = files[0]
text = path.read_text(encoding='utf-8')
checks = {
    'mermaid': '```mermaid' in text,
    'gantt': 'gantt' in text,
    'ready_for_docx_absent': 'READY_FOR_DOCX' not in text,
}
print(path)
print(checks)
if not all(checks.values()):
    sys.exit(1)
PYEOF
- python3 - <<'PYEOF'
import pathlib
import sys
import yaml

files = list(pathlib.Path('.').glob('**/.vassal/case.yaml'))
if not files:
    print('FAIL: case.yaml not found')
    sys.exit(1)

data = yaml.safe_load(files[0].read_text(encoding='utf-8'))
timeline = data.get('timeline', [])
print('timeline_items=', len(timeline))
if not timeline:
    sys.exit(1)
PYEOF
- python3 - <<'PYEOF'
import pathlib
import sys

files = list(pathlib.Path('.').glob('**/*Хронология*.docx'))
print('timeline_docx_files=', files)
if files:
    sys.exit(1)
PYEOF

ОЧИСТКА:
rm -rf "__SMOKE_CASE__"
EOF
