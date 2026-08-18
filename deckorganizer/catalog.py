"""Import decks page by page.

Import records what is objectively on the page — its title, its thumbnail, where
it came from — and stops there. Tags are applied by a person in the workbench.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pymupdf

from . import dedupe, fingerprint, pdfdoc, taxonomy, titles


def build(sources, out_dir: Path, thumb_width: int = 480, log=print) -> dict:
    out_dir = Path(out_dir)
    archive = out_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)

    docs, pages = [], []
    started = time.time()

    for n, src in enumerate(sources):
        src = Path(src)
        doc_id = chr(ord("A") + n) if n < 26 else "D%d" % n
        kept = archive / ("%s.pdf" % doc_id)
        if kept.resolve() != src.resolve():
            shutil.copyfile(src, kept)

        doc_title = pdfdoc.doc_title(kept) or src.stem
        records = pdfdoc.split(kept, out_dir / doc_id, thumb_width=thumb_width)

        with pymupdf.open(str(kept)) as doc:
            heads = [titles.extract(doc[i]) for i in range(doc.page_count)]

        weak = sum(1 for _, c in heads if c < 0.5)
        log("  %s  %-40s %3d pages  (%d titles need a look)"
            % (doc_id, doc_title[:40], len(records), weak))

        docs.append({"id": doc_id, "title": doc_title, "file": str(kept),
                     "orig_name": src.name, "pages": len(records)})

        for rec in records:
            title, confidence = heads[rec.index - 1]
            pages.append({
                "uid": "%s:%d" % (doc_id, rec.index),
                "doc": doc_id, "doc_title": doc_title, "index": rec.index,
                "png": str(rec.png_path) if rec.png_path else "",
                "title": title,
                "title_confidence": confidence,
                "words": rec.word_count, "images": rec.image_count,
                "tags": [],                 # applied by hand in the workbench
                "note": "",
                # Kept for duplicate detection only. The page text is not shown
                # as a title and is never turned into tags.
                "text": rec.text,
                "text_hash": fingerprint.text_hash(rec.text),
                "dhash": fingerprint.dhash(rec.png_path) if rec.png_path else 0,
                "dup_cluster": "", "dup_decision": "",
                "last_used": None, "use_count": 0,
            })

    clusters = dedupe.find(pages)
    log("  duplicate check: %d clusters covering %d pages"
        % (len(clusters), sum(len(c["members"]) for c in clusters)))

    index = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "docs": docs, "pages": pages,
        "categories": taxonomy.starter(),
        "duplicates": clusters,
        "exports": [],
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    log("  imported %d pages from %d deck(s) in %.1fs — all untagged"
        % (len(pages), len(docs), time.time() - started))
    return index


def load(library: Path) -> dict:
    return json.loads((Path(library) / "index.json").read_text(encoding="utf-8"))


def save(library: Path, index: dict) -> None:
    (Path(library) / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


def apply_edits(index: dict, edits: dict) -> dict:
    """Merge an export from the workbench back into the library.

    The workbench is the place tagging happens, so it owns titles, tags and
    notes; everything else in the library (page order, thumbnails, provenance,
    usage) stays as the import left it.
    """
    if "categories" in edits:
        index["categories"] = edits["categories"]
    by_uid = {p["uid"]: p for p in index["pages"]}
    touched = 0
    for uid, patch in (edits.get("pages") or {}).items():
        page = by_uid.get(uid)
        if not page:
            continue
        for field in ("title", "tags", "note", "dup_decision"):
            if field in patch:
                page[field] = patch[field]
        touched += 1
    index["edits_applied_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    index["_touched"] = touched
    return index
