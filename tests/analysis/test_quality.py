from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from econ_digest.analysis.cache import UnitRunner
from econ_digest.analysis.classification import classify_units
from econ_digest.analysis.editor import (apply_edits, edit_digest, edit_units, editor_items,
                                        faithful_text, valid_headline, valid_title)
from econ_digest.analysis.english import guide_unit, pick_unit
from econ_digest.analysis.focus import focus_unit
from econ_digest.analysis.grounding import (apply_grounding, check_facts, facts_unit, ground_digest,
                                          grounding_units, query_units, validate_fact_alerts,
                                          validate_grounding, validate_queries)
from econ_digest.analysis.prompts import PROMPT_DIR
from econ_digest.analysis.summaries import summary_units
from econ_digest.analysis.validation import validate_summary
from econ_digest.config import Config, ConfigError, DEFAULT_MODELS, KEY_MODELS, ModelsConfig, load_config
from econ_digest.facts import load_taiwan_facts
from econ_digest.llm import FakeLLMClient, LLMError
from econ_digest.models import ArticleSummary, BriefItem, Classification, Source, WeekBrief
from econ_digest.render.common import sections
from econ_digest.research.cna import CNAClient, Evidence
from conftest import answer, article, issue, payload, summary


def test_model_routes_and_example(tmp_path: Path) -> None:
    defaults = ModelsConfig()
    for name in defaults.__dataclass_fields__:
        assert getattr(defaults, name) == (KEY_MODELS if name in {'summarize_a', 'ground', 'facts'} else DEFAULT_MODELS)
    example = load_config(Path(__file__).resolve().parents[2] / 'config.example.toml')
    assert example.llm.models == defaults


def test_stage_timeouts_config_and_runner(tmp_path: Path) -> None:
    config = Config()
    assert config.llm.timeout_for('edit') == 900
    assert config.llm.timeout_for('ground') == 600
    assert config.llm.timeout_for('ground_queries') == 600
    assert config.llm.timeout_for('facts') == config.llm.timeout_for('summarize_a') == 300
    path = tmp_path / 'config.toml'
    path.write_text('[llm]\nstage_timeout_seconds = { facts = 45 }')
    custom = load_config(path)
    assert custom.llm.timeout_for('facts') == 45 and custom.llm.timeout_for('edit') == 900
    class RecordingClient:
        def generate_json(self, prompt, **kwargs):
            from econ_digest.llm.api import LLMResult
            assert kwargs['timeout'] == 45
            return LLMResult({'alerts': []}, 'claude-opus-4-6-thinking', 0, 0, [])
    UnitRunner(RecordingClient(), tmp_path / 'cache', timeout_for=custom.llm.timeout_for).run(
        facts_unit('2026.10.03', [], custom))
    for value in ['{ edit = 0 }', '{ invented = 600 }', '{ ground = true }']:
        path.write_text('[llm]\nstage_timeout_seconds = ' + value)
        with pytest.raises(ConfigError, match='stage_timeout_seconds'):
            load_config(path)


def test_cna_budget_config(tmp_path):
    assert Config().research.cna_request_budget == 40
    path = tmp_path / 'config.toml'
    for budget in (0, 15):
        path.write_text(f'[research]\ncna_request_budget = {budget}\n')
        assert load_config(path).research.cna_request_budget == budget
    for invalid in ('-1', 'true', '2.5'):
        path.write_text(f'[research]\ncna_request_budget = {invalid}\n')
        with pytest.raises(ConfigError, match='research.cna_request_budget'):
            load_config(path)


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
    assert all(unit.prompt.startswith((style.split('\n## 三、', 1)[0] if unit.stage == 'edit' else style) + '\n')
               for unit in units)
    assert '泛論「中國影響力擴大，所以台灣受影響」為 0' in units[0].prompt
    assert '待查證的暫定判斷' in units[0].prompt
    assert '必須保留發言者歸屬與時點' in units[-1].prompt
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


