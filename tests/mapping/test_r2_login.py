from __future__ import annotations

import pytest

from tests.mapping._find import one


@pytest.mark.parametrize(
    ("affordance_id", "enabled", "reason"),
    [
        ("do_log_in_to_vote", False, "requires sign-in"),
        ("go_vote", False, "requires sign-in"),
        ("submit_login", False, "requires sign-in"),
        ("go_sign_in", True, None),
    ],
)
def test_r2_login_gate(map_page, affordance_id: str, enabled: bool, reason: str | None) -> None:
    result, _facts = map_page("login_gated.html")
    mapped = one(result, affordance_id)
    assert mapped.enabled is enabled
    assert (mapped.x.reason if mapped.x else None) == reason
