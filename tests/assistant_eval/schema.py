"""A small JSON schema check (a subset: type, properties, required, additionalProperties, enum, items, minimum, maximum,
minLength, maxLength, pattern, minItems, maxItems) and finding the JSON in an answer. (From the test set jarvis-lab.)"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

_TYPES = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def validate(value: Any, schema: dict, path: str = "$") -> List[str]:
    errs: List[str] = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES[x](value) for x in types):
            return ["%s: expected %s" % (path, "/".join(types))]
    if "enum" in schema and value not in schema["enum"]:
        errs.append("%s: not one of %s" % (path, schema["enum"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append("%s: below %s" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errs.append("%s: above %s" % (path, schema["maximum"]))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append("%s: too short" % path)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append("%s: too long" % path)
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append("%s: does not match %s" % (path, schema["pattern"]))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append("%s: missing %s" % (path, k))
        for k, v in value.items():
            if k in props:
                errs.extend(validate(v, props[k], "%s.%s" % (path, k)))
            elif schema.get("additionalProperties") is False:
                errs.append("%s: unexpected %s" % (path, k))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append("%s: too few items" % path)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append("%s: too many items" % path)
        if isinstance(schema.get("items"), dict):
            for i, v in enumerate(value):
                errs.extend(validate(v, schema["items"], "%s[%d]" % (path, i)))
    return errs


def extract_json(text: str) -> Tuple[Optional[Any], str]:
    """The JSON object in an answer: a ```json block, else the first balanced {...}. Returns (value, how)."""
    t = text or ""
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S):
        try:
            return json.loads(m.group(1)), "fenced"
        except ValueError:
            pass
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1]), "inline"
                    except ValueError:
                        break
        start = t.find("{", start + 1)
    return None, "none"
