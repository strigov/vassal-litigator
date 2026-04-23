# Smoke-тесты vassal-litigator

Smoke-тесты — это руководства для ручной проверки скиллов. Скрипты подготавливают тестовое окружение и печатают пошаговые инструкции для Claude Code.

## Предварительные требования

- Установлен плагин `vassal-litigator-cc` в Claude Code
- Доступны модели и инструменты, которые требуют соответствующие скиллы
- Python `>= 3.9`
- Для ручных проверок `catalog` полезны пакеты `yaml` и `openpyxl`
- Smoke-скрипты запускаются только из директории внутри `/tmp/`

## Контракт файловых скиллов

`intake`, `add-evidence`, `add-opponent` работают по схеме `plan → review → (revise)? → apply → verify`:

- **plan** — строится markdown-план в `.vassal/plans/<skill>-<timestamp>.md`
- **review** — Сюзерен проверяет план
- **revise** — при правках Claude пересобирает план
- **apply** — Claude применяет утверждённый план, раскладывает файлы, обновляет индекс и чистит рабочие каталоги
- **verify** — Claude проверяет инварианты и итоговые артефакты

Smoke-тест `intake` покрывает:

- удаление `.vassal/plans/intake-*.md` после apply
- удаление рабочей области `.vassal/work/intake-*/`
- хронологическую раскладку `Материалы от клиента/`
- распаковку архивов
- конверсию изображений в PDF
- полнотекстовую сверку md-зеркала на большой фикстуре через повторное извлечение текста
- фиксацию результата прогона в `.vassal/history.md`

Smoke-тесты `add-evidence`, `add-opponent`, `update-index` дополнительно проверяют:

- полнотекстовую сверку новых и пересобранных зеркал через `scripts/extract_text.py`
- очистку рабочих `plans/` и `work/` каталогов после apply

Smoke-тест `reocr` дополнительно проверяет:

- переход проблемного документа из `ocr_quality: low` в `ocr_quality: ok`
- смену `extraction_method` на `haiku-vision`
- установку `ocr_reattempted: true`

## Структура

```text
tests/
├── fixtures/
│   └── dummy-case/
│       ├── Входящие документы/
│       ├── _sources/
│       ├── case-initial.yaml
│       └── expected/
└── smoke/
    ├── _fulltext_common.sh
    ├── test-add-evidence.sh
    ├── test-add-opponent.sh
    ├── test-update-index.sh
    ├── test-reocr.sh
    ├── test-intake.sh
    ├── test-catalog.sh
    ├── test-timeline.sh
    ├── test-analytical-review.sh
    ├── test-prepare-hearing.sh
    └── test-draft-judgment.sh
```

Новые подпапки в скелете дела, которые создаёт `init-case`:

- `.vassal/plans/` — рабочие markdown-планы
- `.vassal/work/<skill>-<timestamp>/` — рабочие артефакты apply

Legacy-заметка: директория `.vassal/codex-logs/` может остаться в старых делах v0.5.x, но v0.6.0 её не создаёт; текущие прогоны фиксируются через `.vassal/history.md`.

## Запуск

```bash
cd /tmp

PLUGIN_ROOT=/path/to/vassal-litigator-cc

for t in "$PLUGIN_ROOT"/tests/smoke/*.sh; do
  bash "$t" "$PLUGIN_ROOT"
done
```

Каждый скрипт печатает блоки `ШАГИ`, `ОЖИДАЕМЫЙ РЕЗУЛЬТАТ`, `ПРОВЕРКА`, `ОЧИСТКА`. Выполняй шаги вручную в Claude Code, запущенном в указанной smoke-директории.

## Тестовое дело

Дело: `А41-1234/2025`  
Стороны: `ООО "Ромашка"` (истец) vs `ООО "Лютик"` (ответчик)  
Суд: `Арбитражный суд Московской области`  
Суть: `Взыскание задолженности по договору поставки №47 от 2025-06-01`

## Безопасность

Скрипты работают только с временными каталогами вида `/tmp/smoke-vassal-*/` и откажутся запускаться, если текущая рабочая директория не находится внутри `/tmp/`.
