---
description: Каталогизация документов дела — таблица и обновление описаний
---

# catalog — Каталогизация документов

Когда пользователь запускает эту команду:

1. Убедись что `.vassal/index.yaml` существует. Если нет — предложи `/vassal-litigator-cc:init-case` и остановись.
2. Прочитай `skills/catalog/SKILL.md`. Следуй Фазе 1 (Preview, read-only): определи документы без `summary`, покажи план.
3. Покажи preview Сюзерену. Жди подтверждения.
4. После подтверждения: следуй Фазе 3 из `skills/catalog/SKILL.md` (Apply, Claude-main): валидируй зеркала и PLUGIN_ROOT, обнови `summary` в `.vassal/index.yaml`, запусти `generate_table.py`, запиши строку в `.vassal/history.md`.
5. Следуй Фазе 4 из `skills/catalog/SKILL.md` (Верификация): убедись, что `Таблица документов.xlsx` или `.csv` создана; покажи Сюзерену резюме.
