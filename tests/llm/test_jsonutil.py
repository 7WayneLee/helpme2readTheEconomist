import pytest

from econ_digest.llm.jsonutil import extract_json_object


@pytest.mark.parametrize("text,expected", [
    ('{"ok":true}', {"ok": True}),
    ('  ```json\n{"ok":true}\n```  ', {"ok": True}),
    ('```\n{"ok":true}\n```', {"ok": True}),
    ('```JSON\n{"ok":true}\n```', {"ok": True}),
    ('Result follows {"nested":{"list":[{},2]}}\nEnd.', {"nested": {"list": [{}, 2]}}),
    ('{"text":"literal } and { inside string"} commentary', {"text": "literal } and { inside string"}),
    (r'{"text":"escaped quote \" and backslash \\"}', {"text": 'escaped quote " and backslash \\'}),
    ('{"text":"正體中文"} trailing {"second":false}', {"text": "正體中文"}),
    ('Intro\n```json\n{"ok":true}\n```\nAfter', {"ok": True}),
    ('He said "a {brace}" before {"ok":true}', {"ok": True}),
])
def test_extract_objects(text: str, expected: dict) -> None:
    assert extract_json_object(text) == expected


@pytest.mark.parametrize("text,message", [
    ("", "No JSON object"), ("No object", "No JSON object"),
    ("[]", "must be an object"), ('[{"ok":true}]', "must be an object"),
    ("null", "must be an object"), ('"string"', "must be an object"),
    ("{bad json}", "Invalid JSON object"), ('{"ok": }', "Invalid JSON object"),
    ('{"nested":{}} trailing', ""),
    ('{"ok":true', "Unterminated JSON object"), ('{"text":"}"', "Unterminated JSON object"),
])
def test_useful_errors(text: str, message: str) -> None:
    if not message:
        assert extract_json_object(text) == {"nested": {}}
    else:
        with pytest.raises(ValueError, match=message):
            extract_json_object(text)


def test_non_text_output() -> None:
    with pytest.raises(ValueError, match="must be text"):
        extract_json_object(None)  # type: ignore[arg-type]
