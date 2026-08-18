"""PDF backend: split, render, compose.

Most of the source material is PowerPoint exported to PDF, and PDF is the easier
format to work with here — page extraction and merging are lossless by
construction, so none of the master/theme surgery the PPTX path needs applies.
A composed deck is byte-for-byte the pages it was built from.

Pages are never materialised as individual files. A page is a reference into its
archived source document, and composing pulls the page straight out of that
original. Writing one PDF per page instead would copy every shared font and image
into each of them: measured on this material, 28 MB of source decks became 150 MB
of page files, for no gain at all — `insert_pdf` reads any page of the original
just as cheaply.

Text comes out of the page's own text layer, so no OCR and no vision model is
needed to read a page. That matters for tagging: it stays cheap, and pages never
have to leave the machine to be classified.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf


@dataclass
class PdfPage:
    index: int
    png_path: Path | None
    text: str
    lines: list[str] = field(default_factory=list)
    title: str = ""
    word_count: int = 0
    image_count: int = 0
    text_area_ratio: float = 0.0
    media_sha: list[str] = field(default_factory=list)


def doc_title(src: Path) -> str:
    with pymupdf.open(str(src)) as doc:
        return ((doc.metadata or {}).get("title") or "").strip()


def _page_title(lines: list[str]) -> str:
    """First substantive line. Slide titles are short and sit at the top; page
    numbers and boilerplate are filtered out so they never become the title."""
    for line in lines:
        clean = line.strip()
        if len(clean) < 2 or clean.isdigit():
            continue
        if re.fullmatch(r"[\d\s./|-]+", clean):
            continue
        return clean[:80]
    return ""


def split(src: Path, out_dir: Path, thumb_width: int = 480,
          render: bool = True) -> list[PdfPage]:
    """Read every page: text, a thumbnail, and the signals used for tagging."""
    src, out_dir = Path(src), Path(out_dir)
    thumbs_dir = out_dir / "thumbs"
    if render:
        thumbs_dir.mkdir(parents=True, exist_ok=True)

    records: list[PdfPage] = []
    with pymupdf.open(str(src)) as doc:
        for i in range(doc.page_count):
            page = doc[i]
            raw = page.get_text()
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

            thumb = None
            if render:
                # Scale to a fixed width and write JPEG: these are browsing
                # thumbnails, and the slides are photo-heavy, so PNG at print
                # resolution costs ~15x the bytes for no visible benefit.
                thumb = thumbs_dir / ("p%03d.jpg" % (i + 1))
                zoom = thumb_width / page.rect.width
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                pix.pil_save(str(thumb), format="JPEG", quality=82, optimize=True)

            area = abs(page.rect.width * page.rect.height) or 1.0
            text_area = sum(abs(b[2] - b[0]) * abs(b[3] - b[1])
                            for b in page.get_text("blocks") if len(b) > 4)

            shas = []
            for img in page.get_images(full=True):
                try:
                    shas.append(hashlib.sha256(
                        doc.extract_image(img[0])["image"]).hexdigest())
                except Exception:
                    pass

            records.append(PdfPage(
                index=i + 1, png_path=thumb, text=raw.strip(),
                lines=lines, title=_page_title(lines),
                word_count=len(raw.split()), image_count=len(page.get_images()),
                text_area_ratio=round(min(text_area / area, 1.0), 3),
                media_sha=shas,
            ))
    return records


def compose(refs, out_path: Path, title: str = "", subject: str = "") -> int:
    """Build a PDF from `(source_path, page_index)` references, in order.

    Lossless: pages are copied out of their originals, never re-rendered. Source
    documents are opened once and reused, so picking twenty pages out of one deck
    costs one open, not twenty.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    opened: dict[str, pymupdf.Document] = {}
    written = 0
    try:
        with pymupdf.open() as out:
            for source, page_index in refs:
                key = str(source)
                if key not in opened:
                    opened[key] = pymupdf.open(key)
                src = opened[key]
                if not 1 <= page_index <= src.page_count:
                    raise ValueError("%s has no page %d" % (key, page_index))
                out.insert_pdf(src, from_page=page_index - 1, to_page=page_index - 1)
                written += 1
            out.set_metadata({"title": title, "subject": subject,
                              "producer": "slidehub"})
            out.save(str(out_path), garbage=4, deflate=True)
    finally:
        for doc in opened.values():
            doc.close()
    return written
