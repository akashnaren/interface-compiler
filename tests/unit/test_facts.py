"""Facts collected from every §13.1 fixture page."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from interface_compiler.browser.engine import USER_AGENT_SUFFIX, Engine
from interface_compiler.browser.facts import (
    _COLLECT_SOURCE,
    Constraints,
    ElementFact,
    FactCollectionError,
    PageFacts,
    _accessibility_overlay,
    _non_negative_int,
    _overlay_budget,
    _overlay_order,
    _page_facts,
    collect_facts,
)
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


def test_facts_line_coverage_follows_the_mask(facts_page: Page) -> None:
    # 40px targets. C is covered. Fixed bars, then masks that are not position:fixed.
    cases = (
        ("full", "fixed", 10, 0, 10, "CCCCCCCCCC"),
        ("pair", "fixed", 2, 0, 1, "C."),
        ("solo", "fixed", 1, 0, 1, "C"),
        ("mid", "fixed", 3, 1, 2, ".C."),
        ("tail", "fixed", 10, 5, 10, ".....CCCCC"),
        ("one", "fixed", 10, 4, 5, "....C....."),
        ("right", "inline", 10, 7, 10, ".......CCC"),
        ("head", "fixed", 10, 0, 3, "CCC......."),
        ("xform", "transform", 3, 0, 3, "CCC"),
        ("shadow", "shadow", 3, 0, 3, "CCC"),
        ("fade", "margin", 3, 0, 3, "CCC"),
        ("grid", "grid", 3, 0, 3, "CCC"),
        ("flex", "flex", 3, 0, 3, "CCC"),
        ("over", "overflow", 1, 0, 1, "C"),
        ("before", "before", 3, 1, 3, ".CC"),
        ("center", "center", 14, 0, 14, "." * 14),
        # Clipped to the viewport: the geometric center sits outside.
        ("low", "low", 1, 0, 1, "C"),
        ("side", "side", 1, 0, 1, "C"),
        ("sliver", "sliver", 1, 0, 1, "."),
    )
    parts = [
        "<!doctype html><title>cover</title><style>",
        "body{margin:0}",
        ".row{position:absolute;left:0;height:20px;margin:0;white-space:nowrap}",
        ".mask{position:fixed;height:20px}",
        "#before0{position:relative;z-index:1}",
        "#before0::before{content:'';position:absolute;left:100%;top:0;width:120px;height:20px}",
        "@keyframes icspin { from { opacity: 1 } to { opacity: .2 } }",
        "#mover{position:absolute;left:1200px;top:760px;width:10px;height:10px;",
        "animation:icspin 8s linear infinite}",
        "</style>",
    ]

    def link(prefix: str, index: int, plain: bool) -> str:
        if plain:
            return (
                f'<a id="{prefix}{index}" href="/{index}">'
                '<span style="display:inline-block;width:40px;height:20px">x</span></a>'
            )
        return (
            f'<a id="{prefix}{index}" href="/{index}" '
            'style="display:inline-block;width:40px;height:20px">x</a>'
        )

    for slot, (prefix, kind, count, start, end, _expected) in enumerate(cases):
        top = slot * 40
        links = "".join(link(prefix, index, kind == "inline") for index in range(count))
        width = (end - start) * 40
        if kind in {"fixed", "inline"}:
            parts.append(f'<div class="row" style="top:{top}px">{links}</div>')
            parts.append(
                f'<div class="mask" style="top:{top}px;left:{start * 40}px;width:{width}px"></div>'
            )
        elif kind == "transform":
            parts.append(
                f'<div class="row" style="top:{top}px">{links}'
                '<span style="display:inline-block;width:120px;height:20px;'
                'transform:translateX(-120px)"></span></div>'
            )
        elif kind == "shadow":
            parts.append(f'<div class="row" style="top:{top}px">{links}</div>')
            parts.append(
                "<div><template shadowrootmode='open'>"
                f'<div style="position:fixed;top:{top}px;left:0;width:120px;height:20px"></div>'
                "</template></div>"
            )
        elif kind == "margin":
            parts.append(
                f'<div class="row" style="top:{top}px">{links}'
                '<span style="display:inline-block;width:120px;height:20px;'
                'margin-left:-120px;opacity:.99"></span></div>'
            )
        elif kind == "grid":
            parts.append(
                f'<div class="row" style="top:{top}px;display:grid;'
                'grid-template-columns:40px 40px 40px;width:120px">'
                f'<a id="{prefix}0" href="/0" style="grid-area:1/1;width:40px;height:20px">x</a>'
                f'<a id="{prefix}1" href="/1" style="grid-area:1/2;width:40px;height:20px">x</a>'
                f'<a id="{prefix}2" href="/2" style="grid-area:1/3;width:40px;height:20px">x</a>'
                '<div style="grid-area:1/1/2/4;z-index:1"></div></div>'
            )
        elif kind == "flex":
            parts.append(
                f'<div class="row" style="top:{top}px;display:flex;width:120px">'
                f'<a id="{prefix}0" href="/0" style="flex:0 0 40px;height:20px">x</a>'
                f'<a id="{prefix}1" href="/1" style="flex:0 0 40px;height:20px">x</a>'
                f'<a id="{prefix}2" href="/2" style="flex:0 0 40px;height:20px">x</a>'
                '<div style="flex:0 0 120px;height:20px;margin-left:-120px;z-index:1"></div>'
                "</div>"
            )
        elif kind == "overflow":
            parts.append(
                f'<div class="row" style="top:{top}px;height:24px">'
                f'<button id="{prefix}0" style="width:80px;height:24px">Go</button>'
                '<div style="position:relative;width:10px;height:10px;margin-top:-24px">'
                '<div style="width:80px;height:24px"></div></div></div>'
            )
        elif kind == "before":
            parts.append(f'<div class="row" style="top:{top}px">{links}</div>')
        elif kind == "center":
            parts.append(
                f'<div class="row" style="top:{top}px;width:1280px;display:flex;'
                f'justify-content:center">{links}</div>'
            )
        elif kind == "low":
            parts.append(
                "<button id='low0' style='position:absolute;top:720px;left:0;"
                "width:80px;height:200px;margin:0;padding:0;border:0;"
                "box-sizing:border-box'>Go</button>"
                "<div class='mask' style='top:680px;left:0;width:120px;height:120px'></div>"
            )
        elif kind == "side":
            parts.append(
                "<button id='side0' style='position:absolute;left:-50px;top:640px;"
                "width:80px;height:24px;margin:0;padding:0;border:0;"
                "box-sizing:border-box'>Go</button>"
                "<div class='mask' style='top:640px;left:0;width:40px;height:24px'></div>"
            )
        elif kind == "sliver":
            parts.append(
                "<button id='sliver0' style='position:absolute;left:900px;top:-16px;"
                "width:40px;height:24px;margin:0;padding:0;border:0;"
                "box-sizing:border-box'>Go</button>"
            )
        else:
            raise AssertionError(kind)
    parts.append('<div id="mover"></div>')
    parts.append(
        "<script>window.__icStarts=0;"
        "document.getElementById('mover').addEventListener('animationstart',"
        "() => { window.__icStarts += 1; });</script>"
    )
    facts_page.set_content("".join(parts), wait_until="domcontentloaded")
    facts_page.wait_for_function(
        """() => {
          const anim = document.getElementById('mover').getAnimations()[0];
          const time = anim && anim.currentTime;
          const ms = typeof time === 'number' ? time : time && time.value;
          return window.__icStarts === 1 && ms > 0;
        }"""
    )
    started_ms, starts = _animation_clock(facts_page)
    before = _watch_dom(facts_page)
    facts = collect_facts(facts_page)
    _assert_dom_unchanged(facts_page, before)
    later_ms, later_starts = _animation_clock(facts_page)
    assert later_starts == starts == 1
    assert later_ms >= started_ms
    for prefix, _kind, count, _start, _end, expected in cases:
        flags = [
            "C" if _by_id(facts, f"{prefix}{index}").covered else "." for index in range(count)
        ]
        assert "".join(flags) == expected, prefix
    _assert_solo_covers(facts_page)
    _assert_capped_line_fails_closed(facts_page)


def _animation_clock(page: Page) -> tuple[float, int]:
    ms, starts = page.evaluate(
        """() => {
          const anim = document.getElementById('mover').getAnimations()[0];
          const time = anim.currentTime;
          const ms = typeof time === 'number' ? time : time.value;
          return [ms, window.__icStarts];
        }"""
    )
    return float(ms), int(starts)


def _watch_dom(page: Page) -> list[str | None]:
    return page.evaluate(
        """() => {
          window.__icMutations = 0;
          const observer = new MutationObserver((records) => {
            window.__icMutations += records.length;
          });
          observer.observe(document.documentElement, {
            subtree: true,
            attributes: true,
            childList: true,
            characterData: true,
          });
          window.__icStopObs = () => observer.disconnect();
          return [...document.querySelectorAll('*')].map((el) => el.getAttribute('style'));
        }"""
    )


def _assert_dom_unchanged(page: Page, before: list[str | None]) -> None:
    after, mutations = page.evaluate(
        """() => new Promise((resolve) => {
          setTimeout(() => {
            if (window.__icStopObs) window.__icStopObs();
            resolve([
              [...document.querySelectorAll('*')].map((el) => el.getAttribute('style')),
              window.__icMutations,
            ]);
          }, 0);
        })"""
    )
    assert after == before
    assert mutations == 0


def _hit_covers(page: Page, selector: str) -> list[bool]:
    return page.evaluate(
        """(selector) => [...document.querySelectorAll(selector)].map((el) => {
          const rect = el.getBoundingClientRect();
          const left = Math.max(rect.left, 0);
          const top = Math.max(rect.top, 0);
          const right = Math.min(rect.right, innerWidth);
          const bottom = Math.min(rect.bottom, innerHeight);
          if (rect.width <= 0 || rect.height <= 0 || right <= left || bottom <= top) {
            return false;
          }
          const hit = document.elementFromPoint((left + right) / 2, (top + bottom) / 2);
          if (!hit) return true;
          return hit !== el && !el.contains(hit);
        })""",
        selector,
    )


def _collect_watched(page: Page, html: str) -> PageFacts:
    page.set_content(html, wait_until="domcontentloaded")
    before = _watch_dom(page)
    facts = collect_facts(page)
    _assert_dom_unchanged(page, before)
    return facts


def _assert_solo_covers(page: Page) -> None:
    footer = _collect_watched(
        page,
        "<!doctype html><title>footer</title><style>body{margin:0}</style>"
        "<button id='foot0' style='width:80px;height:24px'>Go</button>"
        "<footer style='position:absolute;top:3000px;height:40px'>"
        "<div style='position:fixed;top:0;left:0;width:80px;height:24px'></div>"
        "</footer>",
    )
    assert _by_id(footer, "foot0").covered is True
    fixed = _collect_watched(
        page,
        "<!doctype html><title>fixed</title><style>body{margin:0}</style>"
        "<button id='under0' style='width:80px;height:24px'>Go</button>"
        "<a id='off0' href='/off' style='position:absolute;top:3000px'>"
        "<span style='position:fixed;top:0;left:0;width:80px;height:24px;display:block'>"
        "</span></a>",
    )
    assert _by_id(fixed, "under0").covered is True
    assert _by_id(fixed, "off0").covered is False
    links = "".join(
        f"<a id='flex{index}' href='/{index}' style='display:block;height:20px;width:80px'>x</a>"
        for index in range(60)
    )
    page.set_content(
        "<!doctype html><title>flexend</title><style>body{margin:0}</style>"
        "<div id='col' style='display:flex;flex-direction:column;justify-content:flex-end;"
        "height:1200px;width:200px'>"
        f"{links}</div>"
        "<div id='bar' style='position:fixed;top:0;left:0;width:300px;height:300px'></div>",
        wait_until="domcontentloaded",
    )
    expected = _hit_covers(page, "#col a")
    flex = _collect_watched(
        page,
        "<!doctype html><title>flexend</title><style>body{margin:0}</style>"
        "<div id='col' style='display:flex;flex-direction:column;justify-content:flex-end;"
        "height:1200px;width:200px'>"
        f"{links}</div>"
        "<div id='bar' style='position:fixed;top:0;left:0;width:300px;height:300px'></div>",
    )
    # set_content above was only for the probe. Collect the same document again.
    found = [_by_id(flex, f"flex{index}").covered for index in range(60)]
    assert found == expected
    assert any(found)
    assert not all(found)
    page.set_content(
        "<!doctype html><title>important</title><style>a{display:none !important}"
        "body{margin:0}</style>"
        "<a id='imp0' href='/x' style='display:block !important;position:absolute;"
        "top:3000px;height:24px;width:40px'>x</a>",
        wait_until="domcontentloaded",
    )
    measured = page.evaluate(
        """() => {
          const style = getComputedStyle(document.getElementById('imp0'));
          return {display: style.display, height: style.height};
        }"""
    )
    important = _collect_watched(
        page,
        "<!doctype html><title>important</title><style>a{display:none !important}"
        "body{margin:0}</style>"
        "<a id='imp0' href='/x' style='display:block !important;position:absolute;"
        "top:3000px;height:24px;width:40px'>x</a>",
    )
    again = page.evaluate(
        """() => {
          const style = getComputedStyle(document.getElementById('imp0'));
          return {display: style.display, height: style.height};
        }"""
    )
    assert measured == {"display": "block", "height": "24px"}
    assert again == measured
    assert _by_id(important, "imp0").covered is False


def _assert_capped_line_fails_closed(page: Page) -> None:
    # Own document. A 4000-link line makes elementFromPoint slow enough that
    # the same page would fail closed the rows above it.
    links = "".join(f"<a id='a{index}' href='/{index}'>x</a>" for index in range(4000))
    facts = _collect_watched(
        page,
        "<!doctype html><title>cap</title><style>body{margin:0}"
        "#line{white-space:nowrap;margin:0}"
        "#line a{display:inline-block;width:16px;height:19px}"
        "#mask{position:fixed;left:200px;top:0;width:40px;height:19px}"
        f"</style><p id='line'>{links}</p><div id='mask'></div>",
    )
    # a13's clipped center is (216, 9.5), on #mask. a0 is clear of the mask.
    assert _by_id(facts, "a0").covered is False
    assert _by_id(facts, "a13").covered is True
    if facts.truncated:
        assert _by_id(facts, "a79").covered is True


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
    _expect(when, role="textbox", name="When", input_type="date", landmark="main Product")
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
        role="button",
        name="Fabric",
        aria_expanded="false",
        visible=True,
        covered=False,
    )
    assert "summary|button" in fabric.skeleton_path
    _expect(
        _by_id(facts, "fabric-details"),
        role="group",
        name="Fabric Cotton",
        aria_expanded="false",
        name_source="html",
    )


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


def test_facts_isolated_world_ignores_page_overrides(
    facts_page: Page, fixture_base_url: str
) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")
    facts_page.evaluate(
        """() => {
            document.querySelectorAll = () => [];
            Array.from = () => { throw new Error("overridden"); };
        }"""
    )
    facts = collect_facts(facts_page)
    assert any(el.html_id == "cart" for el in facts.elements)
    left = facts_page.evaluate("() => document.querySelector('[data-ic-fact]')")
    assert left is None


def test_engine_launch_passes_chromium_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: dict[str, object] = {}

    class _Browser:
        def new_browser_cdp_session(self) -> _Browser:
            return self

        def send(self, _method: str) -> dict[str, str]:
            return {"userAgent": "Mozilla/5.0 Chrome/1.0"}

        def detach(self) -> None:
            return None

        def close(self) -> None:
            return None

    class _Playwright:
        def __init__(self) -> None:
            self.chromium = self

        def launch(self, **kwargs: object) -> _Browser:
            launched.update(kwargs)
            return _Browser()

        def stop(self) -> None:
            return None

    class _Driver:
        def start(self) -> _Playwright:
            return _Playwright()

    monkeypatch.setattr("interface_compiler.browser.engine.sync_playwright", _Driver)
    engine = Engine()
    engine.start()
    engine.close()
    assert launched.get("chromium_sandbox") is True


def test_engine_refuses_root_before_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interface_compiler.browser.engine.os.geteuid", lambda: 0)
    engine = Engine()
    with pytest.raises(RuntimeError, match="Do not run the browser as root"):
        engine.start()


@pytest.mark.parametrize(
    ("html", "method", "valid"),
    [
        (
            (
                "<form id='f' method='get' action='/search'>"
                "<input name='checkValidity' required>"
                "<button id='go' type='submit' formmethod='post' formaction='/save'>Save</button>"
                "</form>"
            ),
            "post",
            False,
        ),
    ],
)
def test_facts_submit_override_and_form_validity(
    html: str, method: str, valid: bool, facts_page: Page
) -> None:
    facts_page.set_content(f"<!doctype html><title>form</title>{html}")
    facts = collect_facts(facts_page)
    button = _by_id(facts, "go")
    assert button.form_method == method
    assert button.form_action is not None and button.form_action.endswith("/save")
    assert facts.forms[0].method == "get"
    assert facts.forms[0].valid is valid


_MOVE_MARKER = (
    '<img id="decoy" alt="Search"><button id="go" type="button">Delete account</button>'
    "<script>new MutationObserver(function(records){var img=document.getElementById('decoy');"
    "records.forEach(function(record){var name=record.attributeName;"
    "if(!name||name.indexOf('data-ic-')!==0)return;var from=record.target;"
    "if(!from||from===img)return;var value=from.getAttribute(name);if(value===null)return;"
    "from.removeAttribute(name);img.setAttribute(name,value);});}).observe("
    "document.documentElement,{subtree:true,attributes:true,attributeOldValue:true});</script>"
)
_SWAP_MARKER = (
    '<button id="decoy" type="button">Search</button>'
    '<button id="go" type="button">Delete account</button>'
    "<script>new MutationObserver(function(records){var names=[];"
    "records.forEach(function(record){var name=record.attributeName;"
    "if(name&&name.indexOf('data-ic-')===0&&names.indexOf(name)<0)names.push(name);});"
    "var a=document.getElementById('go'),b=document.getElementById('decoy');"
    "names.forEach(function(name){var av=a.getAttribute(name),bv=b.getAttribute(name);"
    "if(av===null&&bv===null)return;if(bv===null){a.removeAttribute(name);"
    "b.setAttribute(name,av);return;}if(av===null){b.removeAttribute(name);"
    "a.setAttribute(name,bv);return;}a.setAttribute(name,bv);b.setAttribute(name,av);});"
    "}).observe(document.documentElement,{subtree:true,attributes:true,"
    "attributeOldValue:true});</script>"
)


@pytest.mark.parametrize(
    ("html", "html_id", "role", "name", "banned"),
    [
        (
            '<img alt="Search" data-ic-fact="0"><button id="go">Delete account</button>',
            "go",
            "button",
            "Delete account",
            "Search",
        ),
        (_MOVE_MARKER, "go", "button", "Delete account", "Search"),
        (_SWAP_MARKER, "go", "button", "Delete account", None),
    ],
)
def test_facts_preseeded_marker_cannot_relabel(
    html: str,
    html_id: str,
    role: str,
    name: str,
    banned: str | None,
    facts_page: Page,
) -> None:
    facts_page.set_content(f"<!doctype html><title>marker</title>{html}")
    facts = collect_facts(facts_page)
    element = _by_id(facts, html_id)
    assert element.role == role
    assert element.name == name
    if banned is not None:
        assert all(item.name != banned for item in facts.elements)


@pytest.mark.parametrize(
    ("html", "html_id"),
    [
        ("<fieldset disabled><input id='field'></fieldset>", "field"),
        ("<fieldset disabled><button id='go'>Go</button></fieldset>", "go"),
        (
            "<select id='s'><optgroup disabled><option id='sold' value='1'>One</option></optgroup></select>",
            "sold",
        ),
        (
            "<div role='listbox'><div id='sold' role='option' aria-disabled='true'>Sold</div></div>",
            "sold",
        ),
    ],
)
def test_facts_ancestor_disabled_controls(html: str, html_id: str, facts_page: Page) -> None:
    facts_page.set_content(f"<!doctype html><title>disabled</title>{html}")
    facts = collect_facts(facts_page)
    assert _by_id(facts, html_id).disabled is True
    for host in facts.elements:
        if host.options:
            assert host.options[0].disabled is True


def _text_at(page: Page, css: str) -> str:
    text = page.evaluate(
        "(css) => { const node = document.querySelector(css); return node ? node.textContent : ''; }",
        css,
    )
    assert isinstance(text, str)
    return text


def _assert_late_controls_ship_a_row_or_the_deadline() -> None:
    # A million siblings before two id-less controls, at throttle 6. A fast
    # renderer can still position Pay; an empty success is the failure.
    script = """
