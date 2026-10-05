"""A cached batched Chinese editing pass with field-by-field safe fallback."""

from __future__ import annotations

import re
from typing import Any

from ..config import Config
from ..models import ArticleSummary, Classification, Issue, WeekBrief
from ..zhtw import normalize_zh_tw
from .cache import UnitRunner
from .prompts import Unit, make_unit, prompt_json, split_units
from .validation import chinese_length

# Known named entities are checked as complete strings, including common
# abbreviations; the character gate below conservatively catches unfamiliar names.
_NAMES = tuple("川普 特朗普 普丁 習近平 賴清德 澤倫斯基 馬克宏 施凱爾 梅爾茨 納坦雅胡 莫迪 金正恩 高市早苗 卓榮泰 林佳龍 顧立雄 韓國瑜 黃國昌 蕭美琴 輝達 台積電 聯發科 鴻海 美國 中國 台灣 臺灣 日本 南韓 北韓 俄羅斯 烏克蘭 法國 英國 德國 印度 巴西 巴拉圭 海地 瓜地馬拉 貝里斯 墨西哥 芬蘭 以色列 伊朗 伊拉克 葉門 歐盟 北約 菲律賓 加拿大 澳洲 紐西蘭 新加坡 馬來西亞 印尼 泰國 越南 北京 上海 香港 白宮 東京 華府 鹿兒島 宏都拉斯 尼加拉瓜 諾魯 教廷 史瓦帝尼 帛琉 吐瓦魯".split())
_ALIASES = {"美國": ("America", "American", "United States", "US", "U.S.", "USA"),
            "中國": ("China", "Chinese", "PRC"), "台灣": ("Taiwan", "Taiwanese"),
            "日本": ("Japan", "Japanese"), "北韓": ("North Korea",), "南韓": ("South Korea",),
            "台積電": ("TSMC", "Taiwan Semiconductor"), "輝達": ("Nvidia",),
            "川普": ("Trump",), "金正恩": ("Kim Jong Un",), "法國": ("France", "French"),
            "芬蘭": ("Finland", "Finnish"), "印度": ("India", "Indian")}
_STYLE_CHARS = set("新聞民調研究報告經濟學人專欄立場作者主張指出分析認為首度首次創下新高低成長降低增加減少擴大縮小差距超越勝過偏好轉向改變變化政策政府國家企業產業市場商業金融貿易關稅出口進口供應鏈晶片半導體人工智慧科技資訊網路軟體發展安全軍事危機熱線通話溝通接聽應變機制缺乏互信建立盼擬恐將未仍已正再更最不無有是對在的與和及或因但使讓於從由為以到了中上下前後內外本此這其個多少兩各新舊大大小強弱難易快慢短長支持反對批評爭取抵禦防堵抗衡展現彰顯冷淡態度拒絕願意回應合作衝突爭議威脅成本壓力財政赤字紀律債券借貸殖利率攀升動盪政治民主選舉選民信仰宗教溫和保守左左右右派基本盤裂痕競爭翻身迎來挑戰問題機會機遇文化傳統節慶宣傳形象統戰影響全球世界國際區域地區地方首長中央市政廳堡壘防線公益慈善援助資金體系採訪記者團改革制度方案計畫措施活動會談峰會能源用電核廢料深層處置封存茶農抹茶增產低價反補貼課稅揚言祭報復軍艦商船空襲據點釀襲控遭獲拚揭陷飆示警反攻重挫破億萬千百十年月份日票席人元幣美元比例百分比程度數據結構原因結果核心關鍵最重要結論方案評估調整成局隱患埋變數平衡秩序歐洲美洲亞洲拉美中東非洲海空首座熱潮新貴底首次時刻面臨路徑供給需求短缺流行遊戲娛樂健身體育科學健康醫療環境生活藝術書籍影視電影音樂飲食旅遊運動森林工廠農業污染氣候暖化溫度燃料汽車電動車利率貸款負債房價勞工工作失業薪資物價價格通膨央行銀行投資債務償還退休儲蓄人口教育學校學生社會家庭夫婦兒童女人男性女性富豪貧富落差暴力犯罪法律法院判決規範限制管制解禁開放民主威權意識形態興起削弱保護徵收稅收收入支出預算削減制裁衰退萎縮風險效益繁榮效率生產銷售直言呼籲重返維持掌握樂觀悲觀看好反映爭奪備受質疑自動化霸權霸主忠誠力量崛起沒能能否可能可望須必需應該如何何處情勢局勢觀察動向焦點重點摘要" )
_ATTRIBUTIONS = {"經濟學人", "經濟學人專欄", "經濟學人立場", "民調", "研究", "報告", "分析"}


def _numbers(value: str) -> set[str]:
    result = {match.replace(",", "") for match in re.findall(r"\d[\d,]*(?:\.\d+)?", value)}
    digits = {**dict(zip("零一二三四五六七八九", range(10))), "兩": 2}
    for numeral in re.findall(r"[零一二兩三四五六七八九十百千]+(?=[萬億年月日人票席國倍成])", value):
        if not any(character in "十百千" for character in numeral):
            result.add(str(int("".join(str(digits[character]) for character in numeral))))
            continue
        total = current = 0
        for character in numeral:
            if character in digits:
                current = digits[character]
            else:
                total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[character]
                current = 0
        result.add(str(total + current))
    return result


