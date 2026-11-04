from src import database


class _FakeConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return []


def test_job_field_filter_is_applied_to_both_retrieval_paths(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(database, "get_connection", lambda: connection)

    database.retrieve_chunks(
        query_vector=[0.0],
        query_text="find an accountant",
        candidate_ids=[4, 9],
        job_field="Accounting & Finance",
    )

    assert connection.sql.count("d.metadata->'job_fields' ? %s") == 2
    assert connection.params.count("Accounting & Finance") == 4
    assert connection.params.count([4, 9]) == 2
    assert connection.sql.count("%s") == len(connection.params)


def test_all_field_search_keeps_documents_without_classification(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(database, "get_connection", lambda: connection)

    database.retrieve_chunks(query_vector=[0.0], query_text="engineer")

    assert "d.metadata->'job_fields' ? %s" in connection.sql
    assert connection.params.count(None) == 8
    assert connection.sql.count("%s") == len(connection.params)
