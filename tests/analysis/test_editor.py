from __future__ import annotations

from dataclasses import replace

import pytest

from econ_digest.analysis.editor import apply_edits, edit_units, editor_items, faithful_text
from econ_digest.models import Argument, ArticleSummary, BriefItem, Classification, Quote, WeekBrief
from conftest import article, issue


@pytest.mark.parametrize('word', [
    '暗藏', '青睞', '困境', '積極', '致命弱點', '亟待大刀闊斧', '徒勞無功',
    '切勿', '表現', '立意崇高',
])
def test_ordinary_new_vocabulary_is_allowed(word):
    assert faithful_text(f'政策{word}。', {'title_zh': '政策仍須改善'})


@pytest.mark.parametrize('fact', ['史塔默', '柏南', '拉加德', '羅德里格斯', '馬斯克', '17年', '習近平'])
def test_new_facts_require_source_support(fact):
    original = {'title_zh': '川普宣布政策'}
    candidate = f'{fact}政策仍待改善。'
    assert not faithful_text(candidate, original)
    assert faithful_text(candidate, {**original, 'headline_zh': f'政策涉及{fact}。'})


def test_name_characters_must_occur_as_a_consecutive_run_in_source():
    assert not faithful_text('史塔默公布政策。', {'title_zh': '史料記述高塔與沉默'})


def test_existing_name_spelling_is_normalized_on_both_sides():
    assert faithful_text('米雷伊公布新政策。', {'text_zh': '米雷伊公布政策。'})
    assert faithful_text('米萊公布新政策。', {'text_zh': '米雷公布政策。'})
    assert not faithful_text('米雷伊公布新政策。', {'text_zh': '政府公布政策。'})


@pytest.mark.parametrize('role', ['先生', '女士', '總統', '總理', '部長', '執行長', '主席'])
@pytest.mark.parametrize('name', ['王某', '林允中', '張孟思雨'])
def test_new_short_name_followed_by_new_role_is_rejected(name, role):
    candidate = f'{name}{role}公布政策。'
    assert not faithful_text(candidate, {'title_zh': '政府公布政策'})
    assert faithful_text(candidate, {'title_zh': f'{name}公布政策'})
    assert faithful_text(candidate, {'title_zh': f'{role}公布政策'})


def fixture_articles():
    source = issue([article('a1'), article('a2')])
    classes = {a.id: Classification(a.id, 0, False, None, 'culture', '政府宣布政策仍待改善', tier='C')
               for a in source.articles}
    summaries = {a.id: ArticleSummary(a.id, 'C', '政府宣布政策仍待改善。') for a in source.articles}
    return source, classes, summaries


TITLE = '史塔默公布17年政策仍待改善'
HEADLINE = '史塔默公布17年政策，政府認為立意崇高卻暗藏致命弱點，因此亟待大刀闊斧改善。'
FACTS = '史塔默於17年公布政策。'


@pytest.mark.parametrize('field', [
    'summary_zh', 'key_points', 'background', 'structure', 'claim', 'evidence',
    'counterpoints', 'conclusion', 'key_data', 'quotes', 'stance', 'leader_stance',
])
def test_all_summary_fields_support_title_and_headline_facts(field):
    source, classes, summaries = fixture_articles()
    summary = summaries['a1']
    if field in {'claim', 'evidence', 'counterpoints', 'conclusion'}:
        summary.argument = Argument('', [], [], '')
        setattr(summary.argument, field, [FACTS] if field in {'evidence', 'counterpoints'} else FACTS)
    elif field == 'quotes':
        summary.quotes = [Quote('A synthetic quotation.', FACTS)]
    else:
        setattr(summary, field, [FACTS] if field in {'key_points', 'structure', 'key_data'} else FACTS)
    inputs = editor_items(source, classes, summaries, None)
    assert not faithful_text(TITLE, inputs[0])
    apply_edits({'items': [{'id': 'a1', 'title_zh': TITLE, 'headline_zh': HEADLINE}]},
                inputs, classes, summaries, None)
    assert classes['a1'].title_zh == TITLE
    assert summary.headline_zh == HEADLINE


