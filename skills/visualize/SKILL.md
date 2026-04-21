---
name: visualize
description: >
  Генерация sidecar-визуализации через $imagegen. Вызывается из других скиллов — не имеет
  собственной slash-команды. Триггеры из родительских скиллов: «нарисуй схему сторон»,
  «сделай инфографику», «граф договорных связей», «визуальный таймлайн». Производит
  растровый PNG-файл в .vassal/visuals/ — НЕ встраивает картинку в юридические документы.
---

# Visualize — Генерация sidecar-визуализации

Вызывается из других скиллов после подтверждения Сюзерена. Производит PNG в `.vassal/visuals/`. Не пишет в реестр документов дела и не линкует картинку из юридических документов.

## Предварительные условия

- Существует `[CASE_ROOT]/.vassal/case.yaml`
- Для основного Branch A у юриста один раз выполнен `codex features enable image_generation`
- Если feature не включён глобально или companion не поддерживает такой вызов, используй Branch B

## Параметры от родительского скилла

- `VISUAL_TYPE`: `parties-scheme` | `contract-graph` | `timeline-infographic`
- `CONTEXT`: сжатый фактический контекст для визуализации

## Алгоритм — Branch A (основной)

1. Прочитай `skills/codex-invocation/SKILL.md`.
2. Собери prompt из `prompts/imagegen-visualizer.md`, подставь:
   - `case_root`: абсолютный путь к делу
   - `plugin_root`: по 3-tier fallback из `skills/codex-invocation/SKILL.md`
   - `visual_type`: значение `VISUAL_TYPE`
   - `visual_context`: значение `CONTEXT`
   - `extra_constraints`: пустая строка, если дополнительных ограничений нет
   - `report_contract`: секция отчёта из `prompts/_preamble.md`
3. Проверь, что все плейсхолдеры раскрыты:
   - `grep -c "{{" prompt.txt`
   - ожидаемое значение: `0`
4. Диспатч задачу через companion:
   - `node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task --background --write --effort medium "<PROMPT>"`
5. Мониторь статус по шаблону polling из `skills/codex-invocation/SKILL.md` с паузой `25` секунд между проверками.
6. Получи итоговый отчёт:
   - `node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs result "$TASK"`
7. Получи `sessionId` из JSON результата:
   - `node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs result "$TASK" --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['job']['sessionId'])"`
8. Резолвни `CODEX_HOME` как `${CODEX_HOME:-$HOME/.codex}` и найди PNG по паттерну:
   - `$CODEX_HOME/generated_images/{sessionId}/ig_*.png`
   - если файлов несколько, бери последний по `mtime`
   - если файл не найден, сначала проверь переопределение `CODEX_HOME`, затем заверши со статусом `BLOCKED` и приложи отчёт Codex
9. Создай `[CASE_ROOT]/.vassal/visuals/`, если директории ещё нет.
10. Скопируй PNG в `[CASE_ROOT]/.vassal/visuals/{ГГГГ-ММ-ДД}-{visual_type}.png`.
    - если имя занято, добавь суффикс `-2`, затем `-3` и далее
    - оригинал в `$CODEX_HOME/generated_images/...` не изменяй
11. Сохрани лог в `.vassal/codex-logs/{дата-время}-imagegen-{visual_type}.md`.
    - лог включает полный prompt и итоговый отчёт Codex
12. Верни родительскому скиллу абсолютный путь к скопированному PNG.

## Алгоритм — Branch B (fallback)

Используй этот путь, если `image_generation` не включён глобально или companion не даёт рабочий вызов.

1. Собери prompt тем же способом, что и в Branch A.
2. Запусти Codex напрямую:

```bash
codex exec \
  --skip-git-repo-check \
  --sandbox workspace-write \
  --enable image_generation \
  -C "[CASE_ROOT]" \
  -c model_reasoning_effort=medium \
  "<PROMPT>"
```

3. Предупреди Сюзерена: `Branch B — синхронный вызов, Claude-main блокируется на ~30-90 секунд во время генерации.`
4. Из stderr/stdout извлеки `session id: <UUID>`.
5. Дальше выполни те же шаги копирования, логирования и возврата результата, что в Branch A:
   - резолв `CODEX_HOME`
   - поиск `$CODEX_HOME/generated_images/{sessionId}/ig_*.png`
   - создание `.vassal/visuals/`
   - копирование с защитой от коллизий имени
   - сохранение лога
   - возврат абсолютного пути

## Жёсткие правила sidecar-only

- `visualize` не меняет реестр документов дела
- `visualize` не пишет файлы в корень дела
- `visualize` не модифицирует `.md`-файлы дела
- PNG создаётся только в `.vassal/visuals/`
- Не линкуй PNG из `Правовое заключение.md`, позиции, `Хронология дела.md` и любых других юридических документов

## Ручное приобщение картинки — только opt-in

Если юрист захочет использовать картинку в отдельном документе, это делается вручную и осознанно. Сам скилл `visualize` ничего не встраивает и не автоматизирует.

## Fallback без $imagegen

Если `$imagegen` недоступен и в Branch A, и в Branch B, сообщи Сюзерену:

`Визуализация недоступна — убедись, что codex features enable image_generation выполнен, или используй Branch B через codex exec с --enable image_generation.`