def test_ordinary_house_style_verbs_do_not_trigger_the_new_name_guard() -> None:
    assert valid_title('全球瘋抹茶帶動增產　日本茶農迎中國低價競爭',
                       {'title_zh': '全球抹茶熱潮助日本茶農翻身，鹿兒島產量躍居第一與中國競爭威脅'})
    assert valid_title('川普有意再晤金正恩　北韓堅持擁核考驗美朝外交',
                       {'title_zh': '川普有意重啟與金正恩峰會，北韓堅持擁核考驗美朝外交'})
    assert not valid_title('柏南自詡政治異端　挑戰主流政見實為迎合民粹',
                           {'title': 'Andy Burnham, faux heretic', 'title_zh': '包漢姆自詡政治異端，迎合民粹'})


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
    assert summaries['a1'].headline_zh == EDITOR_INPUT['headline_zh']
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
    assert len(units) > 1 and all(unit.prompt_bytes <= 9_000 and len(unit.article_ids) <= 10 for unit in units)
    assert sum(len(unit.article_ids) for unit in units) == 70


NATURAL_HEADLINE = '美國盼建立AI危機熱線，但中國態度冷淡，使雙方在危機應變機制上的互信仍面臨挑戰。'


@pytest.mark.parametrize('candidate,expected', [
    (NATURAL_HEADLINE, True),
    ('政策' * 15 + '。', True),
    ('政策' * 30 + '。', True),
    ('政策' * 31 + '。', False),
    ('政策' * 14 + '。', False),
    ('美中AI危機熱線　中國態度冷淡', False),
    (NATURAL_HEADLINE.replace('，', '　'), False),
    (NATURAL_HEADLINE[:-1], False),
    (NATURAL_HEADLINE.replace('，', '。'), False),
    (NATURAL_HEADLINE.replace('。', '？'), False),
    ('\n' + NATURAL_HEADLINE, False),
])
def test_editor_headline_is_one_complete_sentence(candidate, expected):
    assert valid_headline(candidate, EDITOR_INPUT, '美盼建AI危機專線　中國態度冷淡') == expected


def test_editor_keeps_previous_headline_and_checks_accepted_title(analysis_config):
    source = issue([replace(article('a1'), title=EDITOR_INPUT['title'], rubric='')])
    classes = {'a1': Classification('a1', 0, False, None, 'tech', '美盼建AI危機專線　中國態度冷淡', tier='C')}
    summaries = {'a1': ArticleSummary('a1', 'C', NATURAL_HEADLINE)}
    inputs = editor_items(source, classes, summaries, None)
    for candidate in ('地方首長守民主防線　市政廳成抵禦威權關鍵堡壘',
                      classes['a1'].title_zh, classes['a1'].title_zh + '。'):
        apply_edits({'items': [{'id': 'a1', 'headline_zh': candidate}]}, inputs, classes, summaries, None)
        assert summaries['a1'].headline_zh == NATURAL_HEADLINE
    assert not valid_headline(NATURAL_HEADLINE, inputs[0], NATURAL_HEADLINE[:-1])
    candidate = NATURAL_HEADLINE.replace('但中國態度冷淡', '中國態度仍冷淡')
    apply_edits({'items': [{'id': 'a1', 'headline_zh': candidate}]}, inputs, classes, summaries, None)
    assert summaries['a1'].headline_zh == candidate


