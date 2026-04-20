# Prompts — карта Ф1

В этой директории лежат **каркасы** промптов Codex для vassal-litigator. Ф1 создаёт только инфраструктуру и единый контракт; профильная логика будет дозаполняться в Ф2-Ф6.

## Общая схема

Каждый ролевой шаблон начинается с:

```md
{{include _preamble.md}}
```

<!-- prompt-assembly step expands this include; see skills/codex-invocation/SKILL.md §Как Claude-main собирает prompt -->

Оркестратор обязан **до диспатча**:

1. получить абсолютные `[CASE_ROOT]` и `[PLUGIN_ROOT]`
2. expand `{{include _preamble.md}}` буквальной подстановкой содержимого `prompts/_preamble.md`
3. подставить пути и остальные placeholders конкретной команды
4. проверить, что в собранном prompt не осталось `{{include ...}}` и других `{{...}}`
5. передать в Codex уже готовый текст

## Общие placeholders

- `{{task_name}}` — имя конкретной задачи
- `{{role_id}}` — `file-executor` | `timeline-builder` | `imagegen-visualizer` | `analytical-reviewer`
- `{{case_root}}` — абсолютный путь к делу
- `{{plugin_root}}` — абсолютный путь к установленному плагину
- `{{report_contract}}` — при необходимости локальное уточнение формата отчёта
- `{{extra_constraints}}` — дополнительные ограничения конкретного вызова

## Карта файлов

- `file-executor-intake.md` — apply-шаблон для intake; ключевые placeholders: `{{plan_body}}`, `{{batch_name}}`
- `file-executor-update-index.md` — apply-шаблон для update-index; ключевые placeholders: `{{plan_body}}`, `{{scan_scope}}`
- `file-executor-catalog.md` — apply-шаблон для catalog; ключевые placeholders: `{{plan_body}}`, `{{output_table_path}}`
- `file-executor-add-evidence.md` — apply-шаблон для add-evidence; ключевые placeholders: `{{plan_body}}`, `{{target_folder}}`
- `file-executor-add-opponent.md` — apply-шаблон для add-opponent; ключевые placeholders: `{{plan_body}}`, `{{target_folder}}`
- `timeline-builder.md` — high-effort шаблон хронологии; ключевые placeholders: `{{timeline_goal}}`, `{{existing_timeline_policy}}`
- `imagegen-visualizer.md` — каркас sidecar-визуализатора; ключевые placeholders: `{{visual_type}}`, `{{visual_context}}`
- `analytical-reviewer.md` — xhigh review-каркас; ключевые placeholders: `{{output_path}}`, `{{original_input}}`

## Инварианты Ф1

- шаблоны не должны содержать относительных `scripts/...` и `shared/...`
- шаблоны не должны зашивать логику Ф2-Ф6 глубже, чем нужно для каркаса
- для визуализатора путь к итоговому PNG не описывается как `GENERATED_IMAGE:`-контракт; фактический резолв делается оркестратором через `sessionId`
