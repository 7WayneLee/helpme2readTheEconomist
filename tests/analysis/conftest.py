"""Synthetic articles and source-faithful fake model responses."""

from __future__ import annotations

import json
import re
from pathlib import Path
from collections.abc import Callable
from typing import Any

import pytest

from econ_digest.config import Config, EnglishConfig, LLMConfig, ModelsConfig, PathsConfig
from econ_digest.models import Article, Issue

BODY = ["A policy needs resolve and careful planning. Firms in turn adapt to new costs.",
        "The committee counted 12 votes in 2026. Workers gained 3 new options.",
        "A policy needs resolve and careful planning. The reform could work, if its costs are shared.",
        "Firms in turn adapt to new costs. This is a synthetic example, not a news report."]
ZH = "政策改變提高企業成本，政府與民眾必須評估配套措施，並比較不同制度下的利益與風險。"


def article(identifier: str, *, kind: str = "article", section: str = "Culture", words: int = 100,
            paragraphs: list[str] | None = None, cover: bool = False) -> Article:
    return Article(identifier, int(re.search(r"\d+", identifier)[0]) if re.search(r"\d+", identifier) else 0,
                   section, None, "Synthetic " + identifier, "Synthetic rubric", "2026-10-03",
                   list(BODY) if paragraphs is None else paragraphs, words, kind, cover)


def issue(articles: list[Article]) -> Issue:
    return Issue("2026.10.03", "https://example.invalid/synthetic.epub", "2026-10-03T00:00:00Z", articles)


def payload(prompt: str, marker: str) -> Any:
    return json.JSONDecoder().raw_decode(prompt.rsplit(marker, 1)[1].lstrip())[0]


def summary(identifier: str, tier: str, *, leader: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"article_id": identifier, "headline_zh": ZH}
    if tier == "A":
        result.update(background=ZH * 4, structure=[f"第 {i} 段：" + ZH * 2 for i in range(1, 5)],
                      argument={"claim": ZH, "evidence": [ZH * 2] * 3, "counterpoints": [ZH], "conclusion": ZH},
                      key_data=["12 votes", "2026", "3 new options"],
                      quotes=[{"en": "A policy needs resolve and careful planning.", "zh": "政策需要決心與審慎規劃。"},
                              {"en": "Firms in turn adapt to new costs.", "zh": "企業進而因應新的成本。"}],
                      stance="立場分析：" + ZH * 3, taiwan_implications=["（推論）" + ZH] * 2,
                      further_questions=["台灣可從中學到什麼？"])
    elif tier == "B":
        result.update(key_points=[ZH * 2] * 4,
                      argument={"claim": ZH, "evidence": [ZH] * 2, "counterpoints": [], "conclusion": ZH},
                      taiwan_implications=["（推論）" + ZH])
    elif tier == "C":
        result.update(key_points=[ZH * 2] * 3)
    elif tier == "D":
        result.update(summary_zh=ZH * 2)
    if leader:
        result["leader_stance"] = "作者主張：政府必須重新檢視政策。企業應審慎評估成本。"
    return result


def guide() -> dict[str, Any]:
    return {"cefr": "B2", "pre_reading_zh": ZH * 4,
            "vocabulary": [{"word": "resolve", "pos": "n.", "meaning_zh": "決心",
                            "example_en": BODY[0].split(" Firms")[0], "note_zh": "可搭配 show。"}],
            "phrases": [{"phrase": "in turn", "meaning_zh": "進而", "example_en": "Firms in turn adapt to new costs."}],
            "sentences": [{"sentence_en": BODY[0].split(" Firms")[0], "breakdown_zh": "主詞加動詞與受詞。", "translation_zh": "政策需要決心與審慎規劃。"},
                          {"sentence_en": "The reform could work, if its costs are shared.", "breakdown_zh": "主句加條件子句。", "translation_zh": "如果共同分擔成本，改革可望奏效。"}],
            "writing_notes_zh": ["文章以例子帶出論點。"],
            "quiz": [{"question": "What does the policy need?", "answer": "第 1 段指出需要決心與規劃。"},
                     {"question": "How many votes were counted?", "answer": "第 2 段提到 12 票。"},
                     {"question": "When could the reform work?", "answer": "第 3 段指出共同分擔成本時。"}]}


def answer(prompt: str, model: str, stage: str) -> dict[str, Any]:
    if stage == "classify":
        return {"articles": [{"article_id": item["id"], "taiwan_level": 0, "mentions_taiwan": False,
                               "taiwan_mention_kind": "none", "taiwan_evidence": None,
                               "taiwan_link": None, "category": "culture", "title_zh": "政策改變的成本"}
                              for item in payload(prompt, "文章：")]}
    if stage == "pair":
        return {"pairs": [{"article_id": item["id"], "companion_id": None} for item in payload(prompt.split("候選報導：")[0], "經濟學人立場：")]}
    if stage == "focus":
        count = int(re.search(r"最值得深入理解的 (\d+) 篇", prompt)[1])
        return {"focus": [{"article_id": item["id"], "reason": "本週具有全球重要性，值得深入解析。"}
                          for item in payload(prompt, "候選：")[:count]]}
    if stage.startswith("summarize_"):
        return {"articles": [summary(item["article_id"], item["tier"], leader="leader" in item)
                              for item in payload(prompt, "文章：")]}
    if stage == "brief":
        inputs = payload(prompt, "新聞段落：")
        return {name: [{"text_zh": "政府公布新的政策。", "taiwan_related": False} for _ in paragraphs]
                for name, paragraphs in inputs.items()}
    if stage == "english_pick":
        return {"article_id": payload(prompt.split("最近最多八次選文：")[0], "候選：")[0]["id"], "reason_zh": "結構清楚，單字實用。"}
    if stage == "english_guide":
        return guide()
    if stage == "edit":
        return {"items": [{key: value for key, value in item.items()
                           if key in {"id", "title_zh", "headline_zh", "text_zh"}}
                          for item in payload(prompt, "編修項目：")]}
    if stage == "ground_queries":
        return {"articles": [{"article_id": item["article_id"], "queries": ["台灣 合成查證"]}
                             for item in payload(prompt, "查證文章：")]}
    if stage == "ground":
        return {"articles": [{"article_id": item["article_id"],
                               "taiwan_level": item["provisional_taiwan_level"],
                               "taiwan_link": {"text_zh": "台灣是合成主題。", "basis": ["article"]}
                               if item["provisional_taiwan_level"] else None,
                               "taiwan_implications": []}
                              for item in payload(prompt, "查證文章及各篇證據：")]}
    if stage == "facts":
        return {"alerts": []}
    raise AssertionError(stage)


@pytest.fixture
def analysis_config(tmp_path: Path) -> Config:
    models = ModelsConfig(**{name: ("fake",) for name in ModelsConfig.__dataclass_fields__})
    return Config(paths=PathsConfig(tmp_path / "data"), llm=LLMConfig(models=models, max_parallel=2),
                  english=EnglishConfig(vocab_count=1, phrase_count=1))


@pytest.fixture
def example_issue() -> Issue:
    return issue([article(f"a{i}") for i in range(6)] + [article("p1", kind="world_politics", paragraphs=["Synthetic news."])])


@pytest.fixture
def fake_answer() -> Callable[[str, str, str], dict[str, Any]]:
    return answer
