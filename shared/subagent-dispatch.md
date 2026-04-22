# Subagent-dispatch vassal-litigator

Единый справочник контрактов субагентов для Claude-only оркестрации в `v0.6.0`. Main-Sonnet выбирает модель и ветку контракта по типу скилла, а затем детерминированно парсит OUTPUT субагента.

## Контракт 3.0 — общая форма

Промпт субагента состоит из 5 секций, строго в этом порядке:

```text
1. ROLE      — "Ты <роль> в скилле <skill-name>".
2. THINKING  — опционально: "think hard" | "think harder" | "ultrathink" (в начало TASK).
3. CONTEXT   — абсолютные пути; main НЕ вставляет текст файлов.
4. TASK      — что делать.
5. OUTPUT    — строгая схема (markdown с якорями, YAML, путь).
```

Правила:
- Субагент не меняет файлы дела в аналитических цепочках. Запись в `.vassal/*` делает main-Sonnet после приёма OUTPUT.
- Исключения: Sonnet-subagent пишет `.docx` через `arbitrum-docx`; Haiku-subagent может делать `rename`. Право на tool указывается в ROLE.
- Каждый Task-вызов: `subagent_type: "general-purpose"`, `model: <opus|sonnet|haiku>`, `description` 3-5 слов.

## Контракт 3.1 — Opus-subagent (аналитический)

Контракт 3.1 имеет три ветки по форме итогового артефакта. Main-Sonnet выбирает ветку по скиллу и парсит OUTPUT по детерминированной схеме.

| Ветка | Скиллы | `.docx` | Маркер `READY_FOR_DOCX` |
|---|---|---|---|
| 3.1a — single-document с `.docx` | `legal-review`, `build-position`, `draft-judgment`, `appeal`, `cassation` | да | обязателен, ровно один, последняя строка |
| 3.1b — multi-document с `.docx` | `prepare-hearing` | да (N `.docx` по числу ходатайств) | обязателен в каждом сегменте, ровно один на сегмент |
| 3.1c — markdown-only без `.docx` | `timeline`, `analyze-hearing` | нет | отсутствует |

### 3.1a — single-document с `.docx`

````text
ROLE: Ты юрист-аналитик в скилле <skill-name>.
THINKING: <think hard | think harder | ultrathink>   # из таблицы или override
CONTEXT:
  - case_root: /abs/path/дело
  - Читай для анализа:
      /abs/path/дело/.vassal/case.yaml
      /abs/path/дело/.vassal/index.yaml
      /abs/path/дело/.vassal/mirrors/doc-*.md (фильтр по role)
      /abs/path/дело/.vassal/analysis/<предыдущие-артефакты>.md
TASK:
  <skill-specific: фабула / квалификация / риски / стратегия ...>
  Для legal-review и build-position: включи блок ```mermaid со схемой сторон.
OUTPUT:
  Единый markdown. Набор допустимых верхнеуровневых (`## `) секций — свой
  для каждого скилла; конкретный список фиксируется в шагах Ф5.
  Инварианты, общие для всех скиллов ветки 3.1a:
    1. Заголовки секций — только уровень `## ` (не `### `, не `#`).
       Main-Sonnet режет парсингом по `^## `.
    2. Первый `## ` заголовок рассматривается main-Sonnet как заголовок документа.
       Этот первый заголовок может быть любым осмысленным из списка скилла.
    3. ПОСЛЕДНЯЯ строка файла: `READY_FOR_DOCX: <processual|analytical|letter>`.
       Ровно один такой маркер на весь OUTPUT.
  Порядок секций и полнота определяются per-skill в Ф5.
````

Парсинг в main-Sonnet:
- `title` = текст первого `## ` заголовка в OUTPUT (без префикса `## `); fallback при отсутствии `## ` вообще: `<skill-name> YYYY-MM-DD`.
- `doc_type` = значение после `READY_FOR_DOCX:` (последняя строка).
- `body` = весь markdown без финальной строки `READY_FOR_DOCX: ...`.
- `out_path` = ровно один, из таблицы скиллов Ф5.

