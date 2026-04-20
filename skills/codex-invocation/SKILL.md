---
name: codex-invocation
description: >
  Единый контракт вызова Codex CLI для vassal-litigator. Используй этот скилл, когда
  любой другой скилл плагина должен диспатчить задачу в Codex: файловый apply на medium,
  таймлайн на high, визуализацию через image_gen, контрольное ревью на xhigh. Содержит
  точные команды, monitor-polling, stale-lock workaround, контракт путей [PLUGIN_ROOT] /
  [CASE_ROOT] и резолв generated image path через sessionId.
---

# Codex invocation — единый контракт vassal-litigator

Этот скилл описывает, **как Claude-main вызывает Codex** для ролей плагина vassal-litigator. Он не заменяет профильные скиллы (`intake`, `timeline`, `legal-review` и т.д.), а задаёт общий транспорт, флаги, правила резолвинга путей и отчётности.

## Когда активируется

Используй этот скилл, если задача требует одного из четырёх Codex-ролей плагина:

- `file-executor` — файловый apply-пайплайн, `medium`, с `--write`
- `timeline-builder` — сборка хронологии, `high`, с `--write`
- `imagegen-visualizer` — sidecar-визуализация через `image_gen`, `medium`
- `analytical-reviewer` — контрольное ревью аналитики, `xhigh`, **без** `--write`

## Предусловия

### 1. Однократный логин

Если это первый вызов Codex на машине юриста, сначала нужен логин:

```bash
!codex login
```

Если логин уже делался, повторять не нужно.

### 2. Версия companion

Hardcoded path для companion в v0.5.0:

```bash
~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs
```

Проверка:

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task --help
```

Если получаешь `ENOENT`, почти всегда причина в том, что openai-codex обновился и версия в пути больше не совпадает. В v0.5.0 путь правится **здесь**, в одном месте.

### 3. Feature-flag для визуализатора

Для основного Branch A у роли `imagegen-visualizer` юрист должен один раз включить feature:

```bash
codex features enable image_generation
```

Это включает `features.image_generation = true` в `~/.codex/config.toml`. Если юрист не хочет включать feature глобально, используй Branch B из раздела про визуализатор.

## Роли и точные команды

Во всех командах ниже:

- `[CASE_ROOT]` — абсолютный путь к папке дела
- `<PROMPT>` — уже отрендеренный промпт, где Claude-main **заменил** `[PLUGIN_ROOT]` и `[CASE_ROOT]` на абсолютные пути
- companion path фиксирован на `1.0.3`

### 1. `file-executor` — medium, apply, `--write`

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task \
  --background \
  --write \
  --effort medium \
  "<PROMPT>"
```

Используется для:

- `file-executor-intake`
- `file-executor-update-index`
- `file-executor-catalog`
- `file-executor-add-evidence`
- `file-executor-add-opponent`

### 2. `timeline-builder` — high, apply, `--write`

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task \
  --background \
  --write \
  --effort high \
  "<PROMPT>"
```

### 3. `analytical-reviewer` — xhigh, read-only

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task \
  --background \
  --effort xhigh \
  "<PROMPT>"
```

Для ревьюера `--write` не передаётся.

### 4. `imagegen-visualizer` — два branch-варианта

#### Branch A — основной: companion + глобально включённый feature-flag

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task \
  --background \
  --write \
  --effort medium \
  "<PROMPT с вызовом image_gen>"
```

Когда использовать:

- feature `image_generation` уже включён у юриста
- нужен стандартный background-flow с Monitor polling

#### Branch B — fallback: прямой `codex exec`

```bash
codex exec \
  --skip-git-repo-check \
  --sandbox workspace-write \
  --enable image_generation \
  -C "[CASE_ROOT]" \
  -c model_reasoning_effort=medium \
  "<PROMPT с вызовом image_gen>"
