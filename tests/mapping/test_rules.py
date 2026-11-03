"""Lexicon, enabled, and schema rows. One table per rule."""

from __future__ import annotations

import pytest

from interface_compiler.browser.facts import Box, Constraints, ElementFact, collect_facts
from interface_compiler.extract.lexicon import Lexicon
from interface_compiler.extract.naming import field_name, slug
from interface_compiler.mapping import MapContext, map_facts
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.input_schema import property_for
from tests.mapping._find import one, props

_LEXICON = Lexicon()


def _element(**overrides: object) -> ElementFact:
    base: dict[str, object] = {
        "tag": "button",
        "role": "button",
        "name": "Go",
        "html_id": None,
        "field_name": None,
        "input_type": None,
        "href": None,
        "form_index": None,
        "form_method": None,
        "form_action": None,
        "disabled": False,
        "readonly": False,
        "aria_disabled": False,
        "inert": False,
        "hidden": False,
        "aria_hidden": False,
        "value": None,
        "checked": None,
        "selected": None,
        "options": (),
        "aria_expanded": None,
        "aria_selected": None,
        "aria_checked": None,
        "aria_pressed": None,
        "aria_current": None,
        "aria_valuemin": None,
        "aria_valuemax": None,
        "aria_valuenow": None,
        "aria_haspopup": None,
        "aria_controls": None,
        "box": Box(0, 0, 10, 10),
        "visible": True,
        "covered": False,
        "in_viewport": True,
        "validation_message": "",
        "landmark": "",
        "css": "button",
        "skeleton_path": "button|button",
        "label_text": "",
        "group_key": None,
        "constraints": Constraints(False, None, None, None, None, None, None),
        "name_source": "html",
        "in_dialog": False,
    }
    base.update(overrides)
    return ElementFact(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("label", "verb"),
    [
        ("Pay", "pay"),
        ("Place order", "place_order"),
        ("Delete", "delete"),
        ("Delete account", "delete"),
        ("Delete my account", "delete"),
        ("Pay $49.99", "pay"),
        ("Send email", "send"),
        ("Place order now", "place_order"),
        ("Send", "send"),
        ("Add to bag", "add_to_cart"),
        ("Sign in", "sign_in"),
        ("Show more", "show_more"),
        ("Next", "next_page"),
        ("Previous", "prev_page"),
        ("Close", "close_dialog"),
        ("Search", "search"),
        ("Subscribe", "subscribe"),
        ("Filter", "filter"),
        ("Back", "go_back"),
        ("Download", "download"),
    ],
)
def test_lexicon_verbs(label: str, verb: str) -> None:
    assert _LEXICON.verb(label) == verb


@pytest.mark.parametrize(
    ("url", "gated"),
    [
        ("/vote?id=1&goto=news", True),
        ("/comment?next=/item/3", True),
        ("/vote?id=1", False),
    ],
)
def test_login_redirect_param(url: str, gated: bool) -> None:
    assert _LEXICON.login_target(url) is gated


@pytest.mark.parametrize(
    ("flag", "reason"),
    [
        ({"visible": False}, "not visible"),
        ({"disabled": True}, "disabled"),
        ({"aria_disabled": True}, "aria-disabled"),
        ({"inert": True}, "inert"),
        ({"covered": True}, "covered"),
        ({"readonly": True}, "read-only"),
    ],
)
def test_enabled_reasons(flag: dict[str, bool], reason: str) -> None:
    enabled, found = element_enabled(_element(**flag))
    assert enabled is False
    assert found == reason


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Catalog", "catalog"),
        ("Gift wrap", "gift_wrap"),
        ("9lives", "lives"),
        ("E-mail", "e_mail"),
    ],
)
def test_slug(text: str, expected: str) -> None:
    assert slug(text) == expected