### 3.1b — multi-document (`prepare-hearing`)

````text
ROLE: Ты юрист-аналитик в скилле prepare-hearing.
THINKING: <think harder | ultrathink>
CONTEXT: (как в 3.1a)
TASK:
  Подготовка к заседанию: red/blue-team анализ + список ходатайств на заседание.
  Каждое ходатайство — отдельный процессуальный документ.
OUTPUT:
  Единый markdown, строго из двух блоков:

  ## Заметки
  <red/blue team, тактические заметки — произвольный markdown>

  ## Ходатайство 1: <тема>
  <тело ходатайства в markdown>
  READY_FOR_DOCX: processual

  ## Ходатайство 2: <тема>
  <тело>
  READY_FOR_DOCX: processual

  ... (N ходатайств)
````

Парсинг в main-Sonnet:
- Разрезать по регулярке `^## Ходатайство (\d+): (.+)$` (многострочно).
- Всё до первого матча → `notes_body` (пишется как `notes.md`, не через `arbitrum-docx`).
- Каждый сегмент между матчами:
  - `title` = захваченная группа 2 (тема)
  - `index` = захваченная группа 1
  - `body` = текст сегмента без финальной строки `READY_FOR_DOCX: ...`
  - `doc_type` = `processual` (ассерт: строго `processual`)
  - `out_path` = `<case_root>/hearings/YYYY-MM-DD/ходатайство-<index>-<slug(title)>.docx`
- Для каждого сегмента main-Sonnet диспатчит отдельный Sonnet-subagent по контракту 3.2; итог — массив путей к `.docx` + путь к `notes.md`.
- Ассерт перед диспатчем: `N ≥ 1`; каждый сегмент оканчивается ровно одной строкой `READY_FOR_DOCX: processual`. Если ассерт падает — main возвращает `PARSE_FAILED` и не запускает Sonnet-subagent.

### 3.1c — markdown-only без `.docx`

