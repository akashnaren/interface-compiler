"""Repeated sibling structures. Text is already stripped out of the skeleton."""

from __future__ import annotations

from dataclasses import dataclass

from interface_compiler.browser.facts import ElementFact

_MAX_ITEM = 6


@dataclass(frozen=True, slots=True)
class RepeatItem:
    elements: tuple[ElementFact, ...]


@dataclass(frozen=True, slots=True)
class RepeatGroup:
    items: tuple[RepeatItem, ...]
    signature: str


def find_repeat_groups(elements: tuple[ElementFact, ...] | list[ElementFact]) -> list[RepeatGroup]:
    """Contiguous skeleton patterns that repeat at least three times."""
    rows = list(elements)
    signatures = [element.skeleton_path for element in rows]
    used = [False] * len(rows)
    groups: list[RepeatGroup] = []
    index = 0
    while index < len(rows):
        if used[index]:
            index += 1
            continue
        found = _best_run(signatures, index)
        if found is None:
            index += 1
            continue
        count, length = found
        items: list[RepeatItem] = []
        for step in range(count):
            start = index + step * length
            chunk = tuple(rows[start : start + length])
            if not any(_actionable(element) for element in chunk):
                found = None
                break
            items.append(RepeatItem(chunk))
            for offset in range(length):
                used[start + offset] = True
        if found is not None and len(items) >= 3:
            groups.append(RepeatGroup(tuple(items), signatures[index]))
            index += count * length
            continue
        index += 1
    return groups


def _best_run(signatures: list[str], start: int) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    limit = len(signatures)
    for length in range(1, _MAX_ITEM + 1):
        count = 1
        while start + (count + 1) * length <= limit and _same(
            signatures, start, start + count * length, length
        ):
            count += 1
        if count < 3:
            continue
        covered = count * length
        if best is None or covered > best[0] * best[1]:
            best = (count, length)
    return best


def _same(signatures: list[str], left: int, right: int, length: int) -> bool:
    return signatures[left : left + length] == signatures[right : right + length]


def _actionable(element: ElementFact) -> bool:
    return element.tag in {
        "a",
        "button",
        "input",
        "select",
        "textarea",
        "summary",
    } or element.role in {
        "link",
        "button",
        "menuitem",
        "menuitemradio",
        "menuitemcheckbox",
    }
