# Smoke-тесты vassal-litigator

Smoke-тесты — это руководства для ручной проверки скиллов. Они не запускают Claude/Codex автоматически: скрипты подготавливают тестовое окружение и выводят пошаговые инструкции.

## Предварительные требования

- Установлен плагин `vassal-litigator`
- Установлен `openai-codex` и выполнен `codex login`
- Python `>= 3.9`
- Для ручных проверок `catalog` полезны пакеты `yaml` и `openpyxl`
- Smoke-скрипты запускаются только из директории внутри `/tmp/`

## Структура

```text
tests/
├── fixtures/
│   └── dummy-case/
│       ├── Входящие документы/
│       │   ├── договор.pdf
│       │   ├── претензия.pdf
│       │   ├── скан.jpg
│       │   └── архив.zip
│       ├── case-initial.yaml
│       └── expected/
│           ├── index-after-intake.yaml
│           └── history-entry.md
└── smoke/
    ├── test-intake.sh
    ├── test-catalog.sh
    ├── test-timeline.sh
    └── test-analytical-review.sh
```

## Запуск

```bash
cd /tmp

PLUGIN_ROOT=/path/to/vassal-litigator

bash "$PLUGIN_ROOT/tests/smoke/test-intake.sh" "$PLUGIN_ROOT"
bash "$PLUGIN_ROOT/tests/smoke/test-catalog.sh" "$PLUGIN_ROOT"
bash "$PLUGIN_ROOT/tests/smoke/test-timeline.sh" "$PLUGIN_ROOT"
bash "$PLUGIN_ROOT/tests/smoke/test-analytical-review.sh" "$PLUGIN_ROOT"
```

Каждый скрипт печатает блоки `ШАГИ`, `ОЖИДАЕМЫЙ РЕЗУЛЬТАТ`, `ПРОВЕРКА`, `ОЧИСТКА`. Выполняй шаги вручную в Claude Cowork.

## Тестовое дело

Дело: `А41-1234/2025`  
Стороны: `ООО "Ромашка"` (истец) vs `ООО "Лютик"` (ответчик)  
Суд: `Арбитражный суд Московской области`  
Суть: `Взыскание задолженности по договору поставки №47 от 2025-06-01`

Документы в fixture:

- `договор.pdf` — stub-PDF договора поставки
- `претензия.pdf` — stub-PDF претензии
- `скан.jpg` — stub-JPEG для OCR-проверки
- `архив.zip` — архив с `акт.pdf` и `платёжка.pdf`

## Безопасность

Скрипты работают только с временными каталогами вида `/tmp/smoke-vassal-*/` и откажутся запускаться, если текущая рабочая директория не находится внутри `/tmp/`.
