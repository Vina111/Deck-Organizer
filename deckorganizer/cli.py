"""deck-organizer — import decks, tag pages by hand, compose new decks.

    python3 -m deckorganizer import  你的*.pdf --out library
    python3 -m deckorganizer build   --library library --out workbench.html
    python3 -m deckorganizer apply   --library library --edits export.json
    python3 -m deckorganizer search  --library library --tag 北美 --tag CES
    python3 -m deckorganizer compose --library library --pages "A:6,B:25" --out 新案例.pdf
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import catalog, pdfdoc, workbench


def _rule(title: str = "") -> None:
    print("\n" + (" %s " % title).center(72, "=") if title else "=" * 72)


def cmd_import(args) -> int:
    print("importing %d deck(s)" % len(args.sources))
    index = catalog.build([Path(s) for s in args.sources], Path(args.out),
                          thumb_width=args.thumb_width)
    weak = [p for p in index["pages"] if p["title_confidence"] < 0.5]
    _rule("imported")
    print("  %d pages, all untagged — tagging happens in the workbench"
          % len(index["pages"]))
    print("  %d page titles are uncertain and worth checking first:" % len(weak))
    for page in weak[:12]:
        print("    %-6s %.2f  %s" % (page["uid"], page["title_confidence"],
                                     (page["title"] or "(空)")[:52]))
    print("\n  next:  python3 -m deckorganizer build --library %s" % args.out)
    return 0


def cmd_build(args) -> int:
    index = catalog.load(Path(args.library))
    out = workbench.build(index, Path(args.out), thumb_width=args.thumb_width)
    size = out.stat().st_size / 1e6
    print("workbench -> %s  (%.1f MB, %d pages, %d categories)"
          % (out, size, len(index["pages"]), len(index["categories"])))
    return 0


def cmd_apply(args) -> int:
    index = catalog.load(Path(args.library))
    edits = json.loads(Path(args.edits).read_text(encoding="utf-8"))
    catalog.apply_edits(index, edits)
    catalog.save(Path(args.library), index)
    tagged = sum(1 for p in index["pages"] if p["tags"])
    print("applied edits to %d pages" % index.pop("_touched", 0))
    print("  %d / %d pages now carry at least one tag"
          % (tagged, len(index["pages"])))
    print("  %d categories, %d tags in the directory"
          % (len(index["categories"]),
             sum(len(c["tags"]) for c in index["categories"])))
    return 0


def _tag_names(index: dict) -> dict:
    return {t["id"]: t["name"] for c in index["categories"] for t in c["tags"]}


def cmd_search(args) -> int:
    index = catalog.load(Path(args.library))
    names = _tag_names(index)
    wanted = [w.lower() for w in (args.tag or [])]
    terms = [t.lower() for t in args.query]

    hits = []
    for page in index["pages"]:
        labels = [names.get(t, t).lower() for t in page["tags"]]
        if wanted and not all(any(w in l for l in labels) for w in wanted):
            continue
        blob = ("%s %s %s" % (page["title"], page["note"],
                              " ".join(labels))).lower()
        if terms and not all(t in blob for t in terms):
            continue
        hits.append(page)

    print("%d / %d pages match" % (len(hits), len(index["pages"])))
    for page in hits[:args.limit]:
        labels = [names.get(t, t) for t in page["tags"]]
        print("  %-6s %-44s %s" % (page["uid"], (page["title"] or "(无标题)")[:44],
                                   " · ".join(labels[:5]) or "(未打标签)"))
    if len(hits) > args.limit:
        print("  ... %d more" % (len(hits) - args.limit))
    return 0


def cmd_compose(args) -> int:
    library = Path(args.library)
    index = catalog.load(library)
    by_uid = {p["uid"]: p for p in index["pages"]}
    by_doc = {d["id"]: d["file"] for d in index["docs"]}

    uids = [u.strip() for u in args.pages.split(",") if u.strip()]
    missing = [u for u in uids if u not in by_uid]
    if missing:
        print("unknown page(s): %s" % ", ".join(missing), file=sys.stderr)
        return 2

    dropped = [u for u in uids if by_uid[u].get("dup_decision") == "drop"]
    if dropped:
        # Say it rather than silently removing the page: the person picking
        # pages may well know something the duplicate review did not.
        print("注意：以下页在查重中被标记删除，仍会包含在内 —— %s"
              % ", ".join(dropped), file=sys.stderr)

    refs = [(by_doc[by_uid[u]["doc"]], by_uid[u]["index"]) for u in uids]
    written = pdfdoc.compose(refs, Path(args.out),
                             title=args.title or Path(args.out).stem)

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for uid in set(uids):
        by_uid[uid]["last_used"] = stamp
        by_uid[uid]["use_count"] = by_uid[uid].get("use_count", 0) + 1
    index.setdefault("exports", []).append({
        "at": stamp, "out": str(args.out),
        "title": args.title or Path(args.out).stem, "pages": uids})
    catalog.save(library, index)

    print("composed %d pages -> %s" % (written, args.out))
    for n, uid in enumerate(uids, start=1):
        print("  %2d. %-6s %s" % (n, uid, (by_uid[uid]["title"] or "")[:54]))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="deckorganizer", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="import decks page by page (no tagging)")
    p.add_argument("sources", nargs="+")
    p.add_argument("--out", default="library")
    p.add_argument("--thumb-width", type=int, default=480)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("build", help="generate the tagging workbench page")
    p.add_argument("--library", default="library")
    p.add_argument("--out", default="workbench.html")
    p.add_argument("--thumb-width", type=int, default=340)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("apply", help="merge workbench edits back into the library")
    p.add_argument("--library", default="library")
    p.add_argument("--edits", required=True)
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("search", help="search the library")
    p.add_argument("query", nargs="*", default=[])
    p.add_argument("--library", default="library")
    p.add_argument("--tag", action="append", help="repeatable; all must match")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("compose", help="build a new PDF from chosen pages")
    p.add_argument("--library", default="library")
    p.add_argument("--pages", required=True)
    p.add_argument("--out", default="composed.pdf")
    p.add_argument("--title", default="")
    p.set_defaults(func=cmd_compose)

    args = ap.parse_args(argv)
    return args.func(args)
