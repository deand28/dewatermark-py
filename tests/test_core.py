"""Tests for dewatermark core and CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dewatermark import scan_text, scrub_text, heuristic_perturb
from dewatermark.core import NAMED_INVISIBLES, SPACE_MAP, HOMOGLYPHS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLES = {
    "zwsp": "Hello\u200bworld",
    "zwnj_zwj": "foo\u200cbar\u200dbaz",
    "bom": "hide\ufeffden",
    "soft_hyphen": "soft\u00adhyphen",
    "nbsp": "nbsp\u00a0here",
    "thin_space": "thin\u2009space",
    "tags": "tags\U000e0061\U000e0069",
    "vs16": "vs\ufe0f ok",
    "fullwidth": "fullwidth\uff1a\uff28\uff45\uff4c\uff4c\uff4f",
    "cyrillic": "cyrillic \u0440ayment",
    "bidi": "bidi\u202eevil\u202c",
    "private_use": "pua\ue000end",
}


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------

class TestScan:
    def test_clean_text_no_hits(self):
        rep = scan_text("Hello world, this is clean text.")
        assert rep["suspicious_total"] == 0
        assert rep["by_type"] == {}

    def test_detects_zwsp(self):
        rep = scan_text(SAMPLES["zwsp"])
        assert rep["suspicious_total"] == 1
        assert "zero-width-space" in rep["by_type"]

    def test_detects_all_types(self):
        combined = "\n".join(SAMPLES.values())
        rep = scan_text(combined)
        assert rep["suspicious_total"] >= len(SAMPLES)
        assert len(rep["by_type"]) >= 5

    def test_samples_have_context(self):
        rep = scan_text(SAMPLES["zwsp"])
        assert "zero-width-space" in rep["samples"]
        assert len(rep["samples"]["zero-width-space"]) == 1
        assert "@" in rep["samples"]["zero-width-space"][0]


# ---------------------------------------------------------------------------
# scrub_text
# ---------------------------------------------------------------------------

class TestScrub:
    @pytest.mark.parametrize("key", list(SAMPLES.keys()))
    def test_removes_all_stego(self, key):
        text = SAMPLES[key]
        cleaned, report = scrub_text(text)
        assert report["after"]["suspicious_total"] == 0, (
            f"{key}: still has stego: {report['after']['by_type']}"
        )

    def test_removes_named_invisibles(self):
        for ch, name in NAMED_INVISIBLES.items():
            text = f"a{ch}b"
            cleaned, _ = scrub_text(text)
            assert ch not in cleaned, f"{name} ({hex(ord(ch))}) not removed"

    def test_removes_variation_selectors(self):
        for cp in range(0xFE00, 0xFE10):
            ch = chr(cp)
            cleaned, _ = scrub_text(f"x{ch}y")
            assert ch not in cleaned, f"VS U+{cp:04X} not removed"

    def test_removes_unicode_tags(self):
        for cp in range(0xE0020, 0xE0080):
            ch = chr(cp)
            cleaned, _ = scrub_text(f"x{ch}y")
            assert ch not in cleaned, f"Tag U+{cp:04X} not removed"

    def test_normalizes_exotic_spaces(self):
        for ch in SPACE_MAP:
            if ch == " ":
                continue
            cleaned, _ = scrub_text(f"a{ch}b")
            assert ch not in cleaned
            assert " " in cleaned

    def test_homoglyph_replacement(self):
        cleaned, report = scrub_text(SAMPLES["cyrillic"], strip_homoglyphs=True)
        assert "\u0440" not in cleaned
        assert "p" in cleaned  # Cyrillic р -> p
        assert report["mapped"]

    def test_no_homoglyph_mode(self):
        cleaned, report = scrub_text(SAMPLES["cyrillic"], strip_homoglyphs=False)
        # Cyrillic р is not in NAMED_INVISIBLES, so it stays
        assert "\u0440" in cleaned

    def test_nfkc_folds(self):
        # Fullwidth chars get folded by NFKC
        cleaned, _ = scrub_text(SAMPLES["fullwidth"])
        assert "\uff1a" not in cleaned  # fullwidth colon

    def test_preserves_code_block(self):
        code = "```python\nx = 'hello'\nprint(x)\n```"
        cleaned, _ = scrub_text(code)
        assert "```python" in cleaned
        assert "print(x)" in cleaned

    def test_preserves_newlines(self):
        text = "line1\nline2\nline3"
        cleaned, _ = scrub_text(text)
        assert cleaned.count("\n") == 2

    def test_empty_string(self):
        cleaned, report = scrub_text("")
        assert cleaned == ""
        assert report["chars_in"] == 0

    def test_combines_all_layers(self):
        text = "\n".join(SAMPLES.values()) + "\nnormal sentence."
        cleaned, report = scrub_text(text)
        assert report["after"]["suspicious_total"] == 0
        assert "normal sentence." in cleaned


# ---------------------------------------------------------------------------
# heuristic_perturb
# ---------------------------------------------------------------------------

class TestParaphrase:
    def test_preserves_code_blocks(self):
        text = "It is important. ```python\nx = 'do not skip'\n```"
        result = heuristic_perturb(text)
        assert "```python" in result
        assert "x = 'do not skip'" in result

    def test_applies_some_change(self):
        text = "It is important to utilize this tool. However, we are not done."
        result = heuristic_perturb(text)
        # Should differ from input
        assert result != text
        # Should preserve key nouns
        assert "important" in result.lower() or "tool" in result.lower()

    def test_preserves_meaning(self):
        text = "Do not skip steps. We are ready."
        result = heuristic_perturb(text)
        # Meaning preserved even if words shuffled
        assert "skip" in result.lower()
        assert "ready" in result.lower()


# ---------------------------------------------------------------------------
# CLI (subprocess)
# ---------------------------------------------------------------------------

class TestCLI:
    @pytest.fixture
    def cli_path(self):
        return Path(__file__).parent.parent / "src" / "dewatermark" / "cli.py"

    def _run(self, args, stdin=None, cli_path=None):
        # Always invoke as module so relative imports work
        cmd = [sys.executable, "-m", "dewatermark"]
        cmd.extend(args)
        return subprocess.run(
            cmd, input=stdin, text=True, capture_output=True
        )

    def test_stdin_stdout(self, cli_path):
        r = self._run(["-q"], stdin="Hello\u200bworld", cli_path=cli_path)
        assert r.returncode == 1  # marks found
        assert "\u200b" not in r.stdout
        # ZWSP is removed (not replaced with space), so "Hello" + "world" = "Helloworld"
        assert "Helloworld" in r.stdout

    def test_scan_mode(self, cli_path):
        r = self._run(["--scan"], stdin="Hello\u200bworld", cli_path=cli_path)
        assert r.returncode == 1
        rep = json.loads(r.stdout)
        assert rep["suspicious_total"] == 1

    def test_clean_text_exit_0(self, cli_path):
        r = self._run(["-q"], stdin="clean text", cli_path=cli_path)
        assert r.returncode == 0

    def test_file_output(self, tmp_path, cli_path):
        infile = tmp_path / "input.txt"
        infile.write_text("Hello\u200bworld", encoding="utf-8")
        r = self._run([str(infile)], cli_path=cli_path)
        outfile = tmp_path / "input.txt.clean"
        assert outfile.exists()
        assert "\u200b" not in outfile.read_text(encoding="utf-8")

    def test_in_place(self, tmp_path, cli_path):
        infile = tmp_path / "input.txt"
        infile.write_text("Hello\u200bworld", encoding="utf-8")
        r = self._run(["-i", str(infile)], cli_path=cli_path)
        assert "\u200b" not in infile.read_text(encoding="utf-8")

    def test_paraphrase_flag(self, cli_path):
        text = "It is important to utilize this. Do not skip."
        r = self._run(["-q", "--paraphrase"], stdin=text, cli_path=cli_path)
        assert r.returncode in (0, 1)
        assert r.stdout  # has output


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_pipeline(self):
        """All stego types in one blob, scrub, verify clean."""
        blob = "\n".join(SAMPLES.values())
        cleaned, report = scrub_text(blob)
        assert report["after"]["suspicious_total"] == 0
        assert report["chars_out"] <= report["chars_in"]

    def test_double_scrub_idempotent(self):
        text = "Hello\u200bworld nbsp\u00a0here"
        clean1, _ = scrub_text(text)
        clean2, rep2 = scrub_text(clean1)
        assert clean1 == clean2
        assert rep2["before"]["suspicious_total"] == 0
