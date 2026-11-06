"""M2 gate items carried into M3. One table per fix."""

from __future__ import annotations

import subprocess
import sys

import pytest
from playwright.sync_api import Page

from interface_compiler.browser import facts as facts_module
from interface_compiler.browser.facts import _AxHit, _element, collect_facts
from interface_compiler.browser.raw import raw_snapshot


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tag": "button",
        "role": "button",
        "name": "ignored",
        "html_id": "go",
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
        "options": [],
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
        "box": {"x": 0, "y": 0, "width": 10, "height": 10},
        "visible": True,
        "covered": False,
        "in_viewport": True,
        "validation_message": "",
        "landmark": "",
        "css": "button",
        "skeleton_path": "button|button",
        "label_text": "",
        "group_key": None,
        "constraints": {
            "required": False,
            "pattern": None,
            "min": None,
            "max": None,
            "step": None,
            "minlength": None,
            "maxlength": None,
        },
        "in_dialog": False,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Pay  ", "Pay"),
        ("Pay\nnow", "Pay now"),
        ("A  B", "A B"),
    ],
)
def test_ax_names_are_trimmed_like_html_names(raw: str, expected: str) -> None:
    element = _element(_row(), _AxHit(role="button", name=raw))
    assert element.name == expected
    assert element.name_source == "ax"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("both", ("title", "identity")),
        ("identity", ("identity",)),
    ],
)
def test_skipped_document_checks_are_visible(
    facts_page: Page,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: tuple[str, ...],
) -> None:
    calls = {"n": 0}
    real = facts_module._ax_call_fits

    def fake(needed: float) -> bool:
        if needed == facts_module._DOCUMENT_CHECK_S:
            calls["n"] += 1
            if mode == "both":
                return False
            return calls["n"] == 1
        return real(needed)

    monkeypatch.setattr(facts_module, "_ax_call_fits", fake)
    facts_page.set_content("<!doctype html><title>T</title><button type='button'>Go</button>")
    result = collect_facts(facts_page)
    assert result.skipped_checks == expected
    assert result.truncated is True
    assert result.title == "T"
    assert result.elements


def test_open_shadow_is_collected_and_closed_is_not(facts_page: Page) -> None:
    facts_page.set_content(
        "<!doctype html><title>shadow</title>"
        "<div id='host'><template shadowrootmode='open'>"
        "<button id='in' type='button'>Inside</button></template></div>"
        "<div id='closed'></div>"
        "<script>document.getElementById('closed').attachShadow({mode:'closed'})"
        ".innerHTML = \"<button id='secret' type='button'>Secret</button>\";</script>",
        wait_until="domcontentloaded",
    )
    facts = collect_facts(facts_page)
    names = {element.name for element in facts.elements}
    assert "Inside" in names
    assert "Secret" not in names
    assert facts.skipped_checks == ()
    snapshot = raw_snapshot(facts_page)
    assert "Inside" in snapshot
    assert "Secret" not in snapshot


def test_object_id_cap_keeps_the_later_widget(facts_page: Page) -> None:
    links = "".join(f"<a id='l{index}' href='/l{index}'>Link {index}</a>" for index in range(180))
    facts_page.set_content(
        "<!doctype html><title>cap</title>"
        f"{links}<span id='axlab' aria-label='From AX'></span>"
        "<button id='go' aria-labelledby='axlab'>ignored</button>",
        wait_until="domcontentloaded",
    )
    facts = collect_facts(facts_page)
    button = next(element for element in facts.elements if element.html_id == "go")
    assert facts.ax_capped is True
    assert button.name == "From AX"
    assert button.name_source == "ax"


def test_long_line_does_not_fail_close_a_later_button(facts_page: Page) -> None:
    links = "".join(f"<a id='a{index}' href='/{index}'>x</a>" for index in range(4000))
    facts_page.set_content(
        "<!doctype html><title>line</title><style>body{margin:0}"
        "#line{white-space:nowrap;margin:0}"
        "#line a{display:inline-block;width:16px;height:19px}"
        "#mask{position:fixed;left:0;top:0;width:20px;height:19px}"
        "#clear{position:absolute;top:80px;left:0;width:80px;height:24px}"
        f"</style><p id='line'>{links}</p><div id='mask'></div>"
        "<button id='clear' type='button'>Clear</button>",
        wait_until="domcontentloaded",
    )
    facts = collect_facts(facts_page)
    by_id = {element.html_id: element for element in facts.elements}
    # a0 and a2 are inside the 12-hit budget. a0 sits on the mask.
    # a20 is past that budget, so the hit test fails closed.
    assert by_id["a0"].covered is True
    assert by_id["a2"].covered is False
    assert by_id["a20"].covered is True
    assert by_id["clear"].covered is False


def test_many_inline_runs_do_not_kill_the_engine() -> None:
    # Own process: a second Playwright in this process fights the session engine.
    script = """
from interface_compiler.browser.engine import Engine
from interface_compiler.browser.facts import collect_facts

pages = [
    "<p>" + ("<span>x</span>" * 30000) + "</p>",
    "<p>" + ("<b>x</b>" * 30000) + "</p>",
    "<div><template shadowrootmode='open'>" + ("<span>x</span>" * 30000) + "</template></div>",
]
engine = Engine()
engine.start()
try:
    for html in pages:
        page = engine.new_page()
        try:
            page.set_content(
                "<!doctype html><title>inline</title><style>body{margin:0}</style>"
                + html
                + "<button id='go' type='button'>Go</button>",
                wait_until="domcontentloaded",
            )
            facts = collect_facts(page)
            button = next(element for element in facts.elements if element.html_id == "go")
            if engine.dead or not facts.truncated or not button.in_viewport or not button.covered:
                raise SystemExit(2)
            page.evaluate("() => 1")
        finally:
            page.context.close()
finally:
    engine.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr


def test_shadow_hit_test_covers_the_light_button(facts_page: Page) -> None:
    facts_page.set_content(
        "<style>body{margin:0}</style>"
        "<button id='under' style='position:absolute;left:0;top:0;width:80px;height:24px'>Under</button>"
        "<div><template shadowrootmode='open'>"
        "<div style='position:fixed;top:0;left:0;width:80px;height:24px'></div></template></div>"
        "<div style='position:absolute;top:48px'>"
        "<template shadowrootmode='open'>"
        "<button id='in' type='button' style='width:80px;height:24px'>Inside</button>"
        "</template></div>",
        wait_until="domcontentloaded",
    )
    facts = collect_facts(facts_page)
    by_id = {item.html_id: item for item in facts.elements}
    assert by_id["under"].covered is True
    assert by_id["in"].covered is False


def test_truncated_page_omits_open_shadow_controls(facts_page: Page) -> None:
    facts_page.set_content(
        "<div></div>" * 8001
        + "<div><template shadowrootmode='open'><button type='button'>Inside</button></template></div>",
        wait_until="domcontentloaded",
    )
    facts = collect_facts(facts_page)
    assert facts.truncated is True
    assert "Inside" not in {item.name for item in facts.elements}
