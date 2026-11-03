"""DOM and accessibility facts for one page.

``x.page``, ``state_from``, ``entities_from``, ``precheck``, ``registry``, and
``blocked`` are not read here. They stay open objects until a schema bump.
Fact collection does not validate arguments.
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from playwright.sync_api import CDPSession, Page
from playwright.sync_api import Error as PlaywrightError

from interface_compiler.browser.engine import _note_driver_dead, _playwright_driver_pid

_COLLECT_SOURCE = Path(__file__).with_name("collect.js").read_text(encoding="utf-8")
# Chromium reports these on text runs and on nodes it has dropped. They are not
# the host control's role, so the HTML role from collect.js stands.
_SKIP_AX_ROLES = frozenset({"none", "InlineTextBox", "StaticText", "ignored"})
# Chromium's internal names for controls whose ARIA role is the one below.
_AX_ROLE_ALIASES = {"Date": "textbox", "DisclosureTriangle": "button"}
# Widgets are overlaid before links. Headings and landmarks are not overlaid.
_WIDGET_TAGS = frozenset({"button", "input", "select", "textarea", "summary", "option"})
_WIDGET_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "gridcell",
        "listbox",
        "menu",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
        "treeitem",
    }
)
_ISOLATED_WORLD = "interface-compiler"
_NODE_GROUP = "interface-compiler-nodes"
_EVAL_TIMEOUT_MS = 5_000
_DEADLINE_S = 5.0
# Leave a second for the walk's tail and for returning facts. The cap is how
# long a fast page may spend on accessible names.
_OVERLAY_MARGIN_S = 1.0
_OVERLAY_BUDGET_CAP_S = 2.5
_READ_PAYLOAD = (
    "function(){return JSON.stringify({fields:this.fields,elements:this.elements,"
    "forms:this.forms,modals:this.modals,url:this.url,title:this.title,"
    "truncated:this.truncated,deadline:this.deadline});}"
)


class FactCollectionError(RuntimeError):
    """The page did not yield facts before the deadline."""


@dataclass(frozen=True, slots=True)
class Box:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class Constraints:
    required: bool
    pattern: str | None
    min: str | None
    max: str | None
    step: str | None
    minlength: int | None
    maxlength: int | None


@dataclass(frozen=True, slots=True)
class OptionFact:
    value: str
    label: str
    disabled: bool


@dataclass(frozen=True, slots=True)
class ElementFact:
    tag: str
    role: str
    name: str
    html_id: str | None
    field_name: str | None
    input_type: str | None
    href: str | None
    form_index: int | None
    form_method: str | None
    form_action: str | None
    disabled: bool
    readonly: bool
    aria_disabled: bool
    inert: bool
    hidden: bool
    aria_hidden: bool
    value: str | None
    checked: bool | None
    selected: bool | None
    options: tuple[OptionFact, ...]
    aria_expanded: str | None
    aria_selected: str | None
    aria_checked: str | None
    aria_pressed: str | None
    aria_current: str | None
    aria_valuemin: str | None
    aria_valuemax: str | None
    aria_valuenow: str | None
    aria_haspopup: str | None
    aria_controls: str | None
    box: Box
    visible: bool
    covered: bool
    in_viewport: bool
    validation_message: str
    landmark: str
    css: str
    skeleton_path: str
    label_text: str
    group_key: str | None
    constraints: Constraints
    name_source: Literal["ax", "html"]


@dataclass(frozen=True, slots=True)
class FormFact:
    index: int
    method: str
    action: str
    valid: bool
    html_id: str | None


@dataclass(frozen=True, slots=True)
class ModalFact:
    html_id: str | None
    role: str
    name: str
    open: bool


@dataclass(frozen=True, slots=True)
class PageFacts:
    url: str
    title: str
    elements: tuple[ElementFact, ...]
    forms: tuple[FormFact, ...]
    modals: tuple[ModalFact, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class _AxHit:
    role: str
    name: str | None


def normalized_page_url(page: Page) -> str:
    """Return the URL Playwright is actually on.

    That value is already normalized. Probe checks use it instead of the URL
    string from before navigation.
    """
    return page.url


def collect_facts(page: Page, *, deadline_s: float = _DEADLINE_S) -> PageFacts:
    """Collect element, form, and open-modal facts for the current document.

    The DOM walk in `collect.js` is the source of the element list. It runs in
    an isolated world, so a page that replaces ``querySelectorAll`` or
    ``Array.from`` cannot change the walk. Chromium's accessibility tree
    overlays role and name for on-screen widgets, then other widgets, then
    visible links, then the remaining links. Each element is joined by the
    object id returned from that world, not by an attribute the page can see.
    Shadow controls (a date input's spinbuttons, for example) are not separate
    facts. Headings keep the HTML name. The overlay budget is whatever remains
    of the deadline after the walk, minus one second, and at most 2.5s. When
    it runs out, the remaining controls keep the HTML name and ``name_source``
    is ``html``. A new document loader or a stale node raises instead of mixing
    two documents. The URL and title are the ones read at the start of the
    walk, so a later ``pushState`` cannot relabel those facts. When the walk
    runs out of time it returns the elements collected so far with
    ``truncated`` set. A walk that is given no time, on a page that has
    controls, raises instead of returning no elements. Collection also raises
    when the browser driver cannot be found, so the deadline is never skipped.

    A renderer that is already spinning does not honor a CDP timeout. The
    deadline stops that browser's driver so the blocked call returns. A slow
    overlay does not. It keeps the HTML role for whatever is left.
    """
    if deadline_s <= 0:
        raise ValueError("deadline must be positive")
    pid = _driver_pid(page)
    if not isinstance(pid, int):
        raise FactCollectionError("fact collection cannot find the browser driver")
    stop = threading.Event()
    killed = threading.Event()
    watcher = threading.Thread(
        target=_abort_browser_after,
        args=(pid, deadline_s, stop, killed),
        name="fact-deadline",
        daemon=True,
    )
    watcher.start()
    started = time.perf_counter()
    result: PageFacts | None = None
    try:
        result = _collect_within(page, deadline_s, started)
    except FactCollectionError:
        _note_if_killed(killed, pid)
        raise
    except TypeError as exc:
        raise FactCollectionError("fact collector returned a value of the wrong type") from exc
    except Exception as exc:
        if _is_collection_abort(exc):
            _note_if_killed(killed, pid)
            raise FactCollectionError("fact collection exceeded the deadline") from exc
        raise
    finally:
        stop.set()
        watcher.join()
        if killed.is_set():
            _note_if_killed(killed, pid)
    if killed.is_set() or result is None:
        raise FactCollectionError("fact collection exceeded the deadline")
    return result


def _abort_browser_after(
    pid: int | None,
    deadline_s: float,
    stop: threading.Event,
    killed: threading.Event,
) -> None:
    if pid is None or stop.wait(deadline_s):
        return
    # Set the flag before the signal. The blocked call returns as soon as the
    # driver dies, and the caller must already know this engine was killed.
    killed.set()
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        killed.clear()


def _note_if_killed(killed: threading.Event, pid: int | None) -> None:
    if killed.is_set() and isinstance(pid, int):
        _note_driver_dead(pid)


def _driver_pid(page: Page) -> int | None:
    """PID of the Playwright driver for this page's browser.

    Stopping Chromium alone leaves a CDP call blocked in the driver. The
    lookup stays on the calling thread. The deadline thread only signals
    this pid; it does not call Playwright.
    """
    return _playwright_driver_pid(page.context.browser)


def _overlay_budget(deadline_s: float, elapsed_s: float) -> float:
    remaining = deadline_s - elapsed_s - _OVERLAY_MARGIN_S
    if remaining <= 0:
        return 0.0
    return min(_OVERLAY_BUDGET_CAP_S, remaining)


def _collect_within(page: Page, deadline_s: float, started: float) -> PageFacts:
    session = page.context.new_cdp_session(page)
    try:
        context_id = _isolated_context(session)
        started_loader = _require_frame_stamp(session)[1]
        evaluated = session.send(
            "Runtime.evaluate",
            {
                "expression": _collect_source(deadline_s, started),
                "contextId": context_id,
                "returnByValue": False,
                "timeout": _EVAL_TIMEOUT_MS,
                "objectGroup": _NODE_GROUP,
            },
        )
        root_id = _object_id(evaluated)
        raw_payload = _evaluation_value(
            session.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": root_id,
                    "functionDeclaration": _READ_PAYLOAD,
                    "returnByValue": True,
                },
            )
        )
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else None
        if isinstance(payload, dict) and payload.get("deadline") is True:
            raise FactCollectionError("fact collection exceeded the deadline")
        object_ids = _node_object_ids(session, root_id)
        overlay = _accessibility_overlay(
            session,
            object_ids,
            _overlay_budget(deadline_s, time.perf_counter() - started),
            _overlay_order(payload, len(object_ids)),
        )
        # A closed page here is a lost document, not a deadline failure. The
        # URL and title already captured in the walk are the ones returned.
        _page_title(page)
        if _require_frame_stamp(session)[1] != started_loader:
            raise FactCollectionError("fact collection lost the document")
        if not isinstance(payload, dict):
            raise TypeError("fact collector must return an object")
        page_url, title, truncated = _walked_document(payload)
    except FactCollectionError:
        raise
    except Exception as exc:
        if _is_collection_abort(exc):
            raise FactCollectionError("fact collection exceeded the deadline") from exc
        raise
    finally:
        _release_nodes(session)
        try:
            session.detach()
        except PlaywrightError:
            pass
    return _page_facts(page_url, title, payload, overlay, truncated)


def _isolated_context(session: CDPSession) -> int:
    session.send("Page.enable")
    world = session.send(
        "Page.createIsolatedWorld",
        {"frameId": _frame_id(session.send("Page.getFrameTree")), "worldName": _ISOLATED_WORLD},
    )
    context_id = world.get("executionContextId") if isinstance(world, dict) else None
    if not isinstance(context_id, int):
        raise TypeError("isolated world has no execution context")
    return context_id


def _object_id(result: object) -> str:
    remote = _remote_object(result)
    object_id = remote.get("objectId")
    if isinstance(object_id, str) and object_id:
        return object_id
    raise TypeError("fact collector returned no object")


def _node_object_ids(session: CDPSession, root_id: str) -> list[str]:
    root_props = session.send("Runtime.getProperties", {"objectId": root_id, "ownProperties": True})
    nodes_id = _property_object_id(root_props, "nodes")
    if nodes_id is None:
        return []
    listed = session.send("Runtime.getProperties", {"objectId": nodes_id, "ownProperties": True})
    entries = listed.get("result") if isinstance(listed, dict) else None
    pairs: list[tuple[int, str]] = []
    if isinstance(entries, list):
        for prop in entries:
            if not isinstance(prop, dict):
                continue
            name = prop.get("name")
            value = prop.get("value")
            if not isinstance(name, str) or not name.isdigit() or not isinstance(value, dict):
                continue
            object_id = value.get("objectId")
            if isinstance(object_id, str):
                pairs.append((int(name), object_id))
    pairs.sort()
    return [object_id for _, object_id in pairs]


def _property_object_id(payload: object, name: str) -> str | None:
    entries = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return None
    for prop in entries:
        if not isinstance(prop, dict) or prop.get("name") != name:
            continue
        value = prop.get("value")
        object_id = value.get("objectId") if isinstance(value, dict) else None
        if isinstance(object_id, str):
            return object_id
    return None


def _release_nodes(session: CDPSession) -> None:
    try:
        session.send("Runtime.releaseObjectGroup", {"objectGroup": _NODE_GROUP})
    except PlaywrightError:
        pass


def _row_flag(row: object, fields: list[str], name: str) -> bool:
    if name not in fields or not isinstance(row, list):
        return False
    at = fields.index(name)
    return at < len(row) and row[at] is True


def _overlay_order(payload: object, count: int) -> list[int]:
    """On-screen widgets, then other widgets, then visible links, then other links."""
    if count <= 0:
        return []
    rows = payload.get("elements") if isinstance(payload, dict) else None
    fields = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not isinstance(fields, list):
        return []
    tag_at = fields.index("tag") if "tag" in fields else None
    role_at = fields.index("role") if "role" in fields else None
    if not isinstance(tag_at, int) or not isinstance(role_at, int):
        return []
    on_screen: list[int] = []
    widgets: list[int] = []
    visible_links: list[int] = []
    other_links: list[int] = []
    names = [name for name in fields if isinstance(name, str)]
    for index in range(min(count, len(rows))):
        row = rows[index]
        tag = row[tag_at] if isinstance(row, list) and tag_at < len(row) else None
        role = row[role_at] if isinstance(row, list) and role_at < len(row) else None
        if tag in _WIDGET_TAGS or role in _WIDGET_ROLES:
            if _row_flag(row, names, "visible") and _row_flag(row, names, "in_viewport"):
                on_screen.append(index)
            else:
                widgets.append(index)
            continue
        if tag == "a" or role == "link":
            if _row_flag(row, names, "visible"):
                visible_links.append(index)
            else:
                other_links.append(index)
    return on_screen + widgets + visible_links + other_links


def _accessibility_overlay(
    session: CDPSession,
    object_ids: list[str],
    budget_s: float,
    order: list[int],
) -> dict[str, _AxHit]:
    """Role and name for widgets, then links, until the budget runs out.

    One partial tree per element avoids building Chromium's full tree, which
    is the slow step on tables. Running out of budget keeps the HTML name.
    Losing the node or the document does not.
    """
    if budget_s <= 0 or not object_ids or not order:
        return {}
    session.send("Accessibility.enable")
    started = time.perf_counter()
    resolved: dict[str, _AxHit] = {}
    for index in order:
        if time.perf_counter() - started >= budget_s:
            break
        if index < 0 or index >= len(object_ids):
            continue
        try:
            tree = session.send(
                "Accessibility.getPartialAXTree",
                {"objectId": object_ids[index], "fetchRelatives": False},
            )
        except PlaywrightError as exc:
            if _is_document_lost(exc):
                raise FactCollectionError("fact collection lost the document") from exc
            raise
        hit = _hit_from_partial(tree)
        if hit is not None:
            resolved[str(index)] = hit
    return resolved


def _hit_from_partial(tree: object) -> _AxHit | None:
    nodes = tree.get("nodes") if isinstance(tree, dict) else None
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict) or node.get("ignored") is True:
            continue
        role = _ax_role(node)
        if role is None or role in _SKIP_AX_ROLES:
            continue
        return _AxHit(role=role, name=_ax_name(node))
    return None


def _main_frame(tree: object) -> dict[str, Any]:
    if not isinstance(tree, dict):
        raise TypeError("page has no frame")
    frame_tree = tree.get("frameTree")
    frame = frame_tree.get("frame") if isinstance(frame_tree, dict) else None
    if not isinstance(frame, dict):
        raise TypeError("page has no frame")
    return frame


def _frame_id(tree: object) -> str:
    frame_id = _main_frame(tree).get("id")
    if not isinstance(frame_id, str) or not frame_id:
        raise TypeError("page has no frame")
    return frame_id


def _frame_stamp(session: CDPSession) -> tuple[str, str]:
    """Main-frame URL and loader id for the document being collected."""
    frame = _main_frame(session.send("Page.getFrameTree"))
    url = frame.get("url")
    loader = frame.get("loaderId")
    if not isinstance(url, str) or not isinstance(loader, str) or not loader:
        raise FactCollectionError("fact collection lost the document")
    return url, loader


def _require_frame_stamp(session: CDPSession) -> tuple[str, str]:
    """The current document, or an error if the page navigated away."""
    try:
        return _frame_stamp(session)
    except PlaywrightError as exc:
        if _is_document_lost(exc):
            raise FactCollectionError("fact collection lost the document") from exc
        raise


def _collect_source(deadline_s: float, started: float) -> str:
    """The collector, with the walk's remaining time bound in milliseconds.

    The walk gets the whole remaining deadline, which is the time it had
    before a reserved overlay second could shrink that budget to zero.
    """
    remaining_ms = int((deadline_s - (time.perf_counter() - started)) * 1000)
    budget_ms = max(0, remaining_ms)
    # var, not const: the isolated world persists, and a second collect
    # redeclares this binding.
    return f"var WALK_BUDGET_MS = {budget_ms};\n{_COLLECT_SOURCE}"


def _walked_document(payload: dict[str, Any]) -> tuple[str, str, bool]:
    url = payload.get("url")
    title = payload.get("title")
    if not isinstance(url, str) or not isinstance(title, str):
        raise TypeError("fact collector must return the document url and title")
    return url, title, payload.get("truncated") is True


def _page_title(page: Page) -> str:
    """The document title, or a lost-document error if the page went away.

    A closed page used to match the deadline check (``has been closed``) and
    was reported as an exceeded deadline.
    """
    try:
        return page.title()
    except PlaywrightError as exc:
        if _is_document_lost(exc) or _is_closed_page(exc):
            raise FactCollectionError("fact collection lost the document") from exc
        raise FactCollectionError("fact collection could not read the document title") from exc


def _is_closed_page(exc: Exception) -> bool:
    text = str(exc).lower()
    return "has been closed" in text or "target closed" in text


def _is_document_lost(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        part in text
        for part in (
            "navigat",
            "stale",
            "no longer valid",
            "does not belong to the document",
            "detached",
            "destroyed",
            "cannot find context",
            "no node with given id",
            "could not find node",
        )
    )


def _remote_object(result: object) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TypeError("fact collector returned no result")
    details = result.get("exceptionDetails")
    if isinstance(details, dict):
        text = _cdp_exception_text(details)
        lowered = text.lower()
        if "terminated" in lowered or "timed out" in lowered:
            raise FactCollectionError("fact collection exceeded the deadline")
        raise FactCollectionError("fact collector failed")
    remote = result.get("result")
    if not isinstance(remote, dict):
        raise TypeError("fact collector returned no result")
    return remote


def _evaluation_value(result: object) -> Any:
    remote = _remote_object(result)
    if remote.get("type") == "undefined":
        return None
    if "value" not in remote:
        raise TypeError("fact collector returned no value")
    return remote.get("value")


def _cdp_exception_text(details: dict[str, Any]) -> str:
    exception = details.get("exception")
    if isinstance(exception, dict):
        description = exception.get("description")
        if isinstance(description, str) and description:
            return description.splitlines()[0]
    text = details.get("text")
    if isinstance(text, str):
        return text
    return ""


def _is_collection_abort(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "has been closed" in text
        or "connection closed" in text
        or "terminated" in text
        or "timed out" in text
        or "timeout" in text
    )


def _ax_role(node: dict[str, Any]) -> str | None:
    raw = node.get("role")
    if not isinstance(raw, dict):
        return None
    value = raw.get("value")
    if isinstance(value, str) and value:
        return _AX_ROLE_ALIASES.get(value, value)
    return None


def _ax_name(node: dict[str, Any]) -> str | None:
    if "name" not in node:
        return None
    raw = node["name"]
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        value = raw.get("value")
        return value if isinstance(value, str) else ""
    return ""


def _page_facts(
    url: str,
    title: str,
    payload: dict[str, Any],
    overlay: dict[str, _AxHit],
    truncated: bool = False,
) -> PageFacts:
    try:
        raw_elements = payload.get("elements")
        raw_forms = payload.get("forms")
        raw_modals = payload.get("modals")
        raw_fields = payload.get("fields")
        if not isinstance(raw_elements, list) or not isinstance(raw_forms, list):
            raise TypeError("fact collector must return elements and forms")
        if not isinstance(raw_modals, list):
            raise TypeError("fact collector must return modals")
        if not isinstance(raw_fields, list) or any(
            not isinstance(name, str) for name in raw_fields
        ):
            raise TypeError("fact collector must return field names")
        elements: list[ElementFact] = []
        field_names = [name for name in raw_fields if isinstance(name, str)]
        for index, item in enumerate(raw_elements):
            elements.append(_element(_element_row(item, field_names), overlay.get(str(index))))
        forms = tuple(_form(item) for item in raw_forms)
        modals = tuple(_modal(item) for item in raw_modals)
    except TypeError as exc:
        raise FactCollectionError("fact collector returned a value of the wrong type") from exc
    return PageFacts(
        url=url,
        title=title,
        elements=tuple(elements),
        forms=forms,
        modals=modals,
        truncated=truncated,
    )


def _element_row(item: object, fields: list[str]) -> dict[str, Any]:
    if not isinstance(item, list) or len(item) != len(fields):
        raise TypeError("element fact must be a row")
    return dict(zip(fields, item, strict=True))


def _element(item: dict[str, Any], hit: _AxHit | None) -> ElementFact:
    role = _req(item, "role", str)
    name = _req(item, "name", str)
    name_source: Literal["ax", "html"] = "html"
    if hit is not None:
        ax_role = hit.role or role
        # type=file is a button in Chromium's tree. Keep the HTML role so the
        # overlay and the post-budget fallback agree.
        if _opt(item, "input_type", str) == "file" and ax_role == "button":
            ax_role = role
        role = ax_role
        if hit.name is not None:
            name = hit.name
            name_source = "ax"
    constraints = item.get("constraints")
    box = item.get("box")
    options = item.get("options")
    if (
        not isinstance(constraints, dict)
        or not isinstance(box, dict)
        or not isinstance(options, list)
    ):
        raise TypeError("element fact is missing constraints, box, or options")
    return ElementFact(
        tag=_req(item, "tag", str),
        role=role,
        name=name,
        html_id=_opt(item, "html_id", str),
        field_name=_opt(item, "field_name", str),
        input_type=_opt(item, "input_type", str),
        href=_opt(item, "href", str),
        form_index=_opt(item, "form_index", int),
        form_method=_opt(item, "form_method", str),
        form_action=_opt(item, "form_action", str),
        disabled=_req(item, "disabled", bool),
        readonly=_req(item, "readonly", bool),
        aria_disabled=_req(item, "aria_disabled", bool),
        inert=_req(item, "inert", bool),
        hidden=_req(item, "hidden", bool),
        aria_hidden=_req(item, "aria_hidden", bool),
        value=_opt(item, "value", str),
        checked=_opt(item, "checked", bool),
        selected=_opt(item, "selected", bool),
        options=tuple(_option(option) for option in options),
        aria_expanded=_opt(item, "aria_expanded", str),
        aria_selected=_opt(item, "aria_selected", str),
        aria_checked=_opt(item, "aria_checked", str),
        aria_pressed=_opt(item, "aria_pressed", str),
        aria_current=_opt(item, "aria_current", str),
        aria_valuemin=_opt(item, "aria_valuemin", str),
        aria_valuemax=_opt(item, "aria_valuemax", str),
        aria_valuenow=_opt(item, "aria_valuenow", str),
        aria_haspopup=_opt(item, "aria_haspopup", str),
        aria_controls=_opt(item, "aria_controls", str),
        box=Box(
            x=_num(box, "x"),
            y=_num(box, "y"),
            width=_num(box, "width"),
            height=_num(box, "height"),
        ),
        visible=_req(item, "visible", bool),
        covered=_req(item, "covered", bool),
        in_viewport=_req(item, "in_viewport", bool),
        validation_message=_req(item, "validation_message", str),
        landmark=_req(item, "landmark", str),
        css=_req(item, "css", str),
        skeleton_path=_req(item, "skeleton_path", str),
        label_text=_req(item, "label_text", str),
        group_key=_opt(item, "group_key", str),
        constraints=Constraints(
            required=_req(constraints, "required", bool),
            pattern=_opt(constraints, "pattern", str),
            min=_opt(constraints, "min", str),
            max=_opt(constraints, "max", str),
            step=_opt(constraints, "step", str),
            minlength=_non_negative_int(constraints, "minlength"),
            maxlength=_non_negative_int(constraints, "maxlength"),
        ),
        name_source=name_source,
    )


def _option(item: object) -> OptionFact:
    if not isinstance(item, dict):
        raise TypeError("option fact must be an object")
    return OptionFact(
        value=_req(item, "value", str),
        label=_req(item, "label", str),
        disabled=_req(item, "disabled", bool),
    )


def _form(item: object) -> FormFact:
    if not isinstance(item, dict):
        raise TypeError("form fact must be an object")
    return FormFact(
        index=_req(item, "index", int),
        method=_req(item, "method", str),
        action=_req(item, "action", str),
        valid=_req(item, "valid", bool),
        html_id=_opt(item, "html_id", str),
    )


def _modal(item: object) -> ModalFact:
    if not isinstance(item, dict):
        raise TypeError("modal fact must be an object")
    return ModalFact(
        html_id=_opt(item, "html_id", str),
        role=_req(item, "role", str),
        name=_req(item, "name", str),
        open=_req(item, "open", bool),
    )


def _req[T](item: dict[str, Any], key: str, kind: type[T]) -> T:
    value = item[key]
    if isinstance(value, kind) and not (kind is int and isinstance(value, bool)):
        return value
    raise TypeError(f"{key} has the wrong type")


def _non_negative_int(item: dict[str, Any], key: str) -> int | None:
    """A bad optional length is absent, not a collector failure."""
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _opt[T](item: dict[str, Any], key: str, kind: type[T]) -> T | None:
    value = item[key]
    if value is None:
        return None
    if isinstance(value, kind) and not (kind is int and isinstance(value, bool)):
        return value
    raise TypeError(f"{key} has the wrong type")


def _num(item: dict[str, Any], key: str) -> float:
    value = item[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} has the wrong type")
    return float(value)
