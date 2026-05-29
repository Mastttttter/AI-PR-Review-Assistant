from redis import Redis
from rq import Queue

from apr_backend.core.settings import get_settings
from apr_backend.worker.jobs import review_task_job


def create_review_queue(connection: Redis | None = None) -> Queue:
    settings = get_settings()
    redis_connection = connection or Redis.from_url(str(settings.redis_url))
    return Queue(settings.review_queue_name, connection=redis_connection)


def enqueue_review_job(task_id: str) -> str:
    job = create_review_queue().enqueue(review_task_job, task_id)
    return job.id
