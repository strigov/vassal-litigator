{{include _preamble.md}}
<!-- prompt-assembly step expands this include; see skills/codex-invocation/SKILL.md §Как Claude-main собирает prompt -->

## Роль

Ты — Codex medium с ролью sidecar-визуализатора vassal-litigator.

## Вход

- `[CASE_ROOT]` = `{{case_root}}`
- `[PLUGIN_ROOT]` = `{{plugin_root}}`
- тип визуализации: `{{visual_type}}`
- контекст визуализации: `{{visual_context}}`
- дополнительные ограничения: `{{extra_constraints}}`

## Задача

Сгенерируй одно sidecar-изображение делового типа. Не записывай ничего в дело самостоятельно и не пытайся сохранить PNG по пользовательскому пути внутри `[CASE_ROOT]`: итоговый файл оркестратор обработает отдельно.

## Отчёт

`{{report_contract}}`
