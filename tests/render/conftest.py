"""Hand-written digest built exclusively from synthetic EPUB articles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from econ_digest.models import (Argument, ArticleSummary, BriefItem, Classification, Digest,
                                EnglishPick, Issue, LLMCallStat, PhraseItem, QuizItem, Quote,
                                SentenceAnalysis, VocabItem, WeekBrief)


@pytest.fixture
def sample_digest(synthetic_issue: Issue) -> Digest:
    base = synthetic_issue.articles[0]
    specs = [(1, "intl.us", "A", "台灣晶片展望"), (2, "tech", "B", "台灣與國際合作"),
             (3, "finance", "C", "供應鏈間接影響"), (0, "intl.us", "C", "美國政策"),
             (0, "intl.china", "C", "中國經濟"), (0, "intl.asia", "D", "亞太局勢"),
             (0, "intl.europe", "D", "歐洲選舉"), (0, "intl.other", "E", "其他地區故事"),
             (0, "finance", "D", "財經商業展望"), (0, "tech", "D", "科技軟體"),
             (0, "science", "E", "科學新知"), (0, "culture", "E", "文化生活故事")]
    articles = []
    classifications = {}
    summaries = {}
    for index, (level, category, tier, zh) in enumerate(specs, 1):
        article = replace(base, id=f"sample-{index}", order=index, title=f"Synthetic English title {index}",
                          kind="briefing" if index == 1 else "column" if index == 4 else "article",
                          is_cover=index == 1, section=f"Synthetic section {index}",
                          paragraphs=["A synthetic <script>alert('example')</script> & an invented paragraph.", "The second synthetic paragraph is for language practice."])
        articles.append(article)
        classifications[article.id] = Classification(article.id, level, bool(level),
                                                     "台灣與晶片供應鏈相關 <script> & < 3" if level else None,
                                                     category, zh, tier=tier)
        summaries[article.id] = ArticleSummary(article.id, tier, f"{zh}的一句話重點 & <script>",
                                               summary_zh=f"{zh}的合成摘要。",
                                               key_points=[f"{zh}重點一", f"{zh}重點二"] if tier in "ABC" else [])
    full = summaries[articles[0].id]
    full.background = "背景含 <script> & < 比較符號"
    full.structure = ["先介紹背景", "接著提出證據"]
    full.argument = Argument("合成主張", ["數據證據"], ["另一種解釋"], "合成結論")
    full.key_data = ["42% 是合成數字"]
    full.quotes = [Quote("A synthetic quote & < comparison.", "合成引述中譯")]
    full.stance = "經濟學人主張開放；盲點是忽略成本。"
    full.taiwan_implications = ["對台灣產業的合成意涵"]
    full.further_questions = ["台灣應如何因應？"]
    leader = next(article for article in synthetic_issue.articles if article.kind == "leader")
    leader = replace(leader, order=20)
    articles.append(leader)
    classifications[leader.id] = Classification(leader.id, 2, True, "合成關聯", "tech", "合併社論", articles[1].id, "merged")
    summaries[articles[1].id].leader_stance = "社論主張持續合作。"
    for article in synthetic_issue.articles:
        if article.kind in ("world_politics", "world_business", "cartoon"):
            articles.append(replace(article, order=30 + article.order))
            classifications[article.id] = Classification(article.id, 0, False, None, "intl.other", article.title,
                                                         tier="skip" if article.kind == "cartoon" else "brief")
    indicators = replace(base, id="indicators", order=99, title="Synthetic indicators", kind="indicators")
    articles.append(indicators)
    classifications[indicators.id] = Classification(indicators.id, 0, False, None, "finance", "經濟指標", tier="skip")
    english = EnglishPick(articles[3].id, "句型清楚，適合中級讀者。", "B1", 720, 12,
                          "背景導讀含 & <script>",
                          [VocabItem("resilience", "n.", "韌性", "Synthetic firms show resilience & < 3.", "常用於經濟議題"),
                           VocabItem("policy", "n.", "政策", "A synthetic policy changes.")],
                          [PhraseItem("in the long run", "長期而言", "In the long run, synthetic firms adapt.")],
                          [SentenceAnalysis("Although firms adapt, costs remain.", "Although 引導讓步子句。", "雖然企業因應，成本仍然存在。")],
                          ["用讓步句呈現不同觀點。"], [QuizItem("What remains?", "Synthetic quiz answer: costs remain.")])
    brief = WeekBrief([BriefItem("非台灣政治要聞"), BriefItem("台灣相關政治要聞 & <script>", True)],
                      [BriefItem("商業合成要聞"), BriefItem("台灣商業合成要聞", True)])
    return Digest(synthetic_issue.issue_date, "2026-10-04T02:30:00+00:00",
                  replace(synthetic_issue, articles=articles), classifications, summaries, brief, english,
                  [LLMCallStat("classify", "synthetic-model", True, 100, 1.2),
                   LLMCallStat("summarize", "synthetic-model", True, 200, 2.3),
                   LLMCallStat("english", "synthetic-other", False, 50, 0.8)],
                  ["合成警告 <script> & < 例子"])


@pytest.fixture
def no_taiwan_digest(sample_digest: Digest) -> Digest:
    digest = deepcopy(sample_digest)
    for classification in digest.classifications.values():
        classification.taiwan_level = 0
        classification.mentions_taiwan = False
        classification.taiwan_link = None
    return digest
