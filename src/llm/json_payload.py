"""Single source of truth for extracting a JSON payload from an LLM reply.

Every LLM caller needs the same thing: given a chat completion's content string,
recover THE payload, or fail loudly.  Having two implementations is how the
extraction layer ended up silently returning the `[1]` fragment of
``Список: [1] и ещё текст. {"dose":"500 мг"}``, and how a truncated
``[{"dose":"500 мг"},{"dose":"`` was decoded into the inner ``{"dose":"500 мг"}``
and persisted as if it were a complete extraction.

The contract is deliberately fail-closed:

* the whole (fence-stripped) string is tried first;
* then the LONGEST balanced ``{...}`` / ``[...]`` span, so the outermost
  container of the real payload always beats a surrounding prose fragment;
* a response whose first opener is never terminated is a TRUNCATION and raises --
  an inner balanced fragment of a truncated array is not evidence;
* anything else raises.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)

_OPENERS = {"{": "}", "[": "]"}
_CLOSERS = {v: k for k, v in _OPENERS.items()}


class LLMJSONParseError(json.JSONDecodeError):
    """No recoverable JSON payload in an LLM response.

    Subclasses ``json.JSONDecodeError`` so existing ``except json.JSONDecodeError``
    handlers keep working while callers that must fail closed can catch this
    exact type.
    """


def strip_fence(content: str) -> str:
    match = _FENCE_RE.search(content)
    return match.group(1).strip() if match else content.strip()


def balanced_spans(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` index pairs of every top-level balanced container.

    String literals and escapes are honoured, so a ``{`` inside a quoted
    ``source_quote`` does not open a span.  The first unbalanced closer aborts the
    scan: no enclosing container can be trusted past that point.
    """
    spans: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in _OPENERS:
            stack.append((char, index))
        elif char in _CLOSERS:
            if not stack or _OPENERS[stack[-1][0]] != char:
                return spans
            _opener, start = stack.pop()
            if not stack:
                spans.append((start, index + 1))
    return spans


def parse_json_payload(content: str) -> Any:
    """Recover THE JSON payload from ``content``, or raise :class:`LLMJSONParseError`."""
    text = strip_fence(content or "")
    if not text:
        raise LLMJSONParseError("empty LLM response", text, 0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    spans = balanced_spans(text)
    for start, end in sorted(spans, key=lambda s: (s[1] - s[0]), reverse=True):
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            continue

    first_open = min((i for i, c in enumerate(text) if c in "{["), default=-1)
    if first_open != -1 and not any(start == first_open for start, _end in spans):
        raise LLMJSONParseError(
            "truncated LLM JSON payload: outermost container is unterminated",
            text,
            first_open,
        )
    raise LLMJSONParseError("No valid JSON found", text, 0)


__all__ = ["LLMJSONParseError", "balanced_spans", "parse_json_payload", "strip_fence"]
