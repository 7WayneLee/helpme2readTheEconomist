"""Shape, depth, and source-fidelity checks used by the client's repair path."""

from __future__ import annotations

import re
from typing import Any

from ..config import EnglishConfig
from ..models import Article

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_PUNCTUATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                            "…": "...", "\u00ad": ""})


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def strings(value: Any, field: str, minimum: int, maximum: int) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{field} requires {minimum}–{maximum} items")
    for item in value:
        text(item, field)
    return value


def object_items(data: dict[str, Any], key: str, ids: set[str]) -> list[dict[str, Any]]:
    items = data.get(key)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f"{key} must be a list of objects")
    found = [item.get("article_id") for item in items]
    if any(not isinstance(identifier, str) for identifier in found) or len(found) != len(ids) or set(found) != ids:
        raise ValueError(f"{key}: every article_id must occur exactly once: {sorted(ids)}")
    return items


def canonical_english(value: str) -> str:
    value = " ".join(value.translate(_PUNCTUATION).split())
    value = re.sub(r"\s*-\s*", "-", value)
    return re.sub(r"\.\s*\.\s*\.", "...", value)


def source_contains(article: Article, excerpt: str, *, trimmed: bool = False) -> bool:
    source = canonical_english("\n".join(article.paragraphs))
    if not trimmed:
        return canonical_english(excerpt) in source
    parts = [part.strip() for part in canonical_english(excerpt).split("...")]
    parts = [part for part in parts if part]
    if not parts:
        return False
    offset = 0
    for part in parts:
        position = source.find(part, offset)
        if position < 0:
            return False
        offset = position + len(part)
    return True


def chinese_length(value: Any) -> int:
    if isinstance(value, str):
        return len(_CJK.findall(value))
    if isinstance(value, list):
        return sum(chinese_length(item) for item in value)
    if isinstance(value, dict):
        return sum(chinese_length(item) for key, item in value.items()
                   if key not in {"article_id", "tier", "en", "model"})
    return 0


def length(value: Any, field: str, minimum: int, maximum: int) -> None:
    count = chinese_length(value)
    if not minimum <= count <= maximum:
        raise ValueError(f"{field}: {count} Chinese characters; expected approximately {minimum}–{maximum}")


def validate_headline(value: Any, title: str | None = None) -> None:
    headline = text(value, "headline_zh")
    length(headline, "headline_zh", 30, 60)
    if (headline != headline.strip() or not headline.endswith("。")
            or headline.count("。") != 1 or any(mark in headline for mark in "\u3000\n\r!?！？")):
        raise ValueError("headline_zh must be one natural sentence ending with 。, without full-width spaces")
    if title is not None and re.sub(r"\W", "", headline) == re.sub(r"\W", "", text(title, "title_zh")):
        raise ValueError("headline_zh must differ from title_zh")


def validate_argument(value: Any, *, tier: str) -> None:
    if not isinstance(value, dict):
        raise ValueError("argument must be an object")
    text(value.get("claim"), "argument.claim")
    text(value.get("conclusion"), "argument.conclusion")
    strings(value.get("evidence"), "argument.evidence", 3 if tier == "A" else 2, 6 if tier == "A" else 4)
    strings(value.get("counterpoints"), "argument.counterpoints", 1 if tier == "A" else 0, 3 if tier == "A" else 2)


