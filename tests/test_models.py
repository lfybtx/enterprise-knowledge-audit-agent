import pytest


sqlalchemy = pytest.importorskip("sqlalchemy")

from app.db import Base
from app.models import (
    DocumentChunk,
    KnowledgeBase,
    KnowledgeBaseMember,
    KnowledgeDocument,
    User,
    WorkflowRun,
    WorkflowTraceStep,
)


def test_database_models_define_core_tables():
    assert {
        "knowledge_bases",
        "documents",
        "document_chunks",
        "users",
        "knowledge_base_members",
        "workflow_runs",
        "workflow_trace_steps",
    } <= set(
        Base.metadata.tables
    )
    assert KnowledgeBase.__tablename__ == "knowledge_bases"
    assert KnowledgeDocument.__tablename__ == "documents"
    assert DocumentChunk.__tablename__ == "document_chunks"
    assert User.__tablename__ == "users"
    assert KnowledgeBaseMember.__tablename__ == "knowledge_base_members"
    assert WorkflowRun.__tablename__ == "workflow_runs"
    assert WorkflowTraceStep.__tablename__ == "workflow_trace_steps"


def test_document_chunk_has_unique_document_index_constraint():
    constraints = DocumentChunk.__table__.constraints
    assert any(
        getattr(constraint, "columns", None)
        and {column.name for column in constraint.columns} == {"document_id", "chunk_index"}
        for constraint in constraints
    )


def test_document_chunk_has_vector_embedding_column():
    assert "embedding" in DocumentChunk.__table__.columns
    assert DocumentChunk.__table__.columns["embedding"].type.get_col_spec() == "vector(512)"


def test_knowledge_base_membership_has_unique_user_constraint_and_role():
    constraints = KnowledgeBaseMember.__table__.constraints
    assert any(
        getattr(constraint, "columns", None)
        and {column.name for column in constraint.columns} == {"knowledge_base_id", "user_id"}
        for constraint in constraints
    )
    assert "role" in KnowledgeBaseMember.__table__.columns


def test_knowledge_base_membership_relationships_are_defined():
    assert KnowledgeBase.memberships.property.mapper.class_ is KnowledgeBaseMember
    assert User.memberships.property.mapper.class_ is KnowledgeBaseMember


def test_workflow_trace_models_have_expected_fields():
    assert "trace_id" in WorkflowRun.__table__.columns
    assert "workflow_run_id" in WorkflowTraceStep.__table__.columns
    assert "prompt" in WorkflowTraceStep.__table__.columns
    assert "tool_calls" in WorkflowTraceStep.__table__.columns
