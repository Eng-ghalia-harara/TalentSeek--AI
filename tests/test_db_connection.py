from __future__ import annotations

from db import connection


def test_connection_uses_a_bounded_timeout(monkeypatch) -> None:
    expected = object()
    captured: dict[str, object] = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(connection.psycopg, "connect", fake_connect)
    monkeypatch.setattr(connection, "register_vector", lambda conn: None)
    for key, value in {
        "DB_HOST": "localhost",
        "DB_PORT": "5433",
        "DB_NAME": "test_database",
        "DB_USER": "test_user",
        "DB_PASS": "test_password",
    }.items():
        monkeypatch.setenv(key, value)

    result = connection.get_connection()

    assert result is expected
    assert captured["connect_timeout"] == connection.DB_CONNECT_TIMEOUT
