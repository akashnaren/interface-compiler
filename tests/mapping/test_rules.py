"""Lexicon, enabled, and schema rows. One table per rule."""

from __future__ import annotations

import pytest

from interface_compiler.browser.facts import Box, Constraints, ElementFact, FormFact, collect_facts
from interface_compiler.extract.lexicon import Lexicon
from interface_compiler.extract.naming import field_name, slug
from interface_compiler.mapping import MapContext, map_facts
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.form import fill_missing, map_form
from interface_compiler.mapping.input_schema import property_for
from interface_compiler.mapping.link import map_link
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
        ("Place your order", "place_order"),
        ("Delete", "delete"),
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
        ("/vote?id=1", False),
        ("/?lang=fr&next=/products", False),
        ("vote?goto=https://accounts.example/login", True),
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


@pytest.mark.parametrize("label", ["Log out", "Sign out"])
def test_sign_out_link_is_mutating(label: str) -> None:
    result = map_link(
        _element(tag="a", role="link", name=label, href="/logout"),
        MapContext(page_url="http://example/"),
    )
    mapped = one(result, "go_log_out" if label == "Log out" else "go_sign_out")
    assert mapped.x is not None and mapped.x.tag == "mutating"


@pytest.mark.parametrize(
    ("label", "href", "reason"),
    [("Delete account", "/account/delete", "hard-blocked in v1: delete")],
)
def test_map_link_hard_block(label: str, href: str, reason: str) -> None:
    result = map_link(
        _element(tag="a", role="link", name=label, href=href),
        MapContext(page_url="http://example/"),
    )
    mapped = one(result, "go_account")
    assert mapped.enabled is False
    assert mapped.x is not None and mapped.x.reason == reason


def test_hard_block_beats_missing_after_fill() -> None:
    size = _element(
        tag="select",
        role="combobox",
        name="Size",
        html_id="size",
        label_text="Size",
        validation_message="Required",
    )
    submit = _element(
        tag="button",
        role="button",
        name="Pay now",
        html_id="pay",
        input_type="submit",
    )
    form = FormFact(index=0, method="post", action="/pay", valid=False, html_id="pay")
    result = map_form(form, [size, submit], MapContext(page_url="http://example/checkout"))
    pay = one(result, "pay")
    assert pay.enabled is False
    assert pay.x is not None and pay.x.reason == "hard-blocked in v1: pay"
    pay.enabled = False
    pay.x.reason = "missing: size"
    filled = fill_missing(result, {"size"}, submit)
    again = one(filled, "pay")
    assert again.enabled is False
    assert again.x is not None and again.x.reason == "hard-blocked in v1: pay"


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


def _html(facts_page, html: str, **context: object):
    facts_page.set_content(html, wait_until="domcontentloaded")
    facts = collect_facts(facts_page)
    return map_facts(facts, MapContext(page_url=facts.url, **context)), facts  # type: ignore[arg-type]


def test_form_gate(mapped_once) -> None:
    result, _facts = mapped_once("form_gate.html")
    assert _by_html(result, "add-off").x.reason == "disabled"
    assert _by_html(result, "add-aria").x.reason == "aria-disabled"
    assert _by_html(result, "add-inert").x.reason == "inert"
    assert _by_html(result, "add-cover").x.reason == "covered"
    inert = one(result, "search")
    assert inert.enabled is False and inert.x.reason == "inert"
    assert "query" in props(inert)
    covered = one(result, "submit_mask")
    assert covered.enabled is False and covered.x.reason == "covered"
    saved = one(result, "save")
    assert saved.enabled is False and saved.x.reason == "disabled"


