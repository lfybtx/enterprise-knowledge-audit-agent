from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


EXPECTED_TABLES = (
    "users",
    "knowledge_bases",
    "knowledge_base_members",
    "documents",
    "document_chunks",
    "workflow_runs",
    "workflow_trace_steps",
    "alembic_version",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


def _count_table(connection, table_name: str) -> int:
    from sqlalchemy import text

    return int(connection.execute(text(f"select count(*) from {table_name}")).scalar_one())


def run_database_checks() -> list[CheckResult]:
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import SQLAlchemyError

    from app.db import get_engine

    results: list[CheckResult] = []
    engine = get_engine()

    try:
        with engine.connect() as connection:
            database_name = connection.execute(text("select current_database()")).scalar_one()
            results.append(CheckResult("connection", True, f"connected to {database_name}"))

            vector_installed = connection.execute(
                text("select exists(select 1 from pg_extension where extname = 'vector')")
            ).scalar_one()
            results.append(CheckResult("pgvector", bool(vector_installed), "extension vector installed"))

            inspector = inspect(connection)
            existing_tables = set(inspector.get_table_names())
            missing_tables = [table for table in EXPECTED_TABLES if table not in existing_tables]
            results.append(
                CheckResult(
                    "tables",
                    not missing_tables,
                    "all expected tables exist" if not missing_tables else f"missing: {', '.join(missing_tables)}",
                )
            )

            if "alembic_version" in existing_tables:
                version = connection.execute(text("select version_num from alembic_version")).scalar_one_or_none()
                results.append(CheckResult("alembic", bool(version), f"version: {version or 'empty'}"))

            for table_name in EXPECTED_TABLES:
                if table_name == "alembic_version" or table_name not in existing_tables:
                    continue
                results.append(CheckResult(f"count:{table_name}", True, str(_count_table(connection, table_name))))
    except SQLAlchemyError as exc:
        results.append(CheckResult("database", False, str(exc)))

    return results


def format_results(results: Iterable[CheckResult]) -> str:
    lines = ["Database health check"]
    for result in results:
        lines.append(f"[{_status(result.ok)}] {result.name}: {result.detail}")
    return "\n".join(lines)


def main() -> int:
    results = run_database_checks()
    print(format_results(results))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
