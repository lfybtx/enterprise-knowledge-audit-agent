from pathlib import Path


def test_base_requirements_do_not_include_database_dependencies():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")

    forbidden = ["SQLAlchemy", "alembic", "psycopg", "greenlet"]
    assert not any(package in requirements for package in forbidden)


def test_database_requirements_keep_database_dependencies_separate():
    requirements = (Path(__file__).resolve().parents[1] / "requirements-db.txt").read_text(encoding="utf-8")

    assert "SQLAlchemy" in requirements
    assert "alembic" in requirements
    assert "psycopg" in requirements
