---
slug: skill-scripts-extraction-p1
created: 2026-04-24
status: done
phases:
  - id: Ф1
    scope: "scripts/classify_ocr_quality.py + tests/unit scaffold — single source of truth for OCR quality table"
    status: done
  - id: Ф2
    scope: "scripts/validate_opus_output.py — единый валидатор контрактов 3.1a/3.1b/3.1c + SKILL.md интеграция"
    status: done
  - id: Ф3
    scope: "scripts/scan_case_state.py — сканер ФС vs index.yaml для update-index Ф1"
    status: done
  - id: Ф4
    scope: "scripts/prepare_intake_workdir.py — распаковка архивов + preview-OCR для intake/add-evidence/add-opponent Ф1"
    status: done
  - id: Ф5
    scope: "scripts/apply_intake_plan.py — детерминированный Ф3 apply для intake/add-evidence/add-opponent"
    status: done
---

## Goal

Вынести из SKILL.md детерминированные операции (валидация структуры OUTPUT субагентов, сканирование ФС, классификация OCR quality, распаковка архивов, apply-фаза intake) в переиспользуемые Python-скрипты. Каждая таблица/regex/последовательность файловых операций должна существовать ровно в одном месте — в скрипте — а SKILL.md должен инструктировать LLM вызвать скрипт и распорядиться его JSON-выходом.

Зачем сейчас: таблица OCR-порогов уже дословно дублируется в 4 SKILL.md с расхождениями формулировок; валидация OUTPUT 3.1a повторяется в 5+ файлах; apply-фаза intake/add-evidence/add-opponent — три почти идентичные копии одного алгоритма. Это дрейф. План 1 закрывает только high-value скрипты (пункты 1–5 из пользовательского списка); middle- и low-value будут отдельными планами.

## Files

### Ф1 — classify_ocr_quality
- `scripts/classify_ocr_quality.py` (new) — CLI + importable `classify(extraction_method, confidence, total_chars, pages) -> {ocr_quality, ocr_quality_reason}` по таблице из `shared/conventions.md`; принимает categorical confidence `"high"|"medium"|"low"` (как отдаёт текущий `extract_text.py`) и float; method-based правила имеют приоритет над confidence-based.
- `tests/unit/__init__.py` (new, empty).
- `tests/unit/test_classify_ocr_quality.py` (new) — pytest-покрытие всех строк таблицы, включая categorical-confidence от `extract_text.py`.
- `tests/unit/conftest.py` (new) — добавляет `scripts/` в `sys.path` для импорта.
- Правки SKILL.md (миграция всех in-scope OCR-callers на вызов скрипта в рамках Ф1): `skills/add-evidence/SKILL.md` шаг 2, `skills/add-opponent/SKILL.md` шаг 2, `skills/update-index/SKILL.md` (inline-таблица порогов), `skills/intake/SKILL.md` (inline-таблица порогов).

### Ф2 — validate_opus_output
- `scripts/validate_opus_output.py` (new) — CLI-валидатор markdown-выхода Opus-субагента по веткам 3.1a / 3.1b / 3.1c.
- `tests/unit/test_validate_opus_output.py` (new).
- `tests/fixtures/opus_outputs/` (new dir) — по 1–2 валидных и невалидных фикстуре на каждый контракт.
- Правки SKILL.md (удаление inline-проверок «Проверь OUTPUT», замена на вызов скрипта): `skills/legal-review/SKILL.md`, `skills/build-position/SKILL.md`, `skills/appeal/SKILL.md`, `skills/cassation/SKILL.md`, `skills/draft-judgment/SKILL.md`, `skills/prepare-hearing/SKILL.md`, `skills/timeline/SKILL.md`, `skills/analyze-hearing/SKILL.md`.

### Ф3 — scan_case_state
- `scripts/scan_case_state.py` (new) — CLI, принимает case root, возвращает JSON `{new_files, orphans, stale_mirrors, index_count, fs_count}`.
- `tests/unit/test_scan_case_state.py` (new).
- `tests/fixtures/case-with-drift/` (new dir) — минимальный case root с рассинхронизированным `index.yaml`.
- Правки `skills/update-index/SKILL.md` Ф1 — замена inline-сканирования на вызов скрипта.

### Ф4 — prepare_intake_workdir
- `scripts/prepare_intake_workdir.py` (new) — CLI, распаковывает архивы в `{work_dir}` c защитой от zip-slip/symlink-escape, вызывает `extract_text.py` на каждый файл, собирает JSON-массив `[{source_path, extracted_text_preview, needs_image_to_pdf, extraction_method, confidence, pages, total_chars, ocr_artifact_path}]` (где `ocr_artifact_path` — абсолютный путь к файлу с полным извлечённым текстом, `saved_to` из `extract_text.py`; null для случаев, когда extract_text не сохранял артефакт). Main-Sonnet в Ф1 intake на основе этого JSON формирует per-item `ocr_artifacts[]` и `combined_text_path` в `plan_path.yaml` (для `grouped_inputs` требуется конкатенация в порядке grouped_inputs — см. Ф5 Contracts).
- `tests/unit/test_prepare_intake_workdir.py` (new) — с одним мелким zip-фикстом, без реального tesseract (mock extract_text).
- Правки SKILL.md: `skills/intake/SKILL.md` Ф1 шаги 1–2, `skills/add-evidence/SKILL.md`, `skills/add-opponent/SKILL.md` (читаются, но если файл отсутствует — создание в объёме другого плана; в этом плане только intake достоверно существует).

### Ф5 — apply_intake_plan
- `scripts/apply_intake_plan.py` (new) — CLI, принимает утверждённый YAML-план + case root, выполняет весь Ф3 apply: copy raw → image_to_pdf → place → create mirror → bump next_id → history.md → cleanup. Возвращает JSON-сводку `{added_doc_ids, converted_images, bundle_count, orphan_count, raw_batch_path}`.
- Новый артефакт: `plan_path.yaml` (sibling к markdown-плану) — машиночитаемая часть плана, которую писал агент в Ф1.
- `tests/unit/test_apply_intake_plan.py` (new) — end-to-end на fixture `dummy-case` с 1–2 файлами.
- Правки SKILL.md: `skills/intake/SKILL.md` Ф1 (добавить запись `plan_path.yaml`) и Ф3 (замена inline-операций на вызов скрипта).

## Contracts

### Общие правила (для всех скриптов в плане)
- argparse, позиционный `input_path` (или `case_root`) первым, флаги — следом.
- Успешный stdout — строго один JSON-объект/массив, ничего более.
- Диагностика — только в stderr.
- Exit code: `0` при успехе (в т.ч. частичном — диагностика в JSON), `1` при фатальной ошибке (невалидные аргументы, отсутствие обязательных путей).
- Ни один скрипт не пишет в `.vassal/` в обход main-Sonnet, кроме `apply_intake_plan.py` (этот — весь смысл в том, чтобы писать).
- Для одиночных записей используем `mktemp` → запись → `os.replace` (идемпотентность per-file). Глобальной транзакционной атомарности на множестве целевых путей НЕ гарантируем — для apply используется recoverable partial-apply protocol (см. Ф5).

### Ф1 — `scripts/classify_ocr_quality.py`
```
usage: classify_ocr_quality.py \
  --extraction-method <str> \
  [--confidence <float|null>] \
  [--total-chars <int>] \
  [--pages <int>]
```
- Importable API:
  ```python
  def classify(
      extraction_method: str | None,
      confidence: float | str | None,   # float ИЛИ категория "high"|"medium"|"low" — текущий extract_text.py отдаёт именно категориальную строку
      total_chars: int | None,
      pages: int | None,
  ) -> dict:
      # returns {"ocr_quality": "ok"|"low"|"empty", "ocr_quality_reason": str}
  ```
