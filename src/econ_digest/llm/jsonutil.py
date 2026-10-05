"""Read a JSON object from model text without guessing at malformed JSON."""

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("Model response must be text containing a JSON object")
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text).strip()
    try:
        complete = json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        if not isinstance(complete, dict):
            raise ValueError("JSON output must be an object, not " + type(complete).__name__)
        return complete

    start: int | None = None
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            if start is None:
                start = index
            depth += 1
        elif char == "}" and start is not None:
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start:index + 1])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON object: {exc.msg} at position {exc.pos}") from exc
                if not isinstance(data, dict):
                    raise ValueError("JSON output must be an object")
                return data
    if start is None:
        raise ValueError("No JSON object found in model response")
    raise ValueError("Unterminated JSON object in model response")
