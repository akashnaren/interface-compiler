"""Universal enabled rules. The first match wins."""

from __future__ import annotations

from interface_compiler.browser.facts import ElementFact


def element_enabled(
    element: ElementFact,
    *,
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
    # Only a top-modal control that is itself the hit target is exempt, and
    # that control is already not covered. Every other hit stays covered.
    if element.covered:
        return False, "covered"
    if missing:
        return False, "missing: " + ", ".join(missing)
    if no_options:
        return False, "no options available"
    if readonly or element.readonly:
        return False, "read-only"
    return True, None


def usable(element: ElementFact) -> bool:
    """True when the universal rules would leave this item enabled."""
    enabled, _reason = element_enabled(element)
    return enabled


def group_enabled(elements: list[ElementFact]) -> tuple[bool, str | None]:
    """A group is enabled only when at least one item is usable."""
    if any(usable(element) for element in elements):
        return True, None
    if not elements:
        return False, "not visible"
    return element_enabled(elements[0])