@pytest.mark.parametrize(
    ("overrides", "prop"),
    [
        (
            {"tag": "input", "role": "textbox", "input_type": "email"},
            {"type": "string", "format": "email"},
        ),
        (
            {"tag": "input", "role": "textbox", "input_type": "url"},
            {"type": "string", "format": "uri"},
        ),
        (
            {
                "tag": "input",
                "role": "spinbutton",
                "input_type": "number",
                "constraints": Constraints(False, None, "1", "9", "1", None, None),
            },
            {"type": "integer", "minimum": 1, "maximum": 9, "multipleOf": 1},
        ),
        (
            {"tag": "input", "role": "textbox", "input_type": "date"},
            {"type": "string", "format": "date"},
        ),
        (
            {
                "tag": "input",
                "role": "textbox",
                "input_type": "text",
                "constraints": Constraints(False, "[A-Z]{3}", None, None, None, 3, 3),
            },
            {"type": "string", "pattern": "^(?:[A-Z]{3})$", "minLength": 3, "maxLength": 3},
        ),
    ],
)
def test_property_for(overrides: dict[str, object], prop: dict[str, object]) -> None:
    assert property_for(_element(**overrides)) == prop


def test_field_name_prefers_the_label() -> None:
    assert field_name(_element(label_text="Query", field_name="q")) == "query"
    assert field_name(_element(field_name="q")) == "query"
    assert field_name(_element(field_name="deadbeef", placeholder="City")) == "city"


def _by_html(result, html_id: str):
    found = []
    for item in result.affordances:
        locator = item.x.locator if item.x else None
        extra = locator.model_extra if locator else None
        if extra and extra.get("html_id") == html_id:
            found.append(item)
    assert len(found) == 1, [item.id for item in result.affordances]
    return found[0]


def _html(facts_page, html: str):
    facts_page.set_content(html, wait_until="domcontentloaded")
    facts = collect_facts(facts_page)
    return map_facts(facts, MapContext(page_url=facts.url)), facts


