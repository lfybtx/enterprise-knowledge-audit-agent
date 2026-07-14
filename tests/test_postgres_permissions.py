import os
from uuid import UUID, uuid4

import pytest

pytest.importorskip("sqlalchemy")

if not os.getenv("DATABASE_URL"):
    pytest.skip("Set DATABASE_URL to run PostgreSQL permission tests", allow_module_level=True)

from app.db import get_session_factory
from app.models import KnowledgeBase, KnowledgeDocument, User
from app.repositories.knowledge_repository import (
    create_knowledge_base,
    grant_document_view_permission,
    list_document_summaries,
    list_knowledge_base_members,
    remove_knowledge_base_member,
    upsert_knowledge_base_member,
    persist_document,
)


def test_owner_can_manage_members_and_editor_cannot():
    session = get_session_factory()()
    kb_id = None
    user_ids = []
    try:
        owner_id = f"permission-owner-{uuid4().hex[:8]}"
        member_id = f"permission-member-{uuid4().hex[:8]}"
        editor_id = f"permission-editor-{uuid4().hex[:8]}"
        user_ids = [owner_id, member_id, editor_id]
        from app.repositories.knowledge_repository import ensure_user

        for user_id in user_ids:
            ensure_user(session, user_id, user_id)
        session.commit()
        kb = create_knowledge_base(
            session,
            name=f"Permission test {uuid4()}",
            owner_external_id=owner_id,
            tenant_id="tenant-demo",
            department="sales",
            description="Permission test knowledge base",
        )
        kb_id = UUID(kb["id"])

        member = upsert_knowledge_base_member(
            session,
            knowledge_base_id=kb_id,
            actor_external_id=owner_id,
            member_external_id=member_id,
            role="viewer",
        )
        members = list_knowledge_base_members(session, kb_id, owner_id)

        assert member["role"] == "viewer"
        assert any(item["user_id"] == member_id for item in members)

        remove_knowledge_base_member(
            session,
            knowledge_base_id=kb_id,
            actor_external_id=owner_id,
            member_external_id=member_id,
        )
        assert all(item["user_id"] != member_id for item in list_knowledge_base_members(session, kb_id, owner_id))
        with pytest.raises(PermissionError):
            remove_knowledge_base_member(
                session,
                knowledge_base_id=kb_id,
                actor_external_id=owner_id,
                member_external_id=owner_id,
            )

        upsert_knowledge_base_member(
            session,
            knowledge_base_id=kb_id,
            actor_external_id=owner_id,
            member_external_id=editor_id,
            role="editor",
        )
        with pytest.raises(PermissionError):
            upsert_knowledge_base_member(
                session,
                knowledge_base_id=kb_id,
                actor_external_id=editor_id,
                member_external_id=member_id,
                role="viewer",
            )
    finally:
        if kb_id:
            kb_model = session.get(KnowledgeBase, kb_id)
            if kb_model is not None:
                session.delete(kb_model)
                session.commit()
        session.query(User).filter(User.external_id.in_(user_ids)).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_document_acl_restricts_visible_documents():
    session = get_session_factory()()
    kb_id = None
    document_id = None
    user_ids = []
    try:
        owner_id = f"acl-owner-{uuid4().hex[:8]}"
        viewer_id = f"acl-viewer-{uuid4().hex[:8]}"
        user_ids = [owner_id, viewer_id]
        from app.repositories.knowledge_repository import ensure_user

        for user_id in user_ids:
            ensure_user(session, user_id, user_id)
        session.commit()
        kb = create_knowledge_base(
            session,
            name=f"ACL test {uuid4()}",
            owner_external_id=owner_id,
            tenant_id="tenant-demo",
            department="sales",
            description="ACL test knowledge base",
        )
        kb_id = UUID(kb["id"])
        upsert_knowledge_base_member(
            session,
            knowledge_base_id=kb_id,
            actor_external_id=owner_id,
            member_external_id=viewer_id,
            role="viewer",
        )
        stored = persist_document(
            session,
            user_external_id=owner_id,
            knowledge_base_id=kb_id,
            title=f"Alice private document {uuid4()}",
            source="private.txt",
            file_type="txt",
            content="Only Alice can view this sensitive customer export evidence.",
            chunks=[
                {
                    "text": "Only Alice can view this sensitive customer export evidence.",
                    "location": {"kind": "document"},
                }
            ],
        )
        document_id = UUID(stored["id"])
        grant_document_view_permission(
            session,
            document_id=document_id,
            actor_external_id=owner_id,
            grantee_external_id=owner_id,
        )

        alice_docs = list_document_summaries(session, owner_id)
        bob_docs = list_document_summaries(session, viewer_id)

        assert any(item["id"] == str(document_id) for item in alice_docs)
        assert all(item["id"] != str(document_id) for item in bob_docs)
    finally:
        if document_id:
            document = session.get(KnowledgeDocument, document_id)
            if document is not None:
                session.delete(document)
                session.commit()
        if kb_id:
            kb_model = session.get(KnowledgeBase, kb_id)
            if kb_model is not None:
                session.delete(kb_model)
                session.commit()
        session.query(User).filter(User.external_id.in_(user_ids)).delete(synchronize_session=False)
        session.commit()
        session.close()
