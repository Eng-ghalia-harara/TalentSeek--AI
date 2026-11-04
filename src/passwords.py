from __future__ import annotations

import hmac


def verify_role_password(
    role: str,
    password: str,
    admin_password: str,
    recruiter_password: str,
) -> bool:
    if not isinstance(password, str):
        return False
    if role == "admin":
        expected_password = admin_password
    elif role == "recruiter":
        expected_password = recruiter_password
    else:
        return False
    return bool(expected_password) and hmac.compare_digest(password, expected_password)
