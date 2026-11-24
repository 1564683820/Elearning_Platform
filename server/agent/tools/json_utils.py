"""Shared JSON utility functions used by multiple agents."""

import json
import re


def fix_json_string(s: str) -> str:
    """Heuristically fix common JSON string formatting issues."""
    result = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch in "\r\n\t":
            if ch == "\r":
                result.append("\\r")
            elif ch == "\n":
                result.append("\\n")
            elif ch == "\t":
                result.append("\\t")
            continue
        result.append(ch)
    return "".join(result)


def try_complete_json(text: str) -> str:
    """Try to fix truncated JSON by counting and closing braces."""
    first_brace = text.find("{")
    if first_brace == -1:
        return text
    last_brace = text.rfind("}")
    if last_brace != -1 and last_brace > first_brace:
        content = text[first_brace:last_brace + 1]
    else:
        content = text[first_brace:]

    open_braces = 0
    open_brackets = 0
    in_str = False
    escape = False
    for ch in content:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
        elif ch == "[":
            open_brackets += 1
        elif ch == "]":
            open_brackets -= 1

    result = content
    result += "]" * open_brackets
    result += "}" * open_braces
    return result
