"""Round-trip translation attack against statistical text watermarks.

Why this works: model-level watermarks (Kirchenbauer-style green-list logit
biasing, which Anthropic's EU AI Act marking is documented to resemble)
encode signal in the *choice of tokens* given prior context. Translating to
another language and back re-selects nearly every token while preserving
meaning, so the statistical signal collapses. Anthropic's own docs list
"translated" as a failure mode for their watermark detection.

Backend priority:
  1. DEWATERMARK_TRANSLATE_CMD — shell template, e.g.
     'mytranslate {src} {dst}' — receives text on stdin, prints translation.
     Invoked twice (en->via, via->en).
  2. argostranslate (local, offline) if importable.
  3. MyMemory public API (free, no key) — text leaves the device; a warning
     is included in the report.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request

DEFAULT_VIA = "de"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"


class TranslateError(RuntimeError):
    pass


def _translate_cmd(text: str, src: str, dst: str) -> str | None:
    tmpl = os.environ.get("DEWATERMARK_TRANSLATE_CMD")
    if not tmpl:
        return None
    cmd = tmpl.format(src=src, dst=dst)
    r = subprocess.run(
        cmd, shell=True, input=text, text=True, capture_output=True, timeout=180
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout
    raise TranslateError(f"DEWATERMARK_TRANSLATE_CMD failed: {r.stderr[:200]}")


def _translate_argos(text: str, src: str, dst: str) -> str | None:
    try:
        import argostranslate.translate as argos
    except ImportError:
        return None
    langs = {l.code: l for l in argos.get_installed_languages()}
    if src not in langs or dst not in langs:
        return None
    return langs[src].get_translation(langs[dst]).translate(text)


def _translate_mymemory(text: str, src: str, dst: str) -> str:
    """Free public API. 10k chars/day anonymous. Chunks long text."""
    out_parts: list[str] = []
    # crude sentence chunking to stay under URL length limits
    chunk = ""
    import re as _re

    sentences = _re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        if len(chunk) + len(s) > 450:
            if chunk:
                out_parts.append(_mymemory_call(chunk, src, dst))
            chunk = s
        else:
            chunk = (chunk + " " + s).strip()
    if chunk:
        out_parts.append(_mymemory_call(chunk, src, dst))
    return " ".join(out_parts)


def _mymemory_call(text: str, src: str, dst: str) -> str:
    q = urllib.parse.urlencode({"q": text, "langpair": f"{src}|{dst}"})
    req = urllib.request.Request(
        f"{MYMEMORY_URL}?{q}", headers={"User-Agent": "dewatermark/0.1"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    translated = data.get("responseData", {}).get("translatedText")
    if not translated:
        raise TranslateError(f"MyMemory error: {str(data)[:200]}")
    return translated


def translate(text: str, src: str, dst: str) -> tuple[str, str]:
    """Translate once. Returns (translated_text, backend_name)."""
    r = _translate_cmd(text, src, dst)
    if r is not None:
        return r, "external-cmd"
    r = _translate_argos(text, src, dst)
    if r is not None:
        return r, "argostranslate-local"
    return _translate_mymemory(text, src, dst), "mymemory-public-api"


def round_trip(
    text: str, *, home: str = "en", via: str = DEFAULT_VIA
) -> tuple[str, dict]:
    """Translate home -> via -> home. Returns (result, report)."""
    out1, backend = translate(text, home, via)
    out2, backend2 = translate(out1, via, home)
    return out2, {
        "route": f"{home}->{via}->{home}",
        "backend": backend,
        "chars_in": len(text),
        "chars_out": len(out2),
        "warning": (
            "mymemory-public-api sends text to a third party"
            if backend == "mymemory-public-api"
            else None
        ),
        "note": "Round-trip translation re-selects nearly every token; "
        "statistical watermarks do not survive it.",
    }