@pytest.mark.parametrize(
    "case",
    [
        "dialog",
        "links",
        "combobox",
        "groups",
        "described",
        "rows",
        "orders",
        "secondary",
        "fields",
    ],
)
def test_review_fixes(case: str, map_page, facts_page) -> None:
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
    if case == "combobox":
        result, _facts = _html(
            facts_page,
            "<label for='city'>City</label>"
            "<input id='city' role='combobox' aria-expanded='true' aria-controls='cities'>"
            "<ul id='cities' role='listbox' hidden><li role='option'>Paris</li></ul>",
        )
        assert "enum" not in props(one(result, "set_city"))["city"]
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
            "<span id='hint'>You must sign in to like posts</span>"
            "<button id='hinted' type='button' aria-describedby='hint'>Save</button>",
        )
        assert _by_html(result, "titled").x.reason == "requires sign-in"
        assert _by_html(result, "hinted").x.reason == "requires sign-in"
        return
    if case == "rows":
        result, _facts = _html(
            facts_page,
            "<style>body{margin:0} a{display:block}</style><main>"
            "<a href='/item?id=1'>One</a><a href='/item?id=2'>Two</a>"
            "<a href='/item?id=9' inert>Nine</a>"
            "<a href='/vote?id=1&amp;how=up&amp;goto=news'>Up</a>"
            "<a href='/vote?id=2&amp;how=up&amp;goto=news'>Up</a>"
            "<a href='/vote?id=3&amp;how=up&amp;goto=news'>Up</a></main>",
        )
        opened = one(result, "open_item")
        assert opened.enabled is True and opened.x is not None and opened.x.tag == "safe"
        assert [row["id"] for row in result.catalog["items"]] == ["1", "2"]
        vote = one(result, "vote")
        assert vote.enabled is False
        assert vote.x is not None
        assert vote.x.reason == "requires sign-in" and vote.x.tag == "mutating"
        return
    if case == "orders":
        result, _facts = _html(
            facts_page,
            "<style>body{margin:0} a{display:block}</style><main>"
            "<a href='/o/1'>Place your order 1</a>"
            "<a href='/o/2'>Place your order 2</a>"
            "<a href='/o/3'>Place your order 3</a></main>",
        )
        assert not any(
            item.id == "open_item"
            and (item.enabled or (item.x is not None and item.x.tag == "safe"))
            for item in result.affordances
        )
        order = one(result, "place_order")
        assert order.enabled is False
        assert order.x is not None and order.x.reason == "hard-blocked in v1: place_order"
        assert order.input.model_dump(exclude_none=True) == {"type": "object", "properties": {}}
        return
    if case == "secondary":
        result, _facts = _html(
            facts_page,
            "<style>body{margin:0} a{display:block}</style><main>"
            "<article><h2><a href='/i/1'>Story 1</a></h2>"
            "<a href='/account/delete'>Delete account</a></article>"
            "<article><h2><a href='/i/2'>Story 2</a></h2>"
            "<a href='/account/delete'>Delete account</a></article>"
            "<article><h2><a href='/i/3'>Story 3</a></h2>"
            "<a href='/account/delete'>Delete account</a></article></main>",
            include_secondary=("item.delete_account",),
        )
        opened = one(result, "open_item")
        assert opened.enabled is True
        deleted = one(result, "open_item_delete_account")
        assert deleted.enabled is False
        assert deleted.x is not None and deleted.x.reason == "hard-blocked in v1: delete"
        return
    result, _facts = _html(
        facts_page,
        "<form id='dead' method='post' action='/save'>"
        "<label for='email'>Email</label>"
        "<input id='email' name='email' disabled></form>",
    )
    blocked = one(result, "submit_dead")
    assert blocked.enabled is False and blocked.x is not None and blocked.x.reason == "disabled"


def _cue(case: str, sample: str) -> bool:
    if case == "route":
        return _LEXICON.login_target(sample)
    if case == "account":
        action = _LEXICON.account_action(url=sample)
        assert _LEXICON.login_target(f"{sample}?next=/", account_action=action) is action
        return action
    if case == "hint":
        return _LEXICON.login_hint(sample)
    raise AssertionError(case)


