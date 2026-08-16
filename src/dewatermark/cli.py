"""Command-line interface for dewatermark."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import scan_text, scrub_text, external_paraphrase, heuristic_perturb
from .image import strip_image_provenance


def _read_clipboard() -> str:
    import subprocess
    return subprocess.check_output(["pbpaste"], text=True)


def _write_clipboard(text: str) -> None:
    import subprocess
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dewatermark",
        description=(
            "Strip AI text watermarks, invisible Unicode steganography, "
            "and file provenance marks."
        ),
    )
    ap.add_argument("path", nargs="?", help="Input file (default: stdin)")
    ap.add_argument("-i", "--in-place", action="store_true", help="Overwrite input file")
    ap.add_argument("-o", "--output", help="Output path")
    ap.add_argument("--clip", action="store_true", help="Read+write macOS clipboard")
    ap.add_argument("--scan", action="store_true", help="Detect only; print JSON report")
    ap.add_argument("--json", action="store_true", help="Machine-readable report on stderr")
    ap.add_argument("--no-homoglyphs", action="store_true", help="Keep confusable lookalikes")
    ap.add_argument("--no-nfkc", action="store_true", help="Skip NFKC normalization")
    ap.add_argument(
        "--paraphrase",
        action="store_true",
        help="Fast synonym jitter. WEAK: does not reliably break statistical "
        "watermarks. Use --rewrite or --translate for real breaks.",
    )
    ap.add_argument(
        "--rewrite",
        action="store_true",
        help="Break statistical watermarks via local LLM rewrite "
        "(Ollama, default qwen3:14b). Strongest attack. Never use Claude.",
    )
    ap.add_argument(
        "--model",
        default="qwen3:14b",
        help="Ollama model for --rewrite (default: qwen3:14b)",
    )
    ap.add_argument(
        "--translate",
        action="store_true",
        help="Break statistical watermarks via round-trip translation "
        "(en->de->en; argostranslate local if installed, else MyMemory API)",
    )
    ap.add_argument(
        "--image",
        action="store_true",
        help="Treat path as image; strip C2PA/XMP/EXIF via clean re-encode",
    )
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)

    # --- image mode ---
    if args.image:
        if not args.path:
            print("dewatermark: --image needs a path", file=sys.stderr)
            return 2
        report = strip_image_provenance(
            Path(args.path),
            Path(args.output) if args.output else None,
        )
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 2

    # --- load text ---
    if args.clip:
        text = _read_clipboard()
        src_label = "clipboard"
    elif args.path:
        text = Path(args.path).read_text(encoding="utf-8", errors="surrogateescape")
        src_label = args.path
    else:
        text = sys.stdin.read()
        src_label = "stdin"

    # --- scan-only ---
    if args.scan:
        rep = scan_text(text)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 1 if rep["suspicious_total"] else 0

    # --- scrub ---
    cleaned, report = scrub_text(
        text,
        strip_homoglyphs=not args.no_homoglyphs,
        nfkc=not args.no_nfkc,
    )

    if args.paraphrase:
        rewritten = external_paraphrase(cleaned)
        if rewritten is None:
            rewritten = heuristic_perturb(cleaned)
            report["paraphrase"] = "heuristic"
        else:
            report["paraphrase"] = "external"
        cleaned = rewritten
        report["after_paraphrase_chars"] = len(cleaned)

    if args.translate:
        from .translate import round_trip

        cleaned, trep = round_trip(cleaned)
        report["translate"] = trep
        if trep.get("warning"):
            print(f"  ! {trep['warning']}", file=sys.stderr)

    if args.rewrite:
        from .rewrite import rewrite

        try:
            cleaned, backend = rewrite(cleaned, model=args.model)
            report["rewrite_backend"] = backend
        except Exception as e:
            print(
                f"dewatermark: LLM rewrite FAILED ({e}). "
                "Heuristic fallback does NOT reliably break statistical watermarks. "
                "Start Ollama (ollama serve) and re-run, or use --translate.",
                file=sys.stderr,
            )
            cleaned = heuristic_perturb(cleaned)
            report["rewrite_backend"] = "heuristic-fallback-WEAK"

    # --- write ---
    if args.clip:
        _write_clipboard(cleaned)
        dest_label = "clipboard"
    elif args.path and (args.in_place or args.output):
        dest = Path(args.output) if args.output else Path(args.path)
        dest.write_text(cleaned, encoding="utf-8")
        dest_label = str(dest)
    elif args.path and not args.in_place:
        dest = Path(args.output) if args.output else Path(args.path).with_suffix(
            Path(args.path).suffix + ".clean"
        )
        dest.write_text(cleaned, encoding="utf-8")
        dest_label = str(dest)
    else:
        sys.stdout.write(cleaned)
        dest_label = "stdout"

    found = report["before"]["suspicious_total"] > 0 or args.paraphrase
    if (args.rewrite or args.translate or args.paraphrase) and not args.quiet:
        import re as _re

        if _re.search(r"```.*?```", cleaned, _re.S):
            print(
                "  ! code blocks pass through unchanged: any watermark tokens "
                "inside fenced code survive. Copy code sections manually if needed.",
                file=sys.stderr,
            )
    if not args.quiet:
        if args.json:
            report["src"] = src_label
            report["dest"] = dest_label
            print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        else:
            b = report["before"]["suspicious_total"]
            print(
                f"dewatermark: {src_label} -> {dest_label} | "
                f"stego_hits={b} removed={sum(report['removed'].values())} "
                f"mapped={sum(report['mapped'].values())} "
                f"chars {report['chars_in']}->{report['chars_out']}"
                + (
                    f" | paraphrase={report.get('paraphrase')}"
                    if args.paraphrase
                    else ""
                ),
                file=sys.stderr,
            )
            if b and report["before"]["by_type"]:
                top = list(report["before"]["by_type"].items())[:8]
                for k, v in top:
                    print(f"  - {k}: {v}", file=sys.stderr)
            if not args.paraphrase:
                print(
                    "  ! unicode layer only - Claude/GPT model-level marks are statistical,"
                    " not character-based. Use --paraphrase to break them.",
                    file=sys.stderr,
                )

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
