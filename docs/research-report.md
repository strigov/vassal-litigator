# Ф0 — отчёт о эмпирическом research для v0.5.0 (Codex-интеграция)

**Дата:** 2026-04-20
**Исполнитель:** Opus 4.7 (1M context) subagent в Claude Code sandbox.
**Среда:** macOS 24.6.0 (Darwin), codex-cli 0.121.0, companion.mjs v1.0.3, node v25.9.0.
**Причина выбора исполнителя:** делегирование Codex high провалилось (собственная песочница Codex блокирует meta-запуски других Codex-сессий). Подробности — в правках плана, раздел §Risks.

Все нумерованные вопросы (1–8) ниже — из ТЗ ф0 от оркестратора. Для каждого: метод проверки, сырой результат, вывод, влияние на Ф1–Ф8 и оставшиеся открытые риски.

---

## 1. `$imagegen` — Branch A (через companion) и Branch B (прямой `codex exec`)

### Метод проверки

**Branch A (companion task --background):**

```bash
cd /tmp
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task --background --write --effort medium \
  '$imagegen тестовый треугольник на белом фоне (тест Ф0 v0.5.0 Branch A)'
# task-mo7hqczc-fqtcbz submitted; polled via Monitor; fetched result.
```

Предусловие: включена глобальная feature-flag Codex `image_generation` командой

```bash
codex features enable image_generation
# → "Enabled feature `image_generation` in config.toml."
# → warning: "Under-development features enabled: image_generation."
```

Подтверждено, что companion.mjs v1.0.3 НЕ пробрасывает `--enable image_generation` во вложенный вызов `codex exec`:

```bash
grep -E "image_generation|--enable|featureFlags" ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs
# только упоминания --enable-review-gate / --disable-review-gate — никакого image_generation.
```

**Branch B (прямой `codex exec`, без companion):**

```bash
cd /tmp
codex exec --skip-git-repo-check --sandbox workspace-write --enable image_generation \
  -C /tmp -c model_reasoning_effort=medium \
  '$imagegen тестовый треугольник на белом фоне (Branch B Ф0 v0.5.0)'
```

### Результат (raw)

**Branch A:**
- status: `completed`, phase: `done` (через ~40 сек).
- stdout результата (final output) — естественно-язычное: `"Использую \`imagegen\` в встроенном режиме и сгенерирую один тестовый растр по вашему описанию."` — **БЕЗ** строки `GENERATED_IMAGE: <abs_path>`.
- Реально сгенерированный PNG найден на диске:
  ```
  /Users/strigov/.codex/generated_images/019dac03-f276-7e13-af41-98a30894ac86/ig_0ea7a1a2e64fa5cb0169e667756e9881979f8f63c62e81da25.png
  file: PNG image data, 1024 x 1024, 8-bit/color RGB, non-interlaced; 62 KB
  ```
- `sessionId` = `019dac03-f276-7e13-af41-98a30894ac86` (присутствует в поле `job.sessionId` в `status --json`).

**Branch B:**
- stdout напрямую: `"Использую навык \`imagegen\` в встроенном режиме: сгенерирую простой растровый тестовый треугольник на белом фоне..."` + в конце блок `tokens used 25 577`. Строки `GENERATED_IMAGE:` также нет.
- PNG найден:
  ```
  /Users/strigov/.codex/generated_images/019dac05-938b-79c3-aaf1-82abe157cb10/ig_00927cf1d3b262f20169e667e2c88c81969954445aa5e6490a.png
  file: PNG image data, 1024 x 1024, 8-bit/color RGB, non-interlaced; 56 KB
  ```
- `session id` печатается в stderr-блоке Codex: `session id: 019dac05-938b-79c3-aaf1-82abe157cb10`.

### Вывод

- **Оба branch'а РАБОТАЮТ** эмпирически. PNG действительно генерируется (1024x1024, корректный).
- **Branch A — основной по умолчанию для Ф5.** Поддерживает `--background` + Monitor poll-loop — это консистентно со всеми остальными ролями плагина (file-executor, reviewer, timeline-builder) через companion. Требует однократную настройку: юрист выполняет `codex features enable image_generation` в своём shell.
- **Branch B — fallback**, если юрист не хочет глобально включать `image_generation`. Синхронный блок Claude-main (~30-90 сек), без Monitor. Команда эмпирически отрабатывает.
- **Критичное расхождение с планом (AMENDED):** план R1 ожидает, что Codex печатает строку `GENERATED_IMAGE: <abs_path>` в stdout — такой строки НЕТ ни в Branch A, ни в Branch B. Stdout содержит только естественно-язычное сообщение Codex про «навык imagegen». Плагин должен получать путь иначе — вычислять из `sessionId` и паттерна `$CODEX_HOME/generated_images/<session_id>/ig_*.png`.

