"""Facts collected from every §13.1 fixture page."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Page

from interface_compiler.browser.engine import USER_AGENT_SUFFIX
from interface_compiler.browser.facts import Constraints, ElementFact, PageFacts, collect_facts
from interface_compiler.browser.raw import raw_snapshot

_HTML = Path(__file__).resolve().parents[1] / "fixtures" / "html"

# link_group_shuffled.html is the reordered twin of link_group.html (§13.1).
FIXTURES = (
    "link.html",
    "link_group.html",
    "link_group_shuffled.html",
    "button.html",
    "choice_group.html",
    "select.html",
    "checkbox.html",
    "text_inputs.html",
    "form_search.html",
    "form_contact.html",
    "form_product.html",
    "tabs.html",
    "disclosure.html",
    "menu.html",
    "combobox.html",
    "slider.html",
    "dialog.html",
    "pagination.html",
    "jsonld_search.html",
    "jsonld_product.html",
    "webmcp.html",
    "minishop/catalog.html",
    "minishop/product.html",
    "minishop/checkout.html",
    "link_group_rows.html",
    "login_gated.html",
    "menu_options.html",
    "link_group_long.html",
)


def _open(page: Page, base: str, name: str) -> PageFacts:
    page.goto(f"{base}/{name}", wait_until="domcontentloaded", timeout=15_000)
    return collect_facts(page)


def _by_id(facts: PageFacts, html_id: str) -> ElementFact:
    found = [el for el in facts.elements if el.html_id == html_id]
    assert len(found) == 1, html_id
    return found[0]


def _expect(el: ElementFact, **wanted: object) -> None:
    for key, value in wanted.items():
        actual = getattr(el, key)
        assert actual == value, f"{el.html_id or el.tag}.{key}: {actual!r}"


def _options(el: ElementFact) -> list[tuple[str, str, bool]]:
    return [(opt.value, opt.label, opt.disabled) for opt in el.options]


def test_facts_fixture_files_match_plan() -> None:
    found = sorted(path.relative_to(_HTML).as_posix() for path in _HTML.rglob("*.html"))
    assert found == sorted(FIXTURES)


def test_facts_every_fixture_element(facts_page: Page, fixture_base_url: str) -> None:
    for name in FIXTURES:
        facts = _open(facts_page, fixture_base_url, name)
        assert facts.elements, name
        assert facts.url.endswith(name)
        for el in facts.elements:
            assert el.role, name
            assert isinstance(el.name, str)
            assert isinstance(el.landmark, str)
            assert isinstance(el.constraints, Constraints)
            assert isinstance(el.options, tuple)
            assert isinstance(el.visible, bool)
            assert isinstance(el.covered, bool)
            assert el.css
            assert el.skeleton_path
            if el.visible:
                assert el.box.width > 0 and el.box.height > 0
            else:
                assert el.covered is False


def test_facts_browser_identifies_itself(facts_page: Page) -> None:
    facts_page.goto("about:blank")
    ua = facts_page.evaluate("() => navigator.userAgent")
    size = facts_page.evaluate("() => ({w: innerWidth, h: innerHeight})")
    language = facts_page.evaluate("() => navigator.language")
    assert ua.endswith(USER_AGENT_SUFFIX)
    assert "Chrome" in ua
    assert size == {"w": 1280, "h": 800}
    assert language == "en-US"


def test_facts_markers_are_removed_and_collection_is_repeatable(
    facts_page: Page, fixture_base_url: str
) -> None:
    first = _open(facts_page, fixture_base_url, "link.html")
    left = facts_page.evaluate("() => document.querySelectorAll('[data-ic-fact]').length")
    second = collect_facts(facts_page)
    assert left == 0
    assert [el.html_id for el in first.elements] == [el.html_id for el in second.elements]
    assert [el.name for el in first.elements] == [el.name for el in second.elements]


def test_facts_raw_snapshot_is_aria_yaml(facts_page: Page, fixture_base_url: str) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")
    text = raw_snapshot(facts_page)
    assert 'link "Cart"' in text
    assert text.strip().startswith("-")


def test_facts_raw_cli_prints_yaml_and_exits(fixture_base_url: str) -> None:
    binary = Path(sys.executable).with_name("interface-compiler")
    completed = subprocess.run(
        [str(binary), "raw", f"{fixture_base_url}/link.html"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert 'link "Cart"' in completed.stdout


def test_facts_links(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "link.html")
    cart = _by_id(facts, "cart")
    _expect(
        cart,
        role="link",
        name="Cart",
        landmark="navigation Shop",
        visible=True,
        covered=False,
        in_viewport=True,
        href=f"{fixture_base_url}/cart",
        css="#cart",
        group_key=None,
    )
    assert "a|link" in cart.skeleton_path
    assert "nav|navigation" in cart.skeleton_path
    catalog = _by_id(facts, "catalog")
    _expect(
        catalog,
        role="link",
        name="Catalog",
        landmark="navigation Shop",
        visible=True,
        covered=False,
    )
    section = _by_id(facts, "section")
    _expect(
        section, role="link", name="Details", landmark="main Product", visible=True, covered=False
    )
    assert section.href.endswith("#details")
    secret = _by_id(facts, "secret")
    _expect(
        secret,
        role="link",
        name="Secret",
        landmark="main Product",
        visible=False,
        covered=False,
        hidden=True,
    )


def test_facts_link_group_keeps_identity_when_order_changes(
    facts_page: Page, fixture_base_url: str
) -> None:
    first = _open(facts_page, fixture_base_url, "link_group.html")
    second = _open(facts_page, fixture_base_url, "link_group_shuffled.html")

    def keys(facts: PageFacts) -> list[tuple[str, str | None]]:
        return [
            (el.name, el.href)
            for el in facts.elements
            if el.html_id is not None and el.html_id.startswith("product-")
        ]

    original = keys(first)
    shuffled = keys(second)
    assert len(original) == 8
    assert original != shuffled
    assert set(original) == set(shuffled)
    sample = _by_id(first, "product-tee-navy")
    _expect(
        sample,
        role="link",
        name="Navy Crew Tee",
        landmark="main Catalog",
        visible=True,
        covered=False,
        href=f"{fixture_base_url}/p/tee-navy",
    )


def test_facts_link_group_long_lists_every_card(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "link_group_long.html")
    links = [el for el in facts.elements if el.tag == "a"]
    assert [el.name for el in links] == [f"Product {i}" for i in range(1, 38)]
    assert all(el.role == "link" and el.visible and not el.covered for el in links)
    _expect(_by_id(facts, "p1"), landmark="main Catalog", in_viewport=True)
    assert _by_id(facts, "p37").href == f"{fixture_base_url}/p/37"


def test_facts_link_group_rows(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "link_group_rows.html")
    story = _by_id(facts, "story-1")
    _expect(
        story, role="link", name="Story one", landmark="main Stories", visible=True, covered=False
    )
    _expect(_by_id(facts, "comments-1"), role="link", name="Comments", visible=True)
    _expect(_by_id(facts, "author-1"), role="link", name="Ada", href=f"{fixture_base_url}/u/ada")
    featured = _by_id(facts, "featured-1")
    _expect(featured, role="link", name="Featured one", landmark="region Featured", visible=True)
    _expect(_by_id(facts, "latest-3"), role="link", name="Latest three", landmark="region Latest")


def test_facts_buttons(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "button.html")
    add = _by_id(facts, "add")
    _expect(
        add, role="button", name="Add to bag", landmark="main Product", visible=True, covered=False
    )
    _expect(_by_id(facts, "more"), role="button", name="Show more", visible=True, covered=False)
    _expect(
        _by_id(facts, "off"),
        role="button",
        name="Unavailable",
        disabled=True,
        visible=True,
        covered=False,
    )
    _expect(
        _by_id(facts, "aria"),
        role="button",
        name="Wait",
        disabled=False,
        aria_disabled=True,
        visible=True,
        covered=False,
    )
    _expect(
        _by_id(facts, "pressed"), role="button", name="Filter", aria_pressed="true", visible=True
    )
    _expect(_by_id(facts, "under"), role="button", name="Under", visible=True, covered=True)


def test_facts_choice_group(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "choice_group.html")
    small = _by_id(facts, "size-s")
    _expect(
        small,
        role="radio",
        name="S",
        group_key="size",
        checked=False,
        disabled=False,
        label_text="S",
        landmark="main Product",
        visible=True,
        covered=False,
    )
    _expect(_by_id(facts, "size-m"), role="radio", name="M", checked=True, group_key="size")
    _expect(
        _by_id(facts, "size-xl"),
        role="radio",
        name="XL",
        disabled=True,
        visible=True,
        covered=False,
    )
    _expect(
        _by_id(facts, "red"),
        role="button",
        name="Red",
        aria_pressed="true",
        group_key="Color",
        visible=True,
        covered=False,
    )
    _expect(_by_id(facts, "blue"), aria_pressed="false", group_key="Color")


def test_facts_select_options(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "select.html")
    size = _by_id(facts, "size")
    _expect(
        size,
        role="combobox",
        name="Size",
        label_text="Size",
        visible=True,
        covered=False,
        value="",
    )
    assert size.constraints == Constraints(True, None, None, None, None, None, None)
    assert size.validation_message
    assert _options(size) == [
        ("", "Choose", False),
        ("S", "S", False),
        ("M", "M", False),
        ("L", "L", False),
        ("XL", "XL - sold out", True),
    ]
    tags = _by_id(facts, "tags")
    _expect(tags, role="listbox", name="Tags", visible=True, covered=False)
    assert _options(tags) == [("red", "Red", False), ("blue", "Blue", True)]


def test_facts_checkbox_and_switch(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "checkbox.html")
    _expect(
        _by_id(facts, "gift"),
        role="checkbox",
        name="Gift wrap",
        checked=False,
        label_text="Gift wrap",
        field_name="gift",
        visible=True,
        covered=False,
    )
    _expect(
        _by_id(facts, "alerts"),
        role="switch",
        name="Alerts",
        checked=True,
        input_type="checkbox",
        visible=True,
        covered=False,
    )


def test_facts_text_inputs(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "text_inputs.html")
    email = _by_id(facts, "email")
    _expect(email, role="textbox", name="Email", input_type="email", visible=True, covered=False)
    assert email.constraints.required is True
    assert email.validation_message
    _expect(_by_id(facts, "site"), role="textbox", name="Site", input_type="url")
    qty = _by_id(facts, "qty")
    _expect(qty, role="spinbutton", name="Qty", input_type="number")
    assert qty.constraints == Constraints(False, None, "1", "9", "1", None, None)
    when = _by_id(facts, "when")
    _expect(when, role="Date", name="When", input_type="date", landmark="main Product")
    assert "input|textbox" in when.skeleton_path
    assert not any(el.name in {"Month", "Day", "Year", "Show date picker"} for el in facts.elements)
    _expect(_by_id(facts, "tel"), role="textbox", name="Phone", input_type="tel")
    code = _by_id(facts, "code")
    _expect(code, role="textbox", name="Code")
    assert code.constraints == Constraints(False, "[A-Z]{3}", None, None, None, 3, 3)
    note = _by_id(facts, "note")
    _expect(note, role="textbox", name="Note", readonly=False, visible=True)
    _expect(_by_id(facts, "lock"), role="textbox", name="Lock", readonly=True, value="fixed")
    form = facts.forms[0]
    assert form.html_id == "fields"
    assert form.method == "get"
    assert form.action == f"{fixture_base_url}/fields"
    assert form.valid is False


def test_facts_search_form(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "form_search.html")
    query = _by_id(facts, "q")
    _expect(
        query,
        role="searchbox",
        name="Query",
        field_name="q",
        landmark="search Site",
        visible=True,
        covered=False,
    )
    _expect(_by_id(facts, "search"), role="search", name="Site")
    form = facts.forms[0]
    assert form.method == "get"
    assert form.action == f"{fixture_base_url}/search"
    assert form.valid is True


def test_facts_contact_form(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "form_contact.html")
    email = _by_id(facts, "email")
    message = _by_id(facts, "message")
    _expect(email, role="textbox", name="Email", landmark="main Contact")
    _expect(message, role="textbox", name="Message")
    assert email.constraints.required is True
    assert message.constraints.required is True
    assert email.validation_message
    assert message.validation_message
    form = facts.forms[0]
    assert form.method == "post"
    assert form.action == f"{fixture_base_url}/contact"
    assert form.valid is False


def test_facts_product_form(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "form_product.html")
    size = _by_id(facts, "size")
    _expect(
        size, role="combobox", name="Size", landmark="main Product", visible=True, covered=False
    )
    assert size.constraints.required is True
    assert size.validation_message
    assert _options(size) == [
        ("", "Choose", False),
        ("S", "S", False),
        ("M", "M", False),
        ("L", "L", False),
    ]
    _expect(_by_id(facts, "add"), role="button", name="Add to cart", visible=True, covered=False)
    assert facts.forms[0].method == "post"
    assert facts.forms[0].action == f"{fixture_base_url}/cart"
    assert facts.forms[0].valid is False


def test_facts_tabs(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "tabs.html")
    _expect(_by_id(facts, "details-tabs"), role="tablist", name="Details", visible=True)
    _expect(_by_id(facts, "ship-tabs"), role="tablist", name="Shipping")
    _expect(
        _by_id(facts, "specs"),
        role="tab",
        name="Specs",
        aria_selected="true",
        visible=True,
        covered=False,
    )
    _expect(_by_id(facts, "reviews"), role="tab", name="Reviews", aria_selected="false")
    _expect(_by_id(facts, "ground"), role="tab", name="Ground", aria_selected="true")
    _expect(_by_id(facts, "air"), role="tab", name="Air", aria_selected="false")


def test_facts_disclosure(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "disclosure.html")
    more = _by_id(facts, "more")
    _expect(
        more,
        role="button",
        name="Description",
        aria_expanded="false",
        aria_controls="panel",
        visible=True,
        covered=False,
    )
    fabric = _by_id(facts, "fabric")
    _expect(
        fabric,
        role="DisclosureTriangle",
        name="Fabric",
        aria_expanded="false",
        visible=True,
        covered=False,
    )
    assert "summary|button" in fabric.skeleton_path
    _expect(_by_id(facts, "fabric-details"), role="group", name="", aria_expanded="false")


def test_facts_menu(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "menu.html")
    _expect(
        _by_id(facts, "sort"),
        role="button",
        name="Sort",
        aria_haspopup="menu",
        aria_expanded="false",
        aria_controls="sort-menu",
        visible=True,
    )
    _expect(_by_id(facts, "by-price"), role="menuitem", name="Price", visible=False, covered=False)
    _expect(_by_id(facts, "by-name"), role="menuitem", name="Name", visible=False, covered=False)
    _expect(
        _by_id(facts, "account"),
        role="button",
        name="Account",
        aria_haspopup="menu",
        aria_expanded="false",
    )
    assert not any(el.html_id == "account-item" for el in facts.elements)


def test_facts_combobox(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "combobox.html")
    city = _by_id(facts, "city")
    _expect(
        city,
        role="combobox",
        name="City",
        aria_expanded="true",
        aria_controls="cities",
        visible=True,
    )
    assert _options(city) == [("Paris", "Paris", False), ("Rome", "Rome", False)]
    free = _by_id(facts, "free")
    _expect(free, role="combobox", name="Note", aria_expanded="false", visible=True, covered=False)
    assert free.options == ()
    _expect(_by_id(facts, "paris"), role="option", name="Paris", visible=True)


def test_facts_sliders(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "slider.html")
    volume = _by_id(facts, "vol")
    _expect(volume, role="slider", name="Volume", value="3", visible=True, covered=False)
    assert volume.constraints == Constraints(False, None, "0", "10", "1", None, None)
    zoom = _by_id(facts, "zoom")
    _expect(
        zoom,
        role="slider",
        name="Zoom",
        aria_valuemin="0",
        aria_valuemax="100",
        aria_valuenow="40",
        visible=True,
        covered=False,
    )
    count = _by_id(facts, "count")
    _expect(count, role="spinbutton", name="Count", value="1")
    assert count.constraints == Constraints(False, None, "0", "5", "0.5", None, None)


def test_facts_dialog(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "dialog.html")
    assert [(modal.html_id, modal.role, modal.name, modal.open) for modal in facts.modals] == [
        ("modal", "dialog", "Confirm", True)
    ]
    _expect(_by_id(facts, "modal"), role="dialog", name="Confirm", visible=True)
    _expect(_by_id(facts, "close"), role="button", name="Close", visible=True, covered=False)
    outside = _by_id(facts, "outside")
    _expect(outside, role="button", name="Outside", visible=True, covered=True)


def test_facts_pagination(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "pagination.html")
    _expect(
        _by_id(facts, "prev"),
        role="link",
        name="Previous",
        aria_disabled=True,
        landmark="navigation Pagination",
        visible=True,
        covered=False,
    )
    _expect(_by_id(facts, "page1"), role="link", name="1", aria_current="page")
    _expect(_by_id(facts, "page2"), role="link", name="2", aria_current=None)
    _expect(_by_id(facts, "next"), role="link", name="Next", visible=True, covered=False)


def test_facts_jsonld_pages_still_expose_controls(facts_page: Page, fixture_base_url: str) -> None:
    search = _open(facts_page, fixture_base_url, "jsonld_search.html")
    _expect(_by_id(search, "title"), role="heading", name="Search", visible=True)
    _expect(
        _by_id(search, "q"), role="searchbox", name="Query", landmark="search Site", visible=True
    )
    product = _open(facts_page, fixture_base_url, "jsonld_product.html")
    _expect(
        _by_id(product, "title"),
        role="heading",
        name="Navy Crew Tee",
        landmark="main Product",
        visible=True,
    )


def test_facts_webmcp_page_has_a_control(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "webmcp.html")
    _expect(
        _by_id(facts, "run"),
        role="button",
        name="Run tool",
        landmark="main Tools",
        visible=True,
        covered=False,
    )


def test_facts_minishop_pages(facts_page: Page, fixture_base_url: str) -> None:
    catalog = _open(facts_page, fixture_base_url, "minishop/catalog.html")
    _expect(
        _by_id(catalog, "tee-navy"),
        role="link",
        name="Navy Crew Tee",
        landmark="main Catalog",
        href=f"{fixture_base_url}/p/tee-navy",
        visible=True,
        covered=False,
    )
    _expect(_by_id(catalog, "cart"), role="link", name="Cart", landmark="navigation Shop")
    product = _open(facts_page, fixture_base_url, "minishop/product.html")
    size = _by_id(product, "size")
    _expect(size, role="combobox", name="Size", landmark="main Product")
    assert [opt.value for opt in size.options] == ["", "S", "M", "L"]
    assert size.validation_message
    _expect(_by_id(product, "add"), role="button", name="Add to cart", visible=True, covered=False)
    _expect(
        _by_id(product, "also"),
        role="link",
        name="White Crew Tee",
        landmark="region You may also like",
    )
    _expect(_by_id(product, "checkout"), role="link", name="Checkout", landmark="main Product")
    assert product.forms[0].valid is False
    checkout = _open(facts_page, fixture_base_url, "minishop/checkout.html")
    address = _by_id(checkout, "address")
    _expect(address, role="textbox", name="Address", landmark="main Checkout", visible=True)
    assert address.constraints.required is True
    assert address.validation_message
    _expect(_by_id(checkout, "pay"), role="button", name="Pay", visible=True, covered=False)
    assert checkout.forms[0].method == "post"
    assert checkout.forms[0].action == f"{fixture_base_url}/pay"


def test_facts_login_gate(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "login_gated.html")
    _expect(
        _by_id(facts, "vote"), role="button", name="Log in to vote", visible=True, covered=False
    )
    vote = _by_id(facts, "vote-link")
    _expect(vote, role="link", name="Vote", visible=True)
    assert vote.href.endswith("/vote?id=1&goto=/login")
    _expect(_by_id(facts, "signin"), role="link", name="Sign in", href=f"{fixture_base_url}/login")
    assert facts.forms[0].method == "post"
    assert facts.forms[0].action == f"{fixture_base_url}/login?next=/story"


def test_facts_menu_options(facts_page: Page, fixture_base_url: str) -> None:
    facts = _open(facts_page, fixture_base_url, "menu_options.html")
    _expect(
        _by_id(facts, "sort-newest"),
        role="menuitemradio",
        name="Newest",
        visible=False,
        covered=False,
    )
    _expect(
        _by_id(facts, "open-price"),
        role="menuitemradio",
        name="Price",
        aria_checked="true",
        visible=True,
        covered=False,
    )
    native = _by_id(facts, "native")
    _expect(native, role="combobox", name="Size", visible=True, covered=False)
    assert _options(native) == [("new", "Newest", False), ("price", "Price", False)]
