"""Generate the tagging workbench — a live document people edit together.

The page ships every card and every tag as real HTML. That is not a stylistic
choice: in a live document the markup *is* the shared document, and only changes
a person's own click or keystroke makes to it are saved. Content rendered into a
synced region by script at load time is not saved at all — worse, it switches
syncing off for that view, because otherwise one viewer's render would be written
once per open browser.

So Python authors the document, and the page's JavaScript only ever mutates it
inside event handlers. Anything that is one viewer's own business — filtering,
selection, search — is kept on `data-local-*` attributes, which never leave the
view they happen in.
"""
from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

from PIL import Image

TEMPLATE = Path(__file__).resolve().parent / "templates" / "workbench.html"
LOW_TITLE_CONFIDENCE = 0.5


def _thumb(path: str, width: int, quality: int = 68) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def _directory_html(categories: list[dict]) -> str:
    out = []
    for cat in categories:
        # Must stay in step with tagLi() in the template: the page appends new
        # tags with that builder, and a mismatch would leave half the directory
        # missing its controls.
        tags = "".join(
            '<li class="tag" data-tag="{id}" data-local-filter="0" data-local-brush="0">'
            '<button class="brush" data-act="brush" title="选为当前标签">✎</button>'
            '<span class="tname" contenteditable="true" spellcheck="false">{name}</span>'
            '<button class="mini" data-act="filter" title="按此标签筛选">◎</button>'
            '<button class="mini del" data-act="deltag" title="删除标签">×</button>'
            "</li>".format(id=html.escape(t["id"]), name=html.escape(t["name"]))
            for t in cat["tags"]
        )
        if not tags:
            tags = '<li class="emptytags">还没有标签，点 + 新增</li>'
        out.append(
            '<li class="cat" data-cat="{cid}" data-multi="{multi}">'
            '<div class="chead">'
            '<span class="cname" contenteditable="true" spellcheck="false">{cname}</span>'
            '<button class="multi" data-act="multi" title="切换单选/多选"></button>'
            '<button class="mini" data-act="addtag" title="新增标签">+</button>'
            '<button class="mini del" data-act="delcat" title="删除类别">×</button>'
            "</div>"
            '<ul class="tlist">{tags}</ul></li>'.format(
                cid=html.escape(cat["id"]), multi="1" if cat.get("multi", True) else "0",
                cname=html.escape(cat["name"]), tags=tags)
        )
    return "".join(out)


def _cards_html(pages: list[dict], tag_names: dict, width: int,
                clusters: list[dict]) -> str:
    reason = {}
    order = {}
    for n, cluster in enumerate(clusters, start=1):
        for m, uid in enumerate(cluster["members"]):
            reason[uid] = cluster["reason"]
            order[uid] = n * 100 + m

    out = []
    for page in pages:
        thumb = ""
        if page.get("png") and Path(page["png"]).exists():
            thumb = ('<img loading="lazy" alt="" src="data:image/jpeg;base64,%s">'
                     % _thumb(page["png"], width))
        chips = "".join(
            '<span class="tg" data-tag="{id}"><span class="n">{name}</span>'
            '<button class="x" data-act="untag" title="移除">×</button></span>'.format(
                id=html.escape(t), name=html.escape(tag_names.get(t, t)))
            for t in page.get("tags", [])
        )
        low = page.get("title_confidence", 1.0) < LOW_TITLE_CONFIDENCE
        uid = page["uid"]
        dup = page.get("dup_cluster", "")
        dupbar = ""
        if dup:
            dupbar = (
                '<div class="dupbar"><span class="why">{why}</span>'
                '<button class="dbtn keep" data-act="decide" data-decision="keep">保留</button>'
                '<button class="dbtn drop" data-act="decide" data-decision="drop">标记删除</button>'
                "</div>".format(why=html.escape(reason.get(uid, "相似页"))))
        out.append(
            '<article class="card" data-uid="{uid}" data-doc="{doc}" data-conf="{conf}"'
            ' data-dup="{dup}" data-dup-order="{order}"'
            ' data-local-hidden="0" data-local-has="0" data-local-deck="">'
            '<div class="thumb">{thumb}<span class="uid">{uid}</span>'
            '<span class="flag title">标题待确认</span>'
            '<span class="flag titleok">标题已确认</span>'
            '<span class="flag dup">相似页</span>'
            '<span class="flag kept">已保留</span>'
            '<span class="flag dropped">已标记删除</span></div>'
            "<artifact-sync><div class=\"cardbody\">"
            '<span class="ttl" contenteditable="true" spellcheck="false">{title}</span>'
            '<div class="chips">{chips}</div>'
            '<span class="state" data-decision="{decision}" data-title="{titleok}"></span>'
            "</div></artifact-sync>{dupbar}</article>".format(
                uid=html.escape(uid), doc=html.escape(page["doc"]),
                conf="low" if low else "ok", thumb=thumb,
                dup=html.escape(dup), order=order.get(uid, 0),
                decision=html.escape(page.get("dup_decision", "")),
                titleok="ok" if page.get("title_confirmed") else "",
                title=html.escape(page.get("title") or ""), chips=chips,
                dupbar=dupbar)
        )
    return "".join(out)


def build(index: dict, out_html: Path, thumb_width: int = 340) -> Path:
    categories = index.get("categories", [])
    tag_names = {t["id"]: t["name"] for c in categories for t in c["tags"]}
    clusters = index.get("duplicates", [])
    meta = {"builtAt": index.get("built_at", ""),
            "duplicateCount": len(clusters),
            "docs": [{"id": d["id"], "title": d["title"], "pages": d["pages"]}
                     for d in index["docs"]]}

    html_text = TEMPLATE.read_text(encoding="utf-8")
    html_text = html_text.replace("<!--__DIRECTORY__-->", _directory_html(categories))
    html_text = html_text.replace(
        "<!--__CARDS__-->",
        _cards_html(index["pages"], tag_names, thumb_width, clusters))
    html_text = html_text.replace(
        "/*__META__*/null", json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))

    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html_text, encoding="utf-8")
    return out_html
