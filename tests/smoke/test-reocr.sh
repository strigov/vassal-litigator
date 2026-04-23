#!/usr/bin/env bash

set -euo pipefail

print_usage() {
    cat <<'EOF'
USAGE: bash tests/smoke/test-reocr.sh /path/to/vassal-litigator-cc

Запускать из директории внутри /tmp/.
Скрипт готовит smoke-окружение для reocr: плохой скан сначала должен получить
`ocr_quality: low` после intake, затем после `/vassal-litigator-cc:reocr` перейти
в `haiku-vision` с `ocr_reattempted: true`.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    print_usage
    exit 0
fi

PLUGIN_ROOT="${1:-}"
if [[ -z "$PLUGIN_ROOT" ]]; then
    print_usage
    exit 1
fi

case "$PWD" in
    /tmp|/tmp/*|/private/tmp|/private/tmp/*) ;;
    *)
        echo "WARNING: smoke-скрипт можно запускать только из /tmp/. Текущий CWD: $PWD"
        exit 1
        ;;
esac

if [[ ! -d "$PLUGIN_ROOT" ]]; then
    echo "ERROR: PLUGIN_ROOT не существует: $PLUGIN_ROOT"
    exit 1
fi

if [[ ! -f "$PLUGIN_ROOT/tests/fixtures/dummy-case/_sources/плохой-скан.jpg" ]]; then
    echo "ERROR: не найдена фикстура плохого скана"
    exit 1
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "SKIP: ANTHROPIC_API_KEY не задан, smoke reocr пропущен"
    exit 0
fi

source "$PLUGIN_ROOT/tests/smoke/_fulltext_common.sh"

SMOKE_CASE="/tmp/smoke-vassal-reocr-$(date +%s)"
export SMOKE_CASE
export PLUGIN_ROOT

mkdir -p "$SMOKE_CASE"
cp -R "$PLUGIN_ROOT/tests/fixtures/dummy-case/Входящие документы" "$SMOKE_CASE/"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/case-initial.yaml" "$SMOKE_CASE/.vassal-case-initial.yaml"
cp "$PLUGIN_ROOT/tests/fixtures/dummy-case/_sources/плохой-скан.jpg" "$SMOKE_CASE/Входящие документы/плохой-скан.jpg"
write_fulltext_helper "$SMOKE_CASE" "$PLUGIN_ROOT"

cat <<EOF
=== SMOKE: reocr ===

РАБОЧАЯ ДИРЕКТОРИЯ:
$SMOKE_CASE

ШАГИ:
1. Перейди в smoke-директорию:
   cd "$SMOKE_CASE"
2. Запусти Claude Code в этой папке.
3. Выполни /vassal-litigator:init-case и дождись завершения базового intake.
4. Найди doc-ID плохого скана и проверь, что после intake он имеет `ocr_quality: low`:
   export SMOKE_CASE="$SMOKE_CASE"; export PLUGIN_ROOT="$PLUGIN_ROOT"
   source "\$SMOKE_CASE/.smoke-fulltext.sh"
   export BAD_SCAN_ID=\$(python3 - <<'PY'
import os
import pathlib
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
for entry in data.get("documents", []):
    origin = entry.get("origin", {}) or {}
    if origin.get("name") == "плохой-скан.jpg":
        print(entry["id"])
        break
PY
)
   test -n "\$BAD_SCAN_ID"
   python3 - <<'PYEOF'
import os
import pathlib
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
bad_id = os.environ["BAD_SCAN_ID"]
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
doc = next((entry for entry in data.get("documents", []) if entry.get("id") == bad_id), None)
if doc is None:
    print(f"FAIL: missing {bad_id}")
    sys.exit(1)
if doc.get("ocr_quality") != "low":
    print(f"FAIL: expected ocr_quality=low in {bad_id}, got {doc.get('ocr_quality')!r}")
    sys.exit(1)
print(f"intake low-quality assertion: OK ({bad_id})")
PYEOF
5. Сохрани состояние зеркала до reocr:
   export BAD_SCAN_MIRROR=\$(mirror_of_id "\$BAD_SCAN_ID")
   cp "$SMOKE_CASE/\$BAD_SCAN_MIRROR" "$SMOKE_CASE/.before-reocr.md"
   export BEFORE_MTIME=\$(python3 - <<'PY'
import os
import pathlib

case = pathlib.Path(os.environ["SMOKE_CASE"])
mirror_rel = os.environ["BAD_SCAN_MIRROR"]
print(int((case / mirror_rel).stat().st_mtime))
PY
)
   export BEFORE_SIZE=\$(python3 - <<'PY'
import os
import pathlib

case = pathlib.Path(os.environ["SMOKE_CASE"])
mirror_rel = os.environ["BAD_SCAN_MIRROR"]
print((case / mirror_rel).stat().st_size)
PY
)
   export VISION_RAW="$SMOKE_CASE/.smoke-vision-raw.md"
6. Выполни: /vassal-litigator-cc:reocr \$BAD_SCAN_ID
7. В CI/ручной отладке сохрани сырой markdown OUTPUT Haiku-subagent до перезаписи зеркала в:
   \$VISION_RAW
8. Проверь результат reocr:
   python3 - <<'PYEOF'
import os
import pathlib
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
bad_id = os.environ["BAD_SCAN_ID"]
data = yaml.safe_load((case / ".vassal/index.yaml").read_text(encoding="utf-8"))
doc = next((entry for entry in data.get("documents", []) if entry.get("id") == bad_id), None)
errors = []

if doc is None:
    errors.append(f"missing {bad_id}")
else:
    if doc.get("ocr_quality") != "ok":
        errors.append(f"ocr_quality should be 'ok' in {bad_id}, got {doc.get('ocr_quality')!r}")
    if doc.get("ocr_quality_reason") != "":
        errors.append(f"ocr_quality_reason should be empty string in {bad_id}, got {doc.get('ocr_quality_reason')!r}")
    if doc.get("ocr_reattempted") is not True:
        errors.append(f"ocr_reattempted should be True in {bad_id}, got {doc.get('ocr_reattempted')!r}")
    if doc.get("extraction_method") != "haiku-vision":
        errors.append(f"extraction_method should be 'haiku-vision' in {bad_id}, got {doc.get('extraction_method')!r}")

if errors:
    print("FAIL:")
    print("\\n".join(errors))
    sys.exit(1)

print(f"reocr index assertions: OK ({bad_id})")
PYEOF
   python3 - <<'PYEOF'
import os
import pathlib
import sys
import yaml

case = pathlib.Path(os.environ["SMOKE_CASE"])
mirror_rel = os.environ["BAD_SCAN_MIRROR"]
mirror_path = case / mirror_rel
before_path = case / ".before-reocr.md"
before_mtime = int(os.environ["BEFORE_MTIME"])
before_size = int(os.environ["BEFORE_SIZE"])
after_mtime = int(mirror_path.stat().st_mtime)
after_size = mirror_path.stat().st_size
errors = []

overwrite_only_fields = {
    "pages",
    "extraction_method",
    "extraction_model",
    "extraction_date",
    "confidence",
    "ocr_reattempted",
}


def load_frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"missing opening frontmatter delimiter in {path}")

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        raise ValueError(f"missing closing frontmatter delimiter in {path}")

    data = yaml.safe_load("\n".join(lines[1:closing_index])) or {}
    if not isinstance(data, dict):
        raise ValueError(f"frontmatter is not a mapping in {path}")
    return data


if after_mtime <= before_mtime:
    errors.append(f"mtime did not increase: before={before_mtime} after={after_mtime}")
if after_size == before_size:
    errors.append(f"size did not change: before={before_size} after={after_size}")

try:
    before_frontmatter = load_frontmatter(before_path)
    after_frontmatter = load_frontmatter(mirror_path)
except Exception as exc:
    errors.append(f"frontmatter parse failed: {exc}")
else:
    preserved_fields = sorted(set(before_frontmatter) - overwrite_only_fields)
    for field in preserved_fields:
        if after_frontmatter.get(field) != before_frontmatter.get(field):
            errors.append(
                f"frontmatter field {field!r} changed unexpectedly: "
                f"before={before_frontmatter.get(field)!r} after={after_frontmatter.get(field)!r}"
            )

    extraction_method = after_frontmatter.get("extraction_method")
    if extraction_method != "haiku-vision":
        errors.append(
            f"frontmatter extraction_method should be 'haiku-vision', got {extraction_method!r}"
        )

    extraction_model = after_frontmatter.get("extraction_model")
    if not isinstance(extraction_model, str) or not extraction_model.lower().startswith("haiku"):
        errors.append(
            f"frontmatter extraction_model should start with 'haiku', got {extraction_model!r}"
        )

    ocr_reattempted = after_frontmatter.get("ocr_reattempted")
    if ocr_reattempted is not True:
        errors.append(
            f"frontmatter ocr_reattempted should be True, got {ocr_reattempted!r}"
        )

    from datetime import date as _date, datetime as _datetime
    extraction_date = after_frontmatter.get("extraction_date")
    if not isinstance(extraction_date, (str, _date, _datetime)) or not extraction_date:
        errors.append(
            f"frontmatter extraction_date should be a non-empty date value, got {extraction_date!r}"
        )

    confidence = after_frontmatter.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        errors.append(
            f"frontmatter confidence should be numeric, got {confidence!r}"
        )

if errors:
    print("FAIL:")
    print("\\n".join(errors))
    sys.exit(1)

print(f"mirror rewrite assertions: OK ({mirror_rel})")
PYEOF
   grep -n "reocr" "$SMOKE_CASE/.vassal/history.md"
   test -s "\$VISION_RAW"
   assert_mirror_vision_full "$SMOKE_CASE/\$BAD_SCAN_MIRROR" "\$VISION_RAW"

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
- после intake запись `плохой-скан.jpg` имеет `ocr_quality: low`
- после `/reocr` та же запись имеет `ocr_quality: ok`, `ocr_quality_reason: ""`, `ocr_reattempted: true`, `extraction_method: haiku-vision`
- зеркало `doc-NNN.md` переписано: изменились и размер, и mtime, overwrite-only поля обновлены ожидаемыми значениями, а все остальные frontmatter-поля сохранены
- `.vassal/history.md` содержит запись `reocr`
- полнотекстовость проверяется через `assert_mirror_vision_full`, а не через `assert_mirror_full`

ОЧИСТКА:
rm -rf "$SMOKE_CASE"
EOF
