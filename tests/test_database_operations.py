from pathlib import Path

from scripts.check_database import CheckResult, EXPECTED_TABLES, format_results


def test_database_health_formatter_marks_failures():
    output = format_results(
        [
            CheckResult("connection", True, "connected"),
            CheckResult("tables", False, "missing: documents"),
        ]
    )

    assert "[OK] connection: connected" in output
    assert "[FAIL] tables: missing: documents" in output


def test_expected_tables_cover_core_data_model():
    assert "documents" in EXPECTED_TABLES
    assert "document_chunks" in EXPECTED_TABLES
    assert "workflow_runs" in EXPECTED_TABLES
    assert "workflow_trace_steps" in EXPECTED_TABLES


def test_sql_helper_files_are_present_and_non_empty():
    sql_dir = Path("scripts/sql")
    sql_files = sorted(sql_dir.glob("*.sql"))

    assert len(sql_files) >= 7
    for sql_file in sql_files:
        assert sql_file.read_text(encoding="utf-8").strip()

