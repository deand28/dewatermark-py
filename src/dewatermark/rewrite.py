"""LLM rewrite module — kill statistical watermarks by paraphrasing with a
model that does NOT watermark its own output.

CRITICAL: never rewrite Claude output with Claude. Model-level watermarks
are applied at generation, so a Claude paraphrase just re-embeds the mark.
Use a local model (Ollama) or a non-watermarking vendor.

Backend priority:
  1. DEWATERMARK_REWRITE_CMD — any shell cmd, stdin text -> stdout rewrite
  2. Ollama local model (default qwen3:4b) — offline, free, no refusals
  3. Any OpenAI-compatible endpoint via DEWATERMARK_OPENAI_BASE/KEY/MODEL
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request

DEFAULT_MODEL = "qwen3:14b"
OLLAMA_URL = "http://localhost:11434"

# Benchmarked 2026-08-12 (scripts/bench_rewrite.py):
#   qwen3:14b temp=0.8 -> 8gram-overlap 0.00, length-preserving (BEST)
#   qwen3:4b  temp=0.8 -> 0.05 but rambles (6x length), unreliable
#   temp=1.0 degrades both. qwen3:14b is the smallest reliable model tested.
SYSTEM_PROMPT = (
    "Rewrite the text below with maximum restructuring: change every sentence's "
    "construction, reorder information within sentences, swap every possible "
    "synonym, split or merge sentences. Keep all facts and the same length. "
    "Preserve markdown structure (headings, lists, code blocks). "
    "No preamble, no commentary, output only the rewritten text. /no_think"
)


class RewriteError(RuntimeError):
    pass


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> reasoning blocks some models emit."""
    import re

    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).strip()


def rewrite_cmd(text: str) -> str | None:
    tmpl = os.environ.get("DEWATERMARK_REWRITE_CMD")
    if not tmpl:
        return None
    r = subprocess.run(
        tmpl, shell=True, input=text, text=True, capture_output=True, timeout=300
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout
    raise RewriteError(f"DEWATERMARK_REWRITE_CMD failed: {r.stderr[:200]}")


def rewrite_ollama(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_URL,
    timeout: int = 600,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.8, "num_predict": max(2048, len(text) * 3)},
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RewriteError(f"Ollama request failed: {e}") from e
    out = data.get("message", {}).get("content", "")
    if not out.strip():
        raise RewriteError("Ollama returned empty response")
    return _strip_think_blocks(out)


def rewrite_openai_compat(text: str) -> str | None:
    base = os.environ.get("DEWATERMARK_OPENAI_BASE")
    key = os.environ.get("DEWATERMARK_OPENAI_KEY")
    model = os.environ.get("DEWATERMARK_OPENAI_MODEL")
    if not (base and model):
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.8,
    }
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = data["choices"][0]["message"]["content"]
    return _strip_think_blocks(out)


def rewrite(
    text: str, *, model: str = DEFAULT_MODEL, base_url: str = OLLAMA_URL
) -> tuple[str, str]:
    """Rewrite text. Returns (rewritten_text, backend_name)."""
    r = rewrite_cmd(text)
    if r is not None:
        return r, "external-cmd"
    r = rewrite_openai_compat(text)
    if r is not None:
        return r, f"openai-compat:{os.environ.get('DEWATERMARK_OPENAI_MODEL')}"
    return rewrite_ollama(text, model=model, base_url=base_url), f"ollama:{model}"
