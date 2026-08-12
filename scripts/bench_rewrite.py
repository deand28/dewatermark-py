"""Head-to-head: smallest model + best settings for watermark-killing rewrite."""
import json
import re
import sys
import urllib.request

SAMPLE = (
    "The quarterly report shows that revenue grew significantly across all "
    "major segments this year. Infrastructure spending decreased slightly as "
    "the organization shifted priorities toward research and development. "
    "Customer retention improved because support response times were reduced "
    "by nearly half. The board expects continued growth throughout the next "
    "fiscal period, driven primarily by expansion into adjacent markets and "
    "strategic partnerships with established regional distributors."
)

AGGRESSIVE = (
    "Rewrite the text below with maximum restructuring: change every sentence's "
    "construction, reorder information within sentences, swap every possible "
    "synonym, split or merge sentences. Keep all facts and the same length. "
    "No preamble, no commentary, output only the rewritten text. /no_think"
)


def tokens(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).split()


def ngrams(t, n=8):
    tk = tokens(t)
    return {tuple(tk[i:i + n]) for i in range(len(tk) - n + 1)}


def overlap(a, b):
    ga, gb = ngrams(a), ngrams(b)
    return len(ga & gb) / len(ga) if ga else 0.0


for model in ["qwen3:4b", "qwen3:14b"]:
    for temp in [0.8, 1.0]:
        payload = {
            "model": model, "think": False, "stream": False,
            "messages": [
                {"role": "system", "content": AGGRESSIVE},
                {"role": "user", "content": SAMPLE},
            ],
            "options": {"temperature": temp, "num_predict": 2048},
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())["message"]["content"]
            out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
            print(f"{model} temp={temp}: 8gram-overlap={overlap(SAMPLE, out):.2f} len={len(out)}")
        except Exception as e:
            print(f"{model} temp={temp}: ERROR {e}")
