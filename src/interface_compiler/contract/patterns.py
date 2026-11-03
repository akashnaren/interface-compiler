"""Match JSON Schema patterns in linear time.

The stdlib ``re`` engine backtracks, so a pattern such as ``^(a+)+$`` can hang
on a long failing input. Matching uses RE2, which does not backtrack. A
pattern RE2 cannot compile (a backreference, lookaround, or conditional) is
rejected. A pattern or a subject past the length cap is rejected before it is
compiled or matched.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import re2

_MAX_PATTERN_LENGTH = 1024
_MAX_SUBJECT_LENGTH = 4096
_STDLIB_COMPILE_ERRORS = (re.error, OverflowError, RecursionError)


class PatternError(Exception):
    """A pattern cannot be compiled, or a subject cannot be matched."""

    def __init__(self, detail: str, *, invalid: bool = False) -> None:
        self.detail = detail
        self.invalid = invalid
        super().__init__(detail)


def ensure_pattern(pattern: str) -> None:
    """Raise ``PatternError`` when ``pattern`` cannot be matched safely."""
    _program(pattern)


def pattern_matches(pattern: str, text: str) -> bool:
    """Return whether ``pattern`` matches anywhere in ``text``.

    JSON Schema ``pattern`` is unanchored. A subject past the length cap raises
    ``PatternError`` and is not searched.
    """
    program = _program(pattern)
    if len(text) > _MAX_SUBJECT_LENGTH:
        raise PatternError("string is too long to match")
    found: Any = program.search(text)
    return found is not None


def _program(pattern: str) -> Any:
    if len(pattern) > _MAX_PATTERN_LENGTH:
        raise PatternError("pattern is too long")
    return _cached_program(pattern)


@lru_cache(maxsize=256)
def _cached_program(pattern: str) -> Any:
    try:
        re.compile(pattern)
    except _STDLIB_COMPILE_ERRORS as exc:
        raise PatternError(str(exc), invalid=True) from exc
    options = re2.Options()
    options.log_errors = False
    try:
        return re2.compile(pattern, options=options)
    except re2.error as exc:
        raise PatternError(_re2_detail(exc)) from exc


def _re2_detail(exc: re2.error) -> str:
    parts: list[str] = []
    for arg in exc.args:
        if isinstance(arg, bytes):
            parts.append(arg.decode("utf-8", "replace"))
        else:
            parts.append(str(arg))
    text = "; ".join(part.strip() for part in parts if part.strip())
    if not text:
        text = "invalid pattern"
    if len(text) > 200:
        return f"{text[:197]}..."
    return text
