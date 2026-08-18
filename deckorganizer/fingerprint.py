"""Page fingerprints for duplicate detection.

Two independent signals, because neither alone is enough on this material:

  text        the same case restated in another deck keeps its wording while the
              layout drifts — a headline wraps differently, a logo moves
  perceptual  an image-heavy page with little text is identified by how it looks

Character bigrams, not word tokens: whitespace tokenisation collapses a whole
Chinese sentence into one token and every comparison then reads 0 or 1.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from PIL import Image

_PUNCT = re.compile(r"[\s　·。，、；：？！“”‘’（）《》〈〉【】…—\-_/\\|,.;:?!\"'()\[\]{}<>]+")


def normalize(text: str) -> str:
    return _PUNCT.sub("", unicodedata.normalize("NFKC", text or "").lower())


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def similarity(a: str, b: str) -> float:
    """Dice coefficient over character bigrams."""
    na, nb = normalize(a), normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if len(na) < 2 or len(nb) < 2:
        return 1.0 if na == nb else 0.0
    counts: dict[str, int] = {}
    for i in range(len(na) - 1):
        g = na[i:i + 2]
        counts[g] = counts.get(g, 0) + 1
    overlap = 0
    for i in range(len(nb) - 1):
        g = nb[i:i + 2]
        if counts.get(g, 0) > 0:
            counts[g] -= 1
            overlap += 1
    return 2.0 * overlap / ((len(na) - 1) + (len(nb) - 1))


def dhash(image_path, size: int = 8) -> int:
    with Image.open(image_path) as im:
        im = im.convert("L").resize((size + 1, size), Image.LANCZOS)
        px = list(im.getdata())
    bits = 0
    for row in range(size):
        base = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | int(px[base + col] > px[base + col + 1])
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
