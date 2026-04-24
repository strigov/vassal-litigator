---
name: cassation
description: >
  Кассационная жалоба по single-document ветке Ф5d. Sonnet-main оркестрирует,
  Opus-subagent анализирует существенные нарушения по контракту 3.1a,
  Sonnet-subagent оформляет .docx через arbitrum-docx по контракту 3.2.
---

# cassation — Кассационная жалоба

Скилл следует контрактам из [shared/subagent-dispatch.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/subagent-dispatch.md). Итог ветки Ф5d для `cassation`: один `.docx` в корне дела.

## Предусловия

- Существует `.vassal/case.yaml`.
- Существует `.vassal/index.yaml`.
- Загружены обжалуемые судебные акты либо их зеркала.
- Доступен `Task(model=opus)`.
- Доступен formatter `arbitrum-docx`.

## Переменные сессии

Определи в начале:

- `today` = текущая дата `YYYY-MM-DD`
- `docx_path` = `<case_root>/{{today}} cassation.docx`

## Фаза 1 — Preview (main-Sonnet)

1. Прочитай `.vassal/case.yaml` и `.vassal/index.yaml`.
2. Найди источники:
   - `.vassal/mirrors/doc-*.md`
   - при наличии — `.vassal/analysis/*.md`
   - при наличии — `hearings/*/analysis.md`
3. Если `.vassal/index.yaml` пуст, не содержит документов, или после сверки с `.vassal/mirrors/doc-*.md` не осталось ни одного доступного зеркала документа, верни `SKILL_UNAVAILABLE` с reason `no documents` и остановись без создания выходных файлов.
4. Покажи Сюзерену preview:
   - какие документы попадут в контекст;
   - что итог идёт по ветке 3.1a с `READY_FOR_DOCX: processual`;
   - какой путь будет у `.docx`: `{{docx_path}}`.
5. Дождись подтверждения.

## Фаза 2 — Apply (main-Sonnet + Opus-subagent + Sonnet-subagent)

1. Перед любым `Task(...)` ещё раз проверь, что `.vassal/index.yaml` содержит документы и список доступных `.vassal/mirrors/doc-*.md` не пуст; если документов нет, верни `SKILL_UNAVAILABLE` с reason `no documents` и остановись без создания выходных файлов.
2. Собери prompt Opus-subagent по контрактам 3.0 и 3.1a:
   - `ROLE`: `Ты юрист-аналитик в скилле cassation.`
   - `THINKING`: `think hard` по умолчанию или override из [shared/conventions.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/conventions.md).
   - `CONTEXT`:
     - `case_root`
     - абсолютные пути к `.vassal/case.yaml`, `.vassal/index.yaml`
     - абсолютные пути к `.vassal/mirrors/doc-*.md`
     - при наличии — абсолютные пути к `.vassal/analysis/*.md`
     - при наличии — абсолютные пути к `hearings/*/analysis.md`
   - `TASK`:
     - проанализировать существенные нарушения права и основания кассационного обжалования;
     - использовать только допустимые верхнеуровневые секции:
       - `## Обжалуемый акт`
       - `## Существенные нарушения`
       - `## Доводы`
       - `## Требования`
   - `OUTPUT`: единый markdown; последняя строка строго `READY_FOR_DOCX: processual`.
3. Вызови `Task` с параметрами:
   - `subagent_type: "general-purpose"`
   - `model: "opus"`
   - `description`: 3-5 слов
4. Проверь OUTPUT через валидационный скрипт:
   - передай полный текст OUTPUT Opus-subagent в
     `python3 "$PLUGIN_ROOT/scripts/validate_opus_output.py" --skill cassation --contract 3.1a --stdin`;
   - скрипт должен вернуть `valid=true`.
5. Если `valid=false`, ровно один раз перезапусти Opus-subagent с напоминанием о контракте 3.1a, допустимых секциях и обязательном `READY_FOR_DOCX: processual`, затем повтори валидацию тем же скриптом.
   Если и после retry `valid=false`, покажи `errors` и останови скилл.
6. Подготовь вызов Sonnet-subagent по контракту 3.2:
   - `markdown_input` = markdown без последней строки `READY_FOR_DOCX: processual`
   - `case_meta` = поля из `.vassal/case.yaml`
   - `out_dir` = `<case_root>`
   - `doc_name` = `{{today}} cassation.docx`
7. Запусти Sonnet-subagent. При `SKILL_UNAVAILABLE` main-Sonnet сам вызывает `arbitrum-docx`.

## Фаза 3 — Verify (main-Sonnet)

1. Проверь, что существует `{{docx_path}}`.
2. Проверь, что файл не пустой.
3. Если доступен промежуточный markdown-артефакт или лог subagent-output, проверь наличие `READY_FOR_DOCX: processual`.
4. Покажи Сюзерену короткое резюме:
   - путь к `.docx`;
   - какие секции сформированы;
   - сработал ли fallback formatter-ветки.

## Дисциплина

- Не добавлять верхнеуровневые `## ` секции вне списка Ф5d.
- Не использовать ручную сборку `.docx` вместо `arbitrum-docx`.
- Не смешивать кассационные основания с апелляционной логикой переоценки доказательств.

## Блокер

Если `Task(model=opus)` недоступен, дважды возвращает невалидный OUTPUT, или formatter-ветка 3.2 не создаёт `.docx`:

- покажи Сюзерену причину;
- не записывай частичный `.docx`;
- не подменяй кассационный анализ ручной генерацией main-Sonnet.
