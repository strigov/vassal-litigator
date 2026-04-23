#!/usr/bin/env bash

set -euo pipefail

generate_large_fixture_pdf() {
    local source_txt="$1"
    local output_pdf="$2"

    python3 - "$source_txt" "$output_pdf" <<'PY'
from pathlib import Path
import sys
import textwrap


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text: str, out: Path) -> None:
    wrapped = []
    for block in text.splitlines():
        if not block.strip():
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                block,
                width=92,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )

    lines_per_page = 42
    pages = [wrapped[i:i + lines_per_page] for i in range(0, len(wrapped), lines_per_page)] or [[""]]

    objects = []

    def add_obj(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = add_obj(b"")
    page_ids = []

    for page_lines in pages:
        stream_lines = [b"BT", b"/F1 10 Tf", b"50 790 Td", b"14 TL"]
        first_line = True
        for line in page_lines:
            escaped = pdf_escape(line).encode("latin-1", "ignore")
            if first_line:
                stream_lines.append(b"(" + escaped + b") Tj")
                first_line = False
            else:
                stream_lines.append(b"T*")
                stream_lines.append(b"(" + escaped + b") Tj")
        stream_lines.append(b"ET")
        stream = b"\n".join(stream_lines) + b"\n"

        content_id = add_obj(b"<< /Length %d >>\nstream\n%sendstream" % (len(stream), stream))
        page_id = add_obj(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    out.parent.mkdir(parents=True, exist_ok=True)

    header = b"%PDF-1.4\n%\xff\xff\xff\xff\n"
    offsets = []
    chunks = [header]
    current = len(header)

    for index, obj in enumerate(objects, start=1):
        offsets.append(current)
        chunk = f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        chunks.append(chunk)
        current += len(chunk)

    xref_offset = current
    xref = [f"xref\n0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")

    out.write_bytes(b"".join(chunks + xref + [trailer]))


source = Path(sys.argv[1])
target = Path(sys.argv[2])
text = source.read_text(encoding="utf-8")
make_pdf(text, target)
PY
}

write_fulltext_helper() {
    local smoke_case="$1"
    local plugin_root="$2"
    local helper_path="$smoke_case/.smoke-fulltext.sh"

    cat >"$helper_path" <<EOF
#!/usr/bin/env bash

set -euo pipefail

fail() {
    echo "ASSERT FAIL: \$*" >&2
    return 1
}

mirror_of() {
    python3 - "\$1" "\$SMOKE_CASE/.vassal/index.yaml" <<'PY'
import pathlib
import sys
import yaml

name, idx = sys.argv[1], sys.argv[2]
data = yaml.safe_load(pathlib.Path(idx).read_text(encoding="utf-8"))
for entry in data.get("documents", []):
    origin = entry.get("origin", {}) or {}
    if origin.get("name") == name or entry.get("file", "").endswith(name):
        print(entry["mirror"])
        break
PY
}

source_of() {
    python3 - "\$1" "\$SMOKE_CASE/.vassal/index.yaml" <<'PY'
import pathlib
import sys
import yaml

name, idx = sys.argv[1], sys.argv[2]
data = yaml.safe_load(pathlib.Path(idx).read_text(encoding="utf-8"))
for entry in data.get("documents", []):
    origin = entry.get("origin", {}) or {}
    if origin.get("name") == name or entry.get("file", "").endswith(name):
        print(entry["file"])
        break
PY
}

source_of_id() {
    python3 - "\$1" "\$SMOKE_CASE/.vassal/index.yaml" <<'PY'
import pathlib
import sys
import yaml

doc_id, idx = sys.argv[1], sys.argv[2]
data = yaml.safe_load(pathlib.Path(idx).read_text(encoding="utf-8"))
for entry in data.get("documents", []):
    if entry.get("id") == doc_id:
        print(entry["file"])
        break
PY
}

mirror_of_id() {
    python3 - "\$1" "\$SMOKE_CASE/.vassal/index.yaml" <<'PY'
import pathlib
import sys
import yaml

doc_id, idx = sys.argv[1], sys.argv[2]
data = yaml.safe_load(pathlib.Path(idx).read_text(encoding="utf-8"))
for entry in data.get("documents", []):
    if entry.get("id") == doc_id:
        print(entry["mirror"])
        break
PY
}

assert_mirror_full() {
    local mirror_rel source_rel mirror source tmp ocr_file mirror_chars ocr_chars
    local MIN_MIRROR_CHARS="\${MIN_MIRROR_CHARS:-20000}"

    if [[ "\${1:-}" == "--id" ]]; then
        local doc_id="\${2:?doc id is required}"
        mirror_rel=\$(mirror_of_id "\$doc_id")
        source_rel=\$(source_of_id "\$doc_id")
    else
        local source_name="\${1:?source name is required}"
        mirror_rel=\$(mirror_of "\$source_name")
        source_rel=\$(source_of "\$source_name")
    fi

    mirror="\$SMOKE_CASE/\$mirror_rel"
    source="\$SMOKE_CASE/\$source_rel"

    [[ -f "\$mirror" ]] || fail "mirror not found: \$mirror"
    [[ -f "\$source" ]] || fail "source not found: \$source"

    ! grep -q 'извлечены первые' "\$mirror" || fail "page truncation marker found in mirror"
    ! grep -qE '\\[\\.\\.\\. документ содержит [0-9]+ страниц' "\$mirror" || fail "document-truncation marker found in mirror"

    tmp=\$(mktemp -d -t vassal-assert-XXXXXX)
    python3 "$plugin_root/scripts/extract_text.py" "\$source" --output-dir "\$tmp" >/dev/null || {
        rm -rf "\$tmp"
        fail "re-extraction failed: \$source"
    }

    ocr_file=\$(find "\$tmp" -maxdepth 1 -type f -name '*.txt' -print -quit)
    [[ -n "\$ocr_file" && -s "\$ocr_file" ]] || {
        rm -rf "\$tmp"
        fail "fresh OCR artifact missing"
    }

    mirror_chars=\$(awk 'BEGIN{fm=0} /^---$/{fm++; next} fm>=2{print}' "\$mirror" | wc -m | tr -d ' ')
    ocr_chars=\$(wc -m < "\$ocr_file" | tr -d ' ')
    rm -rf "\$tmp"

    [[ "\$mirror_chars" -gt "\$MIN_MIRROR_CHARS" ]] || fail "mirror body unexpectedly short: body=\$mirror_chars (min=\$MIN_MIRROR_CHARS)"
    [[ "\$mirror_chars" -ge "\$((ocr_chars - 10))" ]] || fail "mirror shorter than fresh OCR: body=\$mirror_chars fresh=\$ocr_chars"
    echo "OK full mirror: \${1:-\$doc_id} body=\$mirror_chars fresh=\$ocr_chars"
}

assert_mirror_vision_full() {
    local mirror_file="\${1:?mirror file is required}"
    local vision_raw_file="\${2:?vision raw file is required}"
    local mirror_body_chars vision_body_chars

    [[ -f "\$mirror_file" ]] || fail "mirror not found: \$mirror_file"
    [[ -f "\$vision_raw_file" ]] || fail "vision raw file not found: \$vision_raw_file"

    ! grep -q 'извлечены первые' "\$mirror_file" || fail "page truncation marker found in mirror"
    ! grep -qE '\\[\\.\\.\\. документ содержит [0-9]+ страниц' "\$mirror_file" || fail "document-truncation marker found in mirror"

    mirror_body_chars=\$(awk 'BEGIN{fm=0} /^---$/{fm++; next} fm>=2{print}' "\$mirror_file" | wc -m | tr -d ' ')
    vision_body_chars=\$(python3 - "\$vision_raw_file" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
trimmed = text

if len(lines) >= 2 and lines[-1].strip() == "---":
    for index in range(len(lines) - 2, -1, -1):
        if lines[index].strip() != "---":
            continue
        yaml_block = "".join(lines[index + 1:-1])
        if any(key in yaml_block for key in ("pages_total:", "confidence_by_page:", "notable_issues:")):
            trimmed = "".join(lines[:index])
        break

print(len(trimmed))
PY
)

    [[ "\$vision_body_chars" -gt 0 ]] || fail "vision markdown body is empty"
    [[ "\$((mirror_body_chars * 100))" -ge "\$((vision_body_chars * 95))" ]] || fail "mirror shorter than vision markdown body: body=\$mirror_body_chars vision_body=\$vision_body_chars"
    echo "OK vision mirror: \$mirror_file body=\$mirror_body_chars vision_body=\$vision_body_chars"
}
EOF

    chmod +x "$helper_path"
}
