import logging

from apr_backend.services.orchestrator import run_review_orchestrator

logger = logging.getLogger(__name__)


def review_task_job(task_id: str) -> str:
    logger.info("Worker picked up review job for task %s", task_id)
    run_review_orchestrator(task_id)
    return task_id
