---
name: build-position
description: >
  Выработка правовой позиции по делу с итогом в markdown и .docx. Используй, когда юрист
  просит «выработать позицию», «подготовить аргументацию», «оценить риски»,
  «разработать стратегию» или «обновить позицию после новых документов».
  Ветка Ф5b: Sonnet-main оркестрирует, Opus-subagent делает анализ по контракту 3.1a,
  Sonnet-subagent оформляет .docx через arbitrum-docx по контракту 3.2.
---

# build-position — Выработка правовой позиции

Скилл следует контрактам из [shared/subagent-dispatch.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/subagent-dispatch.md). Main-Sonnet собирает контекст и проверяет структуру, Opus-subagent формирует позицию, Sonnet-subagent оформляет `.docx`.

Итог Ф5b:
- markdown-оригинал: `<case_root>/positions/position-vN.md`
- `.docx`: `<case_root>/positions/position-vN.docx`

## Предусловия

- Существует `.vassal/case.yaml`.
- Существует `.vassal/index.yaml`.
- Есть хотя бы одно зеркало в `.vassal/mirrors/doc-*.md`.
- Доступен `Task(model=opus)`.
- Доступен formatter `arbitrum-docx`.

## Переменные сессии

Определи в начале:

- `positions_dir` = `<case_root>/positions`
- `preview_version` = следующий свободный номер `N` по существующим `position-v*.md` и `position-v*.docx` на момент preview; это только предварительная оценка
- `version` = финальный номер `N`, атомарно зарезервированный непосредственно перед записью файлов после подтверждения
- `lock_dir` = `{{positions_dir}}/v{{version}}.lock`
- `md_path` = `{{positions_dir}}/position-v{{version}}.md`
- `docx_path` = `{{positions_dir}}/position-v{{version}}.docx`

## Фаза 1 — Preview (main-Sonnet)

1. Прочитай `.vassal/case.yaml` и `.vassal/index.yaml`.
2. Найди источники для контекста:
   - `.vassal/mirrors/doc-*.md`
   - при наличии — `.vassal/analysis/*.md`
   - при наличии — предыдущие версии в `<case_root>/positions/*.md`
3. Если `.vassal/index.yaml` пуст, не содержит документов, или после сверки с `.vassal/mirrors/doc-*.md` не осталось ни одного доступного зеркала документа, верни `SKILL_UNAVAILABLE` с reason `no documents` и остановись без создания выходных файлов.
4. Покажи Сюзерену preview:
   - какие файлы войдут в контекст;
   - какой предварительный номер версии виден сейчас: `v{{preview_version}}`;
   - какие файлы предположительно будут созданы: `<case_root>/positions/position-v{{preview_version}}.md`, `<case_root>/positions/position-v{{preview_version}}.docx`;
   - что финальный `vN` подтверждается только в момент записи после повторного пересчёта;
   - что ветка идёт по 3.1a с `READY_FOR_DOCX: analytical`.
5. Дождись подтверждения.

## Фаза 2 — Apply (main-Sonnet + Opus-subagent + Sonnet-subagent)

1. Перед любым `Task(...)` ещё раз проверь, что `.vassal/index.yaml` содержит документы и список доступных `.vassal/mirrors/doc-*.md` не пуст; если документов нет, верни `SKILL_UNAVAILABLE` с reason `no documents` и остановись без создания выходных файлов.
2. Выполни `mkdir -p {{positions_dir}}` до любых записей и перед повторным вычислением версии.
3. Собери prompt Opus-subagent по контрактам 3.0 и 3.1a:
   - `ROLE`: `Ты юрист-аналитик в скилле build-position.`
   - `THINKING`: `think harder` по умолчанию или override из [shared/conventions.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/conventions.md).
   - `CONTEXT`:
     - `case_root`
     - абсолютные пути к `.vassal/case.yaml`, `.vassal/index.yaml`
     - абсолютные пути к `.vassal/mirrors/doc-*.md`
     - при наличии — абсолютные пути к `.vassal/analysis/*.md`
     - при наличии — абсолютные пути к предыдущим `positions/*.md`
   - `TASK`:
     - собрать фабулу, квалификацию, доказательства, риски и стратегию;
     - для рисков использовать red-team подход;
     - каждый юридический вывод оформлять в аудируемом формате из [shared/conventions.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/conventions.md);
     - включить `## Схема сторон` с блоком ````mermaid```;
     - использовать только допустимые верхнеуровневые секции:
       - `## Фабула`
       - `## Квалификация`
       - `## Доказательства`
       - `## Схема сторон`
       - `## Риски`
       - `## Стратегия`
   - `OUTPUT`: единый markdown; последняя строка строго `READY_FOR_DOCX: analytical`.
