"""Extract a slide's title — the heading, not the first line of prose.

Reading order is the wrong signal on a slide. A slide's title is set apart by
*size and position*: it is the largest text in the upper part of the page. Taking
the first non-empty line instead picks up whatever happens to sit highest in the
text stream, which on these decks is usually the opening sentence of the body
copy, sometimes truncated mid-word.

So the title is found the way a reader finds it: look at the top of the page,
take the text set noticeably larger than the body, and read it left to right.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

# Slide furniture that is large and high up but is not a title.
_NOISE = re.compile(
    r"^(第?\s*\d+\s*页?|\d{1,3}|[ivxlcIVXLC]+|page\s*\d+|\W{1,3})$", re.I)
_COLLAPSE = re.compile(r"\s+")

TOP_BAND = 0.55       # titles live in the upper half; allow a little slack
SIZE_LEAD = 1.12      # a title is at least this much larger than body text
LINE_TOL = 0.6        # spans within this fraction of a line height are one line
NEIGHBOUR_LEAD = 0.85 # an adjacent line joins the title if nearly as large
MIN_CHARS = 2
MAX_CHARS = 90
_DIGITS = re.compile(r"[\d.,%kKmMbB万亿+×]")


@dataclass
class Span:
    text: str
    size: float
    x: float
    y: float
    bold: bool


def _spans(page) -> list[Span]:
    out: list[Span] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                x0, y0, _, _ = span.get("bbox", (0, 0, 0, 0))
                out.append(Span(
                    text=text, size=round(span.get("size", 0), 1),
                    x=x0, y=y0,
                    bold=bool(span.get("flags", 0) & 2 ** 4),
                ))
    return out


def _body_size(spans: list[Span]) -> float:
    """The most common size, weighted by how much text is set in it — that is
    the body copy, and the yardstick a title has to beat."""
    weight: dict[float, int] = {}
    for span in spans:
        weight[span.size] = weight.get(span.size, 0) + len(span.text)
    if not weight:
        return 0.0
    return max(weight.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _lines(spans: list[Span], scale: float) -> list[dict]:
    """Cluster spans into visual lines by vertical position."""
    tolerance = max(scale * LINE_TOL, 2.0)
    lines: list[dict] = []
    for span in sorted(spans, key=lambda s: (s.y, s.x)):
        for line in lines:
            if abs(line["y"] - span.y) <= tolerance:
                line["spans"].append(span)
                line["max_size"] = max(line["max_size"], span.size)
                break
        else:
            lines.append({"y": span.y, "spans": [span], "max_size": span.size})
    for line in lines:
        line["spans"].sort(key=lambda s: s.x)
    return lines


def extract(page) -> tuple[str, float]:
    """Return (title, confidence 0-1)."""
    raw = _spans(page)
    if not raw:
        return "", 0.0

    height = page.rect.height or 1.0
    body = _body_size(raw)
    # Drop furniture only where it is actually furniture. A page number is set
    # at body size or smaller; a numeral set at title size is part of the title
    # ("我们服务的客户已超过500家" loses its point without the 500).
    spans = [s for s in raw if not (_NOISE.match(s.text) and s.size <= body)]
    if not spans:
        return "", 0.0
    top = [s for s in spans if s.y <= height * TOP_BAND]
    pool = top or spans

    biggest = max(s.size for s in pool)
    if body and biggest < body * SIZE_LEAD:
        # Nothing stands out. A slide with uniform type usually has no title at
        # all — a full-bleed image page, or a wall of body copy.
        if not any(s.size == biggest and s.bold for s in pool):
            return "", 0.2

    # Group into visual lines, then pick the line the largest text sits on and
    # take the WHOLE line. A title often mixes sizes within one line — a headline
    # figure set much larger than the words around it ("我们服务的客户已超过500家").
    # Taking only the largest spans keeps the number and drops the sentence.
    lines = _lines(pool, biggest)
    if not lines:
        return "", 0.2
    lead_index = max(range(len(lines)), key=lambda i: (lines[i]["max_size"], -lines[i]["y"]))
    chosen = [lines[lead_index]]

    # A title that wraps continues on the next line at the same weight.
    line_height = biggest * 1.6
    for step in (-1, 1):
        i = lead_index + step
        while 0 <= i < len(lines):
            gap = abs(lines[i]["y"] - chosen[-1 if step > 0 else 0]["y"])
            if gap > line_height or lines[i]["max_size"] < biggest * NEIGHBOUR_LEAD:
                break
            chosen.insert(0, lines[i]) if step < 0 else chosen.append(lines[i])
            i += step

    headline = [span for line in sorted(chosen, key=lambda l: l["y"])
                for span in line["spans"]]
    text = _COLLAPSE.sub(" ", " ".join(s.text for s in headline)).strip()
    text = text.strip("·|-—:：, ")

    if len(text) < MIN_CHARS:
        return "", 0.2

    lead = (biggest / body) if body else 1.0
    confidence = 0.9 if lead >= 1.5 else (0.75 if lead >= 1.25 else 0.5)
    if len(headline) > 6:
        confidence -= 0.2          # many fragments: probably not one clean title
    letters = _DIGITS.sub("", text).strip()
    if len(letters) < max(2, len(text) * 0.4):
        # Mostly figures: this is a results strip ("277M  17篇"), not a title.
        confidence -= 0.5
    if len(text) > 44:
        # A statement slide sets its whole sentence large. That is a legitimate
        # reading of the page, but it is a poor title, so say so.
        confidence -= 0.25
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "…"
    return text, round(max(confidence, 0.1), 2)


def extract_from_file(path, page_number: int) -> tuple[str, float]:
    with pymupdf.open(str(path)) as doc:
        return extract(doc[page_number - 1])
