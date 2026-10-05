from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from econ_digest.analysis.cache import UnitRunner
from econ_digest.analysis.classification import classify_units
from econ_digest.analysis.editor import apply_edits, edit_digest, edit_units, editor_items, faithful_text, valid_title
from econ_digest.analysis.english import guide_unit, pick_unit
from econ_digest.analysis.focus import focus_unit
from econ_digest.analysis.grounding import (apply_grounding, check_facts, facts_unit, ground_digest,
                                          grounding_units, query_units, validate_fact_alerts,
                                          validate_grounding, validate_queries)
from econ_digest.analysis.prompts import PROMPT_DIR
from econ_digest.analysis.summaries import summary_units
from econ_digest.analysis.validation import validate_summary
from econ_digest.config import Config, DEFAULT_MODELS, KEY_MODELS, ModelsConfig, load_config
from econ_digest.facts import load_taiwan_facts
from econ_digest.llm import FakeLLMClient, LLMError
from econ_digest.models import ArticleSummary, BriefItem, Classification, Source, WeekBrief
from econ_digest.render.common import sections
from econ_digest.research.cna import CNAClient, Evidence
from conftest import answer, article, issue, summary


def test_model_routes_and_example(tmp_path: Path) -> None:
    defaults = ModelsConfig()
    for name in defaults.__dataclass_fields__:
        assert getattr(defaults, name) == (KEY_MODELS if name in {'summarize_a', 'edit', 'ground', 'facts'} else DEFAULT_MODELS)
    example = load_config(Path(__file__).resolve().parents[2] / 'config.example.toml')
    assert example.llm.models == defaults


def test_house_style_prefix_on_all_generated_units(analysis_config: Config) -> None:
    source = issue([article('a1', words=800), article('a2')])
    classes = {a.id: Classification(a.id, 0, False, None, 'culture', '政策改變企業成本', tier='A') for a in source.articles}
    summaries = {a.id: ArticleSummary(a.id, 'A', '政策改變提高企業成本。') for a in source.articles}
    units = classify_units(source, analysis_config) + summary_units(source, classes, analysis_config)
    units += [focus_unit(source, classes, analysis_config), pick_unit(source, classes, analysis_config),
              guide_unit(source, source.articles[0], analysis_config), facts_unit(source.issue_date, [], analysis_config)]
    units += edit_units(source, classes, summaries, None, analysis_config)
    units += query_units(source, ['a1'], classes, summaries, analysis_config)
    units += grounding_units(source, ['a1'], classes, summaries, {'a1': []}, analysis_config)
    style = (PROMPT_DIR / '_style.md').read_text()
    assert all(unit.prompt.startswith(style + '\n') for unit in units)
    assert '泛論「中國影響力擴大，所以台灣受影響」為 0' in units[0].prompt
    assert '待查證的暫定判斷' in units[0].prompt
    for tier in 'abcde':
        assert '0–3' in (PROMPT_DIR / f'summarize_{tier}.md').read_text()
        assert '絕不湊數' in (PROMPT_DIR / f'summarize_{tier}.md').read_text()


@pytest.mark.parametrize('tier', list('ABCDE'))
def test_implications_optional_no_minimum(tier: str) -> None:
    data = summary('a1', tier)
    data['taiwan_implications'] = []
    validate_summary(data, article('a1'), tier)
    data.pop('taiwan_implications')
    validate_summary(data, article('a1'), tier)
    data['taiwan_implications'] = ['合成意涵'] * 4
    with pytest.raises(ValueError, match='0–3'):
        validate_summary(data, article('a1'), tier)


def test_fact_sheet_packaged_and_fed_to_taiwan_ab_and_focus_a(analysis_config: Config) -> None:
    facts = load_taiwan_facts()
    assert '邦交國' in facts and '截至' in facts and 'https://www.cna.com.tw/news/' in facts
    source = issue([article('a1')])
    for tier, level, expected in [('A', 1, True), ('B', 2, True), ('A', 0, True), ('C', 3, False), ('B', 0, False)]:
        classes = {'a1': Classification('a1', level, bool(level), '合成關聯' if level else None,
                                       'tech', '政策改變企業成本', tier=tier)}
        unit = summary_units(source, classes, analysis_config)[0]
        assert ('taiwan_facts' in unit.prompt) == expected
        assert unit.prompt_bytes <= 90_000


EDITOR_INPUT = {'id': 'a1', 'title': 'China and America seek an AI crisis hotline', 'rubric': '',
                'title_zh': '人工智慧危機爆發時中國會接熱線嗎？美中軍事應變機制存隱憂',
                'headline_zh': '美國盼建立AI危機專線，中國態度冷淡。', 'tier': 'C'}


