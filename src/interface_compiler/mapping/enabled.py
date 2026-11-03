"""Universal enabled rules. The first match wins."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact


def element_enabled(
    element: ElementFact,
    *,
    login_gated: bool = False,
    missing: tuple[str, ...] = (),
    no_options: bool = False,
    readonly: bool = False,
) -> tuple[bool, str | None]:
    """Return ``enabled`` and the stable reason phrase, if disabled."""
    if not element.visible or element.hidden or element.aria_hidden:
        return False, "not visible"
    if element.disabled:
        return False, "disabled"
    if element.aria_disabled:
        return False, "aria-disabled"
    if element.inert:
        return False, "inert"
    if element.covered and not element.in_dialog:
        return False, "covered"
    if login_gated:
        return False, "requires sign-in"
    if missing:
        return False, "missing: " + ", ".join(missing)
    if no_options:
        return False, "no options available"
    if readonly or element.readonly:
        return False, "read-only"
    return True, None