@pytest.mark.parametrize('failure', ['downgrade', 'invalid-basis', 'unavailable'])
def test_substantive_taiwan_history_survives_grounding(analysis_config, tmp_path, failure):
    body = 'The presidential hotline was established in 1998 after the Taiwan Strait crisis of 1996.'
    source = issue([article('a1', paragraphs=[body])])
    link = '原文回顧 1996 年台海危機後，美中在 1998 年建立元首熱線。'
    classes = {'a1': Classification('a1', 3, True, link, 'tech', '美盼建AI危機專線　中國態度冷淡', tier='C')}
    summaries = {'a1': ArticleSummary('a1', 'C', NATURAL_HEADLINE, taiwan_implications=['沒有根據的推論'])}
    cna = CNAClient(tmp_path / 'research')
    cna.retrieve = lambda _: []
    proposed = {'articles': [{'article_id': 'a1', 'taiwan_level': 0 if failure == 'downgrade' else 3,
                              'taiwan_link': None if failure == 'downgrade' else
                              {'text_zh': '缺乏根據。', 'basis': ['cna999']}, 'taiwan_implications': []}]}
    fake = FakeLLMClient(lambda prompt, model, stage:
                         (LLMError('unavailable', kind='quota') if failure == 'unavailable' else proposed)
                         if stage == 'ground' else answer(prompt, model, stage))
    ground_digest(source, classes, summaries, [], analysis_config, UnitRunner(fake, tmp_path / 'analysis'), cna, [])
    assert classes['a1'].taiwan_level == 3 and classes['a1'].taiwan_link == link
    assert classes['a1'].sources == [] and summaries['a1'].taiwan_implications == []
    assert summaries['a1'].headline_zh == NATURAL_HEADLINE


@pytest.mark.parametrize('link', ['（推論）尚需證據的機制。', '台灣關聯待確認。'])
def test_unverified_signal_or_inference_does_not_get_grounding_floor(analysis_config, link):
    source = issue([article('a1', paragraphs=['Taiwan is mentioned.'])])
    classes = {'a1': Classification('a1', 3, True, link, 'tech', '合成標題', tier='C')}
    data = {'articles': [{'article_id': 'a1', 'taiwan_level': 0, 'taiwan_link': None, 'taiwan_implications': []}]}
    apply_grounding(data, source, classes, {}, {'a1': []}, analysis_config, [])
    assert classes['a1'].taiwan_level == 0


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


@pytest.mark.parametrize('proposed', [0, 1, 2, 3])
def test_focus_keeps_level_zero_and_applies_only_valid_implications(analysis_config: Config, proposed: int) -> None:
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', 0, False, None, 'tech', '合成標題', tier='A')}
    summaries = {'a1': ArticleSummary('a1', 'A', '原摘要')}
    evidence = {'a1': [sample_evidence()]}
    data = {'articles': [{'article_id': 'a1', 'taiwan_level': proposed,
                          'taiwan_link': {'text_zh': '（推論）具體合成關聯。', 'basis': ['cna1']},
                          'taiwan_implications': [{'text_zh': '（推論）合成政策改變台灣企業成本。',
                                                   'basis': ['article', 'cna1']},
                                                  {'text_zh': '缺乏依據的意涵。', 'basis': ['unknown']}]}]}
    apply_grounding(data, source, classes, summaries, evidence, analysis_config, ['a1'])
    assert classes['a1'].taiwan_level == 0 and classes['a1'].taiwan_link is None
    assert classes['a1'].tier == summaries['a1'].tier == 'A' and classes['a1'].sources == []
    assert summaries['a1'].taiwan_implications == ['（推論）合成政策改變台灣企業成本。']
    assert summaries['a1'].sources == [sample_evidence().source]
    from econ_digest.models import Digest
    digest = Digest(source.issue_date, '2026-10-05T00:00:00Z', source, classes, summaries, None, None,
                    focus_ids=['a1'])
    assert [(section.anchor, [entry.article.id for entry in section.entries])
            for section in sections(digest)] == [('focus', ['a1'])]


@pytest.mark.parametrize('provisional, proposed, final', [
    (1, 0, 0), (1, 1, 1), (1, 2, 2), (1, 3, 3),
    (2, 0, 0), (2, 1, 2), (2, 2, 2), (2, 3, 3),
    (3, 0, 0), (3, 1, 3), (3, 2, 3), (3, 3, 3),
])
def test_grounding_cannot_promote_an_article_subject_from_external_context(analysis_config, provisional, proposed, final):
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', provisional, False, '合成關聯', 'tech', '合成標題', tier='C')}
    data = {'articles': [{'article_id': 'a1', 'taiwan_level': proposed,
                          'taiwan_link': {'text_zh': '歷史事件為具體關聯。', 'basis': ['article']},
                          'taiwan_implications': []}]}
    apply_grounding(data, source, classes, {}, {'a1': []}, analysis_config, [])
    assert classes['a1'].taiwan_level == final


