from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from scripts import check_db


def _required_columns_with_overrides(
    overrides: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    columns = {name: set(values) for name, values in check_db.REQUIRED_TABLE_COLUMNS.items()}
    for table_name, table_columns in (overrides or {}).items():
        columns[table_name] = set(table_columns)
    return columns


class _FakeConnection:
    def __init__(
        self,
        *,
        build_versions: list[str],
        table_columns: dict[str, set[str]],
        current_user: str = "dev_rob_bot",
        current_database: str = "rob_dev_v2",
        has_schema_create: bool = False,
        privilege_overrides: dict[tuple[str, str], bool] | None = None,
    ):
        self.build_versions = build_versions
        self.table_columns = table_columns
        self.current_user = current_user
        self.current_database = current_database
        self.has_schema_create = has_schema_create
        self.privilege_overrides = privilege_overrides or {}

    async def fetch(self, query: str, *params):
        normalized = query.strip()
        if normalized.startswith("SELECT version FROM db_build_version"):
            return [{"version": value} for value in self.build_versions]
        if "FROM information_schema.columns" in query and "table_name = $1" in query:
            table_name = str(params[0])
            return [
                {"column_name": column_name}
                for column_name in sorted(self.table_columns.get(table_name, set()))
            ]
        return []

    async def fetchval(self, query: str, *params):
        normalized = query.strip()
        if normalized == "SELECT current_user":
            return self.current_user
        if normalized == "SELECT current_database()":
            return self.current_database
        if "to_regclass" in query:
            relation = str(params[0])
            table_name = relation.removeprefix("public.")
            if table_name.endswith("_seq"):
                # Treat all declared sequences as present in tests.
                return True
            return table_name in self.table_columns
        if "has_database_privilege" in query:
            return True
        if "has_schema_privilege" in query:
            return self.has_schema_create
        if "has_table_privilege" in query:
            relation = str(params[0]) if params else "public.sends"
            privilege = (
                str(params[1])
                if len(params) > 1
                else ("DELETE" if "'DELETE'" in query else "")
            )
            if (relation, privilege) in self.privilege_overrides:
                return self.privilege_overrides[(relation, privilege)]
            return True
        if "has_sequence_privilege" in query:
            return True
        return None


class _FakeDatabase:
    def __init__(self, _database_url: str, *, connection: _FakeConnection):
        self.connection = connection

    async def connect(self):
        return None

    async def close(self):
        return None

    async def health_check(self) -> bool:
        return True

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def _patch_check_db(
    monkeypatch: pytest.MonkeyPatch,
    *,
    connection: _FakeConnection,
    build_dir,
):
    monkeypatch.setattr(check_db, "DB_BUILD_DIR", build_dir)
    monkeypatch.setattr(
        check_db,
        "load_base_settings",
        lambda: SimpleNamespace(log_level="INFO", database_url="postgresql://runtime/db"),
    )
    monkeypatch.setattr(check_db, "configure_logging", lambda _level: None)
    monkeypatch.setattr(
        check_db,
        "Database",
        lambda database_url: _FakeDatabase(database_url, connection=connection),
    )


def test_check_db_detects_missing_db_build_versions(monkeypatch: pytest.MonkeyPatch, tmp_path):
    (tmp_path / "001_core_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "002_indexes.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "003_runtime_grants_template.sql").write_text("SELECT 1;\n", encoding="utf-8")
    connection = _FakeConnection(
        build_versions=["001_core_schema"],
        table_columns=_required_columns_with_overrides(),
    )
    _patch_check_db(monkeypatch, connection=connection, build_dir=tmp_path)

    with pytest.raises(RuntimeError, match="Database is missing required DB build version"):
        asyncio.run(check_db.main())


def test_check_db_detects_missing_required_columns(monkeypatch: pytest.MonkeyPatch, tmp_path):
    (tmp_path / "001_core_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "002_indexes.sql").write_text("SELECT 1;\n", encoding="utf-8")
    columns = _required_columns_with_overrides(
        {
            "sends": {
                "id",
                "guild_id",
                "domme_user_id",
                "amount_cents",
                "currency",
                "source",
                "sent_at",
            }
        }
    )
    connection = _FakeConnection(
        build_versions=["001_core_schema", "002_indexes"],
        table_columns=columns,
    )
    _patch_check_db(monkeypatch, connection=connection, build_dir=tmp_path)

    with pytest.raises(RuntimeError, match="Table sends is missing required columns"):
        asyncio.run(check_db.main())


def test_check_db_detects_missing_required_build_script_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    (tmp_path / "001_core_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")
    connection = _FakeConnection(
        build_versions=["001_core_schema", "002_indexes"],
        table_columns=_required_columns_with_overrides(),
    )
    _patch_check_db(monkeypatch, connection=connection, build_dir=tmp_path)

    with pytest.raises(RuntimeError, match="Required DB build script file is missing"):
        asyncio.run(check_db.main())


def test_check_db_rejects_runtime_schema_create_privilege(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    (tmp_path / "001_core_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "002_indexes.sql").write_text("SELECT 1;\n", encoding="utf-8")
    connection = _FakeConnection(
        build_versions=["001_core_schema", "002_indexes"],
        table_columns=_required_columns_with_overrides(),
        has_schema_create=True,
    )
    _patch_check_db(monkeypatch, connection=connection, build_dir=tmp_path)

    with pytest.raises(RuntimeError, match="schema public"):
        asyncio.run(check_db.main())


def test_check_db_allows_grants_template_to_be_unapplied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    (tmp_path / "001_core_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "002_indexes.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "003_runtime_grants_template.sql").write_text("SELECT 1;\n", encoding="utf-8")
    connection = _FakeConnection(
        build_versions=["001_core_schema", "002_indexes"],
        table_columns=_required_columns_with_overrides(),
    )
    _patch_check_db(monkeypatch, connection=connection, build_dir=tmp_path)

    asyncio.run(check_db.main())


def test_repo_db_build_scripts_include_core_versions():
    expected = {path.stem for path in check_db.DB_BUILD_DIR.glob("*.sql")}
    assert "001_core_schema" in expected
    assert "002_indexes" in expected
    assert "003_runtime_grants_template" in expected
    assert set(check_db.REQUIRED_DB_BUILD_VERSIONS) == {"001_core_schema", "002_indexes"}
