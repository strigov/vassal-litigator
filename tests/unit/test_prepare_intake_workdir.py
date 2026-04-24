"""Unit tests for scripts/prepare_intake_workdir.py."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py already inserts scripts/ into sys.path
import prepare_intake_workdir as piw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_TEXT = "Hello, this is extracted text from the document."
FAKE_EXTRACTOR_RESULT = {
    "text": FAKE_TEXT,
    "method": "pdftext",
    "confidence": "high",
    "pages": 1,
}


def _fake_extractor(path: str) -> dict:
    return FAKE_EXTRACTOR_RESULT.copy()


def _make_inbox(tmp_path: Path) -> tuple[Path, Path]:
    """Return (inbox_dir, work_dir) inside tmp_path."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    work = tmp_path / "work"
    return inbox, work


def _run_main(inbox: Path, work: Path, extra_args: list[str] | None = None) -> dict:
    """Call piw.main() with patched extractor; return parsed JSON result."""
    args = extra_args or []
    with patch.object(piw, "_ensure_extracted_text_module", return_value=_fake_extractor):
        sys_argv = ["prepare_intake_workdir.py", str(inbox), "--work-dir", str(work)] + args
        with patch.object(sys, "argv", sys_argv):
            import io as _io
            import contextlib
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = piw.main()
    assert rc == 0, f"main() returned {rc}"
    return json.loads(buf.getvalue())


def _make_zip(dest: Path, members: dict[str, bytes]) -> None:
    """Write a zip file at *dest* with {member_name: content} pairs."""
    with zipfile.ZipFile(dest, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


# ---------------------------------------------------------------------------
# Test 1 – plain files appear in output with correct source_path and preview
# ---------------------------------------------------------------------------

def test_plain_files_appear_in_output(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    (inbox / "doc.pdf").write_bytes(b"%PDF-1.4 fake")
    (inbox / "note.txt").write_bytes(b"some text")

    result = _run_main(inbox, work)

    assert len(result["files"]) == 2
    names = {Path(f["source_path"]).name for f in result["files"]}
    assert names == {"doc.pdf", "note.txt"}

    for entry in result["files"]:
        assert entry["extracted_text_preview"] == FAKE_TEXT[:piw.MAX_PREVIEW_DEFAULT]
        assert entry["archive_src"] is None


# ---------------------------------------------------------------------------
# Test 2 – needs_image_to_pdf flag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected_flag", [
    ("photo.png", True),
    ("scan.jpg", True),
    ("scan.jpeg", True),
    ("scan.heic", True),
    ("document.pdf", False),
    ("report.docx", False),
    ("data.txt", False),
])
def test_needs_image_to_pdf(tmp_path: Path, filename: str, expected_flag: bool) -> None:
    inbox, work = _make_inbox(tmp_path)
    (inbox / filename).write_bytes(b"data")

    result = _run_main(inbox, work)

    assert len(result["files"]) == 1
    assert result["files"][0]["needs_image_to_pdf"] is expected_flag


# ---------------------------------------------------------------------------
# Test 3 – ZIP extraction: both members appear with correct archive_src
# ---------------------------------------------------------------------------