def faithful_text(candidate: Any, inputs: dict[str, Any]) -> bool:
    if not isinstance(candidate, str) or not candidate.strip() or "社論" in candidate:
        return False
    source = "\n".join(normalize_zh_tw(str(value)) for key, value in inputs.items()
                       if key in {"title", "rubric", "title_zh", "headline_zh", "text_zh"} and value is not None)
    if not _numbers(candidate) <= _numbers(source):
        return False
    for name in _NAMES:
        if name in candidate and name not in source:
            aliases = _ALIASES.get(name, ())
            if not any(re.search(r"\b" + re.escape(alias) + r"\b", source, re.I) for alias in aliases):
                return False
    english = set(re.findall(r"[A-Za-z][A-Za-z'-]*", source.lower())) | {"ai"}
    if not set(re.findall(r"[A-Za-z][A-Za-z'-]*", candidate.lower())) <= english:
        return False
    # Rewriting may introduce ordinary editorial words; unfamiliar characters
    # (often a new proper name) are rejected, keeping the previous text.
    added = set(re.findall(r"[\u3400-\u9fff]", candidate)) - set(source) - _STYLE_CHARS
    return not added


def valid_title(candidate: Any, inputs: dict[str, Any]) -> bool:
    if not faithful_text(candidate, inputs) or not 8 <= chinese_length(candidate) <= 26:
        return False
    if any(mark in candidate for mark in "?？:,，/／;；") or candidate.count("：") > 1:
        return False
    if "：" in candidate:
        attribution, rest = candidate.split("：", 1)
        source = "\n".join(str(value) for value in inputs.values())
        named = attribution in _NAMES and attribution in source
        role = attribution.endswith(("總統", "總理", "財長", "部長", "官員", "學者")) and attribution in source
        if not rest.strip() or not (attribution in _ATTRIBUTIONS or named or role):
            return False
    return True


def editor_items(issue: Issue, classifications: dict[str, Classification],
                 summaries: dict[str, ArticleSummary], brief: WeekBrief | None) -> list[dict[str, Any]]:
    result = [{"id": article.id, "title": article.title, "rubric": article.rubric,
               "title_zh": classifications[article.id].title_zh,
               "headline_zh": summaries[article.id].headline_zh if article.id in summaries else None,
               "tier": classifications[article.id].tier}
              for article in issue.articles if article.id in classifications
              and classifications[article.id].tier not in {"brief", "skip"}]
    if brief:
        for group in ("politics", "business"):
            result.extend({"id": f"brief-{group}-{index}", "tier": "brief", "text_zh": item.text_zh}
                          for index, item in enumerate(getattr(brief, group)))
    return result


def edit_units(issue: Issue, classifications: dict[str, Classification], summaries: dict[str, ArticleSummary],
               brief: WeekBrief | None, config: Config) -> list[Unit]:
    def build(batch: list[dict[str, Any]]) -> Unit:
        ids = {item["id"] for item in batch}

        def validate(data: dict[str, Any]) -> None:
            items = data.get("items")
            if (not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
                    or any(not isinstance(item.get("id"), str) for item in items)
                    or len(items) != len(ids) or {item["id"] for item in items} != ids):
                raise ValueError("edit: each input id must occur exactly once")

        return make_unit("edit", issue.issue_date, sorted(ids), config.llm.models.edit, validate,
                         items=prompt_json(batch))

    return split_units(editor_items(issue, classifications, summaries, brief), build,
                       max_items=10000, max_bytes=60_000)


def apply_edits(data: dict[str, Any], inputs: list[dict[str, Any]], classifications: dict[str, Classification],
                summaries: dict[str, ArticleSummary], brief: WeekBrief | None) -> None:
    by_id = {item["id"]: item for item in inputs}
    for item in data["items"]:
        original = by_id[item["id"]]
        if original["tier"] == "brief" and brief:
            candidate = item.get("text_zh")
            if faithful_text(candidate, original) and 1 <= chinese_length(candidate) <= 80:
                _, group, index = item["id"].split("-")
                getattr(brief, group)[int(index)].text_zh = candidate
            continue
        identifier = item["id"]
        if valid_title(item.get("title_zh"), original):
            classifications[identifier].title_zh = item["title_zh"]
        headline = item.get("headline_zh")
        if (identifier in summaries and faithful_text(headline, original)
                and 1 <= chinese_length(headline) <= (85 if original["tier"] == "E" else 50)):
            summaries[identifier].headline_zh = headline


def edit_digest(issue: Issue, classifications: dict[str, Classification], summaries: dict[str, ArticleSummary],
                brief: WeekBrief | None, config: Config, runner: UnitRunner, warnings: list[str]) -> None:
    inputs = editor_items(issue, classifications, summaries, brief)
    for unit in edit_units(issue, classifications, summaries, brief, config):
        result = runner.run(unit)
        if result.data:
            apply_edits(result.data, inputs, classifications, summaries, brief)
        else:
            warnings.append("標題與要聞編修失敗，保留原文字。")