@pytest.mark.parametrize('text', ['合成政策改變台灣企業成本。', '（推論）合成政策改變台灣企業成本。'])
def test_no_mention_grounded_link_starts_with_inference_label(analysis_config, text):
    source = issue([article('a1')])
    classes = {'a1': Classification('a1', 3, False, '暫定關聯', 'tech', '合成標題', tier='C')}
    evidence = {'a1': [sample_evidence()]}
    data = {'articles': [{'article_id': 'a1', 'taiwan_level': 3,
                          'taiwan_link': {'text_zh': text, 'basis': ['cna1']}, 'taiwan_implications': []}]}
    apply_grounding(data, source, classes, {}, evidence, analysis_config, [])
    assert classes['a1'].taiwan_link == '（推論）合成政策改變台灣企業成本。'
    assert classes['a1'].sources == [sample_evidence().source]


def test_ground_prompt_lists_fixed_zero_articles_and_requires_main_subject(analysis_config):
    source = issue([article(f'a{i}') for i in range(1, 5)])
    classes = {a.id: Classification(a.id, 3 if a.id == 'a2' else 0, False, None,
                                  'tech', '合成標題', tier='A') for a in source.articles}
    units = grounding_units(source, list(classes), classes, {}, {a.id: [] for a in source.articles}, analysis_config)
    assert [payload(unit.prompt, '本批次等級固定為 0 的文章 id：') for unit in units] == [['a1', 'a3'], ['a4']]
    for unit in units:
        assert unit.prompt_bytes <= 90_000 and len(unit.article_ids) <= 3
        assert 'taiwan_level 必須為 0、taiwan_link 必須為 null，不得升級' in unit.prompt
        assert '必須從文章的主要主題直接推導' in unit.prompt
        assert '原文僅順帶提及的另一事件' in unit.prompt
        assert '伊朗戰爭 → 美國軍備庫存 → 對台軍售交付' in unit.prompt
        assert '有疑慮就不寫' in unit.prompt
        assert '標記「（推論）」' in unit.prompt and '每個 basis 是非空清單' in unit.prompt


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
    alert = {'fact': '合成舊值', 'suspected_new_value': '合成新值',
             'evidence_url': ev.source.url, 'evidence_title': ev.source.title}
    data = {'alerts': [alert, {**alert, 'evidence_url': 'https://example.invalid'}, {'fact': '沒有證據'}]}
    validate_fact_alerts(data, {ev.source.url: ev.source.title})
    assert data['alerts'] == [alert]
    cna = CNAClient(tmp_path / 'research')
    retrieved = []
    cna.retrieve_search = lambda queries: retrieved.append(queries) or [ev]
    cna.retrieve = lambda _: pytest.fail('facts checks must not fetch article pages')
    client = FakeLLMClient(lambda *args: {'alerts': [alert]})
    runner = UnitRunner(client, tmp_path / 'analysis')
    assert check_facts('2026.10.03', analysis_config, runner, cna, []) == [alert]
    assert len(retrieved[0]) == 6
    assert check_facts('2026.10.03', analysis_config, runner, cna, []) == [alert]
    assert len(client.calls) == len(retrieved) == 1
    check_facts('2026.10.10', analysis_config, runner, cna, [])
    assert len(client.calls) == 2


