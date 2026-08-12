"""dewatermark — strip AI text watermarks, invisible Unicode steganography,
and file provenance marks.

Public API:
    from dewatermark import scan_text, scrub_text, heuristic_perturb
"""
from .core import scan_text, scrub_text, heuristic_perturb, external_paraphrase
from .image import strip_image_provenance

__version__ = "0.1.0"
__all__ = [
    "scan_text",
    "scrub_text",
    "heuristic_perturb",
    "external_paraphrase",
    "strip_image_provenance",
]