- Текущий producer `scripts/extract_text.py` возвращает categorical `confidence` (`"high"|"medium"|"low"`) — см. lines 47, 71, 89, 99. Скрипт-классификатор НЕ должен деградировать такие значения до `low`.
- **Жёсткий порядок правил (method-based > confidence-based, чтобы не ломать текущий pipeline)**:
  1. Нормализация `extraction_method` (trim, lowercase).
  2. Если `extraction_method in {pdf-text, docx-parse, text-read}` → `ok` + reason `""`. Порог confidence и chars-per-page НЕ проверяются. Это покрывает native-text путь, где confidence приходит как `"high"|"medium"` и не должен вести к `low`.
  3. Если `extraction_method == "ocr"`:
     - `total_chars < 50` (или None) → `empty` + reason `"ocr produced <50 chars"`.
     - Coercion confidence: если float/int-строка — float; иначе маппинг категориальный: `"high"→0.9`, `"medium"→0.65`, `"low"→0.3`, `None`/прочее → «non-numeric».
     - Если coercion провалился → `low` + reason `"confidence missing or non-numeric"`.
     - Порог: `confidence ≥ 0.75` И `total_chars / max(pages, 1) ≥ 200` → `ok`; иначе → `low` + reason с численными значениями.
  4. Если `extraction_method == "haiku-vision"`: та же coercion+порог, что и `ocr`, но без ветки `empty` (haiku-vision всегда возвращает какой-то текст).
  5. **Спец-кейс `extraction_method == "none"`** (так `extract_text.py` помечает провал извлечения — см. производящий код) → `empty` + reason `"extraction failed"`. Это правило проверяется до общего «unknown» fallback'а, чтобы не маркировать нераспознанные файлы тихо как `ok`.
  6. `extraction_method` не из `{pdf-text, ocr, docx-parse, text-read, haiku-vision, none}` (или None) → `ok` + reason `""` (презумпция native text / legacy).
- `ok` → reason всегда `""`; `low`/`empty` → reason непустой, машинно-читаемый.
- stdout: JSON с двумя ключами.
- **Callers в scope этой фазы** (все inline OCR-блоки удаляются и заменяются на вызов скрипта в ЭТОМ плане, Ф1 коммите):
  - `skills/add-evidence/SKILL.md` шаг 2 (блок про `ocr_quality`, lines ~82–88);
  - `skills/add-opponent/SKILL.md` шаг 2 (аналогично lines ~77–83);
  - `skills/update-index/SKILL.md` — inline-таблица порогов;
  - `skills/intake/SKILL.md` — inline-таблица порогов.
  В этих SKILL.md шагах остаётся ровно одна строка-инструкция: «Для каждой записи вызови `python3 "$PLUGIN_ROOT/scripts/classify_ocr_quality.py" --extraction-method X --confidence Y --total-chars N --pages P` и подставь результат в `ocr_quality`/`ocr_quality_reason`».

### Ф2 — `scripts/validate_opus_output.py`
```
usage: validate_opus_output.py (--input-file <path> | --stdin) --contract {3.1a,3.1b,3.1c} --skill <skill-name>
```
- Контракт вызова: валидация происходит ДО записи на диск (как сейчас в inline-проверках). Поэтому скрипт должен принимать raw text одним из двух способов:
  - `--stdin` — main-Sonnet передаёт текст OUTPUT субагента через stdin (основной путь, staging-файл не нужен);
  - `--input-file <path>` — для случаев, когда текст уже лежит на диске (тесты, повторная проверка).
