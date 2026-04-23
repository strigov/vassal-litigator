## [0.6.0] — 2026-04-23

### Breaking

- Удалена зависимость на openai-codex / Codex CLI / `$CODEX_COMPANION`.
- Удалён скилл `visualize` — заменён inline Mermaid-блоками в `legal-review` / `build-position` / `timeline`.
- Удалён скилл `codex-invocation`.
- Контрольное xhigh-ревью аналитики больше не проводится (компенсация: `ultrathink` ключевое слово от пользователя).

### Added

- Новый скилл `reocr` — перепрогон OCR через Haiku vision.
- Команда `/vassal-litigator-cc:reocr [--force] [doc-NNN ...]`.
- Поле `ocr_quality` / `ocr_quality_reason` / `ocr_reattempted` в записях `index.yaml`.
- `shared/subagent-dispatch.md` — единый справочник Task-контрактов.
- `scripts/render_pages.py` — PDF/image → PNG для vision-OCR.

### Changed

- Все файловые скиллы (`intake` / `add-evidence` / `add-opponent` / `update-index`) — Sonnet-main + Haiku-subagent.
- Все аналитические скиллы с `.docx` (`legal-review` / `build-position` / `prepare-hearing` / `draft-judgment` / `appeal` / `cassation`) — Opus-subagent + Sonnet-subagent → `arbitrum-docx`.
- `timeline` / `analyze-hearing` — Opus-subagent.
- `catalog` — Sonnet-main + прямой вызов `scripts/generate_table.py`.

### Migration

- Существующие дела `v0.5.x` работают без миграционного скрипта. Поле `ocr_quality` отсутствует → трактуется как `ok`. Для простановки — прогнать `/vassal-litigator-cc:update-index`.
