"""Windows-compatible durable worker: python -m app.teaching_worker.

Redis Streams carry wakeups; SQL outbox, leases and checkpoints are authoritative.
Duplicate deliveries are safe. Killing a worker resumes at the last saved node.
"""
import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, and_
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from app.core.config import get_settings
from app.db.database import async_session
from app.models.teaching_task import TeachingTask, TeachingTaskOutbox
from app.services.teaching_task_service import TeachingTaskService
from app.services.teaching_agent import TeachingTools, MissingEvidence, build_graph

logger = logging.getLogger(__name__)
LEASE_SECONDS = 90


def utc_now():
    # MySQL DATETIME stores UTC without tzinfo throughout this workflow.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LostLease(Exception):
    pass


async def relay(redis, stream, sessions=async_session):
    async with sessions() as db:
        rows = (await db.execute(select(TeachingTaskOutbox).where(
            TeachingTaskOutbox.delivered_at.is_(None)).order_by(TeachingTaskOutbox.id).limit(50)
            .with_for_update(skip_locked=True))).scalars().all()
        for row in rows:
            await redis.xadd(stream, {'task_id': str(row.task_id)})
            row.delivered_at = utc_now()
        await db.commit()


async def claim(task_id, owner, sessions=async_session):
    async with sessions() as db:
        task = (await db.execute(select(TeachingTask).where(TeachingTask.id == task_id)
            .with_for_update())).scalar_one_or_none()
        now = utc_now()
        if not task or not (task.status == 'queued' or
            (task.status == 'running' and task.lease_until and task.lease_until < now)):
            return None
        task.status, task.lease_owner = 'running', owner
        task.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        await db.commit()
        return task


async def save_state(task_id, owner, state=None, status=None, error=None, sessions=async_session):
    async with sessions() as db:
        task = (await db.execute(select(TeachingTask).where(TeachingTask.id == task_id)
            .with_for_update())).scalar_one()
        if task.status != 'running' or task.lease_owner != owner:
            raise LostLease()
        if state is not None:
            task.checkpoint = state
        if status:
            task.status, task.error_code = status, error
            task.lease_owner, task.lease_until = None, None
            if status == 'awaiting_review':
                task.artifact = state['artifact']
                task.artifact_version += 1
                task.approved_version = None
        else:
            task.lease_until = utc_now() + timedelta(seconds=LEASE_SECONDS)
        await db.commit()


async def heartbeat(task_id, owner, sessions):
    while True:
        await asyncio.sleep(20)
        await save_state(task_id, owner, sessions=sessions)


async def execute(task_id, sessions=async_session, tools_factory=TeachingTools):
    owner = uuid.uuid4().hex
    task = await claim(task_id, owner, sessions)
    if task is None:
        return
    pulse = asyncio.create_task(heartbeat(task_id, owner, sessions))
    try:
        async with sessions() as db:
            tools = tools_factory(db, task)

            async def save(state):
                # Recheck permissions at every durable boundary, even after an LLM call.
                await db.rollback()
                await tools.authorize()
                await save_state(task_id, owner, state, sessions=sessions)

            state = await build_graph(tools, save).ainvoke(task.checkpoint or {
                'config': {'question_count': 10, 'duration_minutes': 20}})
            await db.rollback()
            await tools.authorize()
            await save_state(task_id, owner, state, state['status'],
                'artifact_validation' if state['status'] == 'awaiting_input' else None, sessions)
    except LostLease:
        pass  # Cancellation or another lease owner fences all stale writes.
    except MissingEvidence as exc:
        with contextlib.suppress(LostLease):
            await save_state(task_id, owner, status='awaiting_input', error=str(exc), sessions=sessions)
    except (PermissionError, HTTPException):
        with contextlib.suppress(LostLease):
            await save_state(task_id, owner, status='failed', error='access_revoked', sessions=sessions)
    except (httpx.TransportError, httpx.HTTPStatusError, TimeoutError):
        async with sessions() as db:
            current = (await db.execute(select(TeachingTask).where(TeachingTask.id == task_id)
                .with_for_update())).scalar_one()
            if current.status == 'running' and current.lease_owner == owner:
                current.attempts += 1
                current.status = 'queued' if current.attempts <= 2 else 'failed'
                current.error_code = 'transient_dependency_error'
                current.lease_owner, current.lease_until = None, None
                if current.status == 'queued':
                    db.add(TeachingTaskOutbox(task_id=task_id))
                await db.commit()
    except Exception as exc:
        # Persist a sanitized error code; exception messages may contain provider credentials.
        logger.error('Teaching task %s failed (%s)', task_id, type(exc).__name__)
        with contextlib.suppress(LostLease):
            await save_state(task_id, owner, status='failed', error=type(exc).__name__, sessions=sessions)
    finally:
        pulse.cancel()
        with contextlib.suppress(asyncio.CancelledError, LostLease, SQLAlchemyError):
            await pulse


async def main():
    settings = get_settings()
    stream, group = settings.REDIS_PREFIX + 'teaching-tasks', 'teaching-workers'
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=3)
    consumer = uuid.uuid4().hex
    try:
        while True:
            try:
                try:
                    await redis.xgroup_create(stream, group, id='0', mkstream=True)
                except RedisError as exc:
                    if 'BUSYGROUP' not in str(exc):
                        raise
                await relay(redis, stream)
                # Reclaim orphaned stream messages as well as expired SQL leases.
                reclaimed = await redis.xautoclaim(stream, group, consumer, min_idle_time=120000, count=10)
                messages = reclaimed[1]
                if not messages:
                    batches = await redis.xreadgroup(group, consumer, {stream: '>'}, count=1, block=2000)
                    messages = batches[0][1] if batches else []
                for message_id, payload in messages:
                    await execute(int(payload['task_id']))
                    await redis.xack(stream, group, message_id)
                async with async_session() as db:
                    expired = (await db.execute(select(TeachingTask.id).where(and_(
                        TeachingTask.status == 'running', TeachingTask.lease_until < utc_now())).limit(10))).scalars().all()
                for task_id in expired:
                    await execute(task_id)
            except RedisError:
                logger.warning('Redis unavailable; dispatch intent retained in SQL outbox')
                await asyncio.sleep(3)
            except SQLAlchemyError:
                logger.error('SQL unavailable; worker will reconnect, expired leases remain recoverable')
                await asyncio.sleep(3)
    finally:
        await redis.aclose()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