````text
ROLE: Ты юрист-аналитик в скилле <skill-name>.
THINKING: think hard   # из таблицы или override
CONTEXT:
  - case_root: /abs/path/дело
  - Читай для анализа:
      /abs/path/дело/.vassal/case.yaml
      /abs/path/дело/.vassal/index.yaml
      /abs/path/дело/.vassal/mirrors/doc-*.md
      /abs/path/дело/hearings/YYYY-MM-DD/**   (только для analyze-hearing)
TASK:
  Для timeline: хронология событий по делу; в OUTPUT обязателен блок
    ```mermaid со связкой `gantt`.
  Для analyze-hearing: речевые паттерны участников, тактики оппонента, судьи.
OUTPUT:
  Свободно структурированный markdown — без жёсткого набора якорей,
  без финальной строки `READY_FOR_DOCX`.
  Рекомендуемая структура:
    - timeline: `## События` + `## Gantt` (блок ```mermaid ... gantt ...```).
    - analyze-hearing: `## Ход заседания`, `## Речевые паттерны`,
      `## Тактика оппонента`, `## Реакции суда`, `## Выводы`.
  Маркер `READY_FOR_DOCX` отсутствует: `.docx` не создаётся,
  Sonnet-subagent по контракту 3.2 не диспатчится.
````

Парсинг в main-Sonnet:
- Main принимает markdown как есть и записывает в заранее известный путь:
  - `timeline` → `<case_root>/YYYY-MM-DD Хронология дела.md`
  - `analyze-hearing` → `<case_root>/hearings/YYYY-MM-DD/analysis.md`
- Никакого регэкспа `READY_FOR_DOCX` и сегментации на ходатайства.
- Ассерт для `timeline`: в тексте присутствует блок ```mermaid и ключевое слово `gantt`.

## Контракт 3.2 — Sonnet-subagent (→ arbitrum-docx)

```text
ROLE: Ты форматировщик документов в скилле <skill-name>.
Имеешь право вызывать Skill tool (arbitrum-docx).
THINKING: (нет)
CONTEXT:
  - markdown_input: <полный текст от Opus-subagent'а>
  - case_meta:
      court, case_number, judge, our_party, our_client, other_parties (из .vassal/case.yaml)
  - out_dir: /abs/path/дело/<skill-specific>/
  - doc_name: <skill-specific>.docx
TASK:
  1. Вызови Skill({
       skill: "arbitrum-docx",
       args: {
         doc_type: <из READY_FOR_DOCX>,
         header: <из case_meta>,
         title: <из первого ## в markdown>,
         body: <markdown_input>
       }
     })
  2. Если Skill tool недоступен — верни SKILL_UNAVAILABLE + markdown_input.
OUTPUT:
  ЕДИНСТВЕННАЯ строка: абсолютный путь к созданному .docx
  ИЛИ: SKILL_UNAVAILABLE
       <markdown_input без изменений>
```

Main-Sonnet обрабатывает обе ветки: при `SKILL_UNAVAILABLE` сам вызывает `Skill({skill: "arbitrum-docx", ...})`. Эмпирическая ветка выбирается по результату Ф0.

## Контракт 3.3 — Haiku-subagent

### Вариант A — механическая рутина

```text
ROLE: Ты обработчик файлов в скилле intake.
CONTEXT:
  - case_root: /abs/path/дело
  - raw_dir: /abs/path/дело/.vassal/raw/intake-<timestamp>/
  - Список файлов (inline до 20 штук): file → первые 500 символов OCR.
TASK:
  Для каждого файла верни new_name ("YYYY-MM-DD_тип_описание.ext"
  или "undated_..." при отсутствии даты) и doc_type из {договор,
  определение, судебный акт, платёжка, переписка, прочее}.
OUTPUT:
  YAML-массив без сопровождающего текста:
  - file: ...
    new_name: ...
    doc_type: ...
```

### Вариант B — vision-OCR (`reocr`)

```text
ROLE: Ты OCR через vision в скилле reocr.
CONTEXT:
  - source_pdf: /abs/path/дело/.vassal/raw/.../doc-NNN.pdf
  - pages_rendered_as_images:
      /tmp/vassal-reocr-XXXX/page-001.png
      ...
  (PNG читаются субагентом через Read tool мультимодально)
TASK:
  Прочитай каждый PNG, извлеки текст максимально точно,
  сохрани таблицы markdown-таблицами, рукописное — [рукописно: ...],
  неразборчивое — [неразборчиво].
OUTPUT:
  ## Страница 1
  <текст>
  ## Страница 2
  ...
  В конце YAML-блок:
  ---
  pages_total: N
  confidence_by_page: [0.95, 0.92, ...]
  notable_issues: [...]
  ---
```

## Thinking-override

Main-Sonnet сканирует `user-message` и форвардит override в THINKING-секцию промпта Opus-субагента:

```text
если в user-message есть "ultrathink"                 → "ultrathink"
иначе если "think harder" / "megathink"               → "think harder"
иначе если "think hard" / "think deeply"              → "think hard"
иначе                                                 → default из таблицы по скиллам
```

Дефолты по скиллам:
- `timeline`, `legal-review`, `analyze-hearing`, `draft-judgment`, `appeal`, `cassation` → `think hard`
- `build-position`, `prepare-hearing` → `think harder`
- файловые скиллы и `catalog` → без thinking

**Эмпирическая проверка Ф0 (2026-04-22):** Task(model=opus/sonnet/haiku) — доступен. Skill в Haiku-subagent — доступен. Дефолтная ветка контракта 3.2: прямая (Skill вызывается из субагента напрямую, без fallback через main).