def validate_summary(item: dict[str, Any], article: Article, tier: str, *, leader: bool = False) -> None:
    headline = text(item.get("headline_zh"), "headline_zh")
    validate_headline(headline, item.get("title_zh"))
    if tier == "A":
        length(text(item.get("background"), "background"), "background", 100, 330)
        structure = strings(item.get("structure"), "structure", 4, 8)
        for part in structure:
            match = re.match(r"^第\s*(\d+)(?:\s*[–—−\-~～至]\s*(\d+))?\s*段[：:]", part)
            if not match or not 1 <= int(match[1]) <= int(match[2] or match[1]) <= len(article.paragraphs):
                raise ValueError("structure must start with a valid paragraph range, e.g. 第 1–2 段：")
        starts = [int(re.match(r"^第\s*(\d+)", part)[1]) for part in structure]
        if starts != sorted(starts):
            raise ValueError("structure must follow paragraph order")
        validate_argument(item.get("argument"), tier=tier)
        strings(item.get("key_data"), "key_data", 3, 6)
        quotes = item.get("quotes")
        if not isinstance(quotes, list) or any(not isinstance(quote, dict) for quote in quotes):
            raise ValueError("quotes must be a list of objects")
        kept = []
        for quote in quotes:
            en = text(quote.get("en"), "quotes.en")
            text(quote.get("zh"), "quotes.zh")
            if source_contains(article, en):
                kept.append(quote)
        item["quotes"] = kept
        if not 2 <= len(kept) <= 4:
            raise ValueError("quotes requires 2–4 verbatim source quotations; invented quotes were removed")
        stance = text(item.get("stance"), "stance")
        if not stance.startswith("立場分析"):
            raise ValueError("stance must be explicitly labelled 立場分析")
        length(stance, "stance", 65, 280)
        strings(item.get("further_questions"), "further_questions", 1, 2)
        length(item, "A total", 800, 2700)
    elif tier == "B":
        strings(item.get("key_points"), "key_points", 4, 6)
        validate_argument(item.get("argument"), tier=tier)
        length(item, "B total", 400, 1250)
    elif tier == "C":
        strings(item.get("key_points"), "key_points", 3, 5)
        length(item, "C total", 165, 550)
    elif tier == "D":
        summary = text(item.get("summary_zh"), "summary_zh")
        if not 2 <= len(re.findall(r"[。！？](?:[」』])?", summary)) <= 3:
            raise ValueError("D summary_zh requires 2–3 sentences")
        length(summary, "summary_zh", 50, 210)
    elif tier == "E":
        length(headline, "headline_zh", 30, 60)
    else:
        raise ValueError(f"Unsupported summary tier: {tier}")
    strings(item.get("taiwan_implications", []), "taiwan_implications", 0, 3)
    if leader:
        stance = text(item.get("leader_stance"), "leader_stance")
        if not stance.startswith("作者主張："):
            raise ValueError("leader_stance must start with 作者主張：")
        if not 2 <= len(re.findall(r"[。！？]", stance)) <= 3:
            raise ValueError("leader_stance requires 2–3 sentences")


