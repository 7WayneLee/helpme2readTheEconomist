"""A cached batched Chinese editing pass with field-by-field safe fallback."""

from __future__ import annotations

import re
from typing import Any

from ..config import Config
from ..models import ArticleSummary, Classification, Issue, WeekBrief
from ..llm import run_parallel
from ..zhtw import normalize_zh_tw
from .cache import UnitRunner
from .prompts import Unit, make_unit, prompt_json, split_units, with_term_hints
from .validation import chinese_length, validate_headline

# Known named entities are checked as complete strings, including common
# abbreviations; transliteration and role checks below catch unfamiliar names.
_NAMES = tuple("川普 特朗普 普丁 習近平 賴清德 澤倫斯基 馬克宏 施凱爾 梅爾茨 納坦雅胡 莫迪 金正恩 高市早苗 卓榮泰 林佳龍 顧立雄 韓國瑜 黃國昌 蕭美琴 輝達 台積電 聯發科 鴻海 美國 中國 台灣 臺灣 日本 南韓 北韓 俄羅斯 烏克蘭 法國 英國 德國 印度 巴西 巴拉圭 海地 瓜地馬拉 貝里斯 墨西哥 芬蘭 以色列 伊朗 伊拉克 葉門 歐盟 北約 菲律賓 加拿大 澳洲 紐西蘭 新加坡 馬來西亞 印尼 泰國 越南 北京 上海 香港 白宮 東京 華府 鹿兒島 宏都拉斯 尼加拉瓜 諾魯 教廷 史瓦帝尼 帛琉 吐瓦魯".split())
_ALIASES = {"美國": ("America", "American", "United States", "US", "U.S.", "USA"),
            "中國": ("China", "Chinese", "PRC"), "台灣": ("Taiwan", "Taiwanese"),
            "日本": ("Japan", "Japanese"), "北韓": ("North Korea",), "南韓": ("South Korea",),
            "台積電": ("TSMC", "Taiwan Semiconductor"), "輝達": ("Nvidia",),
            "川普": ("Trump",), "金正恩": ("Kim Jong Un",), "法國": ("France", "French"),
            "芬蘭": ("Finland", "Finnish"), "印度": ("India", "Indian")}
# Transliteration characters are deliberately narrower than ordinary Chinese
# vocabulary. 柏 and 南 also cover common two-character foreign-name spellings.
_TRANSLITERATED_NAME = re.compile(
    r"[阿艾安奧巴貝比波伯布查達德迪杜多恩法菲弗福蓋格戈哈赫霍基吉加賈傑卡凱科克庫"
    r"拉萊蘭朗勞雷里利林魯倫羅洛馬麥曼梅米蒙莫默穆納尼紐諾歐帕佩皮普齊奇喬薩塞桑"
    r"森沙史斯蘇索塔泰坦特提湯圖托瓦威韋維溫沃烏西希謝辛雅亞耶伊尤約澤扎詹柏南]{2,}"
)
_NAME_WITH_ROLE = re.compile(r"([\u3400-\u9fff]{2,4})(先生|女士|總統|總理|部長|執行長|主席)")
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
    candidate = normalize_zh_tw(candidate)
    source = "\n".join(normalize_zh_tw(str(value)) for key, value in inputs.items()
                       if key in {"title", "rubric", "title_zh", "headline_zh", "text_zh"} and value is not None)
    # Summary context is validation-only: it never changes editor prompts or
    # their cache keys, and cannot license new English tokens.
    english_source = source
    source += "\n" + normalize_zh_tw(inputs.get("_summary_zh", ""))
    if not _numbers(candidate) <= _numbers(source):
        return False
    for name in _NAMES:
        if name in candidate and name not in source:
            aliases = _ALIASES.get(name, ())
            if not any(re.search(r"\b" + re.escape(alias) + r"\b", source, re.I) for alias in aliases):
                return False
    english = set(re.findall(r"[A-Za-z][A-Za-z'-]*", english_source.lower())) | {"ai"}
    if not set(re.findall(r"[A-Za-z][A-Za-z'-]*", candidate.lower())) <= english:
        return False
    if any(match.group() not in source for match in _TRANSLITERATED_NAME.finditer(candidate)):
        return False
    if any(name not in source and role not in source for name, role in _NAME_WITH_ROLE.findall(candidate)):
        return False
    return True


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


def valid_headline(candidate: Any, inputs: dict[str, Any], title: str) -> bool:
    if not faithful_text(candidate, inputs):
        return False
    try:
        validate_headline(candidate, title)
    except ValueError:
        return False
    return True


def editor_items(issue: Issue, classifications: dict[str, Classification],
                 summaries: dict[str, ArticleSummary], brief: WeekBrief | None) -> list[dict[str, Any]]:
    result = [with_term_hints({"id": article.id, "title": article.title, "rubric": article.rubric,
               "title_zh": classifications[article.id].title_zh,
               "headline_zh": summaries[article.id].headline_zh if article.id in summaries else None,
               "tier": classifications[article.id].tier},
               "\n".join([article.title, article.rubric or "", *article.paragraphs]))
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
                       max_items=10, max_bytes=9_000)


def _summary_text(summary: ArticleSummary) -> str:
    """Existing summary facts, without English quotes or diagnostic metadata."""
    parts = [summary.headline_zh, summary.summary_zh, summary.background,
             summary.stance, summary.leader_stance, *summary.key_points,
             *summary.structure, *summary.key_data, *(quote.zh for quote in summary.quotes)]
    if summary.argument:
        parts.extend([summary.argument.claim, *summary.argument.evidence,
                      *summary.argument.counterpoints, summary.argument.conclusion])
    return "\n".join(part for part in parts if part)


def apply_edits(data: dict[str, Any], inputs: list[dict[str, Any]], classifications: dict[str, Classification],
                summaries: dict[str, ArticleSummary], brief: WeekBrief | None) -> None:
    by_id = {item["id"]: item for item in inputs}
    summary_sources = {identifier: _summary_text(summary) for identifier, summary in summaries.items()}
    for item in data["items"]:
        original = by_id[item["id"]]
        if original["tier"] == "brief" and brief:
            candidate = item.get("text_zh")
            if faithful_text(candidate, original) and 1 <= chinese_length(candidate) <= 80:
                _, group, index = item["id"].split("-")
                getattr(brief, group)[int(index)].text_zh = candidate
            continue
        identifier = item["id"]
        companion = classifications[identifier].companion_id
        original = {**original, "_summary_zh": "\n".join(
            summary_sources.get(source_id, "") for source_id in (identifier, companion))}
        if (valid_title(item.get("title_zh"), original)
                and re.sub(r"\W", "", item["title_zh"]) != re.sub(
                    r"\W", "", summaries[identifier].headline_zh if identifier in summaries else "")):
            classifications[identifier].title_zh = item["title_zh"]
        headline = item.get("headline_zh")
        if identifier in summaries and valid_headline(headline, original, classifications[identifier].title_zh):
            summaries[identifier].headline_zh = headline


def edit_digest(issue: Issue, classifications: dict[str, Classification], summaries: dict[str, ArticleSummary],
                brief: WeekBrief | None, config: Config, runner: UnitRunner, warnings: list[str]) -> None:
    inputs = editor_items(issue, classifications, summaries, brief)
    units = edit_units(issue, classifications, summaries, brief, config)
    for result in run_parallel(runner.run, units, config.llm.max_parallel):
        if isinstance(result, BaseException):
            raise result
        if result.data:
            apply_edits(result.data, inputs, classifications, summaries, brief)
        else:
            warnings.append("標題與要聞編修失敗，保留原文字。")
