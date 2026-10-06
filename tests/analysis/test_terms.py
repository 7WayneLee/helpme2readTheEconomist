from __future__ import annotations

import random
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


def _slow_matching_terms(text: str, table: tuple[Term, ...]) -> tuple[Term, ...]:
    """Reference copy of the original per-term regex/occupied-list matcher."""
    selected: list[Term] = []
    occupied: list[tuple[int, int]] = []
    ordered = sorted(set(table), key=lambda term: (
        -len(term.english.split()), -len(term.english), term.english.casefold()))
    for term in ordered:
        pattern = re.compile(r"(?<!\w)" + r"\s+".join(
            re.escape(word) for word in term.english.split()) + r"(?!\w)", re.I)
        matches = [match.span() for match in pattern.finditer(text)
                   if not any(match.start() < end and match.end() > start for start, end in occupied)]
        if matches:
            selected.append(term)
            occupied.extend(matches)
            if len(selected) == terms.MAX_HINT_TERMS:
                break
    return tuple(selected)


def _slow_hint(text: str, table: tuple[Term, ...]) -> str:
    entries: list[str] = []
    for term in _slow_matching_terms(text, table):
        entry = f"{term.english} → {term.chinese}"
        candidate = terms._LABEL + "；".join([*entries, entry]) + "\n" + terms._GUIDANCE
        if len(candidate.encode("utf-8")) <= terms.MAX_HINT_BYTES:
            entries.append(entry)
    return terms._LABEL + "；".join(entries) + "\n" + terms._GUIDANCE if entries else ""


@pytest.fixture
def default_term_cache():
    terms._default_terms.cache_clear()
    yield
    terms._default_terms.cache_clear()


@pytest.mark.parametrize("text,english", [
    ("TRADE\nEmbargo; embargo TRADE\tEMBARGO.", ("trade embargo", "embargo", "trade")),
    ("alpha beta gamma delta", ("alpha beta", "beta gamma delta", "alpha", "gamma")),
    ("omega alpha alpha alpha", ("omega alpha", "alpha alpha", "alpha")),
    ("alpha beta gamma delta epsilon", ("alpha beta", "beta gamma delta", "delta epsilon", "epsilon")),
    ("alpha beta gamma delta; alpha beta", ("alpha beta", "beta gamma delta", "alpha")),
    ("alpha\t\n beta   gamma; ALPHA-beta", ("alpha beta", "beta gamma", "alpha-beta", "beta")),
    ("rate rates prerate _rate rate_ 中文rate rate中文 rate-rate", ("rate", "rate-rate")),
    ("İncome taX; ſtock market; Kelvin; ıncome TAX", ("income tax", "stock market", "kelvin")),
    ("alpha beta gamma", ("alpha", "alpha  ", "alpha beta", "beta gamma", "beta")),
    ("", ("", "alpha")),
    ("!alpha? beta.", ("", "!alpha", "alpha", "beta", "?")),
    ("", ()),
])
def test_matcher_and_hint_match_slow_reference(text, english):
    table = tuple(Term(phrase, "合成概念") for phrase in english)
    expected = _slow_matching_terms(text, table)
    assert terms.matching_terms(text, table) == expected
    assert terms.terminology_hint(text, table).encode() == _slow_hint(text, table).encode()
    assert terms.matching_terms(text, tuple(reversed(table))) == _slow_matching_terms(text, tuple(reversed(table)))


def test_randomized_overlaps_repetitions_case_and_caps_match_reference():
    rng = random.Random(167)
    words = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")
    for _ in range(80):
        english = {" ".join(rng.choices(words, k=rng.randint(1, 4))) for _ in range(40)}
        table = tuple(Term(phrase, "合成" * rng.choice((1, 5, 100))) for phrase in sorted(english))
        chunks = [rng.choice(tuple(sorted(english))) for _ in range(35)]
        chunks.extend(rng.choices(words, k=100))
        rng.shuffle(chunks)
        text = " ".join(chunks)
        text = "".join(char.upper() if rng.randrange(3) == 0 else char for char in text)
        text = text.replace(" ", "\t\n" if rng.randrange(2) else " ")
        assert terms.matching_terms(text, table) == _slow_matching_terms(text, table)
        assert terms.terminology_hint(text, table).encode() == _slow_hint(text, table).encode()


def test_duplicate_english_translations_keep_original_priority():
    table = (Term("alpha beta", "甲乙"), Term("alpha beta", "其他"), Term("beta", "乙"))
    assert terms.matching_terms("alpha beta; beta", table) == _slow_matching_terms("alpha beta; beta", table)


def test_default_table_is_read_once_and_explicit_path_can_refresh(tmp_path, monkeypatch, default_term_cache):
    table = tmp_path / "terms.tsv"
    table.write_text("alpha beta\t甲乙\n")
    reads = []

    class Resource:
        def read_text(self, **kwargs):
            reads.append(kwargs)
            return table.read_text(**kwargs)

    class Package:
        def joinpath(self, name):
            assert name == "terms.tsv"
            return Resource()

    monkeypatch.setattr(terms, "files", lambda _: Package())
    original = terms.load_terms()
    assert terms.load_terms() is original
    table.write_text("charlie delta\t丙丁\n")
    assert terms.load_terms() is original
    assert len(reads) == 1
    assert terms.load_terms(table) == (Term("charlie delta", "丙丁"),)
    table.write_text("alpha beta\t甲乙\n")
    assert terms.load_terms(table) == original


def test_matching_cache_uses_text_and_entire_term_tuple(monkeypatch):
    table = (Term("cache concept", "合成概念"),)
    other = (Term("cache concept", "其他概念"),)
    terms._matching_terms.cache_clear()
    original_patterns = terms._patterns
    scans = []

    def track(table):
        scans.append(table)
        return original_patterns(table)

    monkeypatch.setattr(terms, "_patterns", track)
    assert terms.matching_terms("cache concept", table) == table
    assert terms.matching_terms("".join(("cache ", "concept")), table) == table
    assert scans == [table]
    assert terms.matching_terms("cache concept", other) == other
    assert terms.matching_terms("no concept", table) == ()
    assert scans == [table, other, table]


def test_scanning_stops_when_highest_priority_slots_are_fixed(monkeypatch):
    table = tuple(Term(f"synthetic concept {i:02d}", "合成概念") for i in range(20))
    ordered, pattern, buckets = terms._patterns(table)
    scanned = []

    class TrackingPattern:
        def finditer(self, text):
            for match in pattern.finditer(text):
                scanned.append(match.start())
                yield match

    monkeypatch.setattr(terms, "_patterns", lambda _: (ordered, TrackingPattern(), buckets))
    text = "; ".join(term.english for term in table) + "; " + ("synthetic concept 19; " * 100)
    terms._matching_terms.cache_clear()
    assert terms.matching_terms(text, table) == _slow_matching_terms(text, table) == table[:15]
    assert len(scanned) == 16


def test_later_higher_priority_term_replaces_an_earlier_capped_result():
    table = tuple(Term(f"synthetic concept {i:02d}", "合成概念") for i in range(20))
    text = "; ".join(term.english for term in reversed(table))
    assert terms.matching_terms(text, table) == _slow_matching_terms(text, table) == table[:15]


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


def test_missing_packaged_file_does_not_change_payload_or_prompt(tmp_path, monkeypatch, analysis_config,
                                                               default_term_cache):
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