**Исход:** Branch A возможен → выбираем его по умолчанию. Branch C (stub) не нужен.

### Влияние на последующие фазы

- **Ф1 (codex-invocation SKILL.md):** добавить explicit секцию «Получение пути сгенерированного изображения». Claude-main:
  1. Получает `sessionId` из `result --json | .job.sessionId` (Branch A) или парсит из stderr `session id: <UUID>` (Branch B).
  2. Резолвит `CODEX_HOME` как `${CODEX_HOME:-$HOME/.codex}`.
  3. Находит PNG: `ls "$CODEX_HOME/generated_images/<sessionId>/" | grep '^ig_.*\.png$'`. Обычно один файл на turn (проверено эмпирически на 2 turn'ах). Если >1 — берёт последний по mtime.
  4. Копирует в `[CASE_ROOT]/.vassal/visuals/<logical-name>.png`.
- **Ф1 (codex-invocation SKILL.md / секция «Визуализатор»):** прописать, что Branch A требует предусловия `codex features enable image_generation` и это должно быть зафиксировано в README плагина. Branch B как fallback-команда в SKILL.md (уже зафиксирована в плане v0.5.0).
- **Ф5 (`prompts/imagegen-visualizer.md`):** НЕ требовать от Codex печатать `GENERATED_IMAGE:` (Codex не делает этого стабильно). Вместо этого: в промпте просить Codex подтвердить «image_gen вызван» — и оркестратор сам находит файл по `sessionId`.
- **Ф7 (README.md):** добавить раздел «Предустановка Codex feature-flag»: однократная команда `codex features enable image_generation`, объяснить, что это «under development» фича.

### Риски, оставшиеся открытыми

- **Не тестировалось:** надёжность генерации при повторных вызовах imagegen в одной сессии (возможны несколько PNG в одной папке). Мой эмпирический прогон дал 1 PNG на session. Для плагина это НЕ блокер — sessionId новый для каждого Branch A task.
- **Codex feature `image_generation` помечена "under development"** — может регрессировать при обновлении codex-cli. Mitigation: записано в R4 плана (hardcoded версия companion).

**Статус вопроса:** `AMENDED` — эмпирика подтвердила Branch A как основной, но обнаружила расхождение с планом в способе извлечения пути PNG. Требует уточнения в Ф1 SKILL.md и Ф5 промпте.

---

## 2. Длина промпта (~25K байт)

### Метод проверки

Сгенерирован промпт ровно на 24 692 байта / 14 388 символов: повторение строки `"Это тест длинного промпта Ф0 v0.5.0. Повторяю заголовок много раз.\n"` 214 раз + финальный вопрос:

```
===
Вопрос: сколько раз в этом сообщении был упомянут заголовок «v0.5.0»?
Ответь ТОЛЬКО одним целым числом.
```

Ground truth (проверено `re.findall(r'v0\.5\.0', prompt)`): **214 совпадений.**

Задача отправлена через companion:

```bash
cd /tmp
PROMPT="$(cat /tmp/vl-ф0-longprompt/prompt-25k.txt)"
node ~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/codex-companion.mjs task --background --effort medium "$PROMPT"
```

### Результат (raw)

- task-mo7hx7go-g2sn5j, status=completed, duration 48 сек (Turn started→Turn completed).
- final output: `"201"` (единственная строка).
- Ground truth: 214. Разница: −13 (−6%).

### Вывод

- **Промпт на 25K байт (≈14K символов кириллицы) полностью принят Codex medium.** Нет обрыва, нет ошибок CLI/broker, ответ соответствует характеру задачи (целое число).
- Погрешность ответа (201 vs 214) — это особенность LLM при точном подсчёте повторов, НЕ признак обрезания промпта. Если бы Codex получил обрезанный промпт, ожидали бы число сильно меньше 200 или сигнал об ошибке.
- **25K байт — надёжно проходит.** Это покрывает реалистичные промпты vassal-litigator (наполнение `_preamble.md` + контракт путей + тело задачи + `PLAN_BODY` preview ~ обычно 5-15K байт).

### Влияние на последующие фазы

- **Ф1 и все последующие:** стратегия R5 из плана — `Codex читает с диска, а не получает в промпте` — всё ещё правильная, но поднимать her уровень (фиксировать лимит) не требуется: на промптах до 25K байт Codex стабилен. Большие payloads (например `ARCHITECTURE.md` + 3 зеркала) всё равно лучше хранить на диске и указывать Codex прочитать — это консервативнее и проще для отладки.
- **Ф1 (`_preamble.md`):** сам преамбула в районе 1-2K байт + тело ролевого промпта 2-8K байт — с огромным запасом.
- **Ф5 (imagegen-visualizer):** описание визуализации обычно 200-500 байт — тривиальный размер.
- **Ф6 (analytical-reviewer):** input юриста + путь к артефакту — малый payload. Codex сам читает файлы по путям.

### Риски, оставшиеся открытыми

- Верхний предел прома не определялся эмпирически (ответ в п.6 частично покрывает ~50K байт). Если возникнут промпты >50K байт — отложить на доп.research. Для v0.5.0 этого не ожидается.

**Статус вопроса:** `CONFIRMED` — план R5 не требует правок.

---

## 3. `openai-codex` как зависимость (A3: README vs manifest `dependencies`)

### Метод проверки

Прочитан полный справочник: `~/.claude/plugins/cache/claude-plugins-official/plugin-dev/unknown/skills/plugin-structure/references/manifest-reference.md`.

Проверено содержимое `~/.claude/plugins/marketplaces/openai-codex/plugins/codex/.claude-plugin/plugin.json`.

Проверен файл `~/.claude/plugins/installed_plugins.json` — формат реальных установок.

### Результат (raw)

**manifest-reference.md** содержит полный list полей `plugin.json`:
- Core: `name`, `version`, `description`
- Metadata: `author`, `homepage`, `repository`, `license`, `keywords`
- Component paths: `commands`, `agents`, `hooks`, `mcpServers`

**Поле `dependencies` / `requires` / `peerPlugins` — ОТСУТСТВУЕТ.**

`installed_plugins.json` показывает, что установки плагинов отслеживаются через отдельный файл (scope=user/project/local, installPath, installedAt). Плагины НЕ декларируют зависимости друг от друга в своих манифестах.

### Вывод

- Архитектурное решение **A3 подтверждено эмпирически**: README-prerequisite — единственный рабочий способ документировать зависимость от `openai-codex` плагина.
- В plugin.json vassal-litigator секция `dependencies` не может быть добавлена — её просто нет в схеме.

### Влияние на последующие фазы

- **Ф1 (plugin.json):** НЕ добавлять `dependencies`. Только обновить `description`.
- **Ф7 (README.md):** в секции «Предусловия» явно прописать:
  ```
  Плагин vassal-litigator требует установленного плагина openai-codex ≥ 1.0.3.
  Установка: /plugin marketplace add openai/codex-plugin-cc  →  /plugin install codex@openai-codex
  ```

### Риски, оставшиеся открытыми

- Нет.

**Статус вопроса:** `CONFIRMED` — план A3 подтверждён, правки не требуются.

---

## 4. UTF-8 / кириллица в Codex-операциях

### Метод проверки

Создана структура с кириллицей (включая папки с пробелами и файлы с ёлочками «»):

```
/tmp/vl-ф0-test/
├── Входящие документы/
│   └── «Договор поставки».txt   (содержимое: "Тестовый контент. Стороны: ООО Ромашка, ООО Лютик.")
├── raw/
└── Материалы от клиента/
    └── Договоры/
```

Задача через companion (`--write`, medium):

> Прочитай содержимое папки /tmp/vl-ф0-test/Входящие документы/. Для каждого файла:
> 1. Скопируй его в /tmp/vl-ф0-test/raw/ (сохрани имя).
> 2. Переименуй копию в /tmp/vl-ф0-test/Материалы от клиента/Договоры/2026-04-21 ООО Ромашка Договор поставки.txt.
> 3. Выведи содержимое переименованного файла.
> Важно: НЕ транслитерируй имена. Работай в UTF-8. Сохраняй кириллицу и ёлочки («»).

### Результат (raw)

- task-mo7htzxl-e134es, completed за ~40 сек.
- Во всех командах Codex автоматически установил `LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8`:
  ```
  Running command: /bin/zsh -lc 'LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 ls -la "/tmp/vl-ф0-test/Входящие документы"'
  ```
- Итоговая проверка:
  - Целевой файл: `/tmp/vl-ф0-test/Материалы от клиента/Договоры/2026-04-21 ООО Ромашка Договор поставки.txt`
  - `file` — `Unicode text, UTF-8 text`
  - `hexdump` пути — корректные UTF-8 последовательности (`d0 9c d0 b0 d1 82 d0 b5 d1 80 d0 b8 d0 b0 d0 bb d1 8b` = «Материалы»)
  - Содержимое файла: `Тестовый контент. Стороны: ООО Ромашка, ООО Лютик.` — неизменно
  - Исходный `«Договор поставки».txt` ВСЁ ЕЩЁ есть в `Входящие документы/` (copy прошёл, не move).
- **Нарушение плана (важно для R9):** Codex ПРОПУСТИЛ шаг 1 (копирование в `raw/`) — папка `raw/` пуста. Codex в своём assistant message написал «копию положу в raw, затем перемещу в Материалы...», но по факту выполнил `cp` напрямую из «Входящие» в «Материалы...», минуя `raw/`. Это классическое «Codex оптимизирует план» поведение — R9 в действии.

### Вывод

- **Кириллица и UTF-8 работают корректно.** Codex по умолчанию использует `LC_ALL=en_US.UTF-8` и не транслитерирует. Ёлочки «» сохраняются. Имена папок с пробелами — OK (Codex цитирует пути).
- **R9 подтверждён эмпирически на реальном примере:** Codex может «оптимизировать» план, пропуская промежуточные шаги. На тесте шаг `cp в raw/` был склеен с `mv в целевое имя` в один `cp из Входящих сразу в целевое`.
- Хорошая новость: ни один шаг не вышел ЗА пределы plan'а (Codex не создал посторонних файлов), только усечённое исполнение.

### Влияние на последующие фазы

- **Ф1 (`_preamble.md` + все file-executor промпты):** добавить отдельное правило:
  > **Выполняй ВСЕ шаги буквально, даже если они кажутся избыточными.** Например: «копировать в raw/, затем переименовать» — делай именно это, двумя операциями. НЕ склеивай cp+mv в один cp. Промежуточные копии в raw/ нужны для аудита (юрист имеет право восстановить исходник).
- **Ф1/Ф2 (`skills/intake/SKILL.md` и `prompts/file-executor-intake.md`):** явный контракт «raw/ должна содержать копию ВСЕХ исходных файлов из Входящих документов/ до переименования». Claude-main в фазе 4 (верификация) проверяет: `ls .vassal/raw/intake-*/` совпадает по количеству с `FILES_PROCESSED`.
- **Ф2 (smoke-тест):** `tests/smoke/test-intake.sh` должен проверять, что после intake в `.vassal/raw/intake-<дата>/` есть столько же файлов, сколько в preview plan. Если не совпадает — INTEGRITY_FAIL.
- **R3 (кириллица):** доп.mitigation уже не нужен — Codex сам ставит `LC_ALL=en_US.UTF-8`. Убрать из промптов избыточные «Обязательно используй LC_ALL=...» инструкции — Codex делает это сам. Правила «не транслитерировать, цитировать пути» оставить.

### Риски, оставшиеся открытыми

- R9 теперь имеет empirical evidence — нужна жёсткая формулировка в промптах: «буквальное исполнение каждого шага плана».
- Не тестировались: (a) имена с пробелами И эмодзи одновременно, (b) имена >256 байт UTF-8 (редкий случай для юридических дел).

**Статус вопроса:** `AMENDED` — план R3 корректен (UTF-8 сохраняется), но дополнительно R9 подтверждён на живом примере; требуется усилить формулировку «буквальное исполнение» в Ф1 `_preamble.md` + верификация `raw/` в Ф2 smoke.

---

## 5. YAML-мутация `index.yaml`

### Метод проверки

Создан валидный `/tmp/vl-ф0-yaml/index.yaml` с 3 реалистичными записями (doc-001, doc-002, doc-003) по схеме `shared/index-schema.yaml`: version, documents с parties (простые и `from/to`-форма), bundles пустые, next_id=4.

Бэкап в `index.yaml.original`.

Задача через companion (`--write`, medium):

> Добавь в /tmp/vl-ф0-yaml/index.yaml новую запись doc-004 (файл из переписки, parties as from/to, все обязательные поля по схеме), инкрементируй next_id с 4 на 5, проверь `python3 -c "import yaml..."`, не трогай version, bundles.

### Результат (raw)

- task-mo7hw0sj-v1ggfa, completed за ~60 сек.
- `yaml.safe_load('/tmp/vl-ф0-yaml/index.yaml')` — проходит без ошибок.
- `len(documents)` = 4 (было 3).
- `next_id` = 5 (было 4).
- `version` = 2 (не изменилось).
- `bundles` = [] (не изменилось).
- `doc-004.file`: `Материалы от клиента/Переписка/2025-12-05 ООО Ромашка Ответ на претензию.pdf` — кириллица сохранена.
- `doc-004.parties`: `[{'from': 'ООО «Лютик»', 'to': 'ООО «Ромашка»'}]` — ёлочки сохранены.
- `diff` оригинала и результата: добавлены только 32 строки doc-004, плюс инкремент `next_id: 4 → 5`. Остальные записи НЕ тронуты (ни форматирование, ни значения).

### Вывод

- **Codex medium корректно добавляет запись в YAML с инкрементом счётчика, сохраняя структуру и форматирование остальных записей.**
- Кириллица и ёлочки — через `--write` работают.
- В этом конкретном тесте Codex НЕ создал `.bak` файл перед мутацией (и не просили в промпте). План R2 требует `.bak` перед записью — это нужно прописать в промптах явно.

### Влияние на последующие фазы

- **Ф1 (`_preamble.md` / YAML-дисциплина):** добавить явное правило:
  > Перед любой мутацией `.vassal/index.yaml` или `.vassal/case.yaml` создай backup: `cp .vassal/index.yaml .vassal/index.yaml.bak`. После мутации выполни `python3 -c "import yaml; yaml.safe_load(open('.vassal/index.yaml'))"`. Если ошибка — откати: `mv .vassal/index.yaml.bak .vassal/index.yaml` и верни BLOCKED.
- **Ф2 (`prompts/file-executor-intake.md`, `prompts/file-executor-update-index.md`):** этот цикл backup → mutate → validate → rollback_on_failure обязателен. Зафиксировать в промптах.
- **Ф3 (`prompts/file-executor-catalog.md` и др.):** то же самое для index.yaml и case.yaml.
- **Ф2 (smoke-тест):** `tests/smoke/test-yaml-resilience.sh` — намеренно подать Codex некорректный план, проверить, что index.yaml не поехал.

### Риски, оставшиеся открытыми

- Не тестировалось поведение при **конфликте** (две параллельные сессии Codex мутируют index.yaml одновременно). В рамках vassal-litigator это не сценарий — вызовы последовательные, Claude-main оркестрирует.
- Для очень больших index.yaml (500+ документов) — не тестировалось. Ожидание: работает так же, но медленнее.

**Статус вопроса:** `CONFIRMED` — YAML-мутация надёжна, но нужно явное правило `.bak` в промптах (план R2 уже это предусматривает — просто формализовать в `_preamble.md`).

---

## 6. Длина контекста (~50K байт документ + вопрос в конце про начало)

### Метод проверки

Сгенерирован документ 50 078 байт / 27 332 символа:
- В начале: `СЕКРЕТНЫЙ МАРКЕР_НАЧАЛА: название дела ООО Ромашка vs ООО Лютик, номер А40-12345/2025.`
- Середина: 171 раз `Раздел {N}: наполнитель для проверки длинного контекста. Юридические термины: подсудность, исковая давность, правоспособность, реквизиты, исполнительный лист.`
- В конце: вопрос про номер дела из начала.

Задача через companion (medium):

```bash
PROMPT="$(cat /tmp/vl-ф0-longprompt/prompt-50k.txt)"
node ... task --background --effort medium "$PROMPT"
```

### Результат (raw)

- task-mo7hysyl-ozrpko, completed.
- final output: `A40-12345/2025`
- **Точный правильный ответ.** Номер дела был в самом начале 50K-ного документа, вопрос — в самом конце. Codex medium должен был прочесть весь payload, удержать начальный маркер и ответить точно.

### Вывод

- **50K байт (≈27K символов кириллицы) — надёжно проходит через companion в Codex medium.** Нет обрыва, нет галлюцинаций (ответ — точная строка из начала документа).
- Retention контекста на границе beginning→end работает корректно.

### Влияние на последующие фазы

- **Ф1 и последующие:** при необходимости передать большой контекст в промпте (например, ARCHITECTURE.md целиком как справочник) — до 50K байт проходит. Однако стратегия «Codex читает файлы с диска» (§9 Contracts) остаётся предпочтительной по архитектурным соображениям (повторяемость, удобство debug, не зависит от вмещения в лимит).
- **Ф6 (`prompts/analytical-reviewer.md`):** revver может получать ссылку на большой артефакт (`Правовое заключение.md` может быть 20-40K байт) в промпте — это теперь известно как безопасно. Но лучше передавать путь к файлу, Codex читает сам.
- **Ф7 (README.md):** никаких cautions в явном виде юристу не нужно.

### Риски, оставшиеся открытыми

- Не тестировался предел контекста, где Codex начнёт терять точность. Для v0.5.0 50K — с большим запасом.

**Статус вопроса:** `CONFIRMED` — план R5 правильно предполагает, что большие контексты работают; стратегия «читать с диска» остаётся предпочтительной.

---

## 7. Резолвинг `[PLUGIN_ROOT]`

### Метод проверки

1. Проверены env-переменные: `env | grep -Ei "PLUGIN|CLAUDE|CODEX"`.
2. Прочитан `~/.claude/plugins/installed_plugins.json` — формат отслеживания установок.
3. Прочитан `~/.claude/plugins/known_marketplaces.json` — как настроены marketplace sources.
4. Прочитан `~/.claude/plugins/marketplaces/` — реальные скачанные marketplaces.
5. Прочитан `manifest-reference.md` — переменная `${CLAUDE_PLUGIN_ROOT}` упоминается в контексте hooks и mcpServers.

### Результат (raw)

**Переменные окружения в сессии Claude Code:**
- `CLAUDE_PLUGIN_DATA=/Users/strigov/.claude/plugins/data/codex-openai-codex` — **это data-dir openai-codex плагина**, НЕ нашего vassal-litigator, и не root; установлена потому, что в этой сессии активен openai-codex companion (`CODEX_COMPANION_SESSION_ID` тоже есть).
- `CLAUDE_PLUGIN_ROOT` — **отсутствует** в `env` на уровне main Claude session (присутствует только в контексте hooks/mcpServers, как shell-substitution).
- `CODEX_COMPANION_SESSION_ID=fff60193-680d-4e5c-bf55-9a27a08ecd9f` — сессия companion (не имеет отношения к vassal-litigator root).

**Файл `~/.claude/plugins/installed_plugins.json` (v2) для каждого установленного плагина содержит:**
```json
{
  "<plugin>@<marketplace>": [
    {
      "scope": "user" | "project" | "local",
      "projectPath": "...",  // для scope=project/local
      "installPath": "<абсолютный путь к каталогу плагина>",
      "version": "<версия или 'unknown'>",
      ...
    }
  ]
}
```

Например:
- marketplace-плагин: `installPath = /Users/strigov/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`
- dev-плагин из директории (marketplace типа `directory`, как `strigov-local`): `installPath = /Users/strigov/superpowers-strigov-ver` (прямо путь к исходной директории).

**vassal-litigator НЕ зарегистрирован в `installed_plugins.json`** (текущее состояние — dev-репозиторий, не установлен как плагин Cowork'ом).

```bash
find ~/.claude/plugins -type d -name vassal-litigator
# (пусто)
```

**Рабочий путь для production-установки (предсказуемый):**
- Если юрист установит через marketplace (github:strigov/vassal-litigator или подобное):
  `/Users/<user>/.claude/plugins/cache/<marketplace-name>/vassal-litigator/<version>/`
- Если юрист установит как `directory` marketplace (локальный dev):
  absolute путь источника = `installPath`.

### Вывод

Нет универсальной env-переменной для main-Claude-сессии, дающей абсолютный путь к корню текущего плагина. **Claude-main должен резолвить `[PLUGIN_ROOT]` программно**, используя следующую стратегию (fallback-лестница):

1. **Fallback 1 — env `CLAUDE_PLUGIN_ROOT`** (если вдруг установлена, например, из skill-контекста или project settings): проверить `printenv CLAUDE_PLUGIN_ROOT`. Если есть — использовать.
2. **Fallback 2 — парсинг `installed_plugins.json`:**
   ```bash
   python3 -c "
   import json, os
   p = json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))
   for key, entries in p['plugins'].items():
     if key.startswith('vassal-litigator@'):
       print(entries[0]['installPath'])
       break
   "
   ```
   Возвращает абсолютный путь установки.
3. **Fallback 3 — запрос Сюзерену при первом использовании в сессии:** если ни env, ни `installed_plugins.json` не дают результата, Claude-main спрашивает юриста один раз за сессию, где лежит плагин, и кеширует в локальный файл сессии (`~/.claude/plugin-data/vassal-litigator-state.yaml` или просто в переменную внутри session).

**`[CASE_ROOT]`** — это cwd Claude-main на момент команды (`pwd` при вызове `/vassal-litigator:intake`). Это конвенция плагина.

### Влияние на последующие фазы

- **Ф1 (`skills/codex-invocation/SKILL.md`, секция «Путь к плагину и к делу»):** документировать все 3 fallback'а. По умолчанию использовать Fallback 2 (парсинг installed_plugins.json) — он самый надёжный и не требует взаимодействия с юристом.
- **Ф1 (`_preamble.md`):** каждый промпт получает уже подставленный `[PLUGIN_ROOT]` как абсолютный путь. Contracts §9 — Claude-main сам резолвит перед диспатчем. Codex никогда не видит placeholder, всегда абсолютный путь.
- **Ф1 (smoke-тест контракта путей):** создать `/tmp/vassal-path-test/`, cd туда, вызвать Codex medium с резолвленным `[PLUGIN_ROOT]` в промпте, попросить выполнить `python3 [PLUGIN_ROOT]/scripts/extract_text.py --help`. Пройти за счёт того, что `[PLUGIN_ROOT]` уже заменён на абсолют.
- **Ф7 (README.md, секция «Установка»):** описать два сценария:
  - marketplace install: `/plugin marketplace add <repo>` → `/plugin install vassal-litigator@<marketplace>`
  - dev install: marketplace типа directory через `/plugin marketplace add /path/to/repo`.
  В обоих случаях плагин добавляется в `installed_plugins.json` и резолвинг работает автоматически.

### Риски, оставшиеся открытыми

- Формат `installed_plugins.json` может поменяться в будущих версиях Claude Code — это не стабильный API. Mitigation: записать в R4 плана (hardcoded path) вместе с оговоркой, что `installed_plugins.json` — current v2 формат.
- Fallback 3 (запрос юристу) — usability-нагрузка, применять только как last-resort.

**Статус вопроса:** `AMENDED` — план предполагает резолвинг `[PLUGIN_ROOT]`, но не фиксирует стратегию. Теперь зафиксирована (3-уровневая fallback-лестница, основная — парсинг `installed_plugins.json`).

---

## 8. Batch-intake масштаб (30 / 50 / 100 файлов)

### Метод проверки

В `/tmp/vl-ф0-batch/Входящие/` сгенерировано 100 dummy-PDF файлов (каждый ~50 байт, валидный `%PDF-1.4` header). Три последовательных прогона на batch30, batch50, batch100 через companion (`--write`, medium):

```
Для КАЖДОГО файла:
1. Выведи абсолютный путь.
2. Скопируй в /tmp/vl-ф0-batch/out<N>/ (сохрани имя).
Обработай ВСЕ N файлов, ничего не пропускай. В финальном отчёте укажи "Обработано N из N".
```

### Результат (raw)

**Batch 30 (task-mo7hzjdk-izoqg6):**
- Turn started: 17:57:41.313
- Turn completed: 17:58:23.212
- Время: **~42 сек**.
- `ls /tmp/vl-ф0-batch/out30 | wc -l` = **30 / 30** (100%).
- Codex использовал `find | cpio`-подобную стратегию (на деле `cp` в цикле), затем верифицировал через `comm -3`.

**Batch 50 (task-mo7i0txe-1zjwrs):**
- Turn started: 17:58:41.485
- Turn completed: 17:59:32.805
- Время: **~51 сек**.
- `ls /tmp/vl-ф0-batch/out50 | wc -l` = **50 / 50** (100%).

**Batch 100 (task-mo7i2fsf-0rrc3n):**
- Turn started: 17:59:56.476
- Turn completed: 18:01:06.125
- Время: **~70 сек**.
- `ls /tmp/vl-ф0-batch/out100 | wc -l` = **100 / 100** (100%).
- Final output перечисляет все 100 имён (grep `dummy-` по full result: 200 упоминаний = пути + имена, всё на месте).

### Вывод

- **До 100 файлов включительно — стабильно.** Codex medium обрабатывает всё, верифицирует через `comm -3` и `find … wc -l`, печатает полный список в финальном отчёте.
- Время почти линейно растёт с размером батча (42 → 51 → 70 сек для 30 → 50 → 100 файлов; коэффициент ≈ 0.5 сек/файл).
- **Нет обрывов, нет пропусков, нет «улучшений» (в смысле R9 — в этих batch-тестах Codex честно отработал все шаги плана).**
- Для v0.5.0 **безопасный batch-size — до 100 dummy-файлов** за один диспатч Codex medium. Для **реальных** intake'ов (PDF с OCR) порог может быть ниже из-за нагрузки на extract_text.py и длительности turn'а; реалистично рекомендовать **≤ 30-50 реальных документов на один диспатч** (план R6 корректен), а 100 dummy — показатель запаса прочности CLI/broker.

### Влияние на последующие фазы

- **Ф2 (`skills/intake/SKILL.md`), фаза 1 preview:** Claude-main проверяет `количество_файлов_во_Входящих`. Если > 30 — в preview сообщает юристу «батч крупный, будет N подпакетов по ~30». Если > 50 — обязательно батчировать.
- **Ф2 (apply-фаза):** последовательные диспатчи Codex medium по 25-30 файлов в батче; между батчами — проверка integrity (файлы копированы, index.yaml обновлён).
- **Ф3 (add-evidence, add-opponent):** обычно 1-5 файлов за раз, лимит не беспокоит.
- **R6 mitigation в плане** — актуален, значение 30 в качестве порога батчирования подтверждено.

### Риски, оставшиеся открытыми

- Не тестировалось: 100 файлов с **OCR** (реальный intake). Dummy-файлы не отражают нагрузку на extract_text.py. Если юрист принесёт 100 реальных PDF по 10 страниц — OCR может занять часы, Codex-сессия может тайм-аут. Mitigation: план R6 + батчирование + `processed_by: codex` поле `last_verified` для восстановления.

**Статус вопроса:** `CONFIRMED` (включая batch-100). План R6 корректен; эмпирика даёт запас прочности выше порога 30.

---

## Сводная таблица Ф0

| # | Вопрос | Статус |
|---|--------|--------|
| 1 | $imagegen в Branch A/B | `AMENDED` — Branch A работает; stdout НЕ содержит `GENERATED_IMAGE:` линии, путь резолвится через `sessionId` |
| 2 | Промпт ~25K байт | `CONFIRMED` |
| 3 | openai-codex как зависимость | `CONFIRMED` — поле `dependencies` в plugin.json отсутствует, A3 README-prerequisite |
| 4 | UTF-8 / кириллица | `AMENDED` — UTF-8 OK, но R9 empirical evidence: Codex может склеивать шаги, нужна жёсткая формулировка в `_preamble.md` |
| 5 | YAML-мутация | `CONFIRMED` — нужно явное правило `.bak` в `_preamble.md` (план R2 уже это предполагает) |
| 6 | Длина контекста ~50K | `CONFIRMED` |
| 7 | [PLUGIN_ROOT] resolution | `AMENDED` — нет env-переменной, зафиксирована 3-уровневая fallback-лестница |
| 8 | Batch 30 / 50 / 100 | `CONFIRMED` — стабильно до 100 dummy-файлов, R6 план актуален |

**Общий статус Ф0:** `DONE_WITH_CONCERNS` — все 8 вопросов эмпирически исследованы, но 3 из них (`AMENDED`) требуют точечных правок в фазах Ф1 и Ф5. Перечень правок:

1. **Ф1/Ф5 (вопрос 1):** `codex-invocation/SKILL.md` — добавить секцию «Получение пути сгенерированного изображения» (через `sessionId`, а не через `GENERATED_IMAGE:` строку). `prompts/imagegen-visualizer.md` — не требовать от Codex печатать путь.
2. **Ф1 (вопрос 4 / R9):** `_preamble.md` — жёсткое правило «выполняй все шаги плана буквально, не склеивай cp+mv». Все file-executor промпты наследуют. `tests/smoke/test-intake.sh` — проверка наполнения `.vassal/raw/`.
3. **Ф1 (вопрос 7):** `codex-invocation/SKILL.md` — секция «Путь к плагину» с 3-уровневой fallback-лестницей резолва `[PLUGIN_ROOT]`. Основа — парсинг `~/.claude/plugins/installed_plugins.json`.

Остальные `CONFIRMED` — точных правок не требуют, только подтверждение стратегий плана.