@pytest.mark.parametrize('value, expected', [
    ('美盼建AI危機專線　中國態度冷淡', True),
    ('經濟學人：美中AI危機溝通缺乏互信', True),
    ('危機專線', False),
    ('美中AI危機應變' * 5, False),
    ('美中AI危機熱線能否建立？', False),
    ('美中AI危機熱線能否建立?', False),
    ('AI危機：美中溝通缺乏互信', False),
    ('經濟學人：美中危機：互信不足', False),
    ('社論：美中AI危機溝通缺乏互信', False),
    ('美中AI危機溝通　12國拒絕合作', False),
    ('美中AI危機溝通　川普拒絕合作', False),
    ('美中AI危機溝通　巴西拒絕合作', False),
    ('美中AI危機溝通　林允中拒絕合作', False),
    ('美中AI危機專線，合作缺乏互信', False),
])
def test_editor_title_validation(value: str, expected: bool) -> None:
    assert valid_title(value, EDITOR_INPUT) == expected


def test_numbers_and_names_preserved_without_using_ids_as_numbers() -> None:
    original = {'id': 'a123', 'title_zh': '法國公債殖利率創2008年來新高'}
    assert faithful_text('法國借貸成本創2008年來最高', original)
    assert not faithful_text('法國借貸成本創2026年來最高', original)
    assert not faithful_text('法國借貸成本增加123倍', original)
    assert not faithful_text('法國借貸成本增加三倍', original)
    assert not faithful_text('法國借貸成本增加兩倍', original)
    assert faithful_text('封存核廢料10萬年', {'title_zh': '封存核廢料十萬年'})
    assert faithful_text('2026年增加成本', {'title_zh': '二零二六年增加成本'})


def test_editor_individual_fallback_brief_cache_and_english_untouched(analysis_config: Config, tmp_path: Path) -> None:
    original = replace(article('a1'), title=EDITOR_INPUT['title'], rubric='')
    source = issue([original])
    classes = {'a1': Classification('a1', 3, False, '合成關聯', 'tech', EDITOR_INPUT['title_zh'], tier='C')}
    summaries = {'a1': ArticleSummary('a1', 'C', EDITOR_INPUT['headline_zh'])}
    brief = WeekBrief([BriefItem('政府公布新的政策。')], [])
    before = source.to_dict()
    inputs = editor_items(source, classes, summaries, brief)
    apply_edits({'items': [{'id': 'a1', 'title_zh': '美盼建AI危機專線　中國態度冷淡',
                            'headline_zh': '川普宣布新的政策。'},
                           {'id': 'brief-politics-0', 'text_zh': '政府公布新政策。'}]}, inputs, classes, summaries, brief)
    assert classes['a1'].title_zh == '美盼建AI危機專線　中國態度冷淡'
    assert summaries['a1'].headline_zh == EDITOR_INPUT['headline_zh']
    assert brief.politics[0].text_zh == '政府公布新政策。' and source.to_dict() == before
    previous = classes['a1'].title_zh
    apply_edits({'items': [{'id': 'a1', 'title_zh': 'AI危機：美中溝通缺乏互信',
                            'headline_zh': '中國態度冷淡，美國盼建AI危機專線。'}]},
                inputs, classes, summaries, brief)
    assert classes['a1'].title_zh == previous
    assert summaries['a1'].headline_zh == '中國態度冷淡，美國盼建AI危機專線。'
    units = edit_units(source, classes, summaries, brief, analysis_config)
    assert len(units) == 1
    runner = UnitRunner(FakeLLMClient(answer), tmp_path)
    edit_digest(source, classes, summaries, brief, analysis_config, runner, [])
    warm = UnitRunner(FakeLLMClient(lambda *args: pytest.fail('editor should be cached')), tmp_path)
    edit_digest(source, classes, summaries, brief, analysis_config, warm, [])
    assert warm.stats == []


def test_editor_splits_large_batch(analysis_config: Config) -> None:
    source = issue([replace(article(f'a{i}'), rubric='Synthetic rubric ' * 100) for i in range(70)])
    classes = {a.id: Classification(a.id, 0, False, None, 'culture', '政策改變企業成本', tier='E') for a in source.articles}
    units = edit_units(source, classes, {}, None, analysis_config)
    assert len(units) > 1 and all(unit.prompt_bytes <= 60_000 for unit in units)
    assert sum(len(unit.article_ids) for unit in units) == 70


def sample_evidence() -> Evidence:
    return Evidence('cna1', Source('中央社', '2026-10-01', '合成友邦報導',
                                  'https://www.cna.com.tw/news/aipl/202610010001.aspx'), '合成證據摘錄。')


@pytest.mark.parametrize('queries', [[], [''], ['a'], ['台' * 21], ['台灣'] * 4, [3]])
def test_query_validation(queries: list) -> None:
    with pytest.raises(ValueError):
        validate_queries({'articles': [{'article_id': 'a1', 'queries': queries}]}, {'a1'})


