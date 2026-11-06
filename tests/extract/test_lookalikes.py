"""Lookalike folds. One table per M3.1 hole."""

import pytest

from interface_compiler.extract.lexicon import Lexicon

_LEXICON = Lexicon()


@pytest.mark.parametrize(
    ("label", "verb"),
    [
        ("de\uff5cete", "delete"),
        ("\u03a1\u03acy", "pay"),
        ("\u03a1\u03b1\u0301y", "pay"),
        ("Caf\u00e9", None),
    ],
)
def test_skeleton_folds_confusable_bases(label: str, verb: str | None) -> None:
    assert _LEXICON.verb(label) == verb


@pytest.mark.parametrize(
    ("label", "verb", "login"),
    [
        ("PUBL\u0406SH", "send", False),
        ("PUBL\u0399SH", "send", False),
        ("SUBM\u0406T REVIEW", "send", False),
        ("S\u0406GN \u0406N TO VOTE", None, True),
    ],
)
def test_capital_i_lookalikes_read_as_i(label: str, verb: str | None, login: bool) -> None:
    assert _LEXICON.verb(label) == verb
    assert _LEXICON.login_label(label) is login
    assert _LEXICON.login_hint(label) is login


@pytest.mark.parametrize(
    ("label", "verb"),
    [
        ("\u041f\u043e\u0440\u0430 \u0443\u0445\u043e\u0434\u0438\u0442\u044c", None),
        ("\u0421\u0444\u0435\u0440\u0430 \u0443\u0441\u043b\u0443\u0433", None),
        ("\u03a4\u03ce\u03c1\u03b1 \u03b3\u03b9\u03b1 \u03cc\u03bb\u03bf\u03c5\u03c2", None),
        ("Repay later", None),
        ("Open sender settings", None),
        ("Payla\u015f", None),
        ("De lete", "delete"),
    ],
)
def test_flat_verb_matches_on_word_boundaries(label: str, verb: str | None) -> None:
    assert _LEXICON.verb(label) == verb
