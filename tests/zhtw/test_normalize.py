import copy
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from econ_digest.zhtw import DEFAULT_SKIP_KEYS, lint_zh_tw, normalize_tree, normalize_zh_tw
from econ_digest.zhtw import normalize as normalizer


@pytest.fixture
def no_opencc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(normalizer.shutil, "which", lambda executable: None)
    monkeypatch.setattr(normalizer, "_warned_opencc", False)


@pytest.mark.usefixtures("no_opencc")
@pytest.mark.parametrize("source,target", [
    ("視頻和軟件在網絡上傳送", "影片和軟體在網路上傳送"),
    ("人工智能芯片和服務器數據庫", "人工智慧晶片和伺服器資料庫"),
    ("特朗普、普京、澤連斯基、馬克龍", "川普、普丁、澤倫斯基、馬克宏"),
    ("英偉達與臺積電在硅谷", "輝達與台積電在矽谷"),
    ("新西蘭、澳大利亞、意大利、加沙", "紐西蘭、澳洲、義大利、加薩"),
    ("日元、美聯儲、首席執行官", "日圓、聯準會、執行長"),
    ("數據、信息、項目、質量、支持、優化、哈里斯", "數據、信息、項目、質量、支持、優化、哈里斯"),
])
def test_glossary_and_ambiguous_words(source: str, target: str) -> None:
    assert normalize_zh_tw(source) == target


@pytest.mark.usefixtures("no_opencc")
def test_longest_match_precedence() -> None:
    assert normalize_zh_tw("視頻會議、視頻通話、打印機、巡航導彈、超鏈接、固態硬盤") == (
        "視訊會議、視訊通話、印表機、巡弋飛彈、超連結、固態硬碟"
    )


@pytest.mark.usefixtures("no_opencc")
def test_english_text_is_preserved() -> None:
    text = 'Trump said "software", not “hardware”. Python, Taiwan, database, 123. Bitcoin.'
    assert normalize_zh_tw(text) == text


@pytest.mark.usefixtures("no_opencc")
def test_traditional_tai_character_is_preserved_except_glossary() -> None:
    assert normalize_zh_tw("臺灣、臺北、平臺、舞臺、臺積電") == "臺灣、臺北、平臺、舞臺、台積電"


@pytest.mark.usefixtures("no_opencc")
@pytest.mark.parametrize("text,expected", [
    ('“中文”與"中文"', "「中文」與「中文」"),
    ('“English only” and "English only"', '“English only” and "English only"'),
    ('“AI 晶片” and "chip 晶片"', '「AI 晶片」 and 「chip 晶片」'),
    ('“123，。” "123!"', '“123，。” "123!"'),
    ('“” ""', '“” ""'),
    ('已有「中文」和『中文』', '已有「中文」和『中文』'),
    ('未完成“中文', '未完成“中文'),
    ('“多行\n中文”', '「多行\n中文」'),
    ('"多行\n中文"', '「多行\n中文」'),
    ('"他說“你好”"', '「他說「你好」」'),
    (r'"中文 with \"quote\""', r'「中文 with \"quote\"」'),
])
def test_quote_conversion(text: str, expected: str) -> None:
    assert normalize_zh_tw(text) == expected


@pytest.mark.usefixtures("no_opencc")
def test_tree_skip_keys_and_deep_copy() -> None:
    value = {
        "summary": "特朗普使用軟件", "en": "特朗普 uses 軟件",
        "example_en": ["軟件", {"summary": "特朗普"}],
        "nested": [{"title": "視頻", "article_id": "視頻-01"}],
        "model": "網絡", "count": 2, "none": None,
    }
    original = copy.deepcopy(value)
    result = normalize_tree(value)
    assert value == original
    assert result["summary"] == "川普使用軟體"
    assert result["en"] == value["en"]
    assert result["example_en"] == value["example_en"]
    assert result["example_en"] is not value["example_en"]
    assert result["example_en"][1] is not value["example_en"][1]
    assert result["nested"] == [{"title": "影片", "article_id": "視頻-01"}]
    assert result["nested"] is not value["nested"]
    assert result["model"] == "網絡"
    result["nested"][0]["title"] = "changed"
    assert value["nested"][0]["title"] == "視頻"


@pytest.mark.usefixtures("no_opencc")
@pytest.mark.parametrize("key", sorted(DEFAULT_SKIP_KEYS))
def test_each_default_skip_key(key: str) -> None:
    assert normalize_tree({key: "特朗普軟件", "summary": "特朗普軟件"}) == {
        key: "特朗普軟件", "summary": "川普軟體",
    }


@pytest.mark.usefixtures("no_opencc")
def test_custom_skip_keys_replace_defaults() -> None:
    assert normalize_tree({"custom": "軟件", "en": "軟件"}, skip_keys=frozenset({"custom"})) == {
        "custom": "軟件", "en": "軟體",
    }
    assert normalize_tree("軟件") == "軟體"
    assert normalize_tree(["軟件", ("視頻",)]) == ["軟體", ("影片",)]


