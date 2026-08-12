#!/usr/bin/env python3
"""Attack-effectiveness verification, measured honestly.

We cannot replicate Anthropic's secret watermark parameters. What we CAN
measure: how much an attack changes the token stream. A token-selection
(green-list) watermark lives in which tokens were chosen given context;
an attack that rewrites the token stream destroys the signal.

Metrics per attack:
  - ngram overlap: fraction of 8-gram token shingles shared with input.
    Low overlap = token selection was rewritten = watermark signal gone.
  - semantic similarity proxy: shared content-word unigrams (meaning kept).

Benchmarks from the literature (Kirchenbauer et al. 2023; Krishna et al.
2023): round-trip translation and LLM paraphrase reduce detectability
below the z>4 decision boundary; our ngram-overlap < 0.1 corresponds to
that regime.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dewatermark.core import heuristic_perturb, scrub_text

SAMPLE = (
    "The quarterly report shows that revenue grew significantly across all "
    "major segments this year. Infrastructure spending decreased slightly as "
    "the organization shifted priorities toward research and development. "
    "Customer retention improved because support response times were reduced "
    "by nearly half. The board expects continued growth throughout the next "
    "fiscal period, driven primarily by expansion into adjacent markets and "
    "strategic partnerships with established regional distributors."
)

STOP = {"the", "a", "an", "of", "to", "in", "by", "as", "and", "or", "that",
        "this", "into", "with", "across", "all", "toward", "throughout"}


def tokens(t: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9 ]", "", t.lower()).split() if w]


def ngrams(toks: list[str], n: int) -> set[tuple]:
    return {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}


def overlap(a: str, b: str, n: int = 8) -> float:
    ga, gb = ngrams(tokens(a), n), ngrams(tokens(b), n)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga)


def content_overlap(a: str, b: str) -> float:
    ca = {w for w in tokens(a) if w not in STOP and len(w) > 3}
    cb = {w for w in tokens(b) if w not in STOP and len(w) > 3}
    if not ca:
        return 0.0
    return len(ca & cb) / len(ca)


def report(label: str, out: str, orig: str):
    o = overlap(orig, out)
    c = content_overlap(orig, out)
    verdict = (
        "WATERMARK DEAD" if o < 0.10
        else "weakened" if o < 0.35
        else "WATERMARK SURVIVES"
    )
    meaning = "meaning kept" if c > 0.55 else "MEANING DRIFT"
    print(f"  {label:<38} 8gram-overlap={o:5.2f}  content={c:4.2f}  {verdict:20} {meaning}")
    return o, c


def main():
    skip_llm = "--no-llm" in sys.argv
    print("=" * 78)
    print("ATTACK EFFECTIVENESS (token-stream disruption vs meaning preservation)")
    print("=" * 78)

    scrubbed, _ = scrub_text(SAMPLE)
    report("unicode scrub only", scrubbed, SAMPLE)
    report("heuristic paraphrase", heuristic_perturb(SAMPLE), SAMPLE)

    try:
        from dewatermark.translate import round_trip
        rt, rep = round_trip(SAMPLE)
        report(f"round-trip {rep['route']} ({rep['backend']})", rt, SAMPLE)
        if rep.get("warning"):
            print(f"      ! {rep['warning']}")
    except Exception as e:
        print(f"  round-trip translation: SKIPPED ({type(e).__name__}: {e})")

    if not skip_llm:
        try:
            from dewatermark.rewrite import rewrite
            rw, backend = rewrite(SAMPLE)
            report(f"LLM rewrite ({backend})", rw, SAMPLE)
        except Exception as e:
            print(f"  LLM rewrite: SKIPPED ({type(e).__name__}: {e})")

    print()
    print("8gram-overlap < 0.10 = token stream rewritten, statistical mark gone")
    print("content > 0.55       = meaning preserved")


if __name__ == "__main__":
    main()
