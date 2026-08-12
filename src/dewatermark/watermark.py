"""Statistical watermark simulation + detection (Kirchenbauer-style, word-level).

Model-level watermarks bias *token* selection. English tokens ≈ words for
this simulation. We build a vocabulary from the text's words plus a synonym
pool, then simulate the green-list bias by swapping red-listed words for
green-listed synonyms (what a watermarking sampler does at generation).

Purpose: verification. Embed a watermark -> attack it -> measure z-score
collapse. z > 4 = detectable, z < 2 = broken.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from collections import Counter

# Minimal synonym pool so the embedder has green alternatives to swap in.
# Key: word -> candidates that preserve rough meaning.
SYNONYMS = {
    "report": ["summary", "analysis"], "shows": ["indicates", "reveals"],
    "revenue": ["income", "earnings"], "grew": ["increased", "expanded"],
    "significantly": ["substantially", "markedly"], "major": ["primary", "key"],
    "year": ["period"], "spending": ["expenditure", "outlay"],
    "decreased": ["declined", "dropped"], "slightly": ["modestly", "marginally"],
    "organization": ["company", "firm"], "priorities": ["focus", "emphasis"],
    "toward": ["to", "into"], "research": ["study", "investigation"],
    "development": ["engineering", "growth"], "customer": ["client"],
    "improved": ["strengthened", "advanced"], "because": ["since", "as"],
    "support": ["assistance", "service"], "response": ["reply", "reaction"],
    "times": ["intervals"], "reduced": ["cut", "lowered"],
    "nearly": ["almost", "roughly"], "half": ["fifty percent"],
    "board": ["leadership", "directors"], "expects": ["anticipates", "projects"],
    "continued": ["ongoing", "sustained"], "growth": ["expansion"],
    "throughout": ["across", "during"], "next": ["coming", "upcoming"],
    "fiscal": ["financial"], "driven": ["fueled", "powered"],
    "primarily": ["mainly", "chiefly"], "expansion": ["broadening"],
    "adjacent": ["neighboring", "related"], "markets": ["sectors"],
    "strategic": ["planned"], "partnerships": ["alliances"],
    "established": ["entrenched", "veteran"], "regional": ["local"],
    "distributors": ["resellers", "partners"], "across": ["throughout"],
    "all": ["every"], "this": ["the"], "as": ["while"],
    "the": ["this"], "and": ["plus"], "by": ["through"],
    "into": ["in"], "with": ["alongside"],
}


def _green_list(
    prev_word: str, key: str, vocab: list[str], gamma: float = 0.5
) -> set[str]:
    h = int(hashlib.sha256(f"{key}:{prev_word}".encode()).hexdigest(), 16)
    rng = random.Random(h)
    k = max(1, int(len(vocab) * gamma))
    return set(rng.sample(vocab, k))


def _text_vocab(words: list[str]) -> list[str]:
    return sorted({w for w in words if w})


def embed_watermark(
    text: str, key: str = "xprt-test-key", gamma: float = 0.5, delta: float = 4.0
) -> str:
    """Embed a word-level green-list watermark by swapping red words for
    green synonyms where available (simulates logit bias at generation)."""
    words = text.split()
    cores = [re.sub(r"[^a-z]", "", w.lower()) for w in words]
    vocab = _text_vocab([c for c in cores if c])
    prev = "<s>"
    out = []
    for w, core in zip(words, cores):
        green = _green_list(prev, key, vocab, gamma)
        new_w = w
        if core and core in SYNONYMS and core not in green:
            candidates = list(SYNONYMS[core])
            if candidates:
                h = int(
                    hashlib.sha256(f"{key}:{prev}:{core}".encode()).hexdigest(),
                    16,
                )
                if (h % 1000) / 1000.0 < min(1.0, delta / 4.0):
                    replacement = candidates[h % len(candidates)]
                    if w[:1].isupper():
                        replacement = replacement.capitalize()
                    new_w = (
                        w.replace(core, replacement) if core in w else replacement
                    )
        out.append(new_w)
        prev = re.sub(r"[^a-z]", "", new_w.lower()) or prev
    return " ".join(out)


def detect_watermark(
    text: str, key: str = "xprt-test-key", gamma: float = 0.5
) -> dict:
    words = [re.sub(r"[^a-z]", "", w.lower()) for w in text.split()]
    words = [w for w in words if w]
    n = len(words)
    if n == 0:
        return {"n": 0, "green_hits": 0, "z": 0.0, "verdict": "no-text"}
    vocab = _text_vocab(words)
    hits = 0
    prev = "<s>"
    for w in words:
        if w in _green_list(prev, key, vocab, gamma):
            hits += 1
        prev = w
    expected = n * gamma
    var = n * gamma * (1 - gamma)
    z = (hits - expected) / math.sqrt(var) if var > 0 else 0.0
    return {
        "n": n,
        "green_hits": hits,
        "expected": round(expected, 1),
        "z": round(z, 2),
        "verdict": "WATERMARKED" if z > 4 else "suspicious" if z > 2 else "undetectable",
    }


def word_frequency_distance(a: str, b: str) -> float:
    wa = Counter(a.lower().split())
    wb = Counter(b.lower().split())
    if not wa or not wb:
        return 1.0
    overlap = sum(min(wa[w], wb[w]) for w in wa)
    total = max(sum(wa.values()), sum(wb.values()))
    return 1.0 - overlap / total