def test_tree_batches_probe_and_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(normalizer.shutil, "which", lambda executable: "/usr/bin/opencc")

    def convert(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args[:2] == ["/usr/bin/opencc", "-c"] and args[2] in {"s2t", "s2tw"}
        assert kwargs["check"] is True
        calls.append(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout=kwargs["input"].replace("国", "國").replace("台", "臺"))

    monkeypatch.setattr(normalizer.subprocess, "run", convert)
    value = {"title": "中国台灣", "entries": ["視頻\n多行", "軟件", ""], "en": "SKIPPED中国"}
    result = normalize_tree(value)
    assert len(calls) == 2
    assert all("SKIPPED中国" not in call["input"] for call in calls)
    assert calls[0]["input"] == "国"
    assert result == {"title": "中國台灣", "entries": ["影片\n多行", "軟體", ""], "en": "SKIPPED中国"}


def test_broken_separator_preserves_original_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs: list[str] = []
    monkeypatch.setattr(normalizer.shutil, "which", lambda executable: "opencc")

    def convert(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        inputs.append(kwargs["input"])
        converted = kwargs["input"].replace("ECON_DIGEST_SEPARATOR_", "BROKEN_SEPARATOR_").replace("国", "國")
        return subprocess.CompletedProcess(args, 0, stdout=converted)

    monkeypatch.setattr(normalizer.subprocess, "run", convert)
    assert normalize_tree(["中国", "国際"]) == ["中国", "国際"]
    assert len(inputs) == 2


def test_empty_tree_makes_no_subprocess_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("OpenCC should not be invoked for an empty tree")

    monkeypatch.setattr(normalizer.subprocess, "run", forbidden)
    assert normalize_tree({"count": 2, "en": "英文"}) == {"count": 2, "en": "英文"}


@pytest.mark.usefixtures("no_opencc")
def test_missing_opencc_warns_once_and_still_applies_glossary(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert normalize_tree(["軟件说", "視頻"]) == ["軟體说", "影片"]
        assert normalize_zh_tw("特朗普") == "川普"
    assert len([record for record in caplog.records if "OpenCC conversion skipped" in record.message]) == 1


@pytest.mark.parametrize("exception", [FileNotFoundError("missing"), subprocess.CalledProcessError(1, "opencc"), subprocess.TimeoutExpired("opencc", 30)])
def test_opencc_failures_are_graceful(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, exception: Exception) -> None:
    monkeypatch.setattr(normalizer.shutil, "which", lambda executable: "opencc")
    monkeypatch.setattr(normalizer, "_warned_opencc", False)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise exception

    monkeypatch.setattr(normalizer.subprocess, "run", fail)
    with caplog.at_level(logging.WARNING):
        assert normalize_tree(["視頻说", "軟件"]) == ["影片说", "軟體"]
    assert len(caplog.records) == 1


@pytest.mark.skipif(shutil.which("opencc") is None, reason="OpenCC CLI is not installed")
def test_real_opencc_conversion() -> None:
    assert normalize_zh_tw('特朗普说："台湾的芯片和软件通过网络传送视频。"') == (
        "川普說：「台灣的晶片和軟體通過網路傳送影片。」"
    )


@pytest.mark.skipif(shutil.which("opencc") is None, reason="OpenCC CLI is not installed")
def test_real_opencc_glossary_and_preferred_forms() -> None:
    sources = [source for source, _ in normalizer._GLOSSARY]
    targets = [target for _, target in normalizer._GLOSSARY]
    assert normalize_tree(sources) == targets
    assert normalize_tree(targets) == targets


def test_lint_glossary_terms_and_simplified_characters() -> None:
    warnings = lint_zh_tw("特朗普用軟件说话，问题还没解决。")
    assert any("川普" in warning for warning in warnings)
    assert any("軟體" in warning for warning in warnings)
    assert any("簡體字" in warning and "说" in warning and "题" in warning for warning in warnings)
    assert lint_zh_tw("台灣的晶片、網路與軟體演算法。") == []
    assert lint_zh_tw("English software, Trump and Taiwan.") == []
    assert lint_zh_tw("里干范托后台面系制准云只才斗于") == []


@pytest.mark.usefixtures("no_opencc")
def test_glossary_integrity_and_idempotence() -> None:
    path = Path(normalizer.__file__).with_name("glossary.tsv")
    rows = [line.split("\t") for line in path.read_text().splitlines() if line and not line.startswith("#")]
    assert len(rows) >= 150
    assert all(len(row) == 3 and row[0] and row[1] and row[2] for row in rows)
    assert len({row[0] for row in rows}) == len(rows)
    assert {"項目", "質量", "數據", "信息", "支持", "優化", "哈里斯"}.isdisjoint(row[0] for row in rows)
    for source, target, _ in rows:
        assert normalize_zh_tw(source) == target, source
        assert normalize_zh_tw(target) == target, target


@pytest.mark.parametrize("text", ["曼蘇里", "魯托", "范德賴恩", "干預", "于坦",
                                  "臺灣的企業採取措施，保護供應鏈。",
                                  'The firms met in Alaska. "Policy" matters.'])
def test_correct_traditional_and_english_skip_opencc(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Correct Traditional and English must bypass OpenCC")

    monkeypatch.setattr(normalizer.subprocess, "run", forbidden)
    assert normalize_zh_tw(text).encode("utf-8") == text.encode("utf-8")


@pytest.mark.skipif(shutil.which("opencc") is None, reason="OpenCC CLI is not installed")
@pytest.mark.parametrize("source,target", [
    ("特朗普和普京在阿拉斯加会面", "川普和普丁在阿拉斯加會面"),
    ("他說这个計畫很复杂", "他說這個計畫很複雜"),
])
def test_simplified_run_converts_all_neighbours(source: str, target: str) -> None:
    assert normalize_zh_tw(source) == target


def test_cjk_runs_end_at_punctuation_whitespace_latin_and_digits(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs: list[str] = []
    monkeypatch.setattr(normalizer.shutil, "which", lambda _: "opencc")

    def convert(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        inputs.append(kwargs["input"])
        return subprocess.CompletedProcess(args, 0, stdout=kwargs["input"].replace("国", "國").replace("臺", "台").replace("干", "幹"))

    monkeypatch.setattr(normalizer.subprocess, "run", convert)
    source = "干預，国臺 灣国X国2国；曼蘇里、魯托、范德賴恩、于坦、臺灣"
    assert normalize_tree([source, "国"]) == [
        "干預，國台 灣國X國2國；曼蘇里、魯托、范德賴恩、于坦、臺灣", "國"]
    assert len(inputs) == 2
    assert inputs[0] == "国"
    assert all(text not in inputs[1] for text in ("干預", "曼蘇里", "魯托", "范德賴恩", "于坦", "臺灣"))


@pytest.mark.usefixtures("no_opencc")
def test_cp950_fallback_detector_and_lint_cover_requested_characters() -> None:
    flagged = "们这说时为国会对发经过还进现间东车长书买卖门问题让认识语读谁调资质报纸边产业务决议选举头历钟汇获团战总统热线军队冲苏"
    assert all(normalizer._is_simplified(character) for character in flagged)
    assert not any(normalizer._is_simplified(character) for character in "里干范托后台面系制准云只才斗于臺灣蘇魯")
    for character in ("\u3400", "\uf900", "\U00020000", "\U0002fa1f"):
        assert normalizer._is_simplified(character)
        assert any(character in warning for warning in lint_zh_tw(character))
    assert not normalizer._is_simplified("😀")


def test_non_big5_traditional_characters_use_one_s2t_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(normalizer.shutil, "which", lambda _: "opencc")

    def convert(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args[2], kwargs["input"]))
        return subprocess.CompletedProcess(args, 0, stdout=kwargs["input"].replace("国", "國").replace("说", "說"))

    monkeypatch.setattr(normalizer.subprocess, "run", convert)
    assert lint_zh_tw("肽、肽、国、说、国") == ["疑似殘留簡體字：国、说。"]
    assert calls == [("s2t", "国\n肽\n说")]
    calls.clear()
    assert normalize_tree(["肽", "肽", "台灣肽", "国肽", {"en": "SKIP说"}]) == [
        "肽", "肽", "台灣肽", "國肽", {"en": "SKIP说"}]
    assert calls[0] == ("s2t", "国\n肽")
    assert calls[1] == ("s2tw", "国肽")


@pytest.mark.skipif(shutil.which("opencc") is None, reason="OpenCC CLI is not installed")
def test_real_opencc_preserves_traditional_peptide_character() -> None:
    assert lint_zh_tw("肽") == []
    assert normalize_tree(["肽", "胜肽", "胜肽和软件"]) == ["肽", "胜肽", "胜肽和軟體"]
    assert any("说" in warning for warning in lint_zh_tw("肽说话"))


@pytest.mark.usefixtures("no_opencc")
def test_missing_opencc_keeps_big5_fallback() -> None:
    assert lint_zh_tw("肽国") == ["疑似殘留簡體字：国、肽。"]


@pytest.mark.usefixtures("no_opencc")
def test_leaders_label_replaced_in_every_zh_field() -> None:
    value = {"reason_zh": "典型社論的清晰論證結構", "nested": [{"note_zh": "社論。"}],
             "example_en": "社論", "sentence_en": "社論"}
    assert normalize_tree(value) == {"reason_zh": "典型經濟學人立場的清晰論證結構",
                                    "nested": [{"note_zh": "經濟學人立場。"}],
                                    "example_en": "社論", "sentence_en": "社論"}


@pytest.mark.skipif(shutil.which("opencc") is None, reason="OpenCC CLI is not installed")
def test_leaders_label_replaced_after_opencc() -> None:
    assert normalize_zh_tw("社论的论点") == "經濟學人立場的論點"


@pytest.mark.usefixtures("no_opencc")
def test_unambiguous_hou_compounds_and_milei() -> None:
    assert normalize_zh_tw("以后、然后、之后、后来、最后、前后、背后、落后、后果；米雷伊") == (
        "以後、然後、之後、後來、最後、前後、背後、落後、後果；米雷")