```

Когда использовать:

- юрист не включил `image_generation` глобально
- нужен явный `--enable image_generation`
- допустим синхронный вызов без Monitor polling

## Monitor polling — шаблон для background-задач

Для `file-executor`, `timeline-builder`, `analytical-reviewer` и Branch A визуализатора используй один и тот же шаблон. `case`-guard обязателен: без него poll-loop заспамит вывод.

```bash
COMPANION=~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs
TASK=task-XXXX
until
  st=$(node "$COMPANION" status "$TASK" --json 2>/dev/null \
       | python3 -c "import json,sys; print(json.load(sys.stdin)['job']['status'])")
  case "$st" in
    completed|failed|cancelled) echo "codex task terminal: $st"; true ;;
    *) false ;;
  esac
do
  sleep 25
done
```

После терминального статуса:

```bash
node "$COMPANION" result "$TASK"
```

Если нужен `sessionId`, бери JSON:

```bash
node "$COMPANION" status "$TASK" --json
```

## `--resume-last`, stale-lock и `--fresh`

Обычный паттерн follow-up:

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task \
  --background \
  --write \
  --effort medium \
  --resume-last \
  "<PROMPT>"
```

Если предыдущий запуск оборвался и companion считает сессию «ещё running», `--resume-last` может зависнуть на stale-lock. В этом случае workaround только один:

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task \
  --background \
  --write \
  --effort medium \
  --fresh \
  "<PROMPT>"
```

Правило:

- follow-up по той же роли и тому же делу: сначала `--resume-last`
- stale-lock / зависшая старая сессия: сразу `--fresh`

## Контракт путей: `[PLUGIN_ROOT]` и `[CASE_ROOT]`

Это критичный инвариант v0.5.0.

- `[CASE_ROOT]` — абсолютный путь к папке дела; это `cwd` Codex-процесса
- `[PLUGIN_ROOT]` — абсолютный путь к установленному плагину vassal-litigator

Из-за того, что `cwd = [CASE_ROOT]`, относительные пути `scripts/...` и `shared/...` **запрещены**. Все обращения к файлам плагина делаются только так:

- `[PLUGIN_ROOT]/scripts/extract_text.py`
- `[PLUGIN_ROOT]/scripts/generate_table.py`
- `[PLUGIN_ROOT]/scripts/setup.sh`
- `[PLUGIN_ROOT]/shared/conventions.md`
- `[PLUGIN_ROOT]/shared/case-schema.yaml`
- `[PLUGIN_ROOT]/shared/index-schema.yaml`
- `[PLUGIN_ROOT]/shared/mirror-template.md`

### Как Claude-main получает `[CASE_ROOT]`

Базовый вариант:

```bash
CASE_ROOT="$(pwd)"
```

Это должен быть корень конкретного дела, а не корень плагина.

### Как Claude-main получает `[PLUGIN_ROOT]` — 3-tier fallback

`CLAUDE_PLUGIN_ROOT` в main-session обычно **не существует**, поэтому нужен жёстко задокументированный fallback.

#### Tier 1 — env `CLAUDE_PLUGIN_ROOT`, если уже выставлена

```bash
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
fi
```

#### Tier 2 — парсинг `~/.claude/plugins/installed_plugins.json`

Это основной путь для production-установки.

```bash
if [ -z "${PLUGIN_ROOT:-}" ]; then
  PLUGIN_ROOT="$(python3 - <<'PY'
import json
import os
import sys

path = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
try:
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
except FileNotFoundError:
    sys.exit(0)

plugins = data.get('plugins', {})
for key, entries in plugins.items():
    if not key.startswith('vassal-litigator@'):
        continue
    for entry in entries:
        install_path = entry.get('installPath')
        if install_path:
            install_path = os.path.expanduser(install_path)
            if os.path.isdir(install_path):
                print(install_path)
                raise SystemExit(0)
