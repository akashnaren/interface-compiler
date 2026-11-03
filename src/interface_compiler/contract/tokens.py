"""Token counts for a compiled view document.

Counts use the fixed ``o200k_base`` tokenizer. The BPE file is downloaded on
first use into ``$XDG_CACHE_HOME/interface-compiler/tiktoken`` (or
``~/.cache/interface-compiler/tiktoken`` when ``XDG_CACHE_HOME`` is unset).
An offline run needs that cache to exist already. ``TIKTOKEN_CACHE_DIR``, when
set, is left alone.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken

from interface_compiler.contract.models import ViewDoc
from interface_compiler.contract.transforms import extension_payload, strip_x

_encoder: tiktoken.Encoding | None = None


@dataclass(frozen=True, slots=True)
class TokenCounts:
    """``o200k_base`` tokens of the core document and of ``x``, counted apart."""

    core: int
    x: int


def count_tokens(text: str) -> int:
    """Return the ``o200k_base`` token count of ``text``."""
    return len(_encoding().encode(text))


def token_counts(doc: ViewDoc | Mapping[str, Any]) -> TokenCounts:
    """Count the core document and the ``x`` payload separately.

    The core is ``strip_x(doc)`` serialized as compact JSON. The ``x`` count
    is 0 when the document has no top-level ``x`` and no affordance ``x``.
    """
    core_doc = strip_x(doc)
    payload = extension_payload(doc)
    extension_tokens = count_tokens(canonical_json(payload)) if payload else 0
    return TokenCounts(core=count_tokens(canonical_json(core_doc)), x=extension_tokens)


def canonical_json(data: object) -> str:
    """Compact JSON with the dict's key order preserved."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _encoding() -> tiktoken.Encoding:
    global _encoder
    if _encoder is None:
        _prepare_cache_dir()
        _encoder = tiktoken.get_encoding("o200k_base")
    return _encoder


def _prepare_cache_dir() -> None:
    if os.environ.get("TIKTOKEN_CACHE_DIR"):
        return
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    cache = base / "interface-compiler" / "tiktoken"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
