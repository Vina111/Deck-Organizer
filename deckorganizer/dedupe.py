"""Find pages that are the same page.

Across a shelf of proposal decks the same case is restated again and again —
sometimes byte-identical, sometimes re-laid-out, sometimes with a year updated.
Those are not separate assets; they are versions of one, and only one of them
should go to a client.

Nothing is deleted here. The clusters are a *proposal*: a person looks at the
pages side by side and decides which to keep. Automatic deletion is the one
mistake that cannot be undone from the UI, so it is not offered.
"""
from __future__ import annotations

from .fingerprint import hamming, similarity

IDENTICAL_TEXT = 0.995     # same words, allowing for a stray glyph
STRONG_TEXT = 0.90         # same case, restated
WEAK_TEXT = 0.80           # same case, edited — needs visual agreement too
VISUAL_NEAR = 12           # bits of a 64-bit perceptual hash
VISUAL_SAME = 5            # near-identical rendering
MIN_TEXT_CHARS = 24        # below this, text similarity is noise


THIN_TEXT_AGREE = 0.85     # short text still has to agree, not just the layout


def _reason(sim: float, dist: int, thin: bool, both_blank: bool) -> str | None:
    if thin:
        # Layout alone is not evidence here. Section dividers all share one
        # template and carry only a few characters, so a visual-only rule filed
        # "01 产品传播案例" and "02 企业传播案例" as the same page.
        if dist > VISUAL_SAME:
            return None
        if both_blank:
            return "版面几乎相同（页面无文字）"
        return "版面几乎相同且文字一致" if sim >= THIN_TEXT_AGREE else None
    if sim >= IDENTICAL_TEXT:
        return "文字完全一致"
    if sim >= STRONG_TEXT:
        return "文字高度相同（%.0f%%）" % (sim * 100)
    if sim >= WEAK_TEXT and dist <= VISUAL_NEAR:
        return "文字相近（%.0f%%）且版面接近" % (sim * 100)
    if dist <= VISUAL_SAME and sim >= 0.5:
        return "版面几乎相同"
    return None


def find(pages: list[dict]) -> list[dict]:
    """Cluster pages that look like versions of one another."""
    n = len(pages)
    parent = list(range(n))
    evidence: dict[tuple[int, int], str] = {}

    def find_root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find_root(i), find_root(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = pages[i], pages[j]
            thin = (len(a.get("text", "")) < MIN_TEXT_CHARS
                    or len(b.get("text", "")) < MIN_TEXT_CHARS)
            dist = (hamming(a.get("dhash", 0), b.get("dhash", 0))
                    if a.get("dhash") and b.get("dhash") else 64)
            sim = 1.0 if (a.get("text_hash") and a["text_hash"] == b["text_hash"]
                          and not thin) else similarity(a.get("text", ""), b.get("text", ""))
            both_blank = not a.get("text", "").strip() and not b.get("text", "").strip()
            why = _reason(sim, dist, thin, both_blank)
            if why:
                union(i, j)
                evidence[(i, j)] = why

    grouped: dict[int, list[int]] = {}
    for i in range(n):
        grouped.setdefault(find_root(i), []).append(i)

    clusters = []
    for root, members in sorted(grouped.items()):
        if len(members) < 2:
            continue
        cid = "d%02d" % (len(clusters) + 1)
        why = next((evidence[k] for k in evidence
                    if k[0] in members and k[1] in members), "相似")
        # Suggest keeping the page from the deck that carries the most of this
        # cluster — usually the master deck rather than a one-off extract.
        by_doc: dict[str, int] = {}
        for i in members:
            by_doc[pages[i]["doc"]] = by_doc.get(pages[i]["doc"], 0) + 1
        for i in members:
            pages[i]["dup_cluster"] = cid
        clusters.append({
            "id": cid,
            "reason": why,
            "members": [pages[i]["uid"] for i in members],
            "suggested_keep": pages[members[0]]["uid"],
        })
    return clusters
