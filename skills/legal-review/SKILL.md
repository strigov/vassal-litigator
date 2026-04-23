---
name: legal-review
description: >
  Первичный правовой анализ дела с итогом в markdown и .docx. Используй, когда юрист
  просит «проанализировать дело», «сделать правовой анализ», «проверить сроки»,
  «оценить перспективы», «проверить досудебный порядок» или «дать правовую оценку».
  Ветка Ф5a: Sonnet-main оркестрирует, Opus-subagent делает анализ по контракту 3.1a,
  Sonnet-subagent оформляет .docx через arbitrum-docx по контракту 3.2.
---

# legal-review — Первичный правовой анализ

Скилл работает по паттерну `Sonnet-main -> Opus-subagent -> Sonnet-subagent -> arbitrum-docx` и следует контрактам из [shared/subagent-dispatch.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/subagent-dispatch.md). Main-Sonnet не вставляет тексты документов inline: в субагентные вызовы передаются только абсолютные пути.

Итог Ф5a:
- markdown-оригинал: `.vassal/analysis/legal-review-YYYY-MM-DD.md`
- `.docx`: `.vassal/analysis/legal-review-YYYY-MM-DD.docx`

## Предусловия

- Существует `.vassal/case.yaml`.
- Существует `.vassal/index.yaml`.
- Есть хотя бы одно зеркало в `.vassal/mirrors/doc-*.md`.
- Доступен `Task(model=opus)`.
- Доступен formatter `arbitrum-docx` по прямой ветке контракта 3.2 или через fallback main-Sonnet.

## Переменные сессии

Определи в начале:

- `today` = текущая дата `YYYY-MM-DD`
- `analysis_dir` = `<case_root>/.vassal/analysis`
- `md_path` = `{{analysis_dir}}/legal-review-{{today}}.md`
- `docx_path` = `{{analysis_dir}}/legal-review-{{today}}.docx`

## Фаза 1 — Preview (main-Sonnet)

1. Прочитай `.vassal/case.yaml` и `.vassal/index.yaml`.
2. Найди доступные источники:
   - `.vassal/mirrors/doc-*.md`
   - при наличии — предыдущие аналитические артефакты из `.vassal/analysis/*.md`
3. Если `.vassal/index.yaml` пуст, не содержит документов, или после сверки с `.vassal/mirrors/doc-*.md` не осталось ни одного доступного зеркала документа, верни `SKILL_UNAVAILABLE` с reason `no documents` и остановись без создания выходных файлов.
4. Покажи Сюзерену короткий preview:
   - какие файлы пойдут в контекст Opus-subagent;
   - что будет создано: `{{md_path}}` и `{{docx_path}}`;
   - что итог идёт по single-document ветке 3.1a с финальной строкой `READY_FOR_DOCX: analytical`.
5. Дождись подтверждения.

## Фаза 2 — Apply (main-Sonnet + Opus-subagent + Sonnet-subagent)

1. Перед любым `Task(...)` ещё раз проверь, что `.vassal/index.yaml` содержит документы и список доступных `.vassal/mirrors/doc-*.md` не пуст; если документов нет, верни `SKILL_UNAVAILABLE` с reason `no documents` и остановись без создания выходных файлов.
2. Собери prompt Opus-subagent строго по контрактам 3.0 и 3.1a:
   - `ROLE`: `Ты юрист-аналитик в скилле legal-review.`
   - `THINKING`: `think hard` по умолчанию или override из [shared/conventions.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/conventions.md).
   - `CONTEXT`:
     - `case_root`
     - абсолютные пути к `.vassal/case.yaml`, `.vassal/index.yaml`
     - абсолютные пути к `.vassal/mirrors/doc-*.md`
     - при наличии — абсолютные пути к `.vassal/analysis/*.md`
   - `TASK`:
     - выполнить первичный правовой анализ дела без галлюцинаций;
     - разобрать квалификацию, ключевые правовые вопросы, риски и итоговые выводы;
     - каждый юридический вывод оформлять в аудируемом формате из [shared/conventions.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/conventions.md);
     - включить `## Схема сторон` с блоком ````mermaid```;
     - использовать только допустимые верхнеуровневые секции:
       - `## Квалификация`
       - `## Схема сторон`
       - `## Анализ`
       - `## Выводы`
   - `OUTPUT`: единый markdown; последняя строка строго `READY_FOR_DOCX: analytical`.
3. Вызови `Task` с параметрами:
   - `subagent_type: "general-purpose"`
   - `model: "opus"`
   - `description`: 3-5 слов
4. Проверь OUTPUT до записи на диск:
   - markdown не пустой;
   - есть ровно одна строка `READY_FOR_DOCX: analytical`, и она последняя;
   - верхнеуровневые заголовки `## ` ограничены только списком:
     - `## Квалификация`
     - `## Схема сторон`
     - `## Анализ`
     - `## Выводы`
   - присутствует `## Схема сторон`;
   - в секции `## Схема сторон` есть блок ````mermaid```.
5. Если хотя бы одна проверка не проходит, перезапусти Opus-subagent один раз с явным напоминанием о контракте 3.1a, допустимых секциях и финальной строке `READY_FOR_DOCX: analytical`. Если второй ответ невалиден — остановись и покажи блокер.
6. Сохрани валидный markdown-оригинал как есть в `{{md_path}}`.
7. Подготовь вход для Sonnet-subagent по контракту 3.2:
   - `markdown_input` = markdown без последней строки `READY_FOR_DOCX: analytical`
   - `case_meta` = поля из `.vassal/case.yaml`: `court`, `case_number`, `judge`, `our_party`, `our_client`, `other_parties`
   - `out_dir` = `{{analysis_dir}}`
   - `doc_name` = `legal-review-{{today}}.docx`
8. Запусти Sonnet-subagent по контракту 3.2. Если он возвращает `SKILL_UNAVAILABLE`, main-Sonnet сам вызывает `arbitrum-docx` с теми же `doc_type`, `header`, `title`, `body`.
9. Ожидаемый итог ветки 3.2: абсолютный путь к созданному `.docx`.

## Фаза 3 — Verify (main-Sonnet)

1. Проверь, что существуют:
   - `{{md_path}}`
   - `{{docx_path}}`
2. Прочитай `{{md_path}}` и проверь:
   - есть `## Схема сторон`;
   - есть блок ````mermaid```;
   - последняя строка строго `READY_FOR_DOCX: analytical`;
   - нет верхнеуровневых `## ` секций вне разрешённого списка.
3. Проверь `{{docx_path}}`:
   - файл существует;
   - файл не пустой.
4. Покажи Сюзерену короткое резюме:
   - путь к markdown-оригиналу;
   - путь к `.docx`;
   - перечень верхнеуровневых секций.

## Дисциплина

- Не использовать sidecar-изображения и отдельные графические preview.
- Не использовать markdown-only ветку 3.1c и не пропускать Sonnet-subagent.
- Не вставлять тексты зеркал inline в prompt main-Sonnet.
- Не добавлять верхнеуровневые `## ` секции вне списка Ф5a.
- Не заменять `arbitrum-docx` ручной сборкой `.docx`.

## Блокер

Если `Task(model=opus)` недоступен, дважды возвращает невалидный OUTPUT, или formatter-ветка 3.2 не смогла создать `.docx` даже после main-fallback:

- сообщи Сюзерену, какая именно проверка не прошла;
- не подменяй Opus-анализ или formatter ручной генерацией;
- не записывай частичный `.docx`.
