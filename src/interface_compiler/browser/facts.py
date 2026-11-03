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
from typing import Any

from playwright.sync_api import CDPSession, Page
from playwright.sync_api import Error as PlaywrightError

from interface_compiler.browser.engine import _note_driver_dead, _playwright_driver_pid

_COLLECT_SOURCE = Path(__file__).with_name("collect.js").read_text(encoding="utf-8")
# Chromium reports these on text runs and on nodes it has dropped. They are not
# the host control's role, so the HTML role from collect.js stands.
_SKIP_AX_ROLES = frozenset({"none", "InlineTextBox", "StaticText", "ignored"})
# Chromium's internal names for controls whose ARIA role is the one below.
_AX_ROLE_ALIASES = {"Date": "textbox", "DisclosureTriangle": "button"}
_ISOLATED_WORLD = "interface-compiler"
_NODE_GROUP = "interface-compiler-nodes"
_EVAL_TIMEOUT_MS = 5_000
_DEADLINE_S = 5.0
# Stop overlaying once this much of the deadline is gone and keep HTML roles.
_OVERLAY_BUDGET_FRACTION = 0.25
_OVERLAY_BUDGET_CAP_S = 0.75
_READ_PAYLOAD = "function(){return JSON.stringify({elements:this.elements,forms:this.forms,modals:this.modals});}"


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
    overlays role and name. Each element is joined by the object id returned
    from that world, not by an attribute the page can see. Shadow controls (a
    date input's spinbuttons, for example) are not separate facts. When the
    overlay budget runs out, the remaining controls keep the HTML role.

    A renderer that is already spinning does not honor a CDP timeout. The
    deadline stops that browser's driver so the blocked call returns. A slow
    overlay does not. It keeps the HTML role for whatever is left.
    """
    if deadline_s <= 0:
        raise ValueError("deadline must be positive")
    pid = _driver_pid(page)
    stop = threading.Event()
    killed = threading.Event()
    watcher = threading.Thread(
        target=_abort_browser_after,
        args=(pid, deadline_s, stop, killed),
        name="fact-deadline",
        daemon=True,
    )
    watcher.start()
    result: PageFacts | None = None
    try:
        result = _collect_within(page, deadline_s)
    except FactCollectionError:
        _note_if_killed(killed, pid)
        raise
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


def _overlay_budget(deadline_s: float) -> float:
    return min(_OVERLAY_BUDGET_CAP_S, deadline_s * _OVERLAY_BUDGET_FRACTION)


def _collect_within(page: Page, deadline_s: float) -> PageFacts:
    session = page.context.new_cdp_session(page)
    try:
        context_id = _isolated_context(session)
        evaluated = session.send(
            "Runtime.evaluate",
            {
                "expression": _COLLECT_SOURCE,
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
        object_ids = _node_object_ids(session, root_id)
        overlay = _accessibility_overlay(session, object_ids, _overlay_budget(deadline_s))
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
    if not isinstance(payload, dict):
        raise TypeError("fact collector must return an object")
    return _page_facts(normalized_page_url(page), page.title(), payload, overlay)


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


def _accessibility_overlay(
    session: CDPSession,
    object_ids: list[str],
    budget_s: float,
) -> dict[str, _AxHit]:
    """Role and name for as many elements as the budget allows.

    The rest keep the HTML role from the walk. One partial tree per element
    avoids building Chromium's full tree, which is the slow step on tables.
    """
    if budget_s <= 0 or not object_ids:
        return {}
    session.send("Accessibility.enable")
    started = time.perf_counter()
    resolved: dict[str, _AxHit] = {}
    for index, object_id in enumerate(object_ids):
        if time.perf_counter() - started >= budget_s:
            break
        try:
            tree = session.send(
                "Accessibility.getPartialAXTree",
                {"objectId": object_id, "fetchRelatives": False},
            )
        except PlaywrightError:
            break
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


def _frame_id(tree: object) -> str:
    if not isinstance(tree, dict):
        raise TypeError("page has no frame")
    frame_tree = tree.get("frameTree")
    frame = frame_tree.get("frame") if isinstance(frame_tree, dict) else None
    frame_id = frame.get("id") if isinstance(frame, dict) else None
    if not isinstance(frame_id, str) or not frame_id:
        raise TypeError("page has no frame")
    return frame_id


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
) -> PageFacts:
    raw_elements = payload.get("elements")
    raw_forms = payload.get("forms")
    raw_modals = payload.get("modals")
    if not isinstance(raw_elements, list) or not isinstance(raw_forms, list):
        raise TypeError("fact collector must return elements and forms")
    if not isinstance(raw_modals, list):
        raise TypeError("fact collector must return modals")
    elements: list[ElementFact] = []
    for item in raw_elements:
        if not isinstance(item, dict):
            raise TypeError("element fact must be an object")
        elements.append(_element(item, overlay.get(_req(item, "marker", str))))
    forms = tuple(_form(item) for item in raw_forms)
    modals = tuple(_modal(item) for item in raw_modals)
    return PageFacts(url=url, title=title, elements=tuple(elements), forms=forms, modals=modals)


def _element(item: dict[str, Any], hit: _AxHit | None) -> ElementFact:
    role = _req(item, "role", str)
    name = _req(item, "name", str)
    if hit is not None:
        role = hit.role or role
        if hit.name is not None:
            name = hit.name
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