def test_grounding_drops_invalid_bases_downgrades_and_moves_to_category(analysis_config: Config) -> None:
    evidence = {'a1': [sample_evidence()]}
    data = {'articles': [{'article_id': 'a1', 'taiwan_level': 3,
                          'taiwan_link': {'text_zh': '沒有來源。', 'basis': []},
                          'taiwan_implications': [{'text_zh': '合成推論。', 'basis': ['cna999']},
                                                  {'text_zh': '（推論）具體機制。', 'basis': ['article', 'facts', 'cna1']}]}]}
    validate_grounding(data, evidence)
    assert data['articles'][0]['taiwan_level'] == 0
    assert len(data['articles'][0]['taiwan_implications']) == 1
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', 3, False, '暫定關聯', 'tech', '合成標題', tier='C')}
    summaries = {'a1': ArticleSummary('a1', 'C', '原本摘要')}
    apply_grounding(data, source, classes, summaries, evidence, analysis_config, [])
    assert classes['a1'].taiwan_level == 0 and classes['a1'].tier == 'D'
    assert summaries['a1'].headline_zh == '原本摘要' and summaries['a1'].tier == 'C'
    assert summaries['a1'].sources == [sample_evidence().source] and classes['a1'].sources == []
    from econ_digest.models import Digest
    digest = Digest(source.issue_date, '2026-10-05T00:00:00Z', source, classes, summaries, None, None)
    assert [section.anchor for section in sections(digest)] == ['tech']


def test_ground_link_valid_sources_and_focus_depth(analysis_config: Config) -> None:
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', 0, False, None, 'tech', '合成標題', tier='A')}
    summaries = {'a1': ArticleSummary('a1', 'A', '原摘要')}
    evidence = {'a1': [sample_evidence()]}
    data = {'articles': [{'article_id': 'a1', 'taiwan_level': 3,
                          'taiwan_link': {'text_zh': '（推論）具體合成關聯。', 'basis': ['cna1']},
                          'taiwan_implications': []}]}
    apply_grounding(data, source, classes, summaries, evidence, analysis_config, ['a1'])
    assert classes['a1'].tier == 'A' and classes['a1'].sources == [sample_evidence().source]


def test_cna_unreachable_grounding_fallback_and_cache(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', 3, False, '暫定關聯', 'tech', '合成標題', tier='C')}
    summaries = {'a1': ArticleSummary('a1', 'C', '合成摘要')}
    def opener(*args, **kwargs):
        raise OSError('synthetic offline')
    cna = CNAClient(tmp_path / 'research', opener=opener, sleep=lambda _: None)
    runner = UnitRunner(FakeLLMClient(answer), tmp_path / 'analysis')
    warnings = []
    ground_digest(source, classes, summaries, [], analysis_config, runner, cna, warnings)
    assert any('中央社暫時無法連線' in item for item in warnings)
    assert '台灣事實檔' in runner.llm.calls[-1][0] and '"evidence":[]' in runner.llm.calls[-1][0]
    assert classes['a1'].sources == []
    warm = UnitRunner(FakeLLMClient(lambda *args: pytest.fail('ground must be cached')), tmp_path / 'analysis')
    ground_digest(source, classes, summaries, [], analysis_config, warm, cna, [])
    assert warm.stats == []


def test_failed_grounding_never_publishes_provisional_link(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', 3, False, '未查證暫定關聯', 'tech', '合成標題', tier='C')}
    summaries = {'a1': ArticleSummary('a1', 'C', '保留摘要', taiwan_implications=['未查證意涵'])}
    cna = CNAClient(tmp_path / 'research')
    cna.retrieve = lambda _: []
    fake = FakeLLMClient(lambda prompt, model, stage: LLMError('synthetic unavailable', kind='quota')
                         if stage == 'ground' else answer(prompt, model, stage))
    warnings = []
    ground_digest(source, classes, summaries, [], analysis_config, UnitRunner(fake, tmp_path / 'cache'), cna, warnings)
    assert classes['a1'].taiwan_level == 0 and classes['a1'].taiwan_link is None
    assert summaries['a1'].taiwan_implications == [] and summaries['a1'].headline_zh == '保留摘要'


def test_facts_alert_validation_and_once_per_issue(analysis_config: Config, tmp_path: Path) -> None:
    ev = sample_evidence()
    alert = {'fact': '合成舊值', 'suspected_new_value': '合成新值', 'evidence_url': ev.source.url}
    data = {'alerts': [alert, {**alert, 'evidence_url': 'https://example.invalid'}, {'fact': '沒有證據'}]}
    validate_fact_alerts(data, {ev.source.url})
    assert data['alerts'] == [alert]
    cna = CNAClient(tmp_path / 'research')
    retrieved = []
    cna.retrieve = lambda queries: retrieved.append(queries) or [ev]
    client = FakeLLMClient(lambda *args: {'alerts': [alert]})
    runner = UnitRunner(client, tmp_path / 'analysis')
    assert check_facts('2026.10.03', analysis_config, runner, cna, []) == [alert]
    assert len(retrieved[0]) == 6
    assert check_facts('2026.10.03', analysis_config, runner, cna, []) == [alert]
    assert len(client.calls) == len(retrieved) == 1
    check_facts('2026.10.10', analysis_config, runner, cna, [])
    assert len(client.calls) == 2
