from __future__ import annotations

import re
from importlib.resources import files

import pytest

from econ_digest.analysis.editor import edit_units, faithful_text
from econ_digest.analysis.prompts import PROMPT_DIR, with_term_hints
from econ_digest.analysis.summaries import summary_units
from econ_digest.models import ArticleSummary, Classification
from econ_digest.zhtw import terms
from econ_digest.zhtw.terms import Term
from conftest import article, issue, payload


@pytest.fixture
def synthetic_terms(monkeypatch):
    table = (Term("trade embargo", "貿易禁運"), Term("embargo", "禁運"),
             Term("synthetic tariff", "合成關稅"))
    monkeypatch.setattr(terms, "load_terms", lambda: table)
    return table


def test_case_whole_words_whitespace_and_nested_phrases(synthetic_terms):
    assert terms.matching_terms("TRADE\nEmbargo; synthetic tariff.") == (
        Term("synthetic tariff", "合成關稅"), Term("trade embargo", "貿易禁運"))
    assert terms.matching_terms("preembargo embargoes synthetic tariffing") == ()
    assert terms.matching_terms("Trade embargo. Another embargo.") == (
        Term("trade embargo", "貿易禁運"), Term("embargo", "禁運"))


def test_selection_is_deterministic_and_capped():
    table = tuple(Term(f"synthetic concept {i:02d}", "合成概念") for i in range(20))
    source = " ".join(term.english for term in reversed(table))
    selected = terms.matching_terms(source, table)
    assert len(selected) == 15
    assert selected == table[:15]
    assert terms.matching_terms(source, tuple(reversed(table))) == selected
    assert terms.terminology_hint(source, table).count(" → ") == 15


def test_utf8_cap_omits_whole_entries():
    table = tuple(Term(f"synthetic concept {i}", "合成" * 100) for i in range(15))
    hint = terms.terminology_hint(" ".join(term.english for term in table), table)
    assert hint and len(hint.encode()) <= terms.MAX_HINT_BYTES
    assert hint.count(" → ") == 1
    assert "合成" * 100 in hint
    assert hint.endswith("人名、地名仍依中央社慣例。")
    assert terms.terminology_hint("oversized concept", (Term("oversized concept", "合成" * 1000),)) == ""


def test_loader_removes_duplicates_ambiguities_common_words_and_annotations(tmp_path):
    table = tmp_path / "terms.tsv"
    table.write_text("# synthetic\nTRADE EMBARGO\t貿易禁運\t外交\ntrade embargo\t貿易禁運\n"
                     "synthetic treaty\t合成協定\nSYNTHETIC TREATY\t合成條約\n"
                     "bank\t銀行\npower\t電力\nmodel\t模型\nAI\t人工智慧\n"
                     "ambiguous concept\t概念；觀念\nnot a term\t\nmalformed\n")
    assert terms.load_terms(table) == (Term("trade embargo", "貿易禁運"),)


def test_missing_unreadable_and_invalid_encoding_are_optional(tmp_path):
    assert terms.load_terms(tmp_path / "absent.tsv") == ()
    assert terms.load_terms(tmp_path) == ()
    table = tmp_path / "bad.tsv"
    table.write_bytes(b"\xff")
    assert terms.load_terms(table) == ()


@pytest.mark.parametrize("tier", list("ABCDE"))
def test_all_summary_stages_include_article_concepts(tier, analysis_config, synthetic_terms):
    source = issue([article("a1", paragraphs=["A TRADE EMBARGO changes policy."]),
                    article("a2", paragraphs=["A separate synthetic tariff changes policy."])])
    classes = {a.id: Classification(a.id, 0, False, None, "finance", "政策改變企業成本", tier=tier)
               for a in source.articles}
    units = summary_units(source, classes, analysis_config)
    inputs = {item["article_id"]: item for unit in units for item in payload(unit.prompt, "文章：")}
    assert "trade embargo → 貿易禁運" in inputs["a1"]["term_hints"]
    assert "synthetic tariff" not in inputs["a1"]["term_hints"]
    assert "synthetic tariff → 合成關稅" in inputs["a2"]["term_hints"]
    assert all(unit.prompt_bytes <= 90_000 for unit in units)


