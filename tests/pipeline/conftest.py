from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from econ_digest.config import Config, PathsConfig, SecretsConfig, TelegramConfig
from econ_digest.models import ArticleSummary, Classification, Digest, EnglishPick, Issue, QuizItem, WeekBrief


@pytest.fixture
def delivery_config(tmp_path: Path) -> Config:
    return Config(paths=PathsConfig(tmp_path / "data"),
                  secrets=SecretsConfig(telegram_bot_token="synthetic-secret-token", telegram_chat_id="12345"),
                  telegram=TelegramConfig(message_delay_seconds=0))


@pytest.fixture
def delivery_digest(synthetic_issue: Issue) -> Digest:
    article = synthetic_issue.articles[0]
    issue = replace(synthetic_issue, articles=[article])
    classification = Classification(article.id, 0, False, None, "finance", "合成財經故事", tier="D")
    summary = ArticleSummary(article.id, "D", "合成一句話", summary_zh="合成摘要")
    pick = EnglishPick(article.id, "合成選文理由", "B1", 700, 10, "合成背景", [], [], [], [],
                       [QuizItem("Synthetic question?", "Synthetic answer.")])
    return Digest(issue.issue_date, "2026-10-04T02:30:00+00:00", issue, {article.id: classification},
                  {article.id: summary}, WeekBrief([], []), pick)
