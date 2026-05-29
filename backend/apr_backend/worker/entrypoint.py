import argparse
import json

from redis import Redis
from rq import Queue, Worker

from apr_backend.core.settings import get_settings


def create_redis_connection() -> Redis:
    settings = get_settings()
    return Redis.from_url(str(settings.redis_url))


def create_worker() -> Worker:
    settings = get_settings()
    connection = create_redis_connection()
    queue = Queue(settings.review_queue_name, connection=connection)
    return Worker([queue], connection=connection)


def readiness_payload() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ready",
        "queue": settings.review_queue_name,
        "redis_url": str(settings.redis_url),
    }


def main(check_only: bool = False) -> int:
    if check_only:
        print(json.dumps(readiness_payload(), sort_keys=True))
        return 0

    worker = create_worker()
    worker.work()
    return 0


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the APR review worker.")
    parser.add_argument("--check", action="store_true", help="Validate worker settings without connecting to Redis.")
    args = parser.parse_args()
    raise SystemExit(main(check_only=args.check))


if __name__ == "__main__":
    run()
