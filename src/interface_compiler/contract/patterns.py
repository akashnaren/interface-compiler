"""Reject regular expressions whose match time can grow exponentially.

JSON Schema patterns are applied with the stdlib ``re`` engine, which
backtracks. A pattern such as ``^(a+)+$`` compiles and then hangs on a long
failing input. The screen below runs on the same parse tree ``re.compile``
uses and refuses that shape before any match. An opcode this module does not
understand is refused too, so a new engine form cannot skip the screen.
"""

from __future__ import annotations

import re
import re._parser as re_parser
from typing import NamedTuple

_RISK = "nested quantifier can backtrack catastrophically"
# A repeat this wide, wrapped around another repeat with nothing that must
# appear on every iteration, is the catastrophic shape. Exact counts and
# short ranges stay, so ``(?:\\d{1,3}\\.){3}`` is still a usable pattern.
_WIDE_SPAN = 20
_WIDE_UPPER = 64
_PIN_OPS = frozenset({"LITERAL", "NOT_LITERAL", "ANY", "IN", "CATEGORY"})
_SKIP_OPS = frozenset({"AT", "GROUPREF", "GROUPREF_EXISTS"})


class _Shape(NamedTuple):
    has_quantifier: bool
    pinned: bool
    dangerous: bool


_EMPTY = _Shape(False, False, False)
_PIN = _Shape(False, True, False)
_DANGER = _Shape(True, False, True)


def backtracking_risk(pattern: str) -> str | None:
    """Return a reason when ``pattern`` must not be matched, else ``None``.

    ``None`` means the caller may match. A reason means matching is refused.
    """
    try:
        tree = re_parser.parse(pattern)
    except re.error:
        return None
    except (TypeError, ValueError, OverflowError, RecursionError):
        return _RISK
    if _walk(tree).dangerous:
        return _RISK
    return None


def _is_nodes(value: object) -> bool:
    """True for a pattern body. ``SubPattern`` is not a ``list``."""
    return isinstance(value, (list, re_parser.SubPattern))


def _walk(nodes: object) -> _Shape:
    if not _is_nodes(nodes):
        return _DANGER
    shape = _EMPTY
    for item in nodes:
        if not isinstance(item, tuple) or len(item) != 2:
            return _DANGER
        name = getattr(item[0], "name", None)
        if not isinstance(name, str):
            return _DANGER
        shape = _concat(shape, _one(name, item[1]))
        if shape.dangerous:
            return shape
    return shape


def _one(name: str, arg: object) -> _Shape:
    if name in _PIN_OPS or name.startswith(("LITERAL", "NOT_LITERAL")):
        return _PIN
    if name in _SKIP_OPS:
        return _EMPTY
    if name in {"MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"}:
        return _repeat(name, arg)
    if name == "SUBPATTERN":
        return _group(arg)
    if name == "BRANCH":
        return _branch(arg)
    if name in {"ASSERT", "ASSERT_NOT"}:
        return _assert(arg)
    if name == "ATOMIC_GROUP":
        return _atomic(arg)
    return _DANGER


def _repeat(name: str, arg: object) -> _Shape:
    if not isinstance(arg, tuple) or len(arg) != 3:
        return _DANGER
    lower, upper, body = arg
    if not isinstance(lower, int):
        return _DANGER
    inner = _walk(body)
    wide = _wide(lower, upper)
    dangerous = inner.dangerous or (
        name != "POSSESSIVE_REPEAT" and wide and inner.has_quantifier and not inner.pinned
    )
    return _Shape(True, False, dangerous)


def _group(arg: object) -> _Shape:
    return _walk(_nested(arg))


def _branch(arg: object) -> _Shape:
    if not isinstance(arg, tuple) or len(arg) < 2 or not isinstance(arg[1], list):
        return _DANGER
    shape: _Shape | None = None
    for branch in arg[1]:
        piece = _walk(branch)
        shape = piece if shape is None else _alt(shape, piece)
        if shape.dangerous:
            return shape
    return _EMPTY if shape is None else shape


def _assert(arg: object) -> _Shape:
    if not isinstance(arg, tuple) or not arg:
        return _DANGER
    inner = _walk(arg[-1])
    return _Shape(inner.has_quantifier, False, inner.dangerous)


def _atomic(arg: object) -> _Shape:
    """An atomic group does not give characters back to an outer repeat."""
    inner = _walk(arg)
    return _Shape(inner.has_quantifier, inner.pinned or inner.has_quantifier, inner.dangerous)


def _nested(arg: object) -> object:
    if _is_nodes(arg):
        return arg
    if isinstance(arg, tuple):
        for item in reversed(arg):
            if _is_nodes(item):
                return item
    return None


def _wide(lower: int, upper: object) -> bool:
    if upper == re_parser.MAXREPEAT or not isinstance(upper, int):
        return True
    return upper - lower >= _WIDE_SPAN or upper >= _WIDE_UPPER


def _concat(left: _Shape, right: _Shape) -> _Shape:
    return _Shape(
        left.has_quantifier or right.has_quantifier,
        left.pinned or right.pinned,
        left.dangerous or right.dangerous,
    )


def _alt(left: _Shape, right: _Shape) -> _Shape:
    return _Shape(
        left.has_quantifier or right.has_quantifier,
        left.pinned and right.pinned,
        left.dangerous or right.dangerous,
    )
