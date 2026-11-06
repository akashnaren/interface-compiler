"""Write the confusable fold table from UTS #39 confusables.txt.

Usage: python scripts/gen_confusables.py confusables.txt

Source: https://www.unicode.org/Public/security/latest/confusables.txt
Only single-code-point entries whose prototype is one ASCII letter or digit
are kept. ASCII sources are omitted so the fold does not rewrite English.
"""

from __future__ import annotations

import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

_ASCII = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
_OUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "interface_compiler"
    / "extract"
    / "confusables.py"
)


def _codepoints(field: str) -> str:
    return "".join(chr(int(part, 16)) for part in field.split())


def _escape(char: str) -> str:
    code = ord(char)
    if code <= 0xFFFF:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"


def folds(text: str) -> dict[str, str]:
    """Map a confusable character to one ASCII letter or digit."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw or ";" not in raw:
            continue
        source_field, target_field, *_rest = (part.strip() for part in raw.split(";"))
        source = _codepoints(source_field)
        target = _codepoints(target_field)
        if len(source) != 1 or len(target) != 1 or target not in _ASCII or source.isascii():
            continue
        # NFKC already folds compatibility forms such as fullwidth letters.
        folded = unicodedata.normalize("NFKC", source)
        if len(folded) == 1 and folded in _ASCII:
            continue
        previous = found.get(source)
        if previous is not None and previous != target:
            raise SystemExit(f"conflicting fold for U+{ord(source):04X}")
        found[source] = target
    return found


def render(found: dict[str, str]) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for source, target in found.items():
        grouped[target].append(source)
    lines = [
        '"""Confusable folds to one ASCII letter or digit.',
        "",
        "Generated from Unicode UTS #39 confusables.txt 18.0.0 by",
        "scripts/gen_confusables.py. Do not edit by hand.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f"COUNT = {len(found)}",
        "",
        "_GROUPS: dict[str, str] = {",
    ]
    for target in sorted(grouped):
        chars = "".join(_escape(char) for char in sorted(grouped[target], key=ord))
        lines.append(f'    "{target}": "{chars}",')
    lines.extend(
        [
            "}",
            "",
            (
                "FOLDS: dict[str, str] = {char: target "
                "for target, chars in _GROUPS.items() for char in chars}"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: gen_confusables.py confusables.txt")
    found = folds(Path(sys.argv[1]).read_text(encoding="utf-8"))
    _OUT.write_text(render(found), encoding="utf-8")
    print(f"wrote {len(found)} folds to {_OUT}")


if __name__ == "__main__":
    main()
