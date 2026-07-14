from __future__ import annotations

from app.services.tasks import run_recorded_task


def run_task(task_id: str) -> None:
    from app.worker_handlers import HANDLERS
    run_recorded_task(task_id, lambda payload: HANDLERS[payload["handler"]](payload))