- Каждый SKILL.md в шаге валидации использует `--stdin` и подаёт OUTPUT субагента без промежуточной записи.
- Один retry сохраняется: SKILL.md по-прежнему делает ровно одну повторную попытку Opus-subagent при `valid=false`; скрипт никаких retry не выполняет.
- Семантика проверок — строго эквивалентна текущим inline-проверкам skill'ов (никаких послаблений):
  - **3.1a** (`legal-review`, `build-position`, `appeal`, `cassation`, `draft-judgment`):
    - markdown не пустой;
    - ровно одна строка `READY_FOR_DOCX: (processual|analytical|letter)$`, и она последняя непустая строка файла;
    - **skill-specific `doc_type` (жёсткая проверка, не смягчается до общего allowlist значения)**:
      - `legal-review`, `build-position` → ожидаемый `doc_type == "analytical"`;
      - `appeal`, `cassation`, `draft-judgment` → ожидаемый `doc_type == "processual"`;
      - несовпадение фактического значения с ожидаемым → `valid=false` с ошибкой вида `"doc_type mismatch: expected <X> for skill <Y>, got <Z>"`. Это соответствует текущим inline-проверкам соответствующих SKILL.md.
      - `prepare-hearing` (3.1b) — ожидаемый `doc_type == "processual"` на каждом сегменте (см. 3.1b ниже).
      - Для всех прочих 3.1a/3.1b skill'ов, не перечисленных выше, жёсткой проверки `doc_type` нет (поле только распарсивается).
    - allowlist верхнеуровневых `## `-секций — skill-specific (загружается из внутреннего словаря скрипта; для `legal-review` это `{Квалификация, Схема сторон, Анализ, Выводы}`, для остальных 3.1a skill'ов — свой набор из их SKILL.md);
    - обязательные секции — skill-specific (`legal-review`: присутствует `## Схема сторон` и в ней блок ```mermaid);
    - для `build-position`: обязательная секция `## Схема сторон` И блок ```mermaid расположен именно внутри этой секции (проверяется через split по `^## `, поиск ```mermaid только в слайсе секции `## Схема сторон`, а не в документе целиком). Mermaid-блок в другой секции без него в `## Схема сторон` → `valid=false`.
  - **3.1b** (`prepare-hearing`):
    - есть секция `## Заметки` (error, не warning — соответствует текущему SKILL.md);
    - найден хотя бы один блок `## Ходатайство N: <тема>`, регулярка `^## Ходатайство (\d+): (.+)$` (MULTILINE), `N ≥ 1`;
    - каждый сегмент оканчивается ровно одной строкой `READY_FOR_DOCX: processual`;
    - в сегментах нет иных значений `READY_FOR_DOCX`.
  - **3.1c** (`timeline`, `analyze-hearing`):
    - отсутствует строка `READY_FOR_DOCX:` во всём файле;
    - для `timeline`: есть блок ```mermaid, внутри него встречается `gantt`; присутствует секция `## События`; под ней парсируемая markdown-таблица с заголовками строго `Дата | Источник | Событие`; минимум одна строка данных; каждая строка парсится в три непустых значения;
    - для `analyze-hearing`: присутствует `## Ход заседания` и хотя бы одна из рекомендованных `## `-секций (allowlist в скрипте).
- stdout JSON:
  ```json
  {
    "valid": true|false,
    "contract": "3.1a",
    "skill": "legal-review",
    "errors": ["..."],
    "warnings": ["..."],
    "parsed": {
      "title": "...",
      "doc_type": "processual|analytical|letter|null",
      "body_len_chars": 1234,
      "segments": [{"index": 1, "title": "...", "doc_type": "processual"}]  // 3.1b only
    }
  }
  ```
- Exit 0 при `valid` или `!valid` (смотрит caller); exit 1 только при отсутствии файла/неверных аргументах.

### Ф3 — `scripts/scan_case_state.py`
```
usage: scan_case_state.py <case_root>
```
- Читает `<case_root>/.vassal/index.yaml`.
- Сканирует ФС под `<case_root>` рекурсивно, игнорируя: `.vassal/`, `Входящие документы/`, `На удаление/`, `.DS_Store`, `Thumbs.db`, `Таблица документов.xlsx`, любые `.tmp`.
- stdout JSON:
  ```json
  {
    "case_root": "/abs/...",
    "index_count": 12,
    "fs_count": 13,
    "new_files": ["/abs/path/to/file.pdf", ...],          // на диске, нет в index
    "orphans": [{"id":"doc-007","file":"/abs/..."}, ...], // в index, нет на диске
    "stale_mirrors": [{"id":"doc-003","reason":"mirror older than file mtime"}, ...]
  }
  ```
- Правило «stale»: зеркало `<case_root>/.vassal/mirrors/doc-NNN.md` существует, но `mtime(mirror) < mtime(file)` ИЛИ `documents[].last_verified` из `index.yaml` старше `mtime(file)`. `last_verified` читается ИЗ `index.yaml` (этого поля нет в frontmatter шаблона зеркала — см. `shared/mirror-template.md`, каноничный источник — `shared/index-schema.yaml` поле `documents[].last_verified`). Frontmatter зеркала скрипт не модифицирует и не требует расширения.
- Не делает записей.

### Ф4 — `scripts/prepare_intake_workdir.py`
```
usage: prepare_intake_workdir.py <inbox_dir> --work-dir <work_dir> [--max-preview-chars 500]
```
- Распаковывает архивы (`.zip`, `.rar`, `.7z`, `.tar`, `.tar.gz`, `.tgz`) в подпапки `<work_dir>/<archive-stem>/` с помощью системных `unzip`, `unrar`, `7z`, `tar` (уже в `setup.sh`).
- **Защита от zip-slip / symlink-escape (разная по типам архивов, т.к. `.7z`/`.rar` не имеют надёжного pre-listing в Python)**:
  - **ZIP / TAR / TAR.GZ (pre-listing path)**: использовать Python `zipfile` / `tarfile` для пре-листинга ДО извлечения. Для каждого члена резолвить `(extract_root / member_name).resolve(strict=False)` и требовать, чтобы он начинался с `extract_root.resolve()` (проверка `os.path.commonpath == extract_root`). Отклонять членов с `../` компонентами, абсолютными путями, drive-letter'ами. Отклонять symlink/hardlink-entries с target вне `extract_root` (zip — `external_attr`; tar — `TarInfo.issym()/islnk()` + resolve linkname). Если хотя бы один член не проходит — отклонять архив целиком (не распаковывать ни одного файла), писать в `unsupported` с reason. Распаковка — Python-модулями, не subprocess.
  - **7Z / RAR (scratch-dir path)**: у `py7zr` и `rarfile` нет единого надёжного pre-listing API (особенно для symlink/hardlink-членов), а системные `7z x`/`unrar x` могут записать файл до того, как мы его проверим. Поэтому:
    1. Создать изолированный `scratch_dir = work_dir/.scratch/<archive-stem>/` (mkdir; гарантированно пустой).
    2. Запустить системный распаковщик (`7z x -o<scratch_dir> <archive>`, `unrar x <archive> <scratch_dir>/`) — писать ВСЁ только в `scratch_dir`.
    3. Пост-walk по `scratch_dir`: для каждого файла проверить `os.path.realpath(file).startswith(os.path.realpath(scratch_dir) + os.sep)` — это ловит любую попытку распаковщика записать файл вне `scratch_dir` (через symlink-race, абсолютные пути и т.п.).
    4. Если **любой** файл escape'ит → `shutil.rmtree(scratch_dir)`, архив в `unsupported` с `reason: "path escape"`, соседние файлы вне `scratch_dir` (которые мог создать распаковщик) НЕ ищем и не удаляем — сам факт того, что scratch изолирован и мы сносим его целиком, делает дополнительный cleanup ненужным; но мы логируем инцидент в stderr.
    5. Если все файлы внутри — переносим (`shutil.move`) только верифицированные файлы в целевой `extract_root = work_dir/<archive-stem>/`, сохраняя относительные пути; затем `shutil.rmtree(scratch_dir)`.
  - **Пост-валидация (общая, на всякий случай)**: после помещения файлов в `extract_root` — ещё раз `os.walk` + realpath-check; любой escape → удалить конкретный файл, записать в `unsupported`.
  - При любом нарушении текущего архива — прервать его обработку, добавить в `unsupported` с reason, НЕ ронять весь запуск (соседние архивы продолжают обрабатываться).
- Для каждого конечного файла (не архива) вызывает `scripts/extract_text.py` (импорт как модуль, не subprocess, чтобы держать один процесс; fallback на subprocess если импорт неудобен). **Обязательно передавать `--output-dir <work_dir>/extracted/`** (или аналогичный параметр при импорте как модуля) — без этого `extract_text.py` не возвращает поле `saved_to` в JSON, и `ocr_artifact_path` в выводе `prepare_intake_workdir` будет всегда null, что ломает основной путь зеркала через `combined_text_path` в Ф5. Директория создаётся заранее.
- Помечает файлы `.jpg/.jpeg/.png/.tif/.tiff/.bmp/.heic` как `needs_image_to_pdf: true` (список синхронизирован с `shared/conventions.md:110` и `scripts/image_to_pdf.py:8-12`).
- stdout JSON:
  ```json
  {
    "work_dir": "/abs/...",
    "files": [
      {
        "source_path": "/abs/inbox/file.pdf",
        "extracted_text_preview": "первые 500 симв...",
        "extraction_method": "pdf-text",
        "confidence": "high",
        "pages": 3,
        "total_chars": 4521,
        "needs_image_to_pdf": false,
        "archive_src": null,
        "ocr_artifact_path": "/abs/.vassal/work/intake-.../extracted/file.pdf.txt"
      },
      ...
    ],
    "archives_unpacked": [{"archive":"/abs/...zip","extracted_to":"/abs/..."}],
    "unsupported": []
  }
  ```
- Не трогает `Входящие документы/` (только читает). Все артефакты — в `work_dir`.

### Ф5 — `scripts/apply_intake_plan.py`
```
usage: apply_intake_plan.py <case_root> --plan-yaml <path> [--dry-run]
```
- **Location guardrail для `--plan-yaml` (выполняется ПЕРВЫМ, до чтения YAML и до любых файловых операций)**: резолвить `Path(plan_yaml).resolve(strict=True)` и требовать `plan_path.is_relative_to(Path(case_root).resolve() / ".vassal" / "plans")`. Если путь вне этой директории (или символически эскейпит из неё, или файл отсутствует) — немедленный `exit 1` с сообщением `"plan-yaml must reside under <case_root>/.vassal/plans/"`. Только после успешной проверки location разрешено парсить YAML и выполнять остальные guardrails. Это критично, потому что шаг cleanup в конце apply безусловно удаляет `--plan-yaml` и sibling-markdown — произвольный путь допускать нельзя.
- `plan-yaml` — новая машиночитаемая половина плана, которую main-Sonnet пишет в Ф1 (рядом с markdown-планом для юриста) в `<case_root>/.vassal/plans/`. Схема покрывает все ветки текущего intake-плана:
  ```yaml
  batch: intake-2026-04-24
  source_inbox: /abs/Входящие документы      # ДОЛЖЕН быть ровно <case_root>/Входящие документы
  work_dir: /abs/.vassal/work/intake-2026-04-24   # ДОЛЖЕН лежать под <case_root>/.vassal/work/
  raw_dest: /abs/.vassal/raw/intake-2026-04-24
  next_id_start: 42
  next_bundle_id_start: 3          # текущий next_bundle_id из index.yaml на момент планирования

  # Бандлы, которые появляются в этом intake (новые либо расширяемые)
  bundles:
    - id: bundle-003                 # если новый — ID ≥ next_bundle_id_start; если расширяем существующий — ID < next_bundle_id_start
      title: "Переписка в Telegram"
      main_doc: doc-043              # doc_id головного элемента комплекта
      members: [doc-043, doc-044]    # все doc_id участников; все они обязаны появиться в items[] этого плана ИЛИ уже присутствовать в index.yaml (для расширения существующего бандла)
      is_new: true                   # true = создаём бандл в этом intake; false = дописываем members в существующий

  items:
    # (1) Обычный документ — один source → один target
    - source_path: /abs/.vassal/work/intake-2026-04-24/file.pdf
      grouped_inputs: null                   # см. ниже; для одиночного файла — null
      archive_src: null                      # или абсолютный путь к архиву-оригиналу (используется и как guardrail-ввод, и как значение origin.archive_src в index.yaml)
      # OCR-payload на item (см. блокер 4): ocr_artifacts[], combined_text_path.
      ocr_artifacts:
        - path: /abs/.vassal/work/intake-2026-04-24/extracted/file.pdf.txt
          extraction_method: pdf-text
          confidence: high
          pages: 3
          total_chars: 4521
      combined_text_path: /abs/.vassal/work/intake-2026-04-24/extracted/file.pdf.txt
      doc_id: doc-042
      target_file: "/abs/Материалы от клиента/2026-01-15 Договор.pdf"
      convert_image_to_pdf: false
      title: "..."
      date: "2026-01-15"
      type: "договор"
      source: "client"
      bundle_id: null                        # либо null, либо id из bundles[].id (или существующего бандла в index.yaml)
      role_in_bundle: null                   # null | head | attachment (требуется при bundle_id != null)
      attachment_order: null                 # int | null (head → 0/null; attachment → 1..N)
      parent_id: null                        # doc_id головного документа, если это attachment
      origin:
        name: "file.pdf"                     # исходное имя файла (как лежал во Входящих или в архиве), из prepare_intake_workdir
        date: "2026-01-15"                   # дата документа (для целей плана; в index.yaml идёт как documents[].date)
        received: "2026-04-24"               # дата получения файла (ISO). Источник: main-Sonnet берёт batch-дату intake по умолчанию (= дата intake), либо явная дата из Haiku-плана, если известна
        batch: "intake-2026-04-24"           # ОБЯЗАНО совпадать с batch на корне плана
        archive_src: null                    # если файл извлечён из архива — basename архива (не абсолютный путь, а имя как оно в index.yaml); иначе null

    # (2) Несколько изображений → один многостраничный PDF (серия скриншотов одного чата)
    - source_path: null                      # явно null, когда работаем с группой
      grouped_inputs:                        # list[abs-path], ≥2 изображения; порядок сохраняется
        - /abs/work/.../scr-001.jpg
        - /abs/work/.../scr-002.jpg
        - /abs/work/.../scr-003.jpg
      archive_src: null
      ocr_artifacts:                         # ровно len(grouped_inputs) элементов, в том же порядке
        - {path: /abs/work/.../extracted/scr-001.txt, extraction_method: ocr, confidence: medium, pages: 1, total_chars: 420}
        - {path: /abs/work/.../extracted/scr-002.txt, extraction_method: ocr, confidence: medium, pages: 1, total_chars: 380}
        - {path: /abs/work/.../extracted/scr-003.txt, extraction_method: ocr, confidence: low,    pages: 1, total_chars: 210}
      combined_text_path: /abs/work/.../extracted/scr-combined.txt    # склейка в порядке grouped_inputs с разделителем `\n\n--- page N ---\n\n`
      doc_id: doc-043
      target_file: "/abs/Материалы от клиента/2026-02-10 Переписка.pdf"
      convert_image_to_pdf: true             # apply использует image_to_pdf.py multi-input
      title: "Переписка в Telegram"
      date: "2026-02-10"
      type: "переписка"
      source: "client"
      bundle_id: bundle-003
      role_in_bundle: head
      attachment_order: null
      parent_id: null
      origin:
        name: "scr-001.jpg"                  # для grouped — имя первого inputa
        date: "2026-02-10"
        received: "2026-04-24"
        batch: "intake-2026-04-24"
        archive_src: null

  # (3) Архив, который копируется в raw, но НЕ индексируется как документ (индексируется только содержимое — см. conventions.md §Архивы)
  raw_only:
    - archive_src: /abs/Входящие документы/архив.zip
      raw_dest_name: "архив.zip"             # имя под которым архив лежит в raw_dest

  # (4) Файлы, которые apply НЕ индексирует и НЕ копирует (дубликаты, мусор, служебные файлы из архива)
  skipped:
    - path: /abs/work/.../Thumbs.db
      reason: "system file"
    - path: /abs/work/.../duplicate.pdf
      reason: "duplicate of doc-041"

  # (5) Явное множество для финального шага очистки Входящие документы/.
  # apply удаляет ТОЛЬКО то, что перечислено здесь. Раскрытые из архива файлы в работе берутся из work_dir, их удалять не надо.
  cleanup_set:
    - /abs/Входящие документы/архив.zip
    - /abs/Входящие документы/file.pdf
    - /abs/Входящие документы/scr-001.jpg
    - /abs/Входящие документы/scr-002.jpg
    - /abs/Входящие документы/scr-003.jpg

  # (6) Файлы, уже обработанные ранее, которые agent распознал и не включает в items (только для трассируемости; apply игнорирует)
  already_processed:
    - path: /abs/work/.../known.pdf
      matched_doc_id: doc-039
  ```
- Нормативные правила схемы:
  - Ровно одно из `source_path` / `grouped_inputs` в каждом `items[]`; оба null или оба заданы — ошибка валидации.
  - `grouped_inputs` применяется ТОЛЬКО при `convert_image_to_pdf: true` (серия изображений → один PDF); для любой другой комбинации — ошибка.
  - `raw_only[]` архивы копируются в `raw_dest/` как есть, не попадают в `index.yaml`, не создают зеркала.
  - `skipped[]` информационный; apply не трогает эти пути, но валидирует, что они внутри work_dir/inbox.
  - `cleanup_set` — финальный источник истины для удаления из `Входящие документы/`; rm выполняется ПОСЛЕ успешной фиксации `index.yaml` и всех копий (см. Ф5 guardrails ниже).
  - **origin (обязательные поля каждого items[])**:
    - `origin.name` — non-empty string, исходное имя файла (basename, без путей); для `grouped_inputs` — basename первого элемента.
    - `origin.date` — ISO `YYYY-MM-DD`, может совпадать с `date` самого item или отличаться (если дата получения ≠ дата документа).
    - `origin.received` — ISO `YYYY-MM-DD`, дата получения; по умолчанию main-Sonnet подставляет дату batch.
    - `origin.batch` — non-empty string, ОБЯЗАНО быть `== batch` на корне плана (валидация).
    - `origin.archive_src` — либо `null`, либо basename архива-источника (не абсолютный путь); если `items[].archive_src` задан (абсолютный путь к архиву), apply проверяет что `basename(archive_src) == origin.archive_src` и пишет в index именно basename.
  - **bundles (аллокация и валидация)**:
    - Если в `items[]` любой item имеет `bundle_id != null`, этот `bundle_id` ОБЯЗАН фигурировать либо в `bundles[].id` текущего плана, либо в существующих `bundles[].id` из `index.yaml`. В противном случае — ошибка валидации.
    - Для каждого `bundles[]` элемента с `is_new: true`: `id` должен быть формата `bundle-NNN`, `int(NNN) >= next_bundle_id_start` и новые ID в плане идут плотно и без дыр (`next_bundle_id_start`, `next_bundle_id_start+1`, …).
    - Для каждого `bundles[]` элемента с `is_new: false`: `id` обязан уже присутствовать в `index.yaml.bundles[]`; `main_doc` в плане должен совпадать с существующим `main_doc` (расширение не меняет head); `members` плана = объединение старых + новые doc_id из items[].
    - В каждом `bundles[].members` ровно один элемент должен быть `main_doc`; все остальные — attachments. Соответствующие items[] обязаны иметь корректные `role_in_bundle` (head ↔ main_doc, attachment ↔ остальные) и `parent_id == main_doc` для attachments.
    - `attachment_order` для attachments — уникальные положительные целые в пределах одного бандла; для head — `null`.
- **Guardrails безопасности (обязательные, аналогично update-index)**:
  - **Каноникализация путей**: все `source_path`, `grouped_inputs[]`, `archive_src`, `raw_only[].archive_src`, `skipped[].path`, `cleanup_set[]`, `target_file`, `raw_dest`, `ocr_artifacts[].path`, `combined_text_path` проходят через `Path(p).resolve(strict=False)` и проверяются на symlink-escape (`os.path.realpath`).
  - **`raw_only[].archive_src` containment (обязательно, иначе через план можно подсунуть произвольный локальный файл в `.vassal/raw/`)**: после `resolve()` путь ОБЯЗАН быть внутри `source_inbox` (т.е. `resolved.is_relative_to(source_inbox.resolve())`). Любой `raw_only[].archive_src`, резолвящийся вне `source_inbox`, → exit 1 ДО любых файловых операций.
  - **Containment-проверки** (любое нарушение → exit 1, ни одна запись не делается):
    - `source_inbox` после `resolve()` равен строго `Path(case_root).resolve() / "Входящие документы"` (любое отклонение — ошибка, защита от подмены корня);
    - `work_dir` после `resolve()` — подпапка `Path(case_root).resolve() / ".vassal" / "work"` (проверка `is_relative_to`; сам `.vassal/work/` как значение `work_dir` тоже запрещён — требуется именно подпапка);
    - каждый `source_path/grouped_inputs[]/archive_src` лежит внутри `source_inbox` ИЛИ внутри `work_dir` (не просто «под `.vassal/`», а именно под заявленным в плане `work_dir`);
    - каждый `ocr_artifacts[].path` и `combined_text_path` (если не null) лежит внутри `work_dir`;
    - для `grouped_inputs`: `len(ocr_artifacts) == len(grouped_inputs)` и каждый артефакт сопоставлен с соответствующим входом в том же порядке; `combined_text_path` обязан быть задан (non-null); для одиночного `source_path` — `len(ocr_artifacts) in {0,1}` и `combined_text_path` либо равен единственному `ocr_artifacts[0].path`, либо null;
    - каждый `target_file` лежит внутри `case_root` и НЕ внутри `.vassal/` и НЕ внутри `Входящие документы/`;
    - `raw_dest` лежит внутри `case_root/.vassal/raw/`;
    - каждый путь в `cleanup_set` лежит внутри `source_inbox`;
    - `skipped[].path` лежит внутри `source_inbox` ИЛИ `work_dir`.
  - **Staged commit + recoverable partial-apply protocol** (true transactional atomicity на множестве `os.replace` недостижима без journaling-ФС; вместо этого — идемпотентный, восстанавливаемый promote):
    1. **Write phase (атомарная по построению — staging изолирован)**: все копии в `Материалы от клиента/` и `raw_dest/` сначала пишутся в `case_root/.vassal/tmp/apply-<batch>/` (staging). Собранный новый `index.yaml` — в `.vassal/tmp/apply-<batch>/index.yaml.new`. Полная валидация схемы. На любой ошибке до начала promote — `shutil.rmtree(staging)`; ни один целевой файл/индекс не тронут.
    2. **Recovery record**: перед первым promote-шагом записать `<case_root>/.vassal/plans/<batch>-apply-state.json` (через tmp+`os.replace`) со структурой:
       ```json
       {
         "status": "promoting",
         "batch": "...",
         "staged": [{"src": "<staging-abs>", "dst": "<target-abs>"}, ...],
         "promoted": [],
         "index_staged": ".vassal/tmp/apply-<batch>/index.yaml.new",
         "index_target": ".vassal/index.yaml",
         "cleanup_set": [...]
       }
       ```
    3. **Promote phase**: для каждой пары в `staged` выполнить `os.replace(src, dst)` (mkdir -p родителя заранее). После каждого успешного `os.replace` — дописать `dst` в `promoted` в state-файле (tmp+`os.replace` поверх состояния). В самом конце — `os.replace(index_staged, index_target)`.
    4. **Completion**: state → `{"status": "done", ...}`, дописать `history.md`, применить `cleanup_set` (rm из `Входящие документы/` — ТОЛЬКО после `status: done`), `shutil.rmtree(staging)`, удалить state-файл.
    5. **Recovery (повторный запуск после частичного падения)**: если обнаружен `<batch>-apply-state.json` с `status: "promoting"` — скрипт в idempotent-режиме: для каждой пары в `staged` проверить, файл уже на `dst` (если да — пропустить), иначе `os.replace` и обновление `promoted`. Затем — index promote (проверить, что target совпадает с staged; если да — пропустить). Затем — completion. Если staging уже удалён (предыдущий запуск дошёл до шага 4 и упал на cleanup) — state считывается, cleanup повторяется идемпотентно, state удаляется.
    6. Ключевое слово «атомарный» в этом плане НЕ употребляется применительно к promote — гарантия называется «idempotent / recoverable». Окно между первым и последним `os.replace` промежуточно наблюдаемо (частично применённый state), но полностью восстанавливаемо повторным запуском.
    7. `cleanup` (rm из `Входящие документы/`) — только после `status: done`. Если фиксация прошла, но rm частично упал — JSON-ответ содержит `cleanup_errors: [...]`, exit code `0` (файлы уже безопасно скопированы и проиндексированы).
- Выполняет строго в этом порядке:
  0. **Location guardrail для `--plan-yaml`** (см. выше) — резолв пути и containment в `<case_root>/.vassal/plans/`; fail → exit 1 ДО чтения YAML.
  1. Валидация: `case_root/.vassal/index.yaml` существует; `next_id_start` совпадает с текущим `next_id`; все guardrails выше пройдены.
  2. Копирует все `source_path`/`grouped_inputs[]` в `.vassal/tmp/apply-<batch>/raw/` (сохраняя `archive_src` как подпапку, если есть); копирует `raw_only[].archive_src` туда же.
  3. Для каждого `convert_image_to_pdf: true` — вызывает `scripts/image_to_pdf.py` (с поддержкой multi-input при `grouped_inputs`), результат кладётся в staging под `target_file`.
  4. Размещает файлы по staging-пути, зеркальному `target_file` (mkdir -p, copy).
  5. Создаёт `.vassal/mirrors/doc-NNN.md` в staging по `shared/mirror-template.md`. **Источник полного текста детерминирован**:
     - Если `combined_text_path` задан — читать UTF-8 из него. Это основной путь и для одиночных файлов (там `combined_text_path` совпадает с `ocr_artifacts[0].path`), и для `grouped_inputs` (там `combined_text_path` — заранее склеенный main-Sonnet'ом файл, в порядке `grouped_inputs`, с разделителем `\n\n--- page N ---\n\n`).
     - Если `combined_text_path == null` И `ocr_artifacts` пустой (legacy/текстовые форматы без saved_to) — скрипт повторно вызывает `extract_text.py` на `source_path` (или на каждом элементе `grouped_inputs` с последующей конкатенацией в том же порядке и разделителем) с теми же аргументами, что использовал `prepare_intake_workdir`, и берёт поле `text` из JSON.
     - Никаких «дозаполнений прозой» — только эти источники.
  5a. **OCR-метаданные для frontmatter зеркала и для классификации (см. шаг 6)**:
     - `pages = sum(a.pages for a in ocr_artifacts)` (суммарно по всем входам группы) либо `pages` одиночного артефакта.
     - `total_chars = sum(a.total_chars for a in ocr_artifacts)`.
     - `extraction_method` = метод первого (primary) артефакта; если методы разные — фиксируется метод первого и в frontmatter добавляется пометка `extraction_methods_mixed: true`.
     - `confidence` — **консервативно худшее** значение по всем артефактам (ordering `low < medium < high`; float → бинуется тем же правилом порога из `classify_ocr_quality`). Это защищает от случая, когда одна страница серии читается плохо, а остальные — хорошо: классификация пойдёт по худшей.
  6. Классифицирует OCR quality через `classify_ocr_quality.classify(...)` (импорт из Ф1), подавая агрегированные `extraction_method`, `confidence`, `total_chars`, `pages` из шага 5a.
  7. Собирает новый `index.yaml`:
     - Добавляет +N записей `documents[]` для каждого `items[]`. Маппинг полей: `doc_id→id`, `target_file`→relpath от `case_root`→`file`, mirror path, `type`/`title`/`date`/`source`, OCR-классификация (`ocr_quality`, `ocr_quality_reason`), `added` = сегодня, `processed_by = "haiku"`.
     - `origin.name`, `origin.received`, `origin.batch`, `origin.archive_src` — из item копируются 1:1 (с валидацией `batch == plan.batch`).
     - `bundle_id`, `parent_id`, `role_in_bundle`, `attachment_order` — из item копируются 1:1.
     - `raw_only[]` НЕ индексируется, `skipped[]` НЕ индексируется.
     - `bundles[]` в index обновляются: для каждого `bundles[]` из плана с `is_new: true` — новый элемент `{id, title, main_doc, members}` дописывается в `bundles` секцию index; с `is_new: false` — найти существующий по id и добавить новые doc_id в `members` (merge без дубликатов, порядок: старые + новые в порядке items).
     - Bump `next_id = max(existing, next_id_start + len(items))`.
     - Bump `next_bundle_id`: если в плане есть новые бандлы — `next_bundle_id = next_bundle_id_start + count(is_new=true)`; иначе — без изменений. Валидация: результат ≥ текущего `next_bundle_id` в index.yaml.
     - Валидация собранного index против `shared/index-schema.yaml` (обязательные поля на каждом document, уникальность id, ссылочная целостность bundle_id/parent_id/members).
  8. **Promote (recoverable)**: записать `<batch>-apply-state.json` (`status: promoting`), затем по очереди `os.replace` staging → target для каждой пары, обновляя `promoted` после каждого шага; в конце — `os.replace` index.yaml. На re-run после сбоя скрипт детектит state-файл и довыполняет только непроиндексированные шаги (см. §Staged commit + recoverable partial-apply protocol, шаг 5).
  9. Перевести state → `status: done`. Дописать строку в `.vassal/history.md` в формате, совместимом с текущими smoke-тестами и `tests/fixtures/dummy-case/expected/history-entry.md`: `YYYY-MM-DD HH:MM intake apply: batch=<batch>, файлов: N, комплектов: M, сирот: S, план: .vassal/plans/<plan-stem>.md`. Plan-строка (`intake plan: .vassal/plans/<plan-stem>.md, файлов в плане: N`) остаётся за главной Sonnet в фазе plan (вне этого скрипта).
  10. Удалить исходники из `Входящие документы/` строго по `cleanup_set`.
  11. `shutil.rmtree(.vassal/tmp/apply-<batch>/)` — зачистка staging. Удалить state-файл `<batch>-apply-state.json`.
  12. Финальная зачистка артефактов плана (только после успешных шагов 1–11):
      - `shutil.rmtree(work_dir)` — удаляется именно тот `work_dir`, что был объявлен в плане и прошёл containment-проверку (не «всё под `.vassal/work/`»);
      - удаляются `--plan-yaml` и sibling-markdown (`<plan>.md`, если существует рядом с YAML; имя выводится детерминированно — тот же stem, другое расширение);
      - ошибки удаления не откатывают apply, пишутся в JSON-ответ как `cleanup_errors`.
- `--dry-run` — всё логирует, ничего не пишет.
- stdout JSON:
  ```json
  {
    "applied": true,
    "batch": "intake-2026-04-24",
    "added_doc_ids": ["doc-042","doc-043"],
    "converted_images": 1,
    "bundle_count": 1,
    "orphan_count": 2,
    "raw_batch_path": "/abs/.vassal/raw/intake-2026-04-24",
    "history_line": "2026-04-24 15:30 intake apply: batch=intake-2026-04-24, файлов: 2, комплектов: 1, сирот: 0, план: .vassal/plans/intake-2026-04-24-1500.md",
    "state_file": ".vassal/plans/intake-2026-04-24-apply-state.json",
    "cleanup_errors": []
  }
  ```

## Test strategy

- **Unit (pytest, `tests/unit/`)**: чистые функции — classify_ocr_quality (все ветки таблицы, включая legacy/null/unknown-method), validate_opus_output (по фикстурам), scan_case_state (против `tests/fixtures/case-with-drift/`), prepare_intake_workdir (моки для extract_text), apply_intake_plan (e2e над скопированным в tmp фикстом).
- **Smoke (`tests/smoke/*.sh`)**: добавить по одному bash-тесту на Ф3 и Ф5 — вызывают скрипт, парсят JSON через `jq`, проверяют exit code и обязательные ключи.
- **Ключевые кейсы**:
  - Ф1: `extraction_method=ocr, confidence=0.74, 500 chars over 2 pages` → `low`; `haiku-vision, 0.80, 1000/3` → `ok` + `ocr_reattempted` caller ставит сам; `confidence="0.82"` → корректный parse; `extraction_method="none"` (провал `extract_text.py`) → `empty` с reason `"extraction failed"` (регрессионный тест на NIT — без этого правила нераспознанные файлы тихо попадали бы в `ok`).
  - Ф2: 3.1a без последней `READY_FOR_DOCX` → `valid=false`; 3.1b с 3 сегментами, каждый корректен → `valid=true` с `segments.length==3`; 3.1c timeline без ```mermaid → `valid=false`; `build-position` с ```mermaid вне `## Схема сторон` (например, в `## Анализ`) → `valid=false`; `build-position` с ```mermaid внутри `## Схема сторон` → `valid=true`.
  - Ф2 doc_type mismatch: `--skill legal-review` с `READY_FOR_DOCX: processual` → `valid=false` с ошибкой `doc_type mismatch: expected analytical for skill legal-review, got processual`; `--skill appeal` с `READY_FOR_DOCX: analytical` → `valid=false` симметрично; `--skill build-position` с `READY_FOR_DOCX: letter` → `valid=false`; `--skill cassation` с `READY_FOR_DOCX: processual` → `valid=true` (совпадение).
  - Ф3: файл, добавленный вручную, → попадает в `new_files`; запись в индексе без файла → `orphans`; mirror старше file mtime → `stale_mirrors`.
  - Ф4: zip с 2 pdf → оба в `files` с `archive_src` и с `ocr_artifact_path`; png-файл → `needs_image_to_pdf: true`; malicious zip с entry `../evil.txt` → файл не извлечён, архив в `unsupported` с `reason: "path escape"`, рядом с `work_dir` никаких побочных файлов; tar с symlink на `/etc/passwd` → отклонён.
  - Ф5: --dry-run не меняет ФС; happy-path на 2 файла → `index.yaml` валиден, `next_id` смещён на 2, оба зеркала созданы, `Входящие документы/` пустое, `history.md` содержит строку формата `YYYY-MM-DD HH:MM intake apply: batch=..., файлов: N, комплектов: M, сирот: S, план: .vassal/plans/...md`. Recovery: искусственно прерванный promote (N из M replace'ов) + повторный запуск → эквивалентно однопроходному. Containment: `raw_only[].archive_src` вне `source_inbox` → exit 1.
- **Что НЕ тестируем**:
  - Реальный tesseract/ocrmypdf (медленно, уже покрыто смоком `extract_text.py`).
  - LLM-суждение (bundle/orphan-классификация, summary, legal-analysis) — остаётся за агентом.
  - Интеграцию SKILL.md с реальным Haiku-subagent.

## Risks / unknowns / assumptions

1. **Схема `plan_path.yaml` (Ф5)** — новая, раньше существовал только markdown-план. Предположение: main-Sonnet параллельно пишет оба файла в Ф1 intake; markdown остаётся «для юриста», YAML — для скрипта. Если Codex при ревью сочтёт это лишним слоем — можно переиспользовать YAML frontmatter в markdown-плане, но это усложнит парсинг.
2. **Импорт `extract_text.py` как модуль (Ф4)** — скрипт сейчас исполняемый. Возможно потребуется лёгкий рефакторинг (`if __name__ == "__main__": main()`) или fallback на subprocess. Предположение: субпроцесс приемлем, но медленнее.
3. **`classify_ocr_quality` vs. таблица в `shared/conventions.md`** — источник истины остаётся в conventions.md (это канон для людей); скрипт обязан повторять её дословно. Расхождение конвенции и скрипта ловится unit-тестами, но синк-правило — на ревьюере.
4. **Старые SKILL.md, которые не переписываются в этом плане** — update-index, intake, add-evidence, add-opponent продолжают содержать дублирующие inline-таблицы. Ф1 даёт скрипт; миграция 4 SKILL.md с удалением дублей входит в этот план только для intake и update-index (в рамках Ф3 и Ф5); add-evidence и add-opponent — отдельным коммитом внутри Ф4 (раз уже их правим из-за intake_workdir), либо переносятся в Plan 2.
5. **Plan 2 (middle-value, будущий, не этот)**: `mirror_from_extraction.py`, `parse_and_merge_timeline.py`, `reocr_select.py` + `apply_reocr_result.py`, `prepare_hearing_publish.py`.
6. **Plan 3 (low-value + init-case)**: `reserve_position_version.py`, `init_case_scaffold.py`, `extract_case_candidates.py`, и полноценный `skills/init-case/SKILL.md` (сейчас его нет, но на него ссылаются другие скиллы).
7. **`prepare_intake_workdir.py` по archive-типам** — `unrar` может отсутствовать на dev-машинах; тогда `.rar` в `unsupported`. Ограничение принимается.
8. **Обратная совместимость index.yaml** — не меняется. Скрипты читают/пишут ровно те же поля, что и текущий main-Sonnet.

## Phases

## Ф1: classify_ocr_quality.py + tests scaffold

Шаги:
1. Создать `scripts/classify_ocr_quality.py` с функцией `classify(...)` и CLI-обвязкой (argparse).
2. Реализовать ровно таблицу из `shared/conventions.md` §`OCR quality thresholds` с жёстким приоритетом правил: (1) нормализация method → (2) method-based fast path для `pdf-text/docx-parse/text-read` → `ok` без проверки confidence → (3) для `ocr`: empty-check (<50 chars) → coerce confidence (float или categorical `"high|medium|low"`) → порог confidence/chars-per-page → ok|low → (4) для `haiku-vision`: coerce + порог без empty-ветки → (5) unknown method → `ok` (legacy/презумпция native text).
3. JSON-вывод: `{"ocr_quality": "...", "ocr_quality_reason": "..."}`.
4. Создать `tests/unit/__init__.py`, `tests/unit/conftest.py` (добавить `plugins/vassal-litigator/scripts` в `sys.path`).
5. Написать `tests/unit/test_classify_ocr_quality.py` — минимум 10 кейсов, включая: `pdf-text + confidence="high"` → `ok` (регрессионный тест на недеградацию producer'а), `pdf-text + confidence="medium"` → `ok`, `docx-parse + "high"` → `ok`, `ocr + "low"` → `low`, `ocr + "medium"` → `low` или `ok` по порогу chars/page, `ocr + float 0.82 + 500chars/2pages` → `ok`, `ocr + 30 chars` → `empty`, `haiku-vision + 0.80 + 1000/3` → `ok`, `confidence=None` при `ocr` → `low`, `extraction_method="none"` → `empty` (regression на NIT), unknown method (например `"legacy-parser"`) → `ok`.
6. Мигрировать callers:
   - `skills/add-evidence/SKILL.md` шаг 2 — удалить inline-блок про `confidence`/`extraction_method`/`ocr_quality`, заменить одной строкой-вызовом скрипта;
   - `skills/add-opponent/SKILL.md` шаг 2 — аналогично;
   - `skills/update-index/SKILL.md` — удалить inline-таблицу порогов, сослаться на скрипт;
   - `skills/intake/SKILL.md` — удалить inline-таблицу порогов, сослаться на скрипт.
7. Smoke-тест не требуется (чистая функция); достаточно unit.

Коммитабельно: да — скрипт работает standalone, и callers мигрируются в этом же коммите (формулы эквивалентны прежним inline-правилам).

## Ф2: validate_opus_output.py + миграция 8 SKILL.md

Шаги:
1. Создать `scripts/validate_opus_output.py`:
   - общий парсер: split по `^## ` (MULTILINE), извлечение первого заголовка как `title`, последней строки как потенциальный `READY_FOR_DOCX:`.
   - три валидатора: `_validate_3_1a(text, skill)`, `_validate_3_1b(text)`, `_validate_3_1c(text, skill)`.
   - сборка итогового JSON по контракту выше.
2. Создать `tests/fixtures/opus_outputs/` с минимальными примерами: `legal_review_valid.md`, `legal_review_no_ready.md`, `prepare_hearing_3_segments.md`, `prepare_hearing_bad_segment.md`, `timeline_valid.md`, `timeline_no_mermaid.md`, `analyze_hearing_valid.md`.
3. `tests/unit/test_validate_opus_output.py` — по одному позитиву и негативу на каждый контракт.
4. Мигрировать SKILL.md: в `legal-review`, `build-position`, `appeal`, `cassation`, `draft-judgment`, `prepare-hearing`, `timeline`, `analyze-hearing` заменить inline-блоки «Проверь, что OUTPUT субагента…» на одну инструкцию строго в форме `--stdin`/`--input-file` (без позиционного `<path>`):
   > Валидация OUTPUT: передай текст OUTPUT Opus-субагента в `python3 "$PLUGIN_ROOT/scripts/validate_opus_output.py" --skill legal-review --contract 3.1a --stdin` (через stdin, без промежуточной записи). Если `valid=false` — ровно один раз запроси Opus-субагент перегенерировать OUTPUT и повтори валидацию; если `valid=false` и после retry — покажи `errors` Сюзерену и останови скилл. Для уже сохранённых на диск OUTPUT использовать `--input-file <path>`.
5. Проверить, что ни один SKILL.md после миграции не содержит старую позиционную форму `validate_opus_output.py <path> ...` (grep в acceptance этой фазы). Retry выполняется ровно один раз на уровне SKILL.md; скрипт retry не делает.
6. Не трогать логику раздачи `.docx` / записи артефактов — только валидацию.

Коммитабельно: да. SKILL.md работают и до, и после (скрипт делает то же, что раньше описывалось прозой).

## Ф3: scan_case_state.py + миграция update-index Ф1

Шаги:
1. Создать `scripts/scan_case_state.py`.
2. Чтение `.vassal/index.yaml` через `yaml.safe_load`.
3. Рекурсивный `os.walk` с фильтрами-исключениями.
4. Сравнение множеств: relativize paths против `case_root`.
5. Для `stale_mirrors` сравнить `mtime(mirror)` с `mtime(file)` и `documents[id].last_verified` (из index.yaml, а не из frontmatter зеркала) с `mtime(file)`. Frontmatter зеркала не парсится — такого поля там нет по текущему шаблону.
6. Создать фикстуру `tests/fixtures/case-with-drift/` (минимальная структура: `.vassal/index.yaml` на 3 записи, на ФС 2 из них + 1 новый файл + 1 зеркало со старым mtime).
7. Unit-тест на все три категории.
8. Мигрировать `skills/update-index/SKILL.md` Ф1: заменить шаги 2–3 на вызов скрипта; оставить шаг 4 (опциональный Haiku) как есть, шаг 5 (показ Сюзерену) — работает с JSON-выходом.

Коммитабельно: да.

## Ф4: prepare_intake_workdir.py + миграция intake/add-evidence/add-opponent Ф1 шагов 1–2

Шаги:
1. Создать `scripts/prepare_intake_workdir.py`.
2. Детекция типа архива по суффиксу; распаковка через subprocess (`unzip`, `7z x`, `tar -xf`, `unrar x`). RAR — best-effort.
2a. Защита от zip-slip/symlink-escape (см. Contracts §Ф4) — два разных пути по формату:
    - **ZIP/TAR**: пре-листинг через Python `zipfile`/`tarfile` ДО любой распаковки; отклонение небезопасных путей, symlink/hardlink-entries, абсолютных путей, `../`-компонентов; если хотя бы один член небезопасен — архив отклонён целиком, ни один файл не распакован.
    - **7Z/RAR**: pre-listing в Python ненадёжен, поэтому используется scratch-dir: распаковка в `work_dir/.scratch/<archive-stem>/` системным `7z x`/`unrar x`, затем пост-walk по `scratch_dir` с realpath-containment-проверкой каждого извлечённого файла; если всё ок — `shutil.move` верифицированных файлов в `extract_root = work_dir/<archive-stem>/`, после чего `shutil.rmtree(scratch_dir)`. Если хотя бы один файл escape'ит из `scratch_dir` — `shutil.rmtree(scratch_dir)` и архив в `unsupported` с `reason: "path escape"`.
    - Общее: после финального размещения — ещё одна пост-валидация `realpath`-containment. Любое нарушение → `shutil.rmtree(extract_root)` + запись в `unsupported`; соседние архивы продолжают обрабатываться.
3. Рекурсивный обход `work_dir` после распаковки; для каждого конечного файла — вызов `extract_text.py` (subprocess, парсинг JSON stdout) **строго с `--output-dir <work_dir>/extracted/`** — иначе `saved_to` не возвращается и `ocr_artifact_path` всегда null (см. Contracts §Ф4). Директория `<work_dir>/extracted/` создаётся заранее. Поле `saved_to` из ответа `extract_text.py` пробрасывается в `ocr_artifact_path` элемента `files[]`.
4. Сбор превью (первые `--max-preview-chars` из `text`) и пометка `needs_image_to_pdf` по суффиксу `{.jpg, .jpeg, .png, .tif, .tiff, .bmp, .heic}` (синк с `shared/conventions.md` и `scripts/image_to_pdf.py`).
5. Фикстура: `tests/fixtures/intake-sample/` с 1 pdf + 1 png + 1 zip с одним pdf внутри.
6. Unit-тест с моком extract_text (чтобы не дёргать tesseract в CI); плюс smoke-тест `tests/smoke/test_prepare_intake_workdir.sh` — реальный прогон, допустимо medium-speed.
7. Мигрировать SKILL.md `intake` Ф1 шаги 1–2 на вызов скрипта; перед передачей файлов Haiku-субагенту main-Sonnet использует готовый JSON. Аналогично (если файлы существуют в репо) `add-evidence/SKILL.md` и `add-opponent/SKILL.md`.

Коммитабельно: да. Haiku по-прежнему получает свой контракт 3.3A; источник превью — теперь JSON от скрипта, а не самостоятельный сбор main-Sonnet.

## Ф5: apply_intake_plan.py + миграция intake Ф3

Шаги:
1. Определить расширенную схему `plan_path.yaml` (items / raw_only / skipped / cleanup_set / already_processed; grouped_inputs для серий изображений; обязательные поля `work_dir` и per-item OCR-payload — см. блокер 4) и добавить её генерацию в `skills/intake/SKILL.md` Ф1 шаг 6 (рядом с markdown-планом, строго в `<case_root>/.vassal/plans/`). `work_dir` и OCR-payload per item берутся из JSON-вывода `prepare_intake_workdir.py` (Ф4) — main-Sonnet просто копирует их в план.
2. Создать `scripts/apply_intake_plan.py`.
3. Реализовать guardrails в порядке: (0) location guardrail `--plan-yaml` — резолв пути и containment в `<case_root>/.vassal/plans/`, fail → exit 1 ДО чтения YAML; затем (1) `resolve()` + containment-проверки (`source_inbox == case_root/Входящие документы` строго; `work_dir` ⊂ `case_root/.vassal/work/` и не равен самому `.vassal/work/`; source внутри inbox ИЛИ объявленного `work_dir`; каждый путь в OCR-payload (`ocr_artifacts[].path`, `combined_text_path`) внутри `work_dir`; target внутри case_root вне `.vassal/` и `Входящие документы/`; `raw_dest` внутри `.vassal/raw/`; `cleanup_set` внутри inbox; `skipped[].path` внутри inbox или `work_dir`). Любое нарушение — exit 1 до любых записей.
4. Реализовать staged commit + recoverable promote: staging в `.vassal/tmp/apply-<batch>/`; все copy/write идут туда; `os.replace` на целевые пути происходит под recovery-record (`<batch>-apply-state.json` в `.vassal/plans/`, `status: promoting` → `done`); re-run идемпотентно довыполняет непройденные `os.replace`'ы; rm из inbox — только после `status: done`.
5. Реализовать шаги apply в порядке из Contracts; импортировать `classify_ocr_quality.classify` и `scripts/image_to_pdf.py` (subprocess, с поддержкой multi-input для `grouped_inputs`).
6. Mirror-шаблон — загрузить `shared/mirror-template.md`, подставить frontmatter полями из item + агрегированными OCR-метаданными (шаг 5a Contracts: суммарные pages/total_chars, primary extraction_method, консервативная confidence) + результатом classify. Полный текст зеркала — строго из `combined_text_path` (read_text UTF-8); fallback на повторный `extract_text.py` допускается только при `combined_text_path == null` и пустом `ocr_artifacts[]` (текстовые форматы без saved_to). Никакого иного источника текста.
7. Обновление `index.yaml` (single-file atomic replace — `os.replace` одного файла POSIX-атомарен): загрузить → добавить N записей (только для `items`, не для `raw_only`/`skipped`) → валидировать → записать в staging (`index.yaml.new`) → `os.replace` выполняется последним шагом promote (после всех staging-to-target replace'ов по файлам), перед переводом state в `done`.
8. `--dry-run` путь — параллельный: guardrails проверяются, staging не создаётся, JSON содержит что БЫ произошло.
9. Rollback-тест (write phase): искусственно ломать index.yaml после копии в staging → убедиться, что ни один целевой файл не тронут, staging удалён, inbox не пуст, state-файл НЕ создан. Recovery-тест (promote phase): прервать процесс после N из M `os.replace` (инъекция raise в цикл), проверить, что state-файл содержит `status: promoting` с `promoted.length == N`; повторный запуск скрипта довыполняет оставшиеся M-N `os.replace`, переводит state в `done`, выполняет cleanup, удаляет state-файл; итоговое состояние эквивалентно однопроходному apply. Тест raw_only containment: `plan.yaml` с `raw_only[0].archive_src = /tmp/evil.zip` (вне `source_inbox`) → exit 1, ни один файл не записан, state-файл не создан, inbox не тронут.
10. Фикстура `tests/fixtures/dummy-case/` расширить до наличия `Входящие документы/` с 1 файлом + готового `plan.yaml` (плюс вариант с grouped_inputs и raw_only).
11. Unit/e2e-тест: скопировать фикстуру в `tmp`, прогнать скрипт, проверить что `index.yaml` валиден, `next_id` увеличен, зеркало создано (и его тело строго равно содержимому `combined_text_path` из фикстуры), origin-поля (`name`, `received`, `batch`, `archive_src`) записаны в `documents[]`, bundles[] обновлены (новый бандл создан ИЛИ members расширены), `next_bundle_id` забампан ровно на число новых бандлов, inbox очищен по `cleanup_set`, `history.md` дописан, `work_dir` удалён, `plan_path.yaml` и sibling-markdown удалены. Отдельный кейс: `grouped_inputs` на 3 изображениях → зеркало равно конкатенации трёх `ocr_artifacts[].path` в порядке `grouped_inputs` (== `combined_text_path`); суммарные `pages=3`, `total_chars` = сумма; `confidence` зеркала — наихудший из трёх. Кейс: mismatch `len(ocr_artifacts) != len(grouped_inputs)` → exit 1 до копирования. Отдельный кейс: plan с `source_inbox`, отличным от `case_root/Входящие документы`, → exit 1, ФС не изменена. Кейс: `work_dir`, лежащий вне `.vassal/work/`, → exit 1. Кейс: `--plan-yaml` указывает на файл вне `<case_root>/.vassal/plans/` (например, `/tmp/evil-plan.yaml` или `<case_root>/plan.yaml`) → exit 1 ДО любых файловых операций, ни inbox, ни `.vassal/` не тронуты, сам plan-файл не удалён.
12. Smoke-тест `tests/smoke/test_apply_intake_plan.sh`.
13. Мигрировать `skills/intake/SKILL.md` Ф3 — весь блок «Main-Sonnet сам выполняет файловые операции…» заменить одной инструкцией «Вызови `python3 "$PLUGIN_ROOT/scripts/apply_intake_plan.py" <case_root> --plan-yaml <path>`; при exit != 0 остановись и покажи stderr Сюзерену». Аналогично при наличии файлов — `add-evidence` и `add-opponent` (их apply идентичен за вычетом того, какие целевые папки допустимы; схема plan.yaml это уже задаёт).

Коммитабельно: да. Это кульминация плана — после этой фазы 30–40% объёма intake/add-evidence/add-opponent SKILL.md схлопывается до вызовов трёх скриптов (Ф4 workdir, субагент-классификатор, Ф5 apply).
