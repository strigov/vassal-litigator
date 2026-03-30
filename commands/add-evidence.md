---
description: Прием дополнительных доказательств от клиента
---

# add-evidence -- Прием дополнительных доказательств

Когда пользователь запускает эту команду с "$ARGUMENTS":

1. Прочитай скилл `skills/add-evidence/SKILL.md` и следуй его инструкциям.
2. Если `$ARGUMENTS` содержит пояснения -- учти их при категоризации.
3. Убедись, что `.vassal/case.yaml` и `.vassal/index.yaml` существуют. Если нет -- предложи сначала `/vassal-litigator:init-case` и `/vassal-litigator:intake`.
4. Запусти `scripts/setup.sh` для установки OCR-зависимостей (если не запущен в этой сессии).
5. Выполни pipeline из SKILL.md: сохранение -> извлечение -> preview -> apply -> очистка.