4. Вызови `Task` с параметрами:
   - `subagent_type: "general-purpose"`
   - `model: "opus"`
   - `description`: 3-5 слов
5. Проверь OUTPUT через валидационный скрипт:
   - передай полный текст OUTPUT Opus-subagent в
     `python3 "$PLUGIN_ROOT/scripts/validate_opus_output.py" --skill build-position --contract 3.1a --stdin`;
   - скрипт должен вернуть `valid=true`.
6. Если `valid=false`, ровно один раз перезапусти Opus-subagent с напоминанием о контракте 3.1a, разрешённых секциях и обязательном `READY_FOR_DOCX: analytical`, затем повтори валидацию тем же скриптом.
   Если и после retry `valid=false`, покажи `errors` и останови скилл.
7. Непосредственно перед записью файлов атомарно зарезервируй `version`:
   - заново определи кандидат `N` по фактическому содержимому `{{positions_dir}}`; не используй `preview_version` как окончательный номер;
   - попытайся создать sentinel-каталог `{{positions_dir}}/v{{N}}.lock` через `mkdir`; на POSIX это атомарное резервирование слота версии;
   - если `mkdir` не сработал, считай что `v{{N}}` уже занята другим параллельным запуском, увеличь `N` и повтори попытку;
   - только после успешного `mkdir` зафиксируй `version = N`, `lock_dir`, `md_path` и `docx_path`.
8. Сохрани markdown-оригинал как есть в `{{md_path}}`, не снимая `{{lock_dir}}` до завершения записи всех итоговых файлов.
9. Подготовь вызов Sonnet-subagent по контракту 3.2:
   - `markdown_input` = markdown без последней строки `READY_FOR_DOCX: analytical`
   - `case_meta` = поля из `.vassal/case.yaml`
   - `out_dir` = `{{positions_dir}}`
   - `doc_name` = `position-v{{version}}.docx`
10. Запусти Sonnet-subagent. Если получен `SKILL_UNAVAILABLE`, main-Sonnet сам вызывает `arbitrum-docx`.
11. После успешной записи и `{{md_path}}`, и `{{docx_path}}` удали `{{lock_dir}}`. Если после резервирования произошёл сбой до успешного завершения, удали созданный этим запуском `{{lock_dir}}` перед возвратом блокера.

## Фаза 3 — Verify (main-Sonnet)

1. Проверь, что существуют:
   - `{{md_path}}`
   - `{{docx_path}}`
2. Прочитай `{{md_path}}` и проверь:
   - присутствует `## Схема сторон`;
   - внутри есть блок ````mermaid```;
   - последняя строка строго `READY_FOR_DOCX: analytical`;
   - нет верхнеуровневых `## ` секций вне списка Ф5b.
3. Проверь `{{docx_path}}`:
   - файл существует;
   - файл не пустой.
4. Покажи Сюзерену короткое резюме:
   - версия позиции `v{{version}}`;
   - пути к markdown и `.docx`;
   - какие секции попали в итог.

## Дисциплина

- Не использовать sidecar-превью.
- Не генерировать `.docx` в обход `arbitrum-docx`.
- Не добавлять верхнеуровневые `## ` секции вне списка Ф5b.
- Не вставлять тексты исходников inline в prompt main-Sonnet.
- Не считать номер версии окончательным на этапе preview: финальный `vN` резервируется только перед записью через атомарный `mkdir` lock-директории.

## Блокер

Если `Task(model=opus)` недоступен, дважды возвращает невалидный markdown, или formatter-ветка 3.2 не создаёт `.docx` даже после fallback:

- покажи Сюзерену конкретную причину;
- не записывай частичный `.docx`;
- не подменяй аналитическую часть ручной генерацией main-Sonnet.