@pytest.mark.parametrize('change', [
    {'evidence_url': 'https://www.cna.com.tw/news/aipl/202610020001.aspx'},
    {'evidence_url': 'https://example.invalid', 'evidence_title': '合成友邦報導'},
    {'evidence_url': 'https://www.cna.com.tw/news/aipl/202610030001.aspx'},
    {'evidence_title': '另一則合成證據'},
    {'evidence_title': '改寫後的合成友邦報導'},
    {'evidence_title': ' 合成友邦報導'},
    {'evidence_title': ''}, {'evidence_title': None},
])
def test_fact_alert_rejects_unknown_or_mismatched_evidence_pair(change):
    ev = sample_evidence()
    alert = {'fact': '合成舊值', 'suspected_new_value': '合成新值',
             'evidence_url': ev.source.url, 'evidence_title': ev.source.title}
    headlines = {ev.source.url: ev.source.title,
                 'https://www.cna.com.tw/news/aipl/202610030001.aspx': '另一則合成證據',
                 'https://example.invalid': ev.source.title}
    data = {'alerts': [{**alert, **change}, {key: value for key, value in alert.items() if key != 'evidence_title'}]}
    validate_fact_alerts(data, headlines)
    assert data['alerts'] == []


def test_facts_prompt_only_reports_completed_changes(analysis_config):
    unit = facts_unit('2026.10.03', [sample_evidence()], analysis_config)
    assert unit.prompt_bytes <= 90_000
    assert '已經完成的變動' in unit.prompt
    for phrase in ('已就職', '已辭職', '已斷交', '已三讀通過', '正式最終數據',
                   '競選演說', '背書', '提名', '民調', '預測', '計畫', '當選後', '若當選'):
        assert phrase in unit.prompt
    assert '選舉結果僅能在投票日當天或之後認定' in unit.prompt
    assert 'evidence_title 必須逐字等於該網址所附的 title' in unit.prompt


def test_facts_cache_revalidates_headline_against_supplied_evidence(analysis_config, tmp_path):
    from econ_digest.models import save_json
    ev = sample_evidence()
    alert = {'fact': '合成舊值', 'suspected_new_value': '合成新值',
             'evidence_url': ev.source.url, 'evidence_title': ev.source.title}
    cna = CNAClient(tmp_path / 'research')
    cna.retrieve_search = lambda _: [ev]
    runner = UnitRunner(FakeLLMClient(lambda *args: {'alerts': [alert]}), tmp_path / 'analysis')
    assert check_facts('2026.10.03', analysis_config, runner, cna, []) == [alert]
    path = runner.workdir / 'facts-check-2026.10.03.json'
    saved = json.loads(path.read_text())
    assert saved['headlines'] == {ev.source.url: ev.source.title}
    saved['alerts'][0]['evidence_title'] = '改寫的合成標題'
    save_json(path, saved)
    cna.retrieve_search = lambda _: pytest.fail('warm facts check must use saved evidence')
    assert check_facts('2026.10.03', analysis_config, runner, cna, []) == []


def test_evidence_headline_is_preserved_through_digest_normalisation_and_cache(analysis_config, tmp_path, monkeypatch):
    from econ_digest.analysis import pipeline
    from econ_digest.models import Digest, load_json
    ev = replace(sample_evidence(), source=replace(sample_evidence().source, title='合成報導："軟件"政策已三讀'))
    alert = {'fact': '合成政策尚未通過', 'suspected_new_value': '2026-10-01 已三讀通過',
             'evidence_url': ev.source.url, 'evidence_title': ev.source.title}
    monkeypatch.setattr(pipeline.CNAClient, 'retrieve_search', lambda *args: [ev])
    monkeypatch.setattr(pipeline.CNAClient, 'retrieve', lambda *args: [])
    fake = FakeLLMClient(lambda prompt, model, stage: {'alerts': [alert]} if stage == 'facts'
                         else answer(prompt, model, stage))
    source = issue([article('a1')])
    cache = tmp_path / 'analysis'
    digest = pipeline.analyze_issue(source, analysis_config, fake, workdir=cache)
    assert digest.fact_alerts[0]['evidence_title'] == ev.source.title
    saved = load_json(analysis_config.paths.data_dir / 'issues' / 'te_2026.10.03' / 'digest.json', Digest)
    assert saved.fact_alerts == digest.fact_alerts
    warm = FakeLLMClient(lambda *args: pytest.fail('warm analysis must use the cache'))
    assert pipeline.analyze_issue(source, analysis_config, warm, workdir=cache).fact_alerts == digest.fact_alerts
