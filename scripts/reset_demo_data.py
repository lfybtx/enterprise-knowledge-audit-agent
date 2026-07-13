from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.chunking import build_chunks  # noqa: E402
from app.services.object_storage import ObjectStorageError, store_upload  # noqa: E402
from app.services.parsers import parse_document_sections  # noqa: E402


DEFAULT_DEMO_USERS = ["local-demo", "demo-alice", "demo-bob"]
DEFAULT_DOCS_DIR = ROOT / "data" / "test_uploads"
TITLE_BY_FILENAME = {
    "access-control-policy.txt": "访问权限管理制度",
    "contract-sla-terms.txt": "企业客户服务等级与合同条款",
    "sensitive-data-handling.txt": "敏感信息处理规范",
    "legacy-export-guide.txt": "旧版销售数据导出指引",
    "current-export-policy.txt": "现行客户数据导出制度",
    "approval-matrix.txt": "业务审批矩阵",
    "public-faq.txt": "公开客服 FAQ",
    "incident-response-policy.txt": "安全事件响应流程",
}


@dataclass(frozen=True)
class DemoDocument:
    path: Path
    title: str


def discover_demo_documents(docs_dir: Path) -> list[DemoDocument]:
    documents = []
    for path in sorted(docs_dir.glob("*")):
        if not path.is_file():
            continue
        documents.append(DemoDocument(path=path, title=TITLE_BY_FILENAME.get(path.name, path.stem)))
    return documents


def matching_demo_document_filter(documents: list[DemoDocument]):
    from sqlalchemy import or_

    from app.models import KnowledgeDocument

    title_conditions = [KnowledgeDocument.title == document.title for document in documents]
    source_conditions = [KnowledgeDocument.source.ilike(f"%{document.path.name}") for document in documents]
    return or_(*(title_conditions + source_conditions))


def count_demo_documents(session: Any, documents: list[DemoDocument]) -> int:
    from sqlalchemy import func, select

    from app.models import KnowledgeDocument

    if not documents:
        return 0
    return int(session.scalar(select(func.count()).select_from(KnowledgeDocument).where(matching_demo_document_filter(documents))) or 0)


def count_all_documents_for_owner(session: Any, owner_external_id: str) -> int:
    from sqlalchemy import func, select

    from app.models import KnowledgeBase, KnowledgeDocument

    return int(
        session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id)
            .where(KnowledgeBase.owner_id == owner_external_id)
        )
        or 0
    )


def delete_demo_documents(session: Any, documents: list[DemoDocument]) -> int:
    from sqlalchemy import delete

    from app.models import KnowledgeDocument

    if not documents:
        return 0
    result = session.execute(delete(KnowledgeDocument).where(matching_demo_document_filter(documents)))
    return int(result.rowcount or 0)


def delete_all_documents_for_owner(session: Any, owner_external_id: str) -> int:
    from sqlalchemy import delete, select

    from app.models import KnowledgeBase, KnowledgeDocument

    knowledge_base_ids = select(KnowledgeBase.id).where(KnowledgeBase.owner_id == owner_external_id)
    result = session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id.in_(knowledge_base_ids)))
    return int(result.rowcount or 0)


def count_workflow_runs(session: Any, users: list[str]) -> int:
    from sqlalchemy import func, select

    from app.models import WorkflowRun

    return int(session.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.user_id.in_(users))) or 0)


def delete_workflow_runs(session: Any, users: list[str]) -> int:
    from sqlalchemy import delete

    from app.models import WorkflowRun

    result = session.execute(delete(WorkflowRun).where(WorkflowRun.user_id.in_(users)))
    return int(result.rowcount or 0)


def seed_demo_documents(session: Any, documents: list[DemoDocument], user_external_id: str, upload_dir: Path) -> list[dict[str, str]]:
    from app.repositories.knowledge_repository import persist_document

    imported = []
    for document in documents:
        raw_content = document.path.read_bytes()
        parsed = parse_document_sections(document.path.name, raw_content)
        object_id = str(uuid4())
        content_type = mimetypes.guess_type(document.path.name)[0] or "application/octet-stream"
        try:
            stored_object = store_upload(
                content=raw_content,
                filename=document.path.name,
                object_id=object_id,
                content_type=content_type,
                fallback_dir=upload_dir,
            )
            source = stored_object.source
            storage_backend = stored_object.backend
        except ObjectStorageError:
            source = f"demo://{document.path.name}"
            storage_backend = "database-only"

        stored = persist_document(
            session,
            user_external_id=user_external_id,
            title=document.title,
            source=source,
            file_type=parsed.file_type,
            content=parsed.text,
            chunks=build_chunks(
                object_id,
                [{"text": section.text, "location": section.location} for section in parsed.sections],
            ),
        )
        imported.append({"id": stored["id"], "title": document.title, "storage_backend": storage_backend})
    return imported


