> **ВАЖНО: Конфиденциальность.** Плагин отправляет материалы дела (тексты документов, зеркала, метаданные) в Anthropic через Claude для файлового пайплайна, аналитики и подготовки документов. Устанавливая плагин, вы подтверждаете согласие на такую передачу. Если это недопустимо для вашей юрисдикции или клиентского договора — не устанавливайте плагин.

# vassal-litigator-cc

Вассал — плагин для **Claude Code**, помогающий юристу вести судебные дела от первичного приёма материалов клиента до кассационной жалобы. Форк [vassal-litigator](https://github.com/strigov/vassal-litigator) v0.5.4, адаптированный под Claude-only оркестрацию.

## Возможности

**Приём и систематизация документов** — OCR сканов и фотографий, переименование файлов по содержимому, создание текстовых зеркал, автоматическое ведение реестра документов дела.

**Правовой анализ** — квалификация спора, проверка сроков исковой давности, определение подсудности, оценка полноты доказательственной базы, формирование правовой позиции с оценкой рисков.

**Подготовка к заседаниям** — stress-test позиции (red team / blue team), генерация процессуальных документов и заметок к заседанию.

**Анализ заседаний** — разбор транскрипций: речевые паттерны судьи, уклончивые ответы оппонента, рекомендации по тактике.

**Обжалование** — подготовка апелляционных и кассационных жалоб, а также проекта судебного решения с учётом стиля конкретного судьи.

## Скиллы (14)

| Фаза | Скилл | Описание |
|------|-------|----------|
| Фундамент | `intake` | Приём и обработка материалов клиента |
| | `catalog` | Генерация xlsx-таблицы документов |
| | `update-index` | Верификация и синхронизация реестра |
| | `reocr` | Повторный OCR плохо распознанных документов через Haiku vision |
| | `timeline` | Построение юридической хронологии дела |
| Анализ | `legal-review` | Комплексный правовой анализ |
| | `build-position` | Формирование правовой позиции |
| Ведение дела | `add-evidence` | Приём дополнительных доказательств от клиента |
| | `add-opponent` | Приём и анализ документов оппонента |
| | `prepare-hearing` | Подготовка к заседанию |
| | `analyze-hearing` | Анализ транскрипции заседания |
| Обжалование | `draft-judgment` | Проект судебного решения |
| | `appeal` | Апелляционная жалоба |
| | `cassation` | Кассационная жалоба |

## Требования

- [Claude Code](https://claude.com/claude-code) (CLI, desktop или IDE-расширение)
- User-level skill `arbitrum-docx` для оформления `.docx`
- Локальные зависимости, которые ставит `scripts/setup.sh`: `tesseract-ocr`, `pillow`, Python-пакеты `python-docx`, `openpyxl`, `pymupdf`

## Установка

### 1. Добавьте маркетплейс и установите плагин

В Claude Code выполните по очереди:

```text
/plugin marketplace add strigov/strigov-cc-plugins
```

Claude Code скачает `.claude-plugin/marketplace.json` с GitHub и зарегистрирует маркетплейс под именем `strigov-cc-plugins`.

```text
/plugin install vassal-litigator-cc@strigov-cc-plugins
```

Проверить статус:

```text
/plugin
```

Во вкладке *Installed* должен появиться `vassal-litigator-cc`. После этого команды `/vassal-litigator-cc:init-case`, `/vassal-litigator-cc:intake` и остальные становятся доступны.

Обновление плагина:

```text
/plugin update vassal-litigator-cc@strigov-cc-plugins
```

### 2. Установите зависимости

Из папки установленного плагина:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Скрипт установит OCR-зависимости, Python-пакеты и утилиты для работы с архивами. При необходимости `setup.sh` можно вызывать повторно.

## Быстрый старт

1. Создайте папку будущего дела и положите туда сырые материалы клиента: pdf, docx, сканы, zip.
2. Откройте эту папку в Claude Code и выполните:
   ```text
   /vassal-litigator-cc:init-case
   ```
3. Плагин создаст скелет, перенесёт файлы во `Входящие документы/`, выполнит `intake` и спросит только недостающие поля карточки дела.
4. Дальше по ситуации:
   - `/vassal-litigator-cc:catalog` — xlsx-таблица документов
   - `/vassal-litigator-cc:legal-review` — правовой анализ
   - `/vassal-litigator-cc:build-position` — правовая позиция с оценкой рисков
   - `/vassal-litigator-cc:prepare-hearing` — подготовка к заседанию
   - `/vassal-litigator-cc:timeline` — хронология дела
   - `/vassal-litigator-cc:add-evidence` / `/vassal-litigator-cc:add-opponent` — добавление новых материалов
   - `/vassal-litigator-cc:analyze-hearing` — разбор транскрипции
   - `/vassal-litigator-cc:appeal` / `/vassal-litigator-cc:cassation` — жалобы

## Маршрутизация моделей

Claude работает в четырёх ролях:

- `Sonnet-main` — оркестрация, preview/apply, запись файлов дела.
- `Haiku-subagent` — файловая рутина и vision re-OCR.
- `Opus-subagent` — аналитика и юридическое письмо.
- `Sonnet-subagent` — оформление `.docx` через `arbitrum-docx`.

Подробный контракт — в [shared/subagent-dispatch.md](shared/subagent-dispatch.md).

| Скилл | Main | Subagent-цепочка |
|------|------|------------------|
| `intake` | Sonnet-main | Haiku-subagent |
| `add-evidence` | Sonnet-main | Haiku-subagent |
| `add-opponent` | Sonnet-main | Haiku-subagent |
| `update-index` | Sonnet-main | без обязательного субагента |
| `reocr` | Sonnet-main | Haiku-subagent |
| `catalog` | Sonnet-main | без обязательного субагента |
| `timeline` | Sonnet-main | Opus-subagent |
| `analyze-hearing` | Sonnet-main | Opus-subagent |
| `legal-review` | Sonnet-main | Opus-subagent → Sonnet-subagent |
| `build-position` | Sonnet-main | Opus-subagent → Sonnet-subagent |
| `prepare-hearing` | Sonnet-main | Opus-subagent → Sonnet-subagent |
| `draft-judgment` | Sonnet-main | Opus-subagent → Sonnet-subagent |
| `appeal` | Sonnet-main | Opus-subagent → Sonnet-subagent |
| `cassation` | Sonnet-main | Opus-subagent → Sonnet-subagent |

## Что нового в v0.6.0

### Breaking

- Удалена зависимость на openai-плагин CLI-компаньона и внешний companion runtime.
- Удалён sidecar-визуализатор; его заменили inline Mermaid-блоки в `legal-review`, `build-position` и `timeline`.
- Удалён отдельный skill-диспетчер внешнего companion runtime.
- Контрольное отдельное high-effort ревью аналитики больше не выполняется; если нужна глубина, пользователь задаёт thinking-override (`think hard`, `think harder`, `ultrathink`).

### Added

- Новый скилл `reocr` для повторного OCR через Haiku vision.
- Команда `/vassal-litigator-cc:reocr [--force] [doc-NNN ...]`.
- Поля `ocr_quality`, `ocr_quality_reason`, `ocr_reattempted` в `index.yaml`.
- `shared/subagent-dispatch.md` как единый справочник Task-контрактов.
- `scripts/render_pages.py` для конвертации PDF и изображений в PNG перед vision-OCR.

### Changed

- Все файловые скиллы (`intake`, `add-evidence`, `add-opponent`, `update-index`) работают через Sonnet-main; файловая рутина уходит в Haiku-subagent только там, где это оправдано.
- Все аналитические скиллы с `.docx` (`legal-review`, `build-position`, `prepare-hearing`, `draft-judgment`, `appeal`, `cassation`) используют цепочку Opus-subagent → Sonnet-subagent → `arbitrum-docx`.
- `timeline` и `analyze-hearing` перешли на markdown-only вывод через Opus-subagent.
- `catalog` теперь вызывает `scripts/generate_table.py` напрямую, без промежуточного исполнителя.

### Migration

- Дела `v0.5.x` работают без миграционного скрипта.
- Отсутствующее поле `ocr_quality` трактуется как `ok`.
- Чтобы проставить новые OCR-поля в старом деле, запустите `/vassal-litigator-cc:update-index`.

## Структура плагина

```text
vassal-litigator-cc/
├── .claude-plugin/
│   └── plugin.json
├── commands/
├── skills/
├── shared/
│   ├── case-schema.yaml
│   ├── index-schema.yaml
│   ├── mirror-template.md
│   ├── conventions.md
│   └── subagent-dispatch.md
├── scripts/
├── tests/
├── ARCHITECTURE.md
├── CHANGELOG.md
└── README.md
```

## Отличия от vassal-litigator (Cowork edition)

- Оркестрация полностью переведена на Claude-only subagent dispatch, без внешнего companion runtime.
- Sidecar-визуализации убраны; вместо них аналитические скиллы пишут inline Mermaid.
- Для плохо распознанных сканов добавлен `reocr` с Haiku vision.
- Бизнес-логика дела и файловые контракты сохранены, но модельная маршрутизация теперь описана в `shared/subagent-dispatch.md`.

## Лицензия

GPL-3.0. См. [LICENSE](LICENSE).

## Автор

Ian Strigov ([@strigov](https://github.com/strigov))
