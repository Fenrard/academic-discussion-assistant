"""
Fan-out channel between the worker tier (publishes a chunk's result
once it finishes) and the API tier (a WS connection listening for its
session's results to forward to the client). Two backends behind the
same interface:

  - Real Redis pub/sub when CELERY_BROKER_URL/REDIS_URL is configured —
    the actual cross-process, cross-machine mechanism a scaled
    deployment needs, since the worker that finishes a chunk is not
    necessarily the same process (or even machine) holding the client's
    WebSocket connection.
  - An in-process asyncio.Queue fan-out when it isn't — this sandbox's
    default. Safe specifically because CELERY_TASK_ALWAYS_EAGER means
    the "worker" runs inline in the same thread/event loop as the API
    when there's no broker, so a plain in-memory queue is a faithful
    stand-in for that one scenario, not a shortcut that changes behavior.

subscribe() returns a handle with an async get(timeout) -> dict | None
method — deliberately NOT an async generator wrapped in
asyncio.wait_for(): canceling a suspended `await` *inside* an async
generator on a wait_for timeout propagates CancelledError through it,
which closes the generator for good — the next call would raise
StopAsyncIteration instead of resuming. asyncio.Queue.get() and redis's
own pubsub.get_message(timeout=...) are both natively safe to retry
after a timeout, so the polling loop in api/transcribe.py builds on
those directly instead.
"""

import asyncio
import json
from contextlib import asynccontextmanager

from backend.core.config import settings

_USE_REDIS = settings.celery_broker_url is not None

_in_process_channels: dict[str, list[asyncio.Queue]] = {}


def publish_sync(channel: str, message: dict) -> None:
    if _USE_REDIS:
        import redis

        client = redis.Redis.from_url(settings.redis_url)
        try:
            client.publish(channel, json.dumps(message))
        finally:
            client.close()
    else:
        for queue in _in_process_channels.get(channel, []):
            queue.put_nowait(message)


class _RedisSubscription:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    async def get(self, timeout: float) -> dict | None:
        raw = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if raw is None:
            return None
        return json.loads(raw["data"])


class _InProcessSubscription:
    def __init__(self, queue: asyncio.Queue):
        self._queue = queue

    async def get(self, timeout: float) -> dict | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


@asynccontextmanager
async def subscribe(channel: str):
    """Yields an object with `await handle.get(timeout) -> dict | None` for the life of the context."""
    if _USE_REDIS:
        import redis.asyncio as aioredis

        client = aioredis.Redis.from_url(settings.redis_url)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield _RedisSubscription(pubsub)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await client.aclose()
    else:
        queue: asyncio.Queue = asyncio.Queue()
        _in_process_channels.setdefault(channel, []).append(queue)
        try:
            yield _InProcessSubscription(queue)
        finally:
            _in_process_channels[channel].remove(queue)
            if not _in_process_channels[channel]:
                del _in_process_channels[channel]
