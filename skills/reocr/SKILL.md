---
name: reocr
description: >
  Повторное распознавание плохо извлечённых документов через Haiku vision.
  Используй этот скилл, когда юрист говорит «перепроверь OCR», «плохо распознано»,
  «низкое качество распознавания», «сделай re-OCR», или когда в `.vassal/index.yaml`
  есть записи с `ocr_quality: low|empty`, которые нужно перепрогнать через vision.
---

# ReOCR — Повторный OCR через Haiku vision

Скилл оркестрирует **main-Sonnet**. Он выбирает документы, рендерит страницы в PNG через [scripts/render_pages.py](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/scripts/render_pages.py), вызывает **Haiku-subagent** по контракту 3.3B из [shared/subagent-dispatch.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/subagent-dispatch.md), затем перезаписывает зеркало и запись в `.vassal/index.yaml`.

## Предусловия

- Существует `.vassal/index.yaml`.
- Доступен `[PLUGIN_ROOT]/scripts/render_pages.py`.
- Для `docx` и `xlsx` в режиме `--force` установлен `libreoffice`; без него такие документы пропускаются с понятным сообщением.
- Доступен `Task(model=haiku)` по контракту 3.3B.

## Разбор аргументов

1. Прочитай аргументы команды `/vassal-litigator-cc:reocr [--force] [doc-NNN ...]`.
2. Выдели флаг `--force` и список `doc-NNN`.
3. Если явно указаны `doc-NNN`, работай только с ними.
4. Если `doc-NNN` не указаны, выбери записи из `.vassal/index.yaml`, где одновременно:
   - `ocr_quality` равно `low` или `empty`;
   - `ocr_reattempted` не равно `true`.
5. Без `--force` пропускай записи с `ocr_quality: ok`.
6. С `--force` разрешено повторно обработать явно указанные `doc-NNN`, даже если у них `ocr_quality: ok`.
7. Если после фильтрации список пуст — сообщи Сюзерену, что подходящих документов нет, и остановись без изменений.

## Sanity checks

1. Убедись, что `.vassal/index.yaml` читается и содержит `documents`.
2. Для каждой выбранной записи проверь:
   - существует `file`;
   - существует `mirror`;
   - `file` и `mirror` сначала разрешаются в абсолютные пути с учётом симлинков;
   - и `file`, и `mirror` лежат внутри корня дела. Если любой путь выходит наружу — остановись по этому документу как по блокеру и ничего не читай/не перезаписывай.
3. Если `[PLUGIN_ROOT]/scripts/render_pages.py` не найден — остановись с явным блокером.

## Алгоритм по одному документу

Для каждой выбранной записи:

1. Создай временную директорию:
   ```bash
   TMP=$(mktemp -d -t vassal-reocr-XXXXXX)
   ```
2. Определи ветку по расширению исходника:
   - `pdf`, `jpg`, `jpeg`, `png`, `tif`, `tiff`, `bmp`:
     ```bash
     python3 "$PLUGIN_ROOT/scripts/render_pages.py" "$file" --output-dir "$TMP"
     ```
   - `docx`, `xlsx` только при `--force`:
     ```bash
     libreoffice --headless --convert-to pdf "$file" --outdir "$TMP"
     converted_pdf="$TMP/$(basename "${file%.*}").pdf"
     python3 "$PLUGIN_ROOT/scripts/render_pages.py" "$converted_pdf" --output-dir "$TMP"
     ```
     Если `libreoffice` недоступен — сообщи причину, пометь попытку как выполненную и перейди к следующему документу.
   - прочие форматы: сообщи, что формат не поддерживается для `reocr`, пометь попытку как выполненную и перейди к следующему документу.
3. Собери список `page-*.png` из `TMP` и подготовь prompt Haiku-subagent строго по контракту 3.3B из [shared/subagent-dispatch.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/subagent-dispatch.md):
   - `ROLE`: `Ты OCR через vision в скилле reocr.`
   - `CONTEXT`: абсолютный путь к исходнику и список абсолютных путей к PNG.
   - `TASK`: извлечь текст максимально точно, таблицы отдать markdown-таблицами, рукописное помечать `[рукописно: ...]`, неразборчивое — `[неразборчиво]`.
   - `OUTPUT`: markdown по страницам + финальный YAML-блок с `pages_total`, `confidence_by_page`, `notable_issues`.
4. Вызови `Task` с параметрами:
   - `subagent_type: "general-purpose"`
   - `model: "haiku"`
   - `description`: 3-5 слов
5. Прими markdown-тело и YAML-блок. Вычисли средний `confidence` как среднее `confidence_by_page`, округлённое до двух знаков.
6. Оцени результат по правилам `shared/conventions.md`:
   - если средний `confidence >= 0.75` и средний объём не меньше 200 символов на страницу — `ocr_quality: ok`;
   - иначе — `ocr_quality: low`.
7. Даже при неуспехе повторной попытки фиксируй `ocr_reattempted: true`, чтобы не зациклить `/reocr`.

## Перезапись зеркала

Делай read-modify-write существующего frontmatter и синхронизируй его с [shared/mirror-template.md](/Users/strigov/Documents/Claude/Projects/Suzerain/plugins/vassal-litigator/shared/mirror-template.md).

Существующий frontmatter зеркала используй как базу целиком. Не удаляй и не обнуляй поля, которых нет в списке обновлений ниже: должны сохраняться, например, `doc_type`, `source_file`, `parties`, `origin_name`, `intake_batch`, `bundle`, `bundle_item_index`, `needs_manual_review`, `source` и любые другие уже присутствующие поля.

Обновляются:

- `pages` → `pages_total` из vision OUTPUT
- `extraction_method` → `haiku-vision`
- `extraction_model` → `haiku`
- `extraction_date` → текущая дата `YYYY-MM-DD`
- `confidence` → средний float с двумя знаками
- `ocr_reattempted` → `true`

Если какого-то поля из списка обновлений раньше не было — добавь его. Остальные поля frontmatter оставь без изменений.

Тело зеркала полностью замени на полный vision-текст после frontmatter. Усечение запрещено: контракт mirror-full-text сохраняется.

## Обновление `.vassal/index.yaml`

Для соответствующей записи обнови:

- `extraction_method: haiku-vision`
- `confidence: <средний float>`
- `ocr_reattempted: true`
- `ocr_quality: ok | low`
- `ocr_quality_reason`:
  - для `ok` — всегда пустая строка `""`;
  - для `low` — человекочитаемая причина, что re-OCR через Haiku vision всё ещё низкого качества, с текущей датой.

## История и вывод

1. Добавь строку в `.vassal/history.md` в формате `### [YYYY-MM-DD HH:MM] reocr ...`.
2. Покажи Сюзерену summary-таблицу:
   - `doc-id`
   - `before` (`extraction_method`, `confidence`)
   - `after` (`extraction_method`, `confidence`, `ocr_quality`)
3. Для пропущенных документов явно перечисли причину: неподдерживаемый формат, нет LibreOffice, нет PNG после рендера, ошибка `Task(model=haiku)`.

## Дисциплина

- Не меняй документы, не попавшие в выборку.
- Не усекать vision-текст при записи зеркала.
- Не вставляй в prompt main-Sonnet содержимое исходников inline: передавай только абсолютные пути.
- Временный каталог `TMP` удаляй после каждого документа при любом исходе.
