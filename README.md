# dewatermark

Strip AI text watermarks, invisible Unicode steganography, and file provenance marks.

## Why

AI companies train on public data, then brand model output with imperceptible watermarks and signed metadata as if they own the resulting knowledge. This tool removes those marks from text and images you control.

## What it handles

| Layer | Mechanism | Beaten by |
|---|---|---|
| **Unicode stego** | ZWSP, ZWNJ, ZWJ, BOM, soft-hyphen, bidi controls, variation selectors, Unicode Tags, format/control chars, private-use | Character-level scrub |
| **Homoglyphs** | Cyrillic/Greek/fullwidth lookalikes | Confusable normalization + NFKC |
| **Exotic spaces** | NBSP, en/em/thin/hair, ideographic | Space normalization |
| **Statistical watermark** | Model-level logit biasing (Kirchenbauer-style, Claude Aug 2026) | `--paraphrase` heuristic or external rewrite |
| **File provenance** | C2PA signed manifests on PNG/JPG/SVG | `--image` clean re-encode |

## Install

```bash
# from source
git clone https://github.com/deandiego/dewatermark-py.git
cd dewatermark-py
pip install -e .

# with image support
pip install -e ".[image]"

# standalone binary (no Python needed on target)
pip install -e ".[build]"
pyinstaller scripts/build_binary.spec
# → dist/dewatermark
```

## Usage

```bash
# pipe (daily driver)
pbpaste | dewatermark | pbcopy

# clipboard round-trip
dewatermark --clip

# also break statistical/model-level marks
dewatermark --clip --paraphrase

# scan only (JSON report)
dewatermark --scan notes.txt

# file → file.clean
dewatermark notes.txt

# overwrite
dewatermark -i notes.txt

# image: kill C2PA/XMP/EXIF
dewatermark --image shot.png          # → shot.clean.png

# full report on stderr
dewatermark --json notes.txt
```

### External rewrite (stronger paraphrase)

For maximum statistical-watermark break, route through a non-watermarked model:

```bash
export DEWATERMARK_REWRITE_CMD='claude -p "Rewrite preserving meaning and structure:"'
# or any stdin→stdout rewriter
dewatermark --paraphrase input.txt
```

## Python API

```python
from dewatermark import scan_text, scrub_text, heuristic_perturb

# detect
report = scan_text(text)
print(report["by_type"])

# clean
cleaned, report = scrub_text(text)

# break statistical marks
perturbed = heuristic_perturb(cleaned)
```

## Distribution

### PyPI (when ready)
```bash
python -m build
twine upload dist/*
pip install dewatermark
```

### Standalone binary
```bash
pip install ".[build]"
pyinstaller scripts/build_binary.spec
scp dist/dewatermark teammate@host:~/bin/
```

## Limits

- Unicode scrub is complete for character-insertion stego.
- Claude's model-level mark **requires** `--paraphrase` or manual rewrite. Heuristic weakens it; `DEWATERMARK_REWRITE_CMD` through a non-watermarked model kills it.
- Short fragments have weak/no signal.
- Not for misrepresenting AI content as human where law or contract requires disclosure.

## License

MIT
