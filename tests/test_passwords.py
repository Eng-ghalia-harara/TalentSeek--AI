from __future__ import annotations

import pytest

from src.passwords import verify_role_password


@pytest.mark.parametrize(
    ("role", "password", "expected"),
    [
        ("admin", "admin-secret", True),
        ("recruiter", "recruiter-secret", True),
        ("admin", "recruiter-secret", False),
        ("recruiter", "admin-secret", False),
        ("admin", "", False),
        ("other", "admin-secret", False),
    ],
)
def test_role_passwords_are_independent(
    role: str, password: str, expected: bool
) -> None:
    assert verify_role_password(
        role,
        password,
        admin_password="admin-secret",
        recruiter_password="recruiter-secret",
    ) is expected