@pytest.mark.parametrize(
    "case",
    [
        "submit",
        "form",
        "dialog",
        "links",
        "shadow",
        "combobox",
        "hard",
        "groups",
        "described",
        "truncate",
        "controls",
    ],
)
def test_review_fixes(case: str, map_page, facts_page) -> None:
    if case == "submit":
        result, _facts = map_page("form_gate.html")
        assert _by_html(result, "add-off").x.reason == "disabled"
        assert _by_html(result, "add-aria").x.reason == "aria-disabled"
        assert _by_html(result, "add-inert").x.reason == "inert"
        assert _by_html(result, "add-cover").x.reason == "covered"
        return
    if case == "form":
        result, _facts = map_page("form_gate.html")
        inert = one(result, "search")
        assert inert.enabled is False and inert.x.reason == "inert"
        assert "query" in props(inert)
        covered = one(result, "submit_mask")
        assert covered.enabled is False and covered.x.reason == "covered"
        saved = one(result, "save")
        assert saved.enabled is False and saved.x.reason == "disabled"
        return
    if case == "dialog":
        result, facts = map_page("dialog_stack.html")
        assert one(result, "do_stay").enabled is True
        assert _by_html(result, "under").x.reason == "covered"
        assert next(item for item in facts.elements if item.html_id == "lower-btn").covered is True
        assert next(item for item in facts.elements if item.html_id == "plain-btn").covered is True
        assert one(result, "do_outside").x.reason == "blocked by dialog"
        assert result.state["dialog_open"] == "top"
        return
    if case == "links":
        result, _facts = _html(
            facts_page,
            "<style>body{margin:0}</style>"
            "<div style='position:relative;width:240px;height:24px'>"
            "<a href='/p/1'>One</a><a href='/p/2'>Two</a><a href='/p/3'>Three</a>"
            "<div style='position:absolute;inset:0'></div></div>",
        )
        opened = one(result, "open_product")
        assert opened.enabled is False and opened.x.reason == "covered"
        return
    if case == "shadow":
        _result, facts = _html(
            facts_page,
            "<style>body{margin:0}</style>"
            "<button id='under' style='position:absolute;left:0;top:0;width:80px;height:24px'>Under</button>"
            "<div><template shadowrootmode='open'>"
            "<div style='position:fixed;top:0;left:0;width:80px;height:24px'></div></template></div>"
            "<div style='position:absolute;top:48px'>"
            "<template shadowrootmode='open'>"
            "<button id='in' type='button' style='width:80px;height:24px'>Inside</button>"
            "</template></div>",
        )
        by_id = {item.html_id: item for item in facts.elements}
        assert by_id["under"].covered is True
        assert by_id["in"].covered is False
        return
    if case == "combobox":
        result, _facts = _html(
            facts_page,
            "<label for='city'>City</label>"
            "<input id='city' role='combobox' aria-expanded='true' aria-controls='cities'>"
            "<ul id='cities' role='listbox' hidden><li role='option'>Paris</li></ul>",
        )
        assert "enum" not in props(one(result, "set_city"))["city"]
        return
    if case == "hard":
        result, _facts = _html(
            facts_page,
            "<form method='post' action='/account'><button id='del' type='submit'>Delete account</button></form>"
            "<button type='button' aria-haspopup='menu' aria-expanded='true'>Account</button>"
            "<div role='menu'><div id='pay' role='menuitem'>Pay $49.99</div></div>",
        )
        assert _by_html(result, "del").x.reason == "hard-blocked in v1: delete"
        assert _by_html(result, "pay").x.reason == "hard-blocked in v1: pay"
        return
    if case == "groups":
        result, _facts = _html(
            facts_page,
            "<div role='tablist' aria-label='Details'>"
            "<button type='button' role='tab' inert>Hidden</button>"
            "<button type='button' role='tab' aria-selected='true'>Shown</button></div>"
            "<nav aria-label='Pagination'><a href='/page/1' inert>1</a>"
            "<a href='/page/2'>2</a><a href='/page/3'>Next</a></nav>"
            "<label><input type='radio' name='size' inert> S</label>"
            "<label><input type='radio' name='size'> M</label>"
            "<label><input type='radio' name='color' inert> Red</label>"
            "<label><input type='radio' name='color' inert> Blue</label>",
        )
        assert props(one(result, "open_tab"))["tab"]["enum"] == ["Shown"]
        assert props(one(result, "go_page"))["page"]["enum"] == [2]
        assert props(one(result, "set_size"))["size"]["enum"] == ["M"]
        color = one(result, "set_color")
        assert color.enabled is False
        assert "enum" not in props(color).get("color", {"type": "string"})
        return
    if case == "described":
        result, _facts = _html(
            facts_page,
            "<button id='titled' type='button' title='Login required'>Go</button>"
            "<span id='hint'>Members only</span>"
            "<button id='hinted' type='button' aria-describedby='hint'>Save</button>",
        )
        assert _by_html(result, "titled").x.reason == "requires sign-in"
        assert _by_html(result, "hinted").x.reason == "requires sign-in"
        return
    if case == "truncate":
        _result, facts = _html(
            facts_page,
            "<div></div>" * 8001
            + "<div><template shadowrootmode='open'><button type='button'>Inside</button></template></div>",
        )
        assert facts.truncated is True
        assert "Inside" not in {item.name for item in facts.elements}
        return
    result, _facts = _html(
        facts_page,
        "<form method='post' action='/cart'>"
        "<label><input type='radio' name='size' value='S'> S</label>"
        "<label><input type='radio' name='size' value='M' checked> M</label>"
        "<label for='qty'>Qty</label><input id='qty' type='number' name='qty' min='1' max='5'>"
        "<label for='vol'>Vol</label><input id='vol' type='range' name='vol' min='0' max='10'>"
        "<button type='submit'>Add to cart</button></form>",
    )
    assert props(one(result, "set_size"))["size"]["type"] == "string"
    assert props(one(result, "set_qty"))["qty"]["type"] in {"number", "integer"}
    assert "vol" in props(one(result, "set_vol"))
    assert one(result, "add_to_cart").x.grain == "field"
