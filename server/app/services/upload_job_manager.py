"""异步上传 Job 管理器 — 线程安全，Redis + 内存双引擎

与 document_progress.py (旧 3 步进度) 不同，本模块提供 5 步异步 Job 管理：
  upload → cleanup → parse → chunk → embed → done

Redis 可用时优先用 Redis（跨进程共享），Redis 不可用时回退到内存，
确保进度始终可用。
"""
import uuid
import logging
import time
from typing import Optional

from app.utils.redis_client import get_redis, RedisCache

logger = logging.getLogger(__name__)

JOB_TTL = 7200  # Job 数据存活 2 小时

# 标准步骤定义
JOB_STEPS = ["upload", "cleanup", "parse", "chunk", "embed"]

# 各步骤权重（用于计算总进度 %）
STEP_WEIGHTS = {
    "upload": 5,
    "cleanup": 5,
    "parse": 20,
    "chunk": 10,
    "embed": 60,
}

# 步骤中文标签
STEP_LABELS = {
    "upload": "文档上传",
    "cleanup": "清理旧版本",
    "parse": "解析与分块",
    "chunk": "父级分块入库",
    "embed": "向量化入库",
}

# ========== 内存回退存储 ==========
_in_memory_jobs: dict[str, dict] = {}


async def _get_cache() -> Optional[RedisCache]:
    r = await get_redis()
    if r is None:
        return None
    return RedisCache(r)


def _calc_percent(steps: dict) -> int:
    total = 0
    for step_key in JOB_STEPS:
        s = steps.get(step_key, {})
        status = s.get("status", "pending")
        if status == "done":
            total += STEP_WEIGHTS.get(step_key, 0)
        elif status == "running":
            total += int(STEP_WEIGHTS.get(step_key, 0) * s.get("percent", 0) / 100)
    return min(total, 100)


def _build_job(job_id: str, doc_id: int) -> dict:
    return {
        "job_id": job_id,
        "doc_id": doc_id,
        "status": "pending",
        "percent": 0,
        "steps": {
            name: {"label": STEP_LABELS.get(name, name), "percent": 0, "status": "pending", "message": "等待处理"}
            for name in JOB_STEPS
        },
        "error": None,
        "created_at": time.time(),
    }


async def _get_redis_job(key: str) -> Optional[dict]:
    cache = await _get_cache()
    if cache is None:
        return None
    return await cache.get_json(key)


async def _set_redis_job(key: str, data: dict):
    cache = await _get_cache()
    if cache is None:
        return
    await cache.set_json(key, data, ex=JOB_TTL)


async def create_job(doc_id: int) -> str:
    """创建一个新的处理 Job，返回 job_id"""
    job_id = uuid.uuid4().hex[:16]
    job = _build_job(job_id, doc_id)
    _in_memory_jobs[job_id] = job
    await _set_redis_job(f"upload_job:{job_id}", job)
    logger.info(f"创建上传 job | job_id={job_id} doc_id={doc_id}")
    return job_id


async def start_job(job_id: str):
    data = _in_memory_jobs.get(job_id)
    if data:
        data["status"] = "processing"
    rdata = await _get_redis_job(f"upload_job:{job_id}")
    if rdata:
        rdata["status"] = "processing"
        await _set_redis_job(f"upload_job:{job_id}", rdata)


async def update_job_step(job_id: str, step: str, percent: int, status: str = "running", message: str = ""):
    data = _in_memory_jobs.get(job_id)
    if data:
        _apply_step_update(data, step, percent, status, message)
    rdata = await _get_redis_job(f"upload_job:{job_id}")
    if rdata:
        _apply_step_update(rdata, step, percent, status, message)
        await _set_redis_job(f"upload_job:{job_id}", rdata)


def _apply_step_update(data: dict, step: str, percent: int, status: str, message: str):
    steps = data.get("steps", {})
    if step in steps:
        steps[step]["percent"] = percent
        steps[step]["status"] = status
        steps[step]["message"] = message
    data["percent"] = _calc_percent(steps)
    if status == "error":
        data["status"] = "error"
        data["error"] = message
    elif all(s.get("status") == "done" for s in steps.values()):
        data["status"] = "done"


async def set_job_error(job_id: str, error: str):
    data = _in_memory_jobs.get(job_id)
    if data:
        _apply_fail(data, error)
    rdata = await _get_redis_job(f"upload_job:{job_id}")
    if rdata:
        _apply_fail(rdata, error)
        await _set_redis_job(f"upload_job:{job_id}", rdata)


def _apply_fail(data: dict, error: str):
    data["status"] = "error"
    data["error"] = error
    for step in data.get("steps", {}).values():
        if step["status"] == "running":
            step["status"] = "error"
            step["message"] = error


async def set_job_done(job_id: str, message: str = "处理完成"):
    data = _in_memory_jobs.get(job_id)
    if data:
        _apply_done(data, message)
    rdata = await _get_redis_job(f"upload_job:{job_id}")
    if rdata:
        _apply_done(rdata, message)
        await _set_redis_job(f"upload_job:{job_id}", rdata)


def _apply_done(data: dict, message: str):
    data["status"] = "done"
    data["percent"] = 100
    for step in data.get("steps", {}).values():
        if step["status"] in ("running", "pending"):
            step["status"] = "done"
            step["percent"] = 100
            step["message"] = message


async def get_job(job_id: str) -> Optional[dict]:
    """获取 Job 当前状态（优先读 Redis，回退到内存）"""
    rdata = await _get_redis_job(f"upload_job:{job_id}")
    if rdata is not None:
        return rdata
    return _in_memory_jobs.get(job_id)


async def delete_job(job_id: str):
    _in_memory_jobs.pop(job_id, None)
    await _set_redis_job(f"upload_job:{job_id}", None)
