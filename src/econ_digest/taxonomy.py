"""Article kinds, Taiwanese report labels, and summary-depth policy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import TiersConfig

KINDS = (
    "article", "leader", "briefing", "column", "by_invitation", "letters",
    "obituary", "world_politics", "world_business", "cartoon", "indicators",
)
CATEGORIES = {
    "intl.us": "美國",
    "intl.china": "中國（含港澳）",
    "intl.asia": "亞太（日韓、北韓、東南亞、南亞、澳紐、太平洋島國）",
    "intl.europe": "歐洲（含英國、俄烏）",
    "intl.other": "其他地區與全球議題（美洲、中東、非洲、跨國議題）",
    "finance": "財經商業",
    "tech": "科技",
    "science": "科學",
    "culture": "文化生活（書評、藝術、影視、體育、生活、訃聞）",
}
CATEGORY_SHORT_LABELS = dict(zip(CATEGORIES, (
    "美國", "中國", "亞太", "歐洲", "其他地區", "財經商業", "科技", "科學", "文化生活",
)))
SHORT_CATEGORY_LABELS = CATEGORY_SHORT_LABELS
TAIWAN_LEVELS = {1: "台灣本身", 2: "台灣與國際", 3: "間接相關"}
TAIWAN_LEVEL_DEFINITIONS = {
    1: "台灣是報導的主要主題。",
    2: "台灣是國際事件的主要參與者之一，例如台美關係、兩岸、台積電與晶片供應鏈或邦交國。",
    3: "台灣並非主要參與者，但報導實質提及台灣，或議題對台灣有重大影響。",
}
TIERS = {
    "A": "深度解析", "B": "詳細摘要", "C": "重點摘要", "D": "簡要摘要", "E": "一句話",
    "merged": "合併社論", "brief": "本週要聞", "skip": "略過",
}
TIER_ORDER = ("A", "B", "C", "D", "E")
COLUMN_NAMES = (
    "Lexington", "Bagehot", "Charlemagne", "Chaguan", "Banyan", "Bello",
    "Schumpeter", "Bartleby", "Buttonwood", "Free exchange", "The Telegram",
    "Back Story", "Johnson", "Well Informed", "The Economist explains", "By the numbers",
)


def derive_kind(section: str, title: str, fly_title: str | None) -> str:
    section_key = section.strip().casefold()
    title_key = title.strip().casefold()
    if section_key == "the world this week":
        return {"politics": "world_politics", "business": "world_business"}.get(title_key, "cartoon")
    special = {
        "leaders": "leader", "briefing": "briefing", "by invitation": "by_invitation",
        "letters": "letters", "obituary": "obituary", "economic & financial indicators": "indicators",
    }
    if section_key in special:
        return special[section_key]
    if fly_title and fly_title.strip().casefold() in {name.casefold() for name in COLUMN_NAMES}:
        return "column"
    return "article"


def assign_tier(
    kind: str, taiwan_level: int, category: str, has_companion: bool, tiers_cfg: TiersConfig,
) -> str:
    if kind in ("cartoon", "indicators"):
        return "skip"
    if kind in ("world_politics", "world_business"):
        return "brief"
    if kind == "leader" and has_companion:
        return "merged"
    if kind in tiers_cfg.force_tier_by_kind:
        return tiers_cfg.force_tier_by_kind[kind]
    tier = tiers_cfg.taiwan.get(str(taiwan_level), tiers_cfg.category.get(category, "E"))
    minimum = tiers_cfg.min_tier_by_kind.get(kind)
    if minimum and TIER_ORDER.index(minimum) < TIER_ORDER.index(tier):
        tier = minimum
    return tier