def test_editor_matches_full_english_text_without_forwarding_it(analysis_config, synthetic_terms):
    source = issue([article("a1", paragraphs=["TRADE EMBARGO is only in the original body."])])
    classes = {"a1": Classification("a1", 0, False, None, "finance", "政策改變企業成本", tier="C")}
    summaries = {"a1": ArticleSummary("a1", "C", "政策改變企業成本。")}
    unit = edit_units(source, classes, summaries, None, analysis_config)[0]
    item = payload(unit.prompt, "編修項目：")[0]
    assert "trade embargo → 貿易禁運" in item["term_hints"]
    assert "only in the original body" not in unit.prompt
    assert unit.prompt_bytes <= 9_000
    # A concept hint supplies no licence to introduce entities or numbers.
    assert not faithful_text("史塔默宣布17年政策。", {**item, "term_hints": "史塔默17年"})


def test_editor_still_splits_under_byte_cap(analysis_config, monkeypatch):
    table = tuple(Term(f"synthetic concept {i:02d}", "合成概念") for i in range(15))
    monkeypatch.setattr(terms, "load_terms", lambda: table)
    source = issue([article(f"a{i}", paragraphs=[" ".join(t.english for t in table)]) for i in range(10)])
    classes = {a.id: Classification(a.id, 0, False, None, "finance", "政策改變企業成本", tier="C")
               for a in source.articles}
    units = edit_units(source, classes, {}, None, analysis_config)
    assert len(units) > 1
    assert sum(len(unit.article_ids) for unit in units) == 10
    assert all(unit.prompt_bytes <= 9_000 for unit in units)


def test_missing_packaged_file_does_not_change_payload_or_prompt(tmp_path, monkeypatch, analysis_config):
    monkeypatch.setattr(terms, "files", lambda _: tmp_path)
    original = {"text": "Trade embargo."}
    assert with_term_hints(original, original["text"]) is original
    source = issue([article("a1", paragraphs=["Trade embargo."])])
    classes = {"a1": Classification("a1", 0, False, None, "finance", "政策改變企業成本", tier="C")}
    before = [summary_units(source, classes, analysis_config)[0], edit_units(source, classes, {}, None, analysis_config)[0]]
    monkeypatch.setattr(terms, "load_terms", lambda: ())
    after = [summary_units(source, classes, analysis_config)[0], edit_units(source, classes, {}, None, analysis_config)[0]]
    assert [(u.prompt, u.cache_key) for u in before] == [(u.prompt, u.cache_key) for u in after]
    assert all("term_hints" not in unit.prompt for unit in after)


def test_hint_changes_cache_only_for_articles_with_a_match(analysis_config, monkeypatch, synthetic_terms):
    source = issue([article("a1", paragraphs=["Trade embargo."]), article("a2")])
    classes = {a.id: Classification(a.id, 0, False, None, "finance", "政策改變企業成本", tier="B")
               for a in source.articles}
    before = summary_units(source, classes, analysis_config)
    monkeypatch.setattr(terms, "load_terms", lambda: ())
    after = summary_units(source, classes, analysis_config)
    assert before[0].cache_key != after[0].cache_key
    assert before[1].cache_key == after[1].cache_key


def test_new_rules_reach_compact_editor_and_keep_style_length(analysis_config):
    style = (PROMPT_DIR / "_style.md").read_text()
    assert len(re.findall(r"[\u3400-\u9fff]", style)) <= 2_500
    source = issue([article("a1")])
    classes = {"a1": Classification("a1", 0, False, None, "finance", "政策改變企業成本", tier="C")}
    prompt = edit_units(source, classes, {}, None, analysis_config)[0].prompt
    assert "解釋與歸因（轉角國際、公視）" in prompt
    assert "百分點不可混用" in prompt
    assert "合成短例" not in prompt


def test_distribution_includes_attribution_and_licence_note():
    note = files("econ_digest.zhtw").joinpath("terms-NOTICE.md").read_text()
    assert "國家教育研究院" in note and "2026" in note
    assert "https://terms.naer.edu.tw/mysite/about/2/" in note
    assert "https://data.gov.tw/license" in note
    assert "不代表" in note and "刪除" in note
    table = files("econ_digest.zhtw").joinpath("terms.tsv").read_text()
    assert "terms-NOTICE.md" in table