PY
)"
fi
```

#### Tier 3 — спросить у юриста и закешировать на текущую сессию

Если ни env, ни `installed_plugins.json` не дали путь, **первый вызов в сессии** должен остановиться с вопросом:

```text
укажи абсолютный путь к плагину vassal-litigator
```

После ответа:

- проверь, что путь абсолютный
- проверь, что внутри есть `skills/`, `shared/`, `scripts/`
- сохрани значение в session-cache и больше в этой сессии не переспрашивай

Пример простого session-cache в shell:

```bash
if [ -n "${VASSAL_PLUGIN_ROOT_CACHE:-}" ] && [ -d "$VASSAL_PLUGIN_ROOT_CACHE" ]; then
  PLUGIN_ROOT="$VASSAL_PLUGIN_ROOT_CACHE"
fi
```

Если кеш пуст:

```bash
VASSAL_PLUGIN_ROOT_CACHE="$PLUGIN_ROOT"
export VASSAL_PLUGIN_ROOT_CACHE
```

### Валидация резолвинга

Перед первым dispatch в сессии проверь:

```bash
test -f "$PLUGIN_ROOT/scripts/extract_text.py"
test -f "$PLUGIN_ROOT/shared/conventions.md"
test -d "$CASE_ROOT"
```

Если любой тест падает, не запускай Codex. Сначала `NEEDS_CONTEXT`.

## Как Claude-main собирает prompt

Оркестратор делает **prompt-assembly step** до диспатча, а не рассчитывает, что Codex сам что-то резолвит.

Формальный алгоритм:

1. Получи абсолютные `PLUGIN_ROOT` и `CASE_ROOT`.
2. Прочитай целевой шаблон prompt-файла.
3. Если первая строка шаблона содержит `{{include _preamble.md}}`, **expand include** буквальной подстановкой содержимого `prompts/_preamble.md` на место этой директивы.
4. После expand include подставь все переменные шаблона: `[PLUGIN_ROOT]`, `[CASE_ROOT]`, `{{case_root}}`, `{{plugin_root}}` и остальные `{{...}}` placeholders конкретной роли.
5. Проверь, что в собранном prompt не осталось нераскрытых `{{include ...}}` и прочих `{{...}}`.
6. Только после этого передай финальный prompt в Codex как последний аргумент `companion.mjs task` или `codex exec`.

Минимальный пример:

```bash
PROMPT_TEMPLATE="$PLUGIN_ROOT/prompts/timeline-builder.md"
PROMPT="$(cat "$PROMPT_TEMPLATE")"
PREAMBLE="$(cat "$PLUGIN_ROOT/prompts/_preamble.md")"
PROMPT="${PROMPT/\{\{include _preamble.md\}\}/$PREAMBLE}"
PROMPT="${PROMPT//\{\{case_root\}\}/$CASE_ROOT}"
PROMPT="${PROMPT//\{\{plugin_root\}\}/$PLUGIN_ROOT}"
```

Гарантийный check перед dispatch:

```bash
ASSEMBLED_PROMPT_FILE="/tmp/vassal-codex-prompt.txt"
printf '%s\n' "$PROMPT" > "$ASSEMBLED_PROMPT_FILE"
grep -n '{{' "$ASSEMBLED_PROMPT_FILE" && echo "UNRESOLVED_TEMPLATE_TOKENS"
grep -n '\[PLUGIN_ROOT\]\|\[CASE_ROOT\]' "$ASSEMBLED_PROMPT_FILE" && echo "UNRESOLVED_PATH_TOKENS"
```

Ожидание:

- `grep -n '{{' <assembled-prompt>` возвращает `0` совпадений
- `grep -n '\[PLUGIN_ROOT\]\|\[CASE_ROOT\]' <assembled-prompt>` возвращает `0` совпадений

Жёсткое правило:

- Codex не должен видеть «нераскрытые» `{{include _preamble.md}}`, `[PLUGIN_ROOT]`, `[CASE_ROOT]`, `{{case_root}}`, `{{plugin_root}}` и любые другие `{{...}}`
- если путь не удалось получить, правильный исход — `NEEDS_CONTEXT`, а не «попробую с относительным путём»

## Save Codex report

После каждого значимого Codex-dispatch Claude-main сохраняет итоговый отчёт в:

```text
[CASE_ROOT]/.vassal/codex-logs/{ГГГГ-ММ-ДД-ЧЧмм}-{role}.md
```

Это делается для финального результата конкретного dispatch, а не для каждого промежуточного poll.

Минимальный состав лога:

- `task_id`
- `role`
- `effort`
- `prompt_size_bytes`
- `stdout`
- `stderr`
- `taken_ms`
- `final_status`

Если dispatch не стартовал вовсе, лог всё равно желательно сохранить как локальный failure-report с причиной.

## Fallback без Codex

Если Codex недоступен (`network down`, `OpenAI rate limit`, companion broker не отвечает, `status=failed`, timeout, `NEEDS_CONTEXT` до старта), Claude-main не должен молча зависать.

Правило по ролям:

- файловые скиллы (`file-executor-*`) — откат на Claude-native исполнение по логике `v0.4.0`, с явным предупреждением Сюзерену, что Codex-path временно недоступен
- `timeline-builder` — skip по умолчанию; если позже отдельный skill явно задокументирует Claude-native fallback, использовать его, иначе честно вернуть, что таймлайн не собран
- `imagegen-visualizer` — skip: визуализация не создаётся, дело продолжается без sidecar-картинки
- `analytical-reviewer` — skip: показать Сюзерену, что контрольное ревью Codex не проведено

Во всех случаях:

- показать Сюзерену причину сбоя
- сохранить failure-report в `.vassal/codex-logs/`
- не подменять недоступный Codex фиктивным «успехом»

## Визуализатор: как получить путь к PNG на самом деле

Это место **обновлено по Q1 AMENDED**. Нельзя опираться на строку `GENERATED_IMAGE: <abs_path>` в stdout, потому что эмпирически Codex её не печатает стабильно.

### Реальный механизм

1. Определи `sessionId`.
2. Определи `CODEX_HOME` как `${CODEX_HOME:-$HOME/.codex}`.
3. Ищи PNG по паттерну:

```text
$CODEX_HOME/generated_images/<sessionId>/ig_*.png
```

4. Если файлов несколько, бери последний по `mtime`.
5. Claude-main **копирует** найденный PNG в `[CASE_ROOT]/.vassal/visuals/...`; исходник в `$CODEX_HOME/generated_images/...` не трогает.

### Branch A — как получить `sessionId`

Через companion status/result JSON:

```bash
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs status "$TASK" --json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['job']['sessionId'])"
```

### Branch B — как получить `sessionId`

Прямой `codex exec` печатает `session id: <UUID>` в stderr/stdout. Парсинг делается оркестратором по этой строке.

### Поиск PNG

```bash
CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"
SESSION_ID="<полученный sessionId>"
IMAGE_PATH="$(find "$CODEX_HOME_RESOLVED/generated_images/$SESSION_ID" -maxdepth 1 -type f -name 'ig_*.png' -print \
  | xargs ls -t 2>/dev/null | head -n 1)"
```

Если `IMAGE_PATH` пустой, это `BLOCKED`: не пытайся выдумывать путь, не проси Codex «сохранить ещё раз по нужному месту», не пиши в `.vassal/visuals/` напрямую из imagegen-подзадачи.

## Что нельзя делать

- Не запускать файловые роли без `--background`
- Не опираться на относительные `scripts/...` и `shared/...`
- Не использовать `--write` для `analytical-reviewer`
- Не ожидать, что `$imagegen` сам сохранит файл по пути из промпта
- Не считать `GENERATED_IMAGE:` гарантированным интерфейсом
- Не пропускать `--fresh`, если stale-lock уже проявился

## Результат, который ожидает Claude-main

Этот скилл не задаёт содержание профильного ответа роли, но задаёт транспортный контракт:

- роль выбирается строго из четырёх перечисленных выше
- пути всегда переданы как абсолютные
- cwd всегда равен `[CASE_ROOT]`
- companion path всегда фиксирован на `1.0.3`, пока Ф7 не внесёт следующую миграцию
- для визуализатора путь к PNG резолвится через `sessionId` + `$CODEX_HOME/generated_images/...`