import sys
from interface_compiler.browser.engine import Engine
from interface_compiler.browser.facts import FactCollectionError, collect_facts

engine = Engine()
engine.start()
page = engine.new_page()
try:
    page.set_content(
        "<!doctype html><title>late</title>"
        + "<i></i>" * 1_000_000
        + "<button type='button'>Pay</button><a href='/x'>Go</a>",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    session = page.context.new_cdp_session(page)
    session.send("Emulation.setCPUThrottlingRate", {"rate": 6})
    try:
        facts = collect_facts(page)
    except FactCollectionError as exc:
        if "deadline" not in str(exc):
            sys.stderr.write(str(exc))
            raise SystemExit(2)
    else:
        rows = [(element.name, element.css) for element in facts.elements]
        if not rows:
            sys.stderr.write("elements=0 truncated=%s\\n" % facts.truncated)
            raise SystemExit(3)
        names = [name for name, _css in rows]
        if any(name not in ("Pay", "Go") for name in names) or len(names) > 2:
            sys.stderr.write("rows=%s\\n" % (rows,))
            raise SystemExit(3)
        if len(names) < 2 and not facts.truncated:
            sys.stderr.write("rows=%s truncated=%s\\n" % (rows, facts.truncated))
            raise SystemExit(3)
        resolved = page.evaluate(
            "(rows) => rows.map((row) => {"
            " const node = document.querySelector(row.css);"
            " return node ? node.textContent : '';"
            "})",
            [{"css": css} for _name, css in rows],
        )
        if resolved != names:
            sys.stderr.write("resolved=%s rows=%s\\n" % (resolved, rows))
            raise SystemExit(3)
finally:
    engine.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr


def _require_selector(page: Page, facts: PageFacts, label: str, *, required: bool) -> None:
    # A duplicate id or name must not select the earlier control. An unfinished
    # count drops the later row instead of emitting #id or tag[name].
    found = [element for element in facts.elements if element.name == label]
    assert len(found) <= 1, label
    if not found:
        assert required is False
        assert facts.truncated is True
        return
    element = found[0]
    assert element.css not in {"#dup", 'button[name="same"]'}
    assert _text_at(page, element.css) == label


@pytest.mark.parametrize(
    ("case", "disabled", "aria_disabled"),
    [
        (
            "legend",
            {
                "leg": False,
                "legin": False,
                "legta": False,
                "legsel": False,
                "legopt": False,
                "out": True,
                "leg2": True,
            },
            {},
        ),
        ("aria", {}, {"own": False, "bare": False, "yes": True}),
        ("dup-id", {}, {}),
        ("dup-name", {}, {}),
        ("no-rows", {}, {}),
    ],
)
def test_facts_first_legend_stays_enabled_and_duplicate_selectors_resolve(
    case: str,
    disabled: dict[str, bool],
    aria_disabled: dict[str, bool],
    facts_page: Page,
) -> None:
    if case == "legend":
        html = (
            "<fieldset disabled><legend>"
            "<button id='leg' type='button'>Leg</button>"
            "<input id='legin'>"
            "<textarea id='legta'></textarea>"
            "<select id='legsel'><option id='legopt'>A</option></select>"
            "</legend><button id='out' type='button'>Out</button></fieldset>"
            "<fieldset disabled><legend>First</legend>"
            "<legend><button id='leg2' type='button'>Second</button></legend>"
            "</fieldset>"
        )
    elif case == "aria":
        html = (
            "<div aria-disabled='true'>"
            "<button id='own' type='button' aria-disabled='false'>No</button>"
            "<button id='bare' type='button'>Bare</button>"
            "</div>"
            "<button id='yes' type='button' aria-disabled='true'>Yes</button>"
        )
    elif case == "dup-id":
        html = (
            "<button id='dup' type='button'>Keep my data</button>"
            + "".join(f"<i id='i{index}'>x</i>" for index in range(1_000_000))
            + "<button id='dup' type='button'>Delete everything</button>"
        )
    elif case == "dup-name":
        html = (
            "<button type='button' name='same'>One</button>"
            + "<div name='n'></div>" * 100_000
            + "<button type='button' name='same'>Two</button>"
        )
    elif case == "no-rows":
        # A million siblings before id-less controls. The child browser keeps
        # a deadline kill off the session engine.
        _assert_late_controls_ship_a_row_or_the_deadline()
        return
    else:
        raise AssertionError(case)
    session = None
    try:
        facts_page.set_content(
            f"<!doctype html><title>{case}</title>{html}",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        if case == "dup-name":
            session = facts_page.context.new_cdp_session(facts_page)
            session.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            facts = collect_facts(facts_page, deadline_s=2)
        else:
            facts = collect_facts(facts_page)
        for html_id, expect in disabled.items():
            assert _by_id(facts, html_id).disabled == expect
        for html_id, expect in aria_disabled.items():
            assert _by_id(facts, html_id).aria_disabled == expect
        if case == "legend":
            assert _by_id(facts, "legsel").options[0].disabled is False
        elif case == "dup-id":
            _require_selector(facts_page, facts, "Keep my data", required=True)
            _require_selector(facts_page, facts, "Delete everything", required=False)
        elif case == "dup-name":
            _require_selector(facts_page, facts, "One", required=True)
            _require_selector(facts_page, facts, "Two", required=False)
    finally:
        if session is not None:
            session.send("Emulation.setCPUThrottlingRate", {"rate": 1})
        facts_page.set_content(
            "<!doctype html><title>empty</title>",
            wait_until="domcontentloaded",
        )


def test_facts_ancestor_flags_do_not_wait_for_the_document_walk(facts_page: Page) -> None:
    # A million inlines would exhaust the document walk. Flags still come from
    # each control's own ancestors, or the control is absent.
    filler = "<i>x</i> " * 1_000_000
    try:
        facts_page.set_content(
            "<!doctype html><title>flags</title>"
            f"{filler}"
            "<div style='position:absolute;top:3000px'>"
            "<div inert><button id='delete' type='button'>Delete account</button></div>"
            "<button id='vis' type='button' style='visibility:hidden'>Hidden</button>"
            "<a id='ariah' href='/x' aria-hidden='true'>Secret</a>"
            "<div id='ariad' role='button' aria-disabled='true'>Nope</div>"
            "<input id='vin' style='visibility:hidden'>"
            "</div>",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        facts = collect_facts(facts_page)
    finally:
        facts_page.set_content(
            "<!doctype html><title>empty</title>",
            wait_until="domcontentloaded",
        )

    delete = _by_id(facts, "delete")
    _expect(
        delete,
        inert=True,
        hidden=False,
        aria_hidden=False,
        aria_disabled=False,
        visible=True,
        name="Delete account",
    )
    _expect(
        _by_id(facts, "vis"),
        visible=False,
        inert=False,
        hidden=False,
        aria_hidden=False,
        aria_disabled=False,
    )
    _expect(
        _by_id(facts, "ariah"),
        aria_hidden=True,
        inert=False,
        hidden=False,
        aria_disabled=False,
    )
    _expect(
        _by_id(facts, "ariad"),
        aria_disabled=True,
        inert=False,
        hidden=False,
        aria_hidden=False,
    )
    _expect(
        _by_id(facts, "vin"),
        visible=False,
        hidden=False,
        inert=False,
        aria_hidden=False,
        aria_disabled=False,
    )


@pytest.mark.parametrize(
    ("minlength", "maxlength", "expect_min", "expect_max"),
    [
        ("1.5", "2.5", 1, 2),
        ("-1", "", None, None),
        ("3", "8", 3, 8),
        ("08", "0", 8, 0),
        (" 3 ", " 4 ", 3, 4),
    ],
)
def test_facts_length_attributes_are_non_negative_integers(
    minlength: str,
    maxlength: str,
    expect_min: int | None,
    expect_max: int | None,
    facts_page: Page,
) -> None:
    facts_page.set_content(
        "<!doctype html><title>length</title>"
        f"<input id='q' minlength='{minlength}' maxlength='{maxlength}'>"
    )
    constraints = _by_id(collect_facts(facts_page), "q").constraints
    assert constraints.minlength == expect_min
    assert constraints.maxlength == expect_max
    assert _non_negative_int({"minlength": 1.5}, "minlength") is None
    assert _non_negative_int({"maxlength": True}, "maxlength") is None


@pytest.mark.parametrize(
    ("control", "html", "valid"),
    [
        ("action", "<form id='f' action='/go'><input name='action' value='nope'></form>", True),
        ("id", "<form id='f' action='/go'><input name='id' value='nope'></form>", True),
        ("matches", "<form id='f' action='/go'><input name='matches' required></form>", False),
        ("type", "", False),
    ],
)
def test_facts_named_form_controls_do_not_shadow_getters(
    control: str,
    html: str,
    valid: bool,
    facts_page: Page,
    fixture_base_url: str,
) -> None:
    if control == "type":
        with pytest.raises(FactCollectionError, match="wrong type"):
            _page_facts(
                "about:blank",
                "",
                {
                    "fields": [],
                    "elements": [],
                    "forms": [
                        {
                            "index": 0,
                            "method": "get",
                            "action": {"shadowed": True},
                            "valid": True,
                            "html_id": None,
                        }
                    ],
                    "modals": [],
                },
                {},
            )
        return
    # set_content stays on about:blank, where the action getter is empty.
    # Writing into the fixture document keeps an http URL, so the getter
    # resolves /go instead of returning the control named action.
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")
    facts_page.evaluate(
        "(html) => { document.open(); document.write(html); document.close(); }",
        f"<!doctype html><title>form</title>{html}",
    )
    form = collect_facts(facts_page).forms[0]
    assert form.html_id == "f"
    assert form.valid is valid
    assert isinstance(form.action, str)
    assert form.action.endswith("/go")
    assert "nope" not in form.action


@pytest.mark.parametrize(
    "accessor",
    [
        "getAttribute",
        "hasAttribute",
        "children",
        "tagName",
        "parentElement",
        "localName",
        "closest",
        "matches",
        "getBoundingClientRect",
        "willValidate",
    ],
)
def test_facts_form_controls_do_not_shadow_dom_accessors(
    accessor: str,
    facts_page: Page,
    fixture_base_url: str,
) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")
    facts_page.evaluate(
        "(html) => { document.open(); document.write(html); document.close(); }",
        (
            "<!doctype html><title>form</title>"
            "<form id='f' action='/go' method='post'>"
            f"<input name='{accessor}' value='nope'>"
            "<button id='go' type='submit'>Go</button>"
            "</form>"
        ),
    )
    facts = collect_facts(facts_page)
    form = facts.forms[0]
    assert form.html_id == "f"
    assert form.method == "post"
    assert form.action.endswith("/go")
    assert "nope" not in form.action
    assert _by_id(facts, "f").tag == "form"
    assert _by_id(facts, "f").name == ""
    assert _by_id(facts, "go").name == "Go"


@pytest.mark.parametrize(
    ("control_type", "role"),
    [
        ("image", "button"),
        ("submit", "button"),
        ("reset", "button"),
        ("button", "button"),
        ("file", "file"),
    ],
)
def test_facts_input_roles_agree_when_the_overlay_stops(
    control_type: str,
    role: str,
    facts_page: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts_page.set_content(
        "<!doctype html><title>roles</title>"
        f"<input id='c' type='{control_type}' alt='Pic' value='Go'>"
    )
    overlaid = _by_id(collect_facts(facts_page), "c")
    monkeypatch.setattr("interface_compiler.browser.facts._OVERLAY_BUDGET_CAP_S", 0.0)
    fallback = _by_id(collect_facts(facts_page), "c")
    assert overlaid.role == role
    assert overlaid.input_type == control_type
    assert overlaid.name_source == "ax"
    assert fallback.role == role
    assert fallback.name_source == "html"


@pytest.mark.parametrize(
    ("html", "name"),
    [
        (
            (
                "<fieldset><legend>Search options</legend>"
                "<input id='c' type='submit' value='Delete account'></fieldset>"
            ),
            "Delete account",
        ),
        (
            "<button id='c'><img alt='Delete account'></button>",
            "Delete account",
        ),
        (
            "<button id='c'><span style='display:none'>Search</span>Pay now</button>",
            "Pay now",
        ),
    ],
)
def test_facts_html_fallback_names_skip_legend_and_hidden_text(
    html: str,
    name: str,
    facts_page: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("interface_compiler.browser.facts._OVERLAY_BUDGET_CAP_S", 0.0)
    facts_page.set_content(f"<!doctype html><title>names</title>{html}")
    element = _by_id(collect_facts(facts_page), "c")
    assert element.name == name
    assert element.name_source == "html"


@pytest.mark.parametrize(
    ("html", "name"),
    [
        (
            "<input id='c' type='submit' title='Search' value='Delete account'>",
            "Delete account",
        ),
        (
            (
                "<span id='by'>Remove</span>"
                "<input id='c' type='submit' aria-labelledby='by' value='Delete account' title='Search'>"
            ),
            "Remove",
        ),
        (
            "<input id='c' type='submit' aria-label='Remove' value='Delete account' title='Search'>",
            "Remove",
        ),
        ("<input id='c' type='submit' title='Search'>", "Submit"),
        ("<input id='c' type='reset' title='Search'>", "Reset"),
        ("<input id='c' type='reset' value='Undo' title='Search'>", "Undo"),
        ("<input id='c' type='image' alt='Delete account' title='Search'>", "Delete account"),
        ("<input id='c' type='file' title='Search'>", "Choose File"),
        (
            "<label for='c'>Upload</label><input id='c' type='file' title='Search'>",
            "Upload",
        ),
        ("<label>Upload<input id='c' type='file'></label>", "Upload"),
        (
            "<button id='c'><span style='visibility:hidden'>Search</span>Pay now</button>",
            "Pay now",
        ),
        ("<button id='c' title='Save'>Delete</button>", "Delete"),
        (
            "<span id='by'>Remove</span><button id='c' aria-labelledby='by'>Delete</button>",
            "Remove",
        ),
        ("<button id='c' aria-label='Remove'>Delete</button>", "Remove"),
        ("<label for='c'>Save</label><button id='c' title='Go'></button>", "Save"),
        ("<label for='c'>Save</label><button id='c'>Delete</button>", "Save"),
        ("<a id='c' href='/x' title='Home'>Delete account</a>", "Delete account"),
        ("<div id='c' role='button' tabindex='0' title='Save'>Delete</div>", "Delete"),
        ("<div id='c' role='switch' title='Save'>Delete</div>", "Delete"),
        ("<div id='c' role='menuitemcheckbox' title='Save'>Delete</div>", "Delete"),
        ("<div id='c' role='menuitemradio' title='Save'>Delete</div>", "Delete"),
        ("<div id='c' role='gridcell' title='Save'>Delete</div>", "Delete"),
        (
            (
                "<button id='c'>Go <span style='visibility:hidden'>NO "
                "<span style='visibility:visible'>VIS</span></span></button>"
            ),
            "Go VIS",
        ),
        ("<label>Save<input id='c' type='submit' value='Go'></label>", "Save"),
        ("<input id='c' type='image' alt=''>", "Submit"),
        ("<input id='c' type='image' title='Search'>", "Search"),
        ("<form id='c'><button type='submit'>Go</button></form>", ""),
        (
            (
                "<fieldset><legend>Search options</legend>"
                "<input id='c' type='image' alt='' title='Search'></fieldset>"
            ),
            "Search",
        ),
        ("<h1 id='c'>Hello <span style='visibility:hidden'>Secret</span></h1>", "Hello"),
        (
            "<h1 id='c' style='visibility:hidden'><span style='visibility:visible'>Secret</span></h1>",
            "",
        ),
    ],
)
def test_facts_control_names_prefer_value_over_title(
    html: str,
    name: str,
    facts_page: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("interface_compiler.browser.facts._OVERLAY_BUDGET_CAP_S", 0.0)
    facts_page.set_content(f"<!doctype html><title>names</title>{html}")
    element = _by_id(collect_facts(facts_page), "c")
    assert element.name == name
    assert element.name_source == "html"


@pytest.mark.parametrize("change", ["replace", "navigate"])
def test_facts_loader_id_is_the_document(
    change: str,
    facts_page: Page,
    fixture_base_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")

    def during_overlay(
        session: object,
        object_ids: list[str],
        budget_s: float,
        order: list[int],
    ) -> dict[str, object]:
        found = _accessibility_overlay(session, object_ids, budget_s, order)
        if change == "replace":
            facts_page.evaluate("() => history.replaceState(null, '', '/shifted?x=1#section')")
        elif change == "navigate":
            facts_page.goto(f"{fixture_base_url}/button.html", wait_until="domcontentloaded")
        else:
            unexpected: str = change
            raise AssertionError(unexpected)
        return found

    monkeypatch.setattr(
        "interface_compiler.browser.facts._accessibility_overlay",
        during_overlay,
    )
    if change == "navigate":
        with pytest.raises(FactCollectionError, match="fact collection lost the document"):
            collect_facts(facts_page)
        return
    facts = collect_facts(facts_page)
    assert facts.url.endswith("/link.html")
    assert "shifted" not in facts.url
    assert facts.title == "Links"
    assert any(element.html_id == "cart" for element in facts.elements)


def test_facts_push_state_keeps_the_walked_document(
    facts_page: Page,
    fixture_base_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")
    facts_page.set_content(
        "<!doctype html><title>Catalog</title>"
        "<main><a id='catalog' href='/p'>Catalog item</a></main>",
        wait_until="domcontentloaded",
    )

    def slow_overlay(
        session: object,
        object_ids: list[str],
        budget_s: float,
        order: list[int],
    ) -> dict[str, object]:
        time.sleep(0.9)
        return _accessibility_overlay(session, object_ids, budget_s, order)

    monkeypatch.setattr(
        "interface_compiler.browser.facts._accessibility_overlay",
        slow_overlay,
    )
    facts_page.evaluate(
        """() => setTimeout(() => {
          history.pushState(null, "", "/checkout");
          document.title = "Checkout";
          document.body.innerHTML = "<main><button id='pay'>Pay</button></main>";
        }, 400)"""
    )
    facts = collect_facts(facts_page)
    assert facts.title == "Catalog"
    assert "/checkout" not in facts.url
    assert facts.truncated is False
    assert any(element.html_id == "catalog" for element in facts.elements)
    assert all(element.html_id != "pay" for element in facts.elements)


@pytest.mark.parametrize(
    ("message", "match"),
    [
        (
            "Execution context was destroyed, most likely because of a navigation",
            "fact collection lost the document",
        ),
        (
            "Target page, context or browser has been closed",
            "fact collection lost the document",
        ),
        ("page.title blew up", "fact collection could not read the document title"),
    ],
)
def test_facts_title_failure_loses_the_document(
    message: str,
    match: str,
    facts_page: Page,
    fixture_base_url: str,
) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")

    def lost() -> str:
        raise PlaywrightError(message)

    facts_page.title = lost
    with pytest.raises(FactCollectionError, match=match) as exc:
        collect_facts(facts_page)
    assert "deadline" not in str(exc.value)


def test_facts_one_second_deadline_raises_when_the_reserve_takes_the_budget(
    facts_page: Page,
) -> None:
    facts_page.set_content("<!doctype html><title>t</title><button id='c'>Go</button>")
    with pytest.raises(ValueError, match="reserved"):
        collect_facts(facts_page, deadline_s=1.0)


def test_facts_zero_walk_budget_raises_the_deadline(
    facts_page: Page, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interface_compiler.browser.facts._collect_source",
        lambda _deadline, _started: f"var WALK_BUDGET_MS = 0;\n{_COLLECT_SOURCE}",
    )
    facts_page.set_content("<!doctype html><title>t</title><button id='c'>Go</button>")
    with pytest.raises(FactCollectionError, match="fact collection exceeded the deadline"):
        collect_facts(facts_page)


def test_facts_missing_driver_refuses_to_collect(
    facts_page: Page, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("interface_compiler.browser.facts._driver_pid", lambda _page: None)
    facts_page.set_content("<!doctype html><title>t</title><button id='c'>Go</button>")
    with pytest.raises(FactCollectionError, match="cannot find the browser driver"):
        collect_facts(facts_page)


@pytest.mark.parametrize(
    ("deadline", "elapsed", "expected"),
    [(5.0, 0.2, 2.5), (5.0, 3.0, 1.0), (5.0, 4.0, 0.0), (5.0, 4.5, 0.0)],
)
def test_facts_overlay_budget_leaves_a_margin(
    deadline: float, elapsed: float, expected: float
) -> None:
    assert _overlay_budget(deadline, elapsed) == expected


@pytest.mark.parametrize(
    ("rows", "order"),
    [
        (
            [
                ["a", "link", True, False],
                ["button", "button", True, True],
                ["h1", "heading", True, True],
            ],
            [1, 0],
        ),
        (
            [
                ["button", "button", False, False],
                ["input", "textbox", True, True],
                ["button", "button", True, False],
            ],
            [1, 0, 2],
        ),
        (
            [
                ["a", "link", False, False],
                ["a", "link", True, False],
                ["button", "button", True, True],
            ],
            [2, 1, 0],
        ),
    ],
)
def test_facts_overlay_prefers_visible_widgets(rows: list[list[object]], order: list[int]) -> None:
    payload = {"fields": ["tag", "role", "visible", "in_viewport"], "elements": rows}
    assert _overlay_order(payload, len(rows)) == order


@pytest.mark.parametrize(
    ("rows", "layout"),
    [(3000, "flat"), (3000, "table"), (4000, "table"), (4000, "inline")],
)
def test_facts_row_count_finishes_under_the_deadline(rows: int, layout: str) -> None:
    # Own browser: a deadline kill must not take down the session engine.
    script = """
import sys
import time
from interface_compiler.browser.engine import Engine
from interface_compiler.browser.facts import FactCollectionError, _DEADLINE_S, collect_facts

rows = int(sys.argv[1])
layout = sys.argv[2]
engine = Engine()
engine.start()
page = engine.new_page()
try:
    parts = ["<!doctype html><title>rows</title>", "<h1>Section</h1>" * 8]
    parts.append("<span id='axlab' aria-label='From AX'></span>")
    parts.append("<button id='go' aria-labelledby='axlab'>ignored</button>")
    if layout == "inline":
        parts.append('<p style="white-space:nowrap">')
        for index in range(rows):
            parts.append(f'<a id="r{index}" href="/r{index}">Row {index}</a>')
        parts.append("</p>")
        for index in range(400):
            parts.append(f'<button type="button"><img alt="Icon {index}"></button>')
    elif layout == "table":
        parts.append("<table><tbody>")
        for index in range(rows):
            parts.append(
                "<tr>"
                f'<td><label for="f{index}">Field {index}</label>'
                f'<input id="f{index}" name="f{index}"></td>'
                f'<td><button type="button">Go {index}</button></td>'
                f'<td><a id="r{index}" href="/r{index}">Row {index}</a></td>'
                "</tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<main>")
        for index in range(rows):
            parts.append(
                f'<label for="f{index}">Field {index}</label>'
                f'<input id="f{index}" name="f{index}">'
                f'<a id="r{index}" href="/r{index}">Row {index}</a>'
            )
        parts.append("</main>")
    page.set_content("".join(parts), wait_until="domcontentloaded")
    started = time.perf_counter()
    facts = collect_facts(page)
    elapsed = time.perf_counter() - started
    inputs = sum(element.tag == "input" for element in facts.elements)
    links = sum(element.tag == "a" for element in facts.elements)
    buttons = sum(element.tag == "button" for element in facts.elements)
    row = next(element for element in facts.elements if element.html_id == "r0")
    go = next(element for element in facts.elements if element.html_id == "go")
    headings = [element for element in facts.elements if element.tag == "h1"]
    covered = [element for element in facts.elements if element.name_source == "ax"]
    actionable = {"a", "button", "input", "select", "textarea", "summary", "option"}
    if layout == "inline":
        if links != rows or buttons < 401 or row.name != "Row 0":
            raise SystemExit(2)
    else:
        field = next(element for element in facts.elements if element.html_id == "f0")
        last = next(element for element in facts.elements if element.html_id == f"f{rows - 1}")
        if not (inputs == rows and links == rows and field.name == "Field 0" and row.name == "Row 0"):
            raise SystemExit(2)
        if last.disabled or last.role != "textbox":
            raise SystemExit(2)
    # Headings come first in the document and are not overlaid. The button is.
    if go.role != "button" or go.name != "From AX" or go.name_source != "ax":
        raise SystemExit(2)
    if not headings or any(element.name_source == "ax" for element in headings):
        raise SystemExit(2)
    if not covered or any(element.tag not in actionable for element in covered):
        raise SystemExit(2)
    # The inline line trips the hit-test cap. Tables and flat rows do not.
    if facts.truncated and layout != "inline":
        sys.stderr.write("truncated elements=%s\\n" % len(facts.elements))
        raise SystemExit(6)
    print(f"{elapsed:.3f} {_DEADLINE_S:.3f} {layout} {rows} {len(facts.elements)}")
finally:
    engine.close()

engine = Engine()
engine.start()
page = engine.new_page()
try:
    page.set_content(
        "<!doctype html><title>busy</title>"
        "<script>setTimeout(function () { while (true) {} }, 0);</script>",
        wait_until="domcontentloaded",
        timeout=5000,
    )
    time.sleep(0.3)
    try:
        collect_facts(page, deadline_s=2)
    except FactCollectionError:
        pass
    else:
        raise SystemExit(3)
    if not engine.dead:
        raise SystemExit(4)
    try:
        engine.new_page()
    except RuntimeError as exc:
        if "dead" not in str(exc).lower():
            raise SystemExit(5)
    else:
        raise SystemExit(5)
finally:
    engine.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(rows), layout],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert completed.returncode == 0, completed.stderr
    elapsed_text, deadline_text = completed.stdout.split()[:2]
    elapsed = float(elapsed_text)
    deadline = float(deadline_text)
    assert elapsed < deadline * 0.8, (
        f"{rows} {layout} rows took {elapsed:.2f}s ({completed.stdout})"
    )


@pytest.mark.parametrize(
    ("kind", "count", "deadline", "throttle"),
    [
        ("table", 12000, 2.0, 1),
        ("table", 20000, 5.0, 4),
        ("nested", 12000, 5.0, 1),
        ("nested", 14000, 5.0, 1),
        ("table", 30000, 5.0, 1),
        ("late", 120000, 2.0, 4),
    ],
)
def test_facts_huge_table_is_truncated_instead_of_killed(
    kind: str,
    count: int,
    deadline: float,
    throttle: int,
) -> None:
    script = """
import sys
from interface_compiler.browser.engine import Engine
from interface_compiler.browser.facts import FactCollectionError, collect_facts

kind = sys.argv[1]
count = int(sys.argv[2])
deadline = float(sys.argv[3])
throttle = int(sys.argv[4])
engine = Engine()
engine.start()
page = engine.new_page()
try:
    parts = ["<!doctype html><title>wide</title>"]
    if kind == "nested":
        opened = "<div>" * 30
        closed = "</div>" * 30
        for index in range(count):
            parts.append("%s<a id='r%d' href='/r%d'>R</a>%s" % (opened, index, index, closed))
    elif kind == "table":
        parts.append("<table><tbody>")
        for index in range(count):
            parts.append(
                "<tr><td><label for='f%d'>Field %d</label>"
                "<input id='f%d' name='f%d'></td>"
                "<td><a id='r%d' href='/r%d'>Row %d</a></td></tr>"
                % (index, index, index, index, index, index, index)
            )
        parts.append("</tbody></table>")
    elif kind == "late":
        # Controls after a long run of empty divs. A walk that stops early
        # must not emit default flags or nth-of-type(1) for a later button.
        parts.append("<div></div>" * count)
        parts.append(
            "<button id='first' type='button'>First</button>"
            "<button id='hid' type='button' style='visibility:hidden'>Hidden</button>"
            "<div inert><button id='nope' type='button'>No</button></div>"
            "<button type='button'>Pay</button>"
        )
    else:
        raise SystemExit(6)
    page.set_content("".join(parts), wait_until="domcontentloaded")
    if throttle > 1:
        session = page.context.new_cdp_session(page)
        session.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
    try:
        facts = collect_facts(page, deadline_s=deadline)
    except FactCollectionError as exc:
        sys.stderr.write(str(exc))
        raise SystemExit(2)
    if kind == "late":
        by_id = {element.html_id: element for element in facts.elements if element.html_id}
        expected = {
            "first": {"visible": True, "inert": False, "name": "First"},
            "hid": {"visible": False, "inert": False, "hidden": False, "aria_hidden": False},
            "nope": {"inert": True, "visible": True, "aria_disabled": False, "hidden": False},
        }
        for html_id, fields in expected.items():
            element = by_id.get(html_id)
            if element is None:
                sys.stderr.write("missing %s\\n" % html_id)
                raise SystemExit(3)
            for key, value in fields.items():
                actual = getattr(element, key)
                if actual != value:
                    sys.stderr.write("%s %s=%r\\n" % (html_id, key, actual))
                    raise SystemExit(3)
        pay = [
            element
            for element in facts.elements
            if element.tag == "button" and element.name == "Pay"
        ]
        if len(pay) > 1:
            sys.stderr.write("pay=%s\\n" % len(pay))
            raise SystemExit(3)
        checked = [by_id["first"], by_id["hid"], by_id["nope"]]
        resolved_expect = ["first", "hid", "nope"]
        if len(pay) == 1:
            pay = pay[0]
            if pay.html_id is not None or pay.inert or pay.visible is not True:
                sys.stderr.write("pay flags\\n")
                raise SystemExit(3)
            if pay.aria_disabled or pay.hidden or pay.css == "body > button:nth-of-type(1)":
                sys.stderr.write("pay css %s\\n" % pay.css)
                raise SystemExit(3)
            checked.append(pay)
            resolved_expect.append("Pay")
        elif not facts.truncated:
            sys.stderr.write("missing pay\\n")
            raise SystemExit(3)
        resolved = page.evaluate(
            "(rows) => rows.map((row) => {"
            " const found = document.querySelector(row.css);"
            " if (!found) return '';"
            " return found.id || found.textContent || '';"
            "})",
            [{"css": element.css} for element in checked],
        )
        if resolved != resolved_expect:
            sys.stderr.write("css %s\\n" % resolved)
            raise SystemExit(3)
    full = 4 if kind == "late" else count * 2 if kind == "table" else count
    got = len(facts.elements)
    if got <= 0 or got > full or (got < full and not facts.truncated):
        sys.stderr.write("elements=%s truncated=%s" % (got, facts.truncated))
        raise SystemExit(3)
    if engine.dead:
        raise SystemExit(4)
    if not isinstance(facts.url, str) or not isinstance(facts.title, str):
        raise SystemExit(5)
    print(len(facts.elements))
finally:
    engine.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, kind, str(count), str(deadline), str(throttle)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert int(completed.stdout.strip()) > 0


def test_facts_busy_renderer_returns_before_the_deadline() -> None:
    # A second sync Playwright in this process fights the session browser, and
    # killing the busy renderer would take that browser down with it. The
    # child process has its own Chromium.
    script = """
import time
from interface_compiler.browser.engine import Engine
from interface_compiler.browser.facts import FactCollectionError, collect_facts

engine = Engine()
engine.start()
page = engine.new_page()
try:
    page.set_content(
        "<!doctype html><title>busy</title>"
        "<script>setTimeout(function () { while (true) {} }, 0);</script>",
        wait_until="domcontentloaded",
        timeout=5000,
    )
    time.sleep(0.3)
    started = time.perf_counter()
    try:
        collect_facts(page, deadline_s=2)
    except FactCollectionError as exc:
        elapsed = time.perf_counter() - started
        if elapsed >= 8 or "deadline" not in str(exc):
            raise SystemExit(1)
    else:
        raise SystemExit(2)
finally:
    engine.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_facts_raw_cli_refuses_file_urls_unless_local_fixture(tmp_path: Path) -> None:
    marker = "IC-LOCAL-FIXTURE-MARKER"
    page = tmp_path / "local.html"
    page.write_text(
        f'<!doctype html><title>local</title><a href="/x">{marker}</a>\n',
        encoding="utf-8",
    )
    binary = Path(sys.executable).with_name("interface-compiler")
    url = page.resolve().as_uri()
    blocked = subprocess.run(
        [str(binary), "raw", url],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert blocked.returncode == 2
    assert marker not in blocked.stdout
    assert "http or https" in blocked.stderr
    scripted = subprocess.run(
        [str(binary), "raw", "--local-fixture", "javascript:alert(1)"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert scripted.returncode == 2
    assert marker not in scripted.stdout
    allowed = subprocess.run(
        [str(binary), "raw", "--local-fixture", url],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert allowed.returncode == 0, allowed.stderr
    assert marker in allowed.stdout
