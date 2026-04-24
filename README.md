> **ВАЖНО: Конфиденциальность.** Плагин отправляет материалы дела (тексты документов, зеркала, метаданные) в Anthropic через Claude для файлового пайплайна, аналитики и подготовки документов. Устанавливая плагин, вы подтверждаете согласие на такую передачу. Если это недопустимо для вашей юрисдикции или клиентского договора — не устанавливайте плагин.

# vassal-litigator

Плагин для **Claude Cowork** ([claude.ai/code](https://claude.ai/code)), помогающий юристу вести судебные дела от первичного приёма материалов клиента до кассационной жалобы.

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

- [Claude Cowork](https://claude.ai/code) — браузерная версия Claude Code
- User-level skill `arbitrum-docx` для оформления `.docx`

## Установка

### 1. Скачайте архив плагина

Откройте [Releases](../../releases) и скачайте архив последней версии `vassal-litigator`.

Нужен именно архив релиза, а не отдельные файлы из репозитория: Cowork устанавливает плагин как цельный пакет с `.claude-plugin/plugin.json`, командами, скиллами, shared-файлами и скриптами.

### 2. Добавьте плагин в Claude Cowork

Откройте [claude.ai/code](https://claude.ai/code), перейдите в интерфейс управления плагинами и добавьте скачанный архив.

После установки в списке плагинов должен появиться `vassal-litigator`. Команды `/vassal-litigator:init-case`, `/vassal-litigator:intake` и остальные станут доступны в Cowork.

### Обновление

Скачайте новый архив из [Releases](../../releases) и замените установленный плагин через тот же интерфейс Cowork.

## Быстрый старт

1. Создайте папку будущего дела и положите туда сырые материалы клиента: pdf, docx, сканы, zip.
2. Откройте эту папку в Claude Cowork и выполните:
   ```text
   /vassal-litigator:init-case
   ```
3. Плагин создаст скелет, перенесёт файлы во `Входящие документы/`, выполнит `intake` и спросит только недостающие поля карточки дела.
4. Дальше по ситуации:
   - `/vassal-litigator:catalog` — xlsx-таблица документов
   - `/vassal-litigator:legal-review` — правовой анализ
   - `/vassal-litigator:build-position` — правовая позиция с оценкой рисков
   - `/vassal-litigator:prepare-hearing` — подготовка к заседанию
   - `/vassal-litigator:timeline` — хронология дела
   - `/vassal-litigator:add-evidence` / `/vassal-litigator:add-opponent` — добавление новых материалов
   - `/vassal-litigator:analyze-hearing` — разбор транскрипции
   - `/vassal-litigator:appeal` / `/vassal-litigator:cassation` — жалобы

## Маршрутизация моделей

| Скилл | Main | Subagent-цепочка |
|-------|------|------------------|
| `intake`, `add-evidence`, `add-opponent`, `update-index`, `reocr` | Sonnet-main | Haiku-subagent |
| `catalog` | Sonnet-main | — |
| `timeline`, `analyze-hearing` | Sonnet-main | Opus-subagent |
| `legal-review`, `build-position`, `prepare-hearing`, `draft-judgment`, `appeal`, `cassation` | Sonnet-main | Opus-subagent → Sonnet-subagent |

Подробный контракт — в [shared/subagent-dispatch.md](shared/subagent-dispatch.md).

## Структура плагина

```text
vassal-litigator/
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

## Лицензия

GPL-3.0. См. [LICENSE](LICENSE).

## Автор

Ian Strigov ([@strigov](https://github.com/strigov))
