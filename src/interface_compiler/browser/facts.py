"""DOM and accessibility facts for one page.

``x.page``, ``state_from``, ``entities_from``, ``precheck``, ``registry``, and
``blocked`` are not read here. They stay open objects until a schema bump.
Fact collection does not validate arguments.
"""

from __future__ import annotations

import os
import signal
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import CDPSession, Page
from playwright.sync_api import Error as PlaywrightError

_COLLECT_SOURCE = Path(__file__).with_name("collect.js").read_text(encoding="utf-8")
_CLEAR_MARKERS = (
    "(() => { document.querySelectorAll('[data-ic-fact]').forEach((el) => "
    "el.removeAttribute('data-ic-fact')); })()"
)
# Chromium reports these on text runs and on nodes it has dropped. They are not
# the host control's role, so the HTML role from collect.js stands.
_SKIP_AX_ROLES = frozenset({"none", "InlineTextBox", "StaticText", "ignored"})
# Chromium's internal names for controls whose ARIA role is the one below.
_AX_ROLE_ALIASES = {"Date": "textbox", "DisclosureTriangle": "button"}
_ISOLATED_WORLD = "interface-compiler"
_EVAL_TIMEOUT_MS = 5_000
_DEADLINE_S = 5.0


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
    ``Array.from`` cannot change the walk. Chromium's accessibility tree only
    overlays role and name, and only for a host node that the walk marked.
    Shadow controls (a date input's spinbuttons, for example) are not separate
    facts. An open modal drops the rest of the page from that tree; those
    controls keep the HTML role.

    A renderer that is already spinning does not honor a CDP timeout. The
    deadline stops that browser's driver so the blocked call returns.
    """
    if deadline_s <= 0:
        raise ValueError("deadline must be positive")
    stop = threading.Event()
    watcher = threading.Thread(
        target=_abort_browser_after,
        args=(_driver_pid(page), deadline_s, stop),
        name="fact-deadline",
        daemon=True,
    )
    watcher.start()
    try:
        payload = _evaluate_isolated(page, _COLLECT_SOURCE)
        overlay: dict[str, _AxHit] = {}
        session: CDPSession | None = None
        try:
            session = page.context.new_cdp_session(page)
            overlay = _accessibility_overlay(session)
        finally:
            if session is not None:
                try:
                    session.detach()
                except PlaywrightError:
                    pass
            _evaluate_isolated(page, _CLEAR_MARKERS)
    except FactCollectionError:
        raise
    except Exception as exc:
        if _is_collection_abort(exc):
            raise FactCollectionError("fact collection exceeded the deadline") from exc
        raise
    finally:
        stop.set()
    if not isinstance(payload, dict):
        raise TypeError("fact collector must return an object")
    return _page_facts(normalized_page_url(page), page.title(), payload, overlay)


def _abort_browser_after(pid: int | None, deadline_s: float, stop: threading.Event) -> None:
    if pid is None or stop.wait(deadline_s):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _driver_pid(page: Page) -> int | None:
    """PID of the Playwright driver for this page's browser.

    Stopping Chromium alone leaves a CDP call blocked in the driver. The
    lookup stays on the calling thread. The deadline thread only signals
    this pid; it does not call Playwright.
    """
    browser = page.context.browser
    if browser is None:
        return None
    connection = getattr(getattr(browser, "_impl_obj", None), "_connection", None)
    transport = getattr(connection, "_transport", None)
    proc = getattr(transport, "_proc", None)
    pid = getattr(proc, "pid", None)
    return pid if isinstance(pid, int) else None


def _evaluate_isolated(page: Page, expression: str) -> Any:
    session = page.context.new_cdp_session(page)
    try:
        session.send("Page.enable")
        tree = session.send("Page.getFrameTree")
        frame_id = _frame_id(tree)
        world = session.send(
            "Page.createIsolatedWorld",
            {
                "frameId": frame_id,
                "worldName": _ISOLATED_WORLD,
                "grantUniveralAccess": True,
            },
        )
        context_id = world.get("executionContextId") if isinstance(world, dict) else None
        if not isinstance(context_id, int):
            raise TypeError("isolated world has no execution context")
        result = session.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "contextId": context_id,
                "returnByValue": True,
                "timeout": _EVAL_TIMEOUT_MS,
            },
        )
    except Exception as exc:
        if _is_collection_abort(exc):
            raise FactCollectionError("fact collection exceeded the deadline") from exc
        raise
    finally:
        try:
            session.detach()
        except PlaywrightError:
            pass
    return _evaluation_value(result)


def _frame_id(tree: object) -> str:
    if not isinstance(tree, dict):
        raise TypeError("page has no frame")
    frame_tree = tree.get("frameTree")
    frame = frame_tree.get("frame") if isinstance(frame_tree, dict) else None
    frame_id = frame.get("id") if isinstance(frame, dict) else None
    if not isinstance(frame_id, str) or not frame_id:
        raise TypeError("page has no frame")
    return frame_id


def _evaluation_value(result: object) -> Any:
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


def _accessibility_overlay(session: CDPSession) -> dict[str, _AxHit]:
    session.send("DOM.enable")
    session.send("Accessibility.enable")
    document = session.send("DOM.getDocument", {"depth": -1, "pierce": True})
    root = document.get("root") if isinstance(document, dict) else None
    markers = _markers(root)
    tree = session.send("Accessibility.getFullAXTree")
    nodes = tree.get("nodes") if isinstance(tree, dict) else None
    if not isinstance(nodes, list):
        raise TypeError("accessibility tree has no nodes")
    hits: dict[int, _AxHit] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        backend_id = node.get("backendDOMNodeId")
        if not isinstance(backend_id, int) or backend_id not in markers:
            continue
        role = _ax_role(node)
        if role is None or role in _SKIP_AX_ROLES:
            continue
        hits.setdefault(backend_id, _AxHit(role=role, name=_ax_name(node)))
    resolved: dict[str, _AxHit] = {}
    for backend_id, marker in markers.items():
        # The accessibility hit is applied only after describeNode and
        # resolveNode both return this backend id. That is the join from the
        # accessibility node to the element collect.js marked.
        if not _backend_joined(session, backend_id):
            continue
        hit = hits.get(backend_id)
        if hit is not None:
            resolved[marker] = hit
    return resolved


def _markers(root: object) -> dict[int, str]:
    found: dict[int, str] = {}
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        attributes = node.get("attributes")
        backend_id = node.get("backendNodeId")
        if isinstance(attributes, list) and isinstance(backend_id, int):
            pairs = [item for item in attributes if isinstance(item, str)]
            attr = dict(zip(pairs[0::2], pairs[1::2], strict=False))
            marker = attr.get("data-ic-fact")
            if isinstance(marker, str) and marker:
                found[backend_id] = marker
        for key in ("children", "shadowRoots"):
            children = node.get(key)
            if isinstance(children, list):
                stack.extend(children)
        content = node.get("contentDocument")
        if isinstance(content, dict):
            stack.append(content)
    return found


def _backend_joined(session: CDPSession, backend_id: int) -> bool:
    described = session.send("DOM.describeNode", {"backendNodeId": backend_id})
    node = described.get("node") if isinstance(described, dict) else None
    if not isinstance(node, dict) or not isinstance(node.get("nodeName"), str):
        return False
    resolved = session.send("DOM.resolveNode", {"backendNodeId": backend_id})
    obj = resolved.get("object") if isinstance(resolved, dict) else None
    object_id = obj.get("objectId") if isinstance(obj, dict) else None
    if not isinstance(object_id, str) or not object_id:
        return False
    session.send("Runtime.releaseObject", {"objectId": object_id})
    return True


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
            minlength=_opt(constraints, "minlength", int),
            maxlength=_opt(constraints, "maxlength", int),
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
