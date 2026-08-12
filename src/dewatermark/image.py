"""Image provenance stripping — C2PA / XMP / EXIF removal via clean re-encode.

Optional dependency: Pillow (``pip install dewatermark[image]``).
"""
from __future__ import annotations

from pathlib import Path

from .core import KEEP_CONTROLS  # noqa: F401  (re-export convenience)


def strip_image_provenance(path: Path, out: Path | None = None) -> dict:
    """Re-encode image pixels only, dropping C2PA/XMP/EXIF/ICC containers.

    This is the reliable path for C2PA manifest removal — matches
    Anthropic's own documented limitation that re-saving/conversion
    strips provenance metadata.

    Args:
        path: Source image (.png/.jpg/.jpeg/.svg-png).
        out:  Optional output path; defaults to ``<stem>.clean<ext>``.

    Returns:
        Dict with status, paths, and optional c2patool verification.
    """
    try:
        from PIL import Image
    except ImportError:
        return {
            "ok": False,
            "error": "Pillow not installed. pip install dewatermark[image]",
        }

    path = Path(path)
    img = Image.open(path)
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)

    dest = out or path.with_name(path.stem + ".clean" + path.suffix)
    save_kwargs: dict = {}
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        save_kwargs = {"quality": 95, "optimize": True}
        clean = clean.convert("RGB")
    elif ext == ".png":
        save_kwargs = {"optimize": True}
    clean.save(dest, **save_kwargs)

    c2pa_note = None
    import shutil
    import subprocess
    if shutil.which("c2patool"):
        r = subprocess.run(
            ["c2patool", str(dest)], capture_output=True, text=True
        )
        c2pa_note = (
            "present" if "claim" in r.stdout.lower() or "title" in r.stdout.lower()
            else "absent-or-unreadable"
        )

    return {
        "ok": True,
        "src": str(path),
        "dest": str(dest),
        "format": ext,
        "c2pa": c2pa_note,
        "note": "Pixels re-encoded; EXIF/XMP/C2PA containers dropped.",
    }