def test_zip_extraction(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    zip_path = inbox / "bundle.zip"
    _make_zip(zip_path, {
        "file_a.txt": b"content a",
        "file_b.pdf": b"%PDF fake",
    })

    result = _run_main(inbox, work)

    assert result["archives_unpacked"], "Expected at least one archive to be unpacked"
    assert len(result["files"]) == 2

    for entry in result["files"]:
        assert entry["archive_src"] is not None
        assert Path(entry["archive_src"]).name == "bundle.zip"


# ---------------------------------------------------------------------------
# Test 4 – zip-slip protection: ../escape.txt must be rejected
# ---------------------------------------------------------------------------

def test_zip_slip_rejected(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    zip_path = inbox / "evil.zip"
    _make_zip(zip_path, {"../escape.txt": b"pwned"})

    result = _run_main(inbox, work)

    assert len(result["files"]) == 0
    assert len(result["unsupported"]) == 1
    assert "evil.zip" in result["unsupported"][0]["archive"]
    reason = result["unsupported"][0]["reason"]
    assert "rejected" in reason or "slip" in reason

    # Verify no file was written outside work_dir (filesystem check)
    escape_target = tmp_path / "escape.txt"
    assert not escape_target.exists(), "zip-slip file must not exist outside work_dir"
    # Also check the inbox parent didn't get any stray file
    for stray in tmp_path.iterdir():
        if stray.name not in ("inbox", "work"):
            assert False, f"stray file created outside work_dir: {stray}"


# ---------------------------------------------------------------------------
# Test 5 – absolute path inside zip rejected
# ---------------------------------------------------------------------------

def test_zip_absolute_path_rejected(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    zip_path = inbox / "absolute.zip"
    _make_zip(zip_path, {"/etc/passwd": b"root:x:0:0"})

    result = _run_main(inbox, work)

    assert len(result["files"]) == 0
    assert len(result["unsupported"]) == 1
    assert "absolute.zip" in result["unsupported"][0]["archive"]


# ---------------------------------------------------------------------------
# Test 6 – symlink in zip is rejected or not extracted as a regular file
# ---------------------------------------------------------------------------

def test_zip_symlink_rejected(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    zip_path = inbox / "symlink.zip"

    # Craft a zip member with symlink external_attr (Unix mode 0o120644)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link_to_etc")
        # Set Unix mode to symlink (S_IFLNK = 0o120000)
        info.external_attr = (0o120644) << 16
        zf.writestr(info, "/etc/passwd")  # symlink target as content
    zip_path.write_bytes(buf.getvalue())

    result = _run_main(inbox, work)

    # Symlink pointing outside must be rejected
    assert len(result["files"]) == 0
    assert len(result["unsupported"]) == 1


# ---------------------------------------------------------------------------
# Test 7 – unsupported archive extension ends up in unsupported[]
# ---------------------------------------------------------------------------

def test_unsupported_archive_extension(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    # .xyz is not in ARCHIVE_SUFFIXES so it is treated as a plain file, not an archive
    # A .rar file with unsupported handler (unrar not present) ends up in unsupported[]
    # Use a plain non-archive extension that IS an archive kind we can spoof via _archive_kind:
    # The cleanest approach: patch _archive_kind to return "xyz" for our file.
    (inbox / "weird.xyz").write_bytes(b"data")

    with patch.object(piw, "_archive_kind", return_value="xyz"):
        with patch.object(piw, "_ensure_extracted_text_module", return_value=_fake_extractor):
            sys_argv = ["prepare_intake_workdir.py", str(inbox), "--work-dir", str(work)]
            import io as _io, contextlib
            buf = _io.StringIO()
            with patch.object(sys, "argv", sys_argv):
                with contextlib.redirect_stdout(buf):
                    rc = piw.main()
    assert rc == 0
    result = json.loads(buf.getvalue())

    assert len(result["unsupported"]) == 1
    assert "weird.xyz" in result["unsupported"][0]["archive"]
    assert "Unsupported" in result["unsupported"][0]["reason"]


# ---------------------------------------------------------------------------
# Test 8 – empty inbox directory
# ---------------------------------------------------------------------------

def test_empty_inbox(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)

    result = _run_main(inbox, work)

    assert result["files"] == []
    assert result["archives_unpacked"] == []
    assert result["unsupported"] == []


# ---------------------------------------------------------------------------
# Test 9 – CLI subprocess returns valid JSON with expected top-level keys
# ---------------------------------------------------------------------------

def test_cli_subprocess_valid_json(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    (inbox / "sample.txt").write_bytes(b"hello world")

    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "prepare_intake_workdir.py"
    )

    # We need to mock extract_text.py so the CLI process doesn't need tesseract.
    # Write a minimal shim into a temporary scripts overlay and prepend it to PYTHONPATH.
    shim_dir = tmp_path / "shim_scripts"
    shim_dir.mkdir()
    (shim_dir / "extract_text.py").write_text(
        "def extract(path):\n"
        "    return {'text': 'cli test text', 'method': 'shim', 'confidence': 'high', 'pages': 1}\n",
        encoding="utf-8",
    )

    # Temporarily replace scripts/extract_text.py via PATH manipulation is tricky;
    # instead run with PYTHONPATH so importlib finds our shim first.
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(shim_dir) + (":" + existing_pp if existing_pp else "")

    proc = subprocess.run(
        [sys.executable, str(script), str(inbox), "--work-dir", str(work)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    data = json.loads(proc.stdout)

    for key in ("work_dir", "files", "archives_unpacked", "unsupported"):
        assert key in data, f"Missing key: {key}"
    assert isinstance(data["files"], list)


# ---------------------------------------------------------------------------
# Test 10 – --max-preview-chars truncates extracted_text_preview
# ---------------------------------------------------------------------------

def test_max_preview_chars_truncation(tmp_path: Path) -> None:
    inbox, work = _make_inbox(tmp_path)
    (inbox / "doc.pdf").write_bytes(b"%PDF fake")

    limit = 10
    result = _run_main(inbox, work, extra_args=[f"--max-preview-chars={limit}"])

    assert len(result["files"]) == 1
    preview = result["files"][0]["extracted_text_preview"]
    assert len(preview) <= limit
    assert preview == FAKE_TEXT[:limit]


# ---------------------------------------------------------------------------
# Test 11 – missing 7z binary: archive goes to unsupported[], no exception
# ---------------------------------------------------------------------------

def test_7z_missing_binary_goes_to_unsupported(tmp_path: Path) -> None:
    """When 7z binary is not available, the archive ends up in unsupported[],
    no exception is raised, and no files are added to files[]."""
    inbox, work = _make_inbox(tmp_path)
    # Create a file with .7z extension (content doesn't matter — 7z won't be called)
    archive = inbox / "archive.7z"
    archive.write_bytes(b"fake 7z content")

    # Patch _prelist_7z_members to simulate binary not found
    with patch.object(piw, "_prelist_7z_members", return_value=(None, "7z command not found")):
        result = _run_main(inbox, work)

    assert len(result["files"]) == 0, "No files should be extracted when 7z is missing"
    assert len(result["unsupported"]) == 1
    entry = result["unsupported"][0]
    assert "archive.7z" in entry["archive"]
    assert "7z" in entry["reason"] or "command not found" in entry["reason"]