@pytest.mark.parametrize(
    ("case", "sample", "expected"),
    [
        ("route", "/Login", True),
        ("route", "/Account/Login", True),
        ("account", "/book/odyssey", False),
        ("account", "/item/3/comment", True),
        ("hint", "members only pricing", False),
        ("hint", "members only", True),
        ("hint", "Please sign in to continue", True),
        ("hint", "nonmembers only", False),
        ("fieldset", "save", False),
        ("mixed", "save", False),
        ("legend", "save", True),
        ("choices", "add_to_cart", False),
        ("modal", "high", True),
    ],
)
def test_fieldset_modal_and_login_cues(
    case: str, sample: str, expected: bool, request: pytest.FixtureRequest
) -> None:
    if case in {"route", "account", "hint"}:
        assert _cue(case, sample) is expected
        return
    page = request.getfixturevalue("facts_page")
    if case == "fieldset":
        result, facts = _html(
            page,
            "<form method='post' action='/save'><input type='hidden' name='csrf' value='t'>"
            "<fieldset disabled><label for='email'>Email</label>"
            "<input id='email' type='email' name='email'></fieldset>"
            "<button id='go' type='submit'>Save</button></form>",
        )
        saved = one(result, sample)
        assert saved.enabled is expected and saved.x is not None and saved.x.reason == "disabled"
        assert facts.forms[0].disabled is True
        assert next(item for item in facts.elements if item.html_id == "email").disabled is True
        return
    if case == "mixed":
        result, facts = _html(
            page,
            "<form method='post' action='/c'><fieldset disabled>"
            "<input name='email' aria-label='Email'></fieldset>"
            "<input name='name' aria-label='Name'><button>Save</button></form>",
        )
        saved = one(result, sample)
        assert saved.enabled is False
        assert saved.x is not None and saved.x.reason == "disabled"
        assert facts.forms[0].disabled is True
        assert "email" not in props(saved)
        return
    if case == "legend":
        result, facts = _html(
            page,
            "<form method='post' action='/save'><fieldset disabled>"
            "<legend><label>Query<input id='q' name='q'></label></legend>"
            "<label>Email<input id='email' type='email' name='email'></label></fieldset>"
            "<button type='submit'>Save</button></form>",
        )
        saved = one(result, sample)
        assert saved.enabled is expected and "query" in props(saved) and "email" not in props(saved)
        assert next(item for item in facts.elements if item.html_id == "q").disabled is False
        assert next(item for item in facts.elements if item.html_id == "email").disabled is True
        return
    if case == "choices":
        result, _facts = _html(
            page,
            "<form method='post' action='/cart'><fieldset disabled>"
            "<label><input type='radio' name='size' value='s'> S</label>"
            "<label><input type='radio' name='size' value='m'> M</label></fieldset>"
            "<button type='submit'>Add to cart</button></form>",
        )
        added = one(result, sample)
        assert added.enabled is expected and added.x is not None and added.x.reason == "disabled"
        assert one(result, "set_size").enabled is False
        return
    if case != "modal":
        raise AssertionError(case)
    result, facts = _html(
        page,
        "<style>body{margin:0}</style>"
        "<div style='transform:translateZ(0);position:relative;z-index:0'>"
        "<div id='low' role='dialog' aria-modal='true' aria-label='Low' "
        "style='position:fixed;top:16px;left:16px;width:160px;height:48px;z-index:80'>"
        "<button type='button'>Low</button></div></div>"
        "<div id='high' role='dialog' aria-modal='true' aria-label='High' "
        "style='position:fixed;top:200px;left:16px;width:160px;height:48px;z-index:1'>"
        "<button type='button'>High</button></div>",
    )
    assert next(modal.html_id for modal in facts.modals if modal.top) == sample
    assert one(result, "do_high").enabled is expected
    assert one(result, "do_low").x is not None
    assert one(result, "do_low").x.reason == "blocked by dialog"
