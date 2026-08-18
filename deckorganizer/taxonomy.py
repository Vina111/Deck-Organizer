"""The tag directory: categories, and the tags inside them.

Categories and tags are *data*, not code. Nothing here is fixed — every category
and tag can be renamed, added or deleted in the workbench, and the starting set
below is only a first draft to save typing on the first pass.

Pages import with no tags at all. Tagging is a decision about a case, and the
page text does not reliably support it: the same words appear in a case study,
in a capability slide describing that service, and in a section divider. What a
dictionary can extract is what a page *mentions*, which is not what a page *is*.
"""
from __future__ import annotations

# Starting draft. Categories the user named come first; the tags under them are
# drawn from what the imported decks actually contain, so the first tagging pass
# is mostly clicking rather than typing.
STARTER = [
    {"name": "案例年份", "multi": False, "tags": [
        "2021", "2022", "2023", "2024", "2025", "2026"]},
    {"name": "案例地区", "multi": True, "tags": [
        "北美", "加拿大", "欧洲", "中东", "东南亚", "日韩", "非洲", "澳洲",
        "南美", "中国", "全球"]},
    {"name": "案例行业", "multi": True, "tags": [
        "AI与大模型", "机器人", "AR/AI眼镜", "消费电子与智能硬件", "新能源与储能",
        "汽车与出行", "家电与家居", "医疗与生物科技", "金融", "母婴与个护",
        "宠物", "餐饮与食品", "工业与B2B", "文化与内容"]},
    {"name": "案例服务分类", "multi": True, "tags": [
        "展会传播", "媒体活动与发布会", "媒体关系与Pitch", "新闻稿与通稿发布",
        "KOL与达人", "社交媒体运维", "内容与物料制作", "视频与拍摄",
        "危机与舆情", "品牌本地化基建", "CSR与公共事务", "雇主品牌与招聘",
        "培训与咨询", "调研"]},
    {"name": "展会节点", "multi": True, "tags": [
        "CES", "IFA", "MWC", "NVIDIA GTC", "RE+", "GDC", "KBIS", "WEF 达沃斯",
        "COP28", "Global Connect Show"]},
    {"name": "客户", "multi": True, "tags": []},
    {"name": "页型", "multi": False, "tags": [
        "封面", "目录", "过渡页", "正文", "正文续页", "封底"]},
]


def starter() -> list[dict]:
    """Materialise the draft with stable ids."""
    categories = []
    tag_seq = 0
    for n, spec in enumerate(STARTER, start=1):
        tags = []
        for name in spec["tags"]:
            tag_seq += 1
            tags.append({"id": "t%03d" % tag_seq, "name": name})
        categories.append({
            "id": "c%02d" % n, "name": spec["name"],
            "multi": spec["multi"], "tags": tags,
        })
    return categories
