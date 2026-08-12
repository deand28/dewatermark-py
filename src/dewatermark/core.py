"""Core text watermark/steganography detection and scrubbing.

This module handles three layers:
  1. Invisible Unicode steganography (ZWSP, ZWNJ, WJ, BOM, soft hyphen,
     variation selectors, tags, bidi controls, formatting chars).
  2. Homoglyph / confusable normalization (fullwidth, Cyrillic lookalikes,
     fancy math alphanumerics -> ASCII where safe).
  3. Whitespace / NBSP / exotic space collapse + NFKC fold.

A fourth layer (statistical watermark break) is provided via
``heuristic_perturb`` and ``external_paraphrase`` — the only reliable
counter to model-level logit watermarks like Claude's (Anthropic, Aug
2026 EU AI Act marking).
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from typing import Iterable

# ---------------------------------------------------------------------------
# Character classes that are pure payload carriers for text steganography
# ---------------------------------------------------------------------------

NAMED_INVISIBLES: dict[str, str] = {
    "\u00ad": "soft-hyphen",
    "\u034f": "combining-grapheme-joiner",
    "\u061c": "arabic-letter-mark",
    "\u180e": "mongolian-vowel-separator",
    "\u200b": "zero-width-space",
    "\u200c": "zero-width-non-joiner",
    "\u200d": "zero-width-joiner",
    "\u200e": "left-to-right-mark",
    "\u200f": "right-to-left-mark",
    "\u202a": "lre",
    "\u202b": "rle",
    "\u202c": "pdf",
    "\u202d": "lro",
    "\u202e": "rlo",
    "\u2060": "word-joiner",
    "\u2061": "function-application",
    "\u2062": "invisible-times",
    "\u2063": "invisible-separator",
    "\u2064": "invisible-plus",
    "\u2066": "lri",
    "\u2067": "rli",
    "\u2068": "fsi",
    "\u2069": "pdi",
    "\u206a": "inhibit-symmetric-swapping",
    "\u206b": "activate-symmetric-swapping",
    "\u206c": "inhibit-arabic-form-shaping",
    "\u206d": "activate-arabic-form-shaping",
    "\u206e": "national-digit-shapes",
    "\u206f": "nominal-digit-shapes",
    "\ufeff": "bom-zwnbsp",
    "\ufff9": "interlinear-annotation-anchor",
    "\ufffa": "interlinear-annotation-separator",
    "\ufffb": "interlinear-annotation-terminator",
}

VS_RANGES = (
    (0xFE00, 0xFE0F),   # VS1-VS16
    (0xE0100, 0xE01EF), # VS17-VS256
)

TAG_RANGES = (
    (0xE0001, 0xE0001),
    (0xE0020, 0xE007F),
)

SPACE_MAP = {
    "\u00a0": " ",
    "\u1680": " ",
    "\u2000": " ",
    "\u2001": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2004": " ",
    "\u2005": " ",
    "\u2006": " ",
    "\u2007": " ",
    "\u2008": " ",
    "\u2009": " ",
    "\u200a": " ",
    "\u202f": " ",
    "\u205f": " ",
    "\u3000": " ",
}

HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "α": "a", "ο": "o", "ν": "v",
    **{chr(0xFF01 + i): chr(0x21 + i) for i in range(94)},
}

KEEP_CONTROLS = {"\t", "\n", "\r"}


def _in_ranges(cp: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def scan_text(text: str) -> dict:
    """Inventory of suspicious chars. Does not modify text."""
    counts: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}
    for i, ch in enumerate(text):
        cp = ord(ch)
        label: str | None = None
        if ch in NAMED_INVISIBLES:
            label = NAMED_INVISIBLES[ch]
        elif ch in SPACE_MAP and ch != " ":
            label = f"exotic-space-U+{cp:04X}"
        elif _in_ranges(cp, VS_RANGES):
            label = f"variation-selector-U+{cp:04X}"
        elif _in_ranges(cp, TAG_RANGES):
            label = f"unicode-tag-U+{cp:04X}"
        else:
            cat = unicodedata.category(ch)
            if cat == "Cf" and ch not in KEEP_CONTROLS:
                label = f"format-{cat}-U+{cp:04X}"
            elif cat == "Cc" and ch not in KEEP_CONTROLS:
                label = f"control-{cat}-U+{cp:04X}"
            elif cat == "Co":
                label = f"private-use-U+{cp:04X}"
            elif ch in HOMOGLYPHS and HOMOGLYPHS[ch] != ch:
                label = f"homoglyph-{ch!r}->{HOMOGLYPHS[ch]!r}"

        if label:
            counts[label] += 1
            bucket = samples.setdefault(label, [])
            if len(bucket) < 3:
                ctx = text[max(0, i - 12): i + 13].replace("\n", "⏎")
                bucket.append(f"@{i}: ...{ctx}...")

    return {
        "total_chars": len(text),
        "suspicious_total": sum(counts.values()),
        "by_type": dict(counts.most_common()),
        "samples": samples,
    }


def scrub_text(
    text: str,
    *,
    strip_homoglyphs: bool = True,
    normalize_spaces: bool = True,
    nfkc: bool = True,
) -> tuple[str, dict]:
    """Remove steganographic / invisible carriers.

    Returns ``(clean, report)``.
    Does NOT break statistical/logit watermarks — use ``heuristic_perturb``
    or ``external_paraphrase`` for that.
    """
    before = scan_text(text)
    out: list[str] = []
    removed: Counter[str] = Counter()
    mapped: Counter[str] = Counter()

    for ch in text:
        cp = ord(ch)

        if ch in NAMED_INVISIBLES:
            removed[NAMED_INVISIBLES[ch]] += 1
            continue

        if _in_ranges(cp, VS_RANGES):
            removed[f"variation-selector-U+{cp:04X}"] += 1
            continue
        if _in_ranges(cp, TAG_RANGES):
            removed[f"unicode-tag-U+{cp:04X}"] += 1
            continue

        cat = unicodedata.category(ch)
        if cat in {"Cf", "Cc", "Co"} and ch not in KEEP_CONTROLS:
            removed[f"{cat}-U+{cp:04X}"] += 1
            continue

        if normalize_spaces and ch in SPACE_MAP:
            mapped[f"space-U+{cp:04X}"] += 1
            out.append(SPACE_MAP[ch])
            continue

        if strip_homoglyphs and ch in HOMOGLYPHS:
            repl = HOMOGLYPHS[ch]
            if repl != ch:
                mapped[f"homoglyph-{ch!r}"] += 1
                out.append(repl)
                continue

        out.append(ch)

    cleaned = "".join(out)

    if nfkc:
        folded = unicodedata.normalize("NFKC", cleaned)
        if folded != cleaned:
            mapped["nfkc-fold"] += abs(len(cleaned) - len(folded)) or 1
            cleaned = folded

    if normalize_spaces:
        cleaned = re.sub(r"[^\S\n\r\t]+", " ", cleaned)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)

    after = scan_text(cleaned)
    report = {
        "before": before,
        "after": after,
        "removed": dict(removed),
        "mapped": dict(mapped),
        "bytes_in": len(text.encode("utf-8")),
        "bytes_out": len(cleaned.encode("utf-8")),
        "chars_in": len(text),
        "chars_out": len(cleaned),
        "layer": "unicode-stego",
        "note": (
            "Unicode/stego layer only. Claude-style model-level statistical "
            "watermarks need --paraphrase (or manual heavy edit / translate)."
        ),
    }
    return cleaned, report


# ---------------------------------------------------------------------------
# Statistical watermark break
# ---------------------------------------------------------------------------

def heuristic_perturb(text: str) -> str:
    """Zero-dependency statistical-signal breaker.

    Not a full paraphrase — applies meaning-preserving surface edits that
    destroy token-level green/red list alignment used by Kirchenbauer-style
    and similar logit watermarks:
      - contraction expand/collapse
      - synonym micro-swaps on function words
      - clause comma / 'and'/'then' jitter
      - quote style normalize
    Safe for code blocks (left untouched).
    """
    fences: list[str] = []

    def _stash(m: re.Match) -> str:
        fences.append(m.group(0))
        return f"@@FENCE{len(fences) - 1}@@"

    body = re.sub(r"```.*?```", _stash, text, flags=re.S)
    body = re.sub(r"`[^`\n]+`", _stash, body)

    body = (
        body.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )

    swaps = [
        (r"\bdo not\b", "don't"),
        (r"\bdon't\b", "do not"),
        (r"\bcannot\b", "can't"),
        (r"\bcan't\b", "cannot"),
        (r"\bwill not\b", "won't"),
        (r"\bwon't\b", "will not"),
        (r"\bit is\b", "it's"),
        (r"\bit's\b", "it is"),
        (r"\bthat is\b", "that's"),
        (r"\bthat's\b", "that is"),
        (r"\bwe are\b", "we're"),
        (r"\bthey're\b", "they are"),
        (r"\bthey are\b", "they're"),
        (r"\bin order to\b", "to"),
        (r"\bdue to the fact that\b", "because"),
        (r"\ba number of\b", "several"),
        (r"\bin addition\b", "also"),
        (r"\bhowever\b", "though"),
        (r"\btherefore\b", "so"),
        (r"\bthus\b", "so"),
        (r"\butilize\b", "use"),
        (r"\butilize[sd]\b", "used"),
        (r"\bconcerning\b", "about"),
        (r"\bregarding\b", "about"),
        (r"\bprior to\b", "before"),
        (r"\bsubsequent to\b", "after"),
        (r"\bassist in\b", "help"),
        (r"\bin the event that\b", "if"),
    ]
    parts = re.split(r"(?<=[.!?])\s+", body)
    for i, p in enumerate(parts):
        if i % 2 == 1:
            for pat, rep in swaps:
                p2, n = re.subn(pat, rep, p, count=1, flags=re.I)
                if n:
                    p = p2
                    break
        parts[i] = p
    body = " ".join(parts)

    for i, f in enumerate(fences):
        body = body.replace(f"@@FENCE{i}@@", f)
    return body


def external_paraphrase(text: str) -> str | None:
    """Optional heavy break.

    Honors ``DEWATERMARK_REWRITE_CMD`` — shell cmd, text on stdin,
    rewritten text on stdout. Returns ``None`` if unavailable.
    """
    import subprocess

    cmd = os.environ.get("DEWATERMARK_REWRITE_CMD")
    if not cmd:
        return None
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            input=text,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    except Exception as e:
        print(f"dewatermark: rewrite cmd failed: {e}", file=__import__("sys").stderr)
    return None