_IRREGULAR_VERBS = {
    "arise": "arose arisen", "be": "am is are was were been being", "bear": "bore borne born",
    "beat": "beat beaten", "become": "became become", "begin": "began begun", "bend": "bent",
    "bind": "bound", "bite": "bit bitten", "bleed": "bled", "blow": "blew blown",
    "break": "broke broken", "breed": "bred", "bring": "brought", "build": "built",
    "buy": "bought", "cast": "cast", "catch": "caught", "choose": "chose chosen", "cling": "clung",
    "come": "came come", "cost": "cost", "creep": "crept", "cut": "cut", "deal": "dealt",
    "dig": "dug", "do": "did done", "draw": "drew drawn", "drink": "drank drunk",
    "drive": "drove driven", "eat": "ate eaten", "fall": "fell fallen", "feed": "fed",
    "feel": "felt", "fight": "fought", "find": "found", "flee": "fled", "fly": "flew flown",
    "forbid": "forbade forbidden", "forget": "forgot forgotten", "forgive": "forgave forgiven",
    "freeze": "froze frozen", "get": "got gotten", "give": "gave given", "go": "went gone",
    "grow": "grew grown", "hang": "hung hanged", "have": "has had", "hear": "heard",
    "hide": "hid hidden", "hit": "hit", "hold": "held", "hurt": "hurt", "keep": "kept",
    "know": "knew known", "lay": "laid", "lead": "led", "leave": "left", "lend": "lent",
    "let": "let", "lie": "lay lain", "lose": "lost", "make": "made", "mean": "meant",
    "meet": "met", "pay": "paid", "put": "put", "read": "read", "ride": "rode ridden",
    "ring": "rang rung", "rise": "rose risen", "run": "ran run", "say": "said",
    "see": "saw seen", "seek": "sought", "sell": "sold", "send": "sent", "set": "set",
    "shake": "shook shaken", "shed": "shed", "shine": "shone shined", "shoot": "shot",
    "show": "showed shown", "shrink": "shrank shrunk", "shut": "shut", "sing": "sang sung",
    "sink": "sank sunk", "sit": "sat", "sleep": "slept", "slide": "slid", "speak": "spoke spoken",
    "spend": "spent", "spin": "spun", "split": "split", "spread": "spread", "spring": "sprang sprung",
    "stand": "stood", "steal": "stole stolen", "stick": "stuck", "strike": "struck stricken",
    "string": "strung", "swear": "swore sworn", "sweep": "swept", "swim": "swam swum",
    "swing": "swung", "take": "took taken", "teach": "taught", "tear": "tore torn",
    "tell": "told", "think": "thought", "throw": "threw thrown", "undergo": "underwent undergone",
    "understand": "understood", "wake": "woke woken", "wear": "wore worn", "weep": "wept",
    "win": "won", "withdraw": "withdrew withdrawn", "write": "wrote written",
}
_IRREGULAR_NOUNS = {
    "child": "children", "person": "people", "man": "men", "woman": "women", "mouse": "mice",
    "foot": "feet", "tooth": "teeth", "goose": "geese", "ox": "oxen", "analysis": "analyses",
    "basis": "bases", "crisis": "crises", "thesis": "theses", "criterion": "criteria",
    "phenomenon": "phenomena", "index": "indices indexes", "matrix": "matrices",
    "life": "lives", "wife": "wives", "knife": "knives", "half": "halves", "leaf": "leaves",
    "shelf": "shelves", "wolf": "wolves", "loaf": "loaves", "self": "selves",
}


def _vocabulary_forms(word: str, pos: str) -> set[str]:
    """Inflect a dictionary headword, including the head of a multi-word term."""
    word = canonical_english(word).strip().casefold()
    forms = {word}
    if " " in word:
        head, tail = word.split(" ", 1)
        if pos in {"v.", "phr."}:
            forms.update(form + " " + tail for form in _vocabulary_forms(head, "v."))
        prefix, head = word.rsplit(" ", 1)
        if pos in {"n.", "adj.", "adv.", "phr."}:
            forms.update(prefix + " " + form for form in _vocabulary_forms(head, "n." if pos == "phr." else pos))
        return forms
    if pos == "phr.":
        return _vocabulary_forms(word, "v.") | _vocabulary_forms(word, "n.")
    if pos not in {"n.", "v.", "adj.", "adv."}:
        return forms
    if pos == "v.":
        forms.update(_IRREGULAR_VERBS.get(word, "").split())
        for prefix in ("under", "over", "fore", "with", "mis", "out", "off", "un", "up", "re"):
            if word.startswith(prefix):
                forms.update(prefix + form for form in _IRREGULAR_VERBS.get(word[len(prefix):], "").split())
    elif pos == "n.":
        forms.update(_IRREGULAR_NOUNS.get(word, "").split())
    else:
        forms.update({"good": "better best", "well": "better best", "bad": "worse worst",
                      "far": "farther further farthest furthest", "little": "less least",
                      "many": "more most", "much": "more most"}.get(word, "").split())
    forms.update({word + "s", word + "es"})
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        forms.add(word[:-1] + "ies")
    if pos in {"v.", "adj.", "adv."}:
        stems = {word}
        if word.endswith("e"):
            stems.add(word[:-1])
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            stems.add(word[:-1] + "i")
        if len(word) >= 3 and word[-3] not in "aeiou" and word[-2] in "aeiou" and word[-1] not in "aeiouwxy":
            stems.add(word + word[-1])
        if word.endswith("c"):
            stems.add(word + "k")
        suffixes = ("ed", "ing") if pos == "v." else ("ed", "ing", "er", "est")
        forms.update(stem + suffix for stem in stems for suffix in suffixes)
        if word.endswith("ie"):
            forms.add(word[:-2] + "ying")
    return forms


