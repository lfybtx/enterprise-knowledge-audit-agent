from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.db import get_session_factory
from app.models import IndexTask


def enqueue_task(*, task_type: str, requested_by: str, payload: dict[str, Any], document_id: UUID | None = None) -> dict[str, Any]:
    """Persist task state before handing work to RQ; database remains the source of truth."""
    from redis import Redis
    from rq import Queue, Retry

    # 先提交任务记录再投递队列，使 API 返回的 task_id 始终可以从数据库查询和追踪。
    session = get_session_factory()()
    task = IndexTask(id=uuid4(), document_id=document_id, task_type=task_type, requested_by=requested_by, status="queued", payload=payload)
    session.add(task)
    session.commit()
    task_id = str(task.id)
    session.close()
    queue = Queue(os.getenv("RQ_QUEUE", "default"), connection=Redis.from_url(os.environ["REDIS_URL"]))
    queue.enqueue("app.worker.run_task", task_id, retry=Retry(max=3, interval=[10, 30, 60]), job_id=task_id)
    return task_record(task_id)


def task_record(task_id: str) -> dict[str, Any]:
    session = get_session_factory()()
    try:
        task = session.get(IndexTask, UUID(task_id))
        if task is None:
            raise KeyError(task_id)
        return {"id": str(task.id), "task_type": task.task_type, "status": task.status, "requested_by": task.requested_by,
                "document_id": str(task.document_id) if task.document_id else None, "processed_count": task.processed_count,
                "error": task.error, "retry_count": task.retry_count, "created_at": task.created_at.isoformat() if task.created_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None, "duration_ms": task.duration_ms, "result": task.result}
    finally:
        session.close()


def run_recorded_task(task_id: str, handler) -> None:
    started = time.perf_counter()
    session = get_session_factory()()
    task = session.get(IndexTask, UUID(task_id))
    if task is None:
        session.close()
        raise KeyError(task_id)
    task.status = "running"
    task.retry_count += 1
    session.commit()
    try:
        result = handler(task.payload or {})
        task.result = result if isinstance(result, dict) else None
        task.status = "succeeded"
        task.processed_count = int(result.get("processed_count", 0)) if isinstance(result, dict) else 0
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc)
        raise
    finally:
        # 成功和失败都在 finally 中落盘结束时间，保证异常任务也有完整的可观测状态。
        task.finished_at = datetime.now(timezone.utc)
        task.duration_ms = round((time.perf_counter() - started) * 1000)
        session.commit()
        session.close()