@pytest.mark.parametrize('field', ['headline_zh', 'summary_zh', 'leader_stance'])
def test_merged_leader_uses_companion_summary(field):
    source, classes, summaries = fixture_articles()
    source.articles[0] = replace(source.articles[0], kind='leader')
    classes['a1'].companion_id = 'a2'
    setattr(summaries['a2'], field, FACTS)
    inputs = editor_items(source, classes, summaries, None)
    apply_edits({'items': [{'id': 'a1', 'title_zh': TITLE, 'headline_zh': HEADLINE}]},
                inputs, classes, summaries, None)
    assert classes['a1'].title_zh == TITLE
    assert summaries['a1'].headline_zh == HEADLINE


@pytest.mark.parametrize('field', ['quotes', 'sources', 'taiwan_implications', 'further_questions', 'other_article'])
def test_unrelated_context_does_not_license_article_facts(field):
    source, classes, summaries = fixture_articles()
    if field == 'quotes':
        summaries['a1'].quotes = [Quote(FACTS, '政策需要改善。')]
    elif field == 'sources':
        from econ_digest.models import Source
        summaries['a1'].sources = [Source(FACTS, '17', FACTS, 'https://example.invalid/17')]
    elif field == 'other_article':
        summaries['a2'].summary_zh = FACTS
    else:
        setattr(summaries['a1'], field, [FACTS])
    previous = classes['a1'].title_zh, summaries['a1'].headline_zh
    apply_edits({'items': [{'id': 'a1', 'title_zh': TITLE, 'headline_zh': HEADLINE}]},
                editor_items(source, classes, summaries, None), classes, summaries, None)
    assert (classes['a1'].title_zh, summaries['a1'].headline_zh) == previous


def test_summary_context_does_not_license_new_english_tokens():
    source, classes, summaries = fixture_articles()
    summaries['a1'].summary_zh = 'Orbit 政策需要改善。'
    original = classes['a1'].title_zh
    apply_edits({'items': [{'id': 'a1', 'title_zh': 'Orbit 政策立意崇高卻暗藏致命弱點'}]},
                editor_items(source, classes, summaries, None), classes, summaries, None)
    assert classes['a1'].title_zh == original


def test_summary_source_does_not_change_editor_units_or_cache_keys(analysis_config):
    source, classes, summaries = fixture_articles()
    before = edit_units(source, classes, summaries, None, analysis_config)
    summaries['a1'].summary_zh = FACTS
    summaries['a2'].leader_stance = FACTS
    classes['a1'].companion_id = 'a2'
    after = edit_units(source, classes, summaries, None, analysis_config)
    assert [(unit.prompt, unit.cache_key) for unit in before] == [(unit.prompt, unit.cache_key) for unit in after]


def test_brief_items_use_only_their_own_previous_text():
    source, classes, summaries = fixture_articles()
    summaries['a1'].summary_zh = FACTS
    classes['a1'].title_zh = FACTS
    brief = WeekBrief([BriefItem('政府公布政策。'), BriefItem(FACTS)], [BriefItem('政府公布政策。')])
    inputs = editor_items(source, classes, summaries, brief)
    apply_edits({'items': [
        {'id': 'brief-politics-0', 'text_zh': FACTS},
        {'id': 'brief-politics-1', 'text_zh': '史塔默的17年政策暗藏致命弱點。'},
        {'id': 'brief-business-0', 'text_zh': '政府政策立意崇高卻暗藏致命弱點。'},
    ]}, inputs, classes, summaries, brief)
    assert brief.politics[0].text_zh == '政府公布政策。'
    assert brief.politics[1].text_zh == '史塔默的17年政策暗藏致命弱點。'
    assert brief.business[0].text_zh == '政府政策立意崇高卻暗藏致命弱點。'


def test_invalid_field_falls_back_independently():
    source, classes, summaries = fixture_articles()
    inputs = editor_items(source, classes, summaries, None)
    previous_title = classes['a1'].title_zh
    valid_headline = HEADLINE.replace('史塔默公布17年', '政府公布')
    apply_edits({'items': [{'id': 'a1', 'title_zh': TITLE, 'headline_zh': valid_headline}]},
                inputs, classes, summaries, None)
    assert classes['a1'].title_zh == previous_title
    assert summaries['a1'].headline_zh == valid_headline
    valid_title = '政府政策立意崇高卻暗藏致命弱點'
    apply_edits({'items': [{'id': 'a1', 'title_zh': valid_title, 'headline_zh': HEADLINE}]},
                inputs, classes, summaries, None)
    assert classes['a1'].title_zh == valid_title
    assert summaries['a1'].headline_zh == valid_headline