def _example_has_term(example: str, terms: set[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", canonical_english(example), re.I)
               for term in terms)


def validate_guide(data: dict[str, Any], article: Article, config: EnglishConfig) -> None:
    if not isinstance(data.get("cefr"), str) or data["cefr"] not in {"A2", "B1", "B2", "C1", "C2"}:
        raise ValueError("cefr must be A2–C2")
    length(text(data.get("pre_reading_zh"), "pre_reading_zh"), "pre_reading_zh", 100, 330)
    for key, count in (("vocabulary", config.vocab_count), ("phrases", config.phrase_count)):
        items = data.get(key)
        if (not isinstance(items, list) or not max(1, count - 2) <= len(items) <= count + 2
                or any(not isinstance(item, dict) for item in items)):
            raise ValueError(f"{key} requires approximately {count} objects (±2, at least 1)")
        items = items[:count]
        data[key] = items
        terms: list[str] = []
        for index, item in enumerate(items, 1):
            term = text(item.get("word" if key == "vocabulary" else "phrase"), key)
            terms.append(canonical_english(term).strip().casefold())
            if key == "vocabulary":
                if not isinstance(item.get("pos"), str) or item["pos"] not in {"n.", "v.", "adj.", "adv.", "phr."}:
                    raise ValueError("vocabulary.pos must be n./v./adj./adv./phr.")
                text(item.get("note_zh"), "vocabulary.note_zh")
            text(item.get("meaning_zh"), f"{key}.meaning_zh")
            example = text(item.get("example_en"), f"{key}.example_en")
            if not source_contains(article, example, trimmed=True):
                raise ValueError(f"{key}[{index}].example_en for {term!r} must occur verbatim in the source")
            if len(example.split()) > 42:
                raise ValueError(f"{key}.example_en must be trimmed to approximately 40 words")
            forms = _vocabulary_forms(term, item["pos"] if key == "vocabulary" else "phr.")
            if not _example_has_term(example, forms):
                raise ValueError(f"{key}.example_en must contain {term}")
        if len(set(terms)) != len(terms):
            raise ValueError(f"{key} must not repeat terms")
    sentences = data.get("sentences")
    if not isinstance(sentences, list) or not 2 <= len(sentences) <= 3 or any(not isinstance(item, dict) for item in sentences):
        raise ValueError("sentences requires 2–3 objects")
    for index, item in enumerate(sentences, 1):
        sentence = text(item.get("sentence_en"), "sentence_en")
        if not source_contains(article, sentence, trimmed=True):
            raise ValueError(f"sentences[{index}].sentence_en must occur verbatim in the source")
        text(item.get("breakdown_zh"), "breakdown_zh")
        text(item.get("translation_zh"), "translation_zh")
    strings(data.get("writing_notes_zh"), "writing_notes_zh", 1, 2)
    quiz = data.get("quiz")
    if not isinstance(quiz, list) or len(quiz) != 3 or any(not isinstance(item, dict) for item in quiz):
        raise ValueError("quiz requires 3 objects")
    for item in quiz:
        question = text(item.get("question"), "quiz.question")
        if _CJK.search(question):
            raise ValueError("quiz.question must be in English")
        answer = text(item.get("answer"), "quiz.answer")
        match = re.search(r"第\s*(\d+)\s*段|\[(\d+)\]", answer)
        if not match or not 1 <= int(match[1] or match[2]) <= len(article.paragraphs):
            raise ValueError("quiz.answer must cite a valid paragraph number")