def run(args: argparse.Namespace) -> dict[str, Any]:
    from app.db import get_session_factory

    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required. Run this inside the Docker app container or export DATABASE_URL.")

    docs_dir = args.docs_dir.resolve()
    if not docs_dir.exists():
        raise RuntimeError(f"Demo docs directory does not exist: {docs_dir}")
    documents = discover_demo_documents(docs_dir)
    users = args.users or DEFAULT_DEMO_USERS
    upload_dir = args.upload_dir.resolve()
    session_factory = get_session_factory()
    session = session_factory()
    try:
        preview = {
            "mode": "apply" if args.apply else "dry-run",
            "documents_to_seed": len(documents) if args.seed_documents else 0,
            "matching_documents_to_delete": (
                count_all_documents_for_owner(session, args.seed_user)
                if args.clear_all_documents
                else count_demo_documents(session, documents)
                if args.clear_documents
                else 0
            ),
            "workflow_runs_to_delete": count_workflow_runs(session, users) if args.clear_audit else 0,
            "users": users,
            "docs_dir": str(docs_dir),
        }
        if not args.apply:
            return {**preview, "imported_documents": []}

        if args.clear_all_documents:
            deleted_documents = delete_all_documents_for_owner(session, args.seed_user)
        else:
            deleted_documents = delete_demo_documents(session, documents) if args.clear_documents else 0
        deleted_workflow_runs = delete_workflow_runs(session, users) if args.clear_audit else 0
        session.commit()
        imported_documents = seed_demo_documents(session, documents, args.seed_user, upload_dir) if args.seed_documents else []
        return {
            **preview,
            "deleted_documents": deleted_documents,
            "deleted_workflow_runs": deleted_workflow_runs,
            "imported_documents": imported_documents,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset and seed repeatable demo data for the audit-agent project.")
    parser.add_argument("--apply", action="store_true", help="Actually modify the database. Without this flag, only previews changes.")
    parser.add_argument("--clear-audit", action="store_true", help="Delete workflow/audit history for demo users.")
    parser.add_argument("--clear-documents", action="store_true", help="Delete previously seeded demo documents.")
    parser.add_argument(
        "--clear-all-documents",
        action="store_true",
        help="Delete all persisted uploaded documents owned by --seed-user before seeding.",
    )
    parser.add_argument("--seed-documents", action="store_true", help="Import files from data/test_uploads.")
    parser.add_argument("--all", action="store_true", help="Run clear-audit, clear-documents, and seed-documents.")
    parser.add_argument("--seed-user", default="local-demo", help="User that owns newly seeded documents.")
    parser.add_argument("--users", nargs="*", default=None, help="Users whose audit history should be cleared.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR, help="Directory containing demo upload files.")
    parser.add_argument("--upload-dir", type=Path, default=ROOT / "data" / "runtime" / "uploads")
    args = parser.parse_args()
    if args.all:
        args.clear_audit = True
        args.clear_all_documents = True
        args.seed_documents = True
    if not any([args.clear_audit, args.clear_documents, args.clear_all_documents, args.seed_documents]):
        args.clear_audit = True
        args.clear_all_documents = True
        args.seed_documents = True
    return args


def main() -> None:
    args = parse_args()
    result = run(args)
    print(f"Mode: {result['mode']}")
    print(f"Demo docs: {result['documents_to_seed']}")
    print(f"Matching seeded documents to delete: {result['matching_documents_to_delete']}")
    print(f"Workflow runs to delete: {result['workflow_runs_to_delete']}")
    if result["mode"] == "dry-run":
        print("No changes were made. Re-run with --apply to execute.")
        return
    print(f"Deleted documents: {result['deleted_documents']}")
    print(f"Deleted workflow runs: {result['deleted_workflow_runs']}")
    print("Imported documents:")
    for document in result["imported_documents"]:
        print(f"- {document['title']} ({document['storage_backend']}) {document['id']}")


if __name__ == "__main__":
    main()
