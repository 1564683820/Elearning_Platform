"""
文档处理进度追踪模块 — 基于 Redis，实时记录各步骤进度
支持步骤：文本提取、文本分块、向量入库（按 chunk 上报）
"""
import logging
from typing import Optional

from app.utils.redis_client import get_redis, RedisCache

logger = logging.getLogger(__name__)

PROGRESS_TTL = 3600  # 进度数据存活 1 小时

# 步骤标识
STEP_EXTRACT = "extract"
STEP_CHUNK = "chunk"
STEP_EMBED = "embed"

STEP_LABELS = {
    STEP_EXTRACT: "文本提取",
    STEP_CHUNK: "文本分块",
    STEP_EMBED: "向量入库",
}

# 各步骤权重（用于计算总进度）
STEP_WEIGHTS = {STEP_EXTRACT: 20, STEP_CHUNK: 10, STEP_EMBED: 70}


async def _get_cache() -> Optional[RedisCache]:
    """获取 Redis cache 实例（Redis 不可用时返回 None）"""
    r = await get_redis()
    if r is None:
        return None
    return RedisCache(r)


async def init_progress(doc_id: int, total_chunks: int = 0):
    """初始化文档处理进度"""
    cache = await _get_cache()
    if cache is None:
        return
    progress = {
        "status": "processing",
        "percent": 0,
        "steps": {
            STEP_EXTRACT: {"label": STEP_LABELS[STEP_EXTRACT], "percent": 0, "status": "pending", "message": "等待处理"},
            STEP_CHUNK: {"label": STEP_LABELS[STEP_CHUNK], "percent": 0, "status": "pending", "message": "等待处理"},
            STEP_EMBED: {"label": STEP_LABELS[STEP_EMBED], "percent": 0, "status": "pending", "message": "等待处理", "current": 0, "total": total_chunks},
        },
    }
    await cache.set_json(f"doc_progress:{doc_id}", progress, ex=PROGRESS_TTL)


async def update_step(doc_id: int, step: str, percent: int, status: str, message: str):
    """更新某个步骤的进度"""
    cache = await _get_cache()
    if cache is None:
        return
    key = f"doc_progress:{doc_id}"
    data = await cache.get_json(key)
    if data is None:
        return
    if step in data.get("steps", {}):
        data["steps"][step]["percent"] = percent
        data["steps"][step]["status"] = status
        data["steps"][step]["message"] = message
    data["percent"] = _calc_overall(data["steps"])
    if status == "error":
        data["status"] = "error"
    await cache.set_json(key, data, ex=PROGRESS_TTL)


async def update_embed_progress(doc_id: int, current: int, total: int):
    """更新向量入库进度（基于已处理的 chunk 数）"""
    percent = int(current / total * 100) if total > 0 else 0
    status = "running" if current < total else "done"
    msg = f"正在入库 {current}/{total} 块" if current < total else f"入库完成 ({total} 块)"
    await update_step(doc_id, STEP_EMBED, percent, status, msg)

    # 同时更新 embed 步骤的 current/total 用于前端显示
    cache = await _get_cache()
    if cache is None:
        return
    key = f"doc_progress:{doc_id}"
    data = await cache.get_json(key)
    if data and STEP_EMBED in data.get("steps", {}):
        data["steps"][STEP_EMBED]["current"] = current
        data["steps"][STEP_EMBED]["total"] = total
        await cache.set_json(key, data, ex=PROGRESS_TTL)


def _calc_overall(steps: dict) -> int:
    """根据各步骤权重计算总进度百分比"""
    total = 0
    for step_key, weight in STEP_WEIGHTS.items():
        s = steps.get(step_key, {})
        if s.get("status") == "done":
            total += weight
        elif s.get("status") == "running":
            total += int(weight * s.get("percent", 0) / 100)
    return min(total, 100)


async def get_progress(doc_id: int) -> Optional[dict]:
    """获取文档处理进度"""
    cache = await _get_cache()
    if cache is None:
        return None
    return await cache.get_json(f"doc_progress:{doc_id}")


async def set_progress_done(doc_id: int, message: str = "处理完成"):
    """标记处理完成"""
    await _set_all_steps(doc_id, "done", message)


async def set_progress_error(doc_id: int, message: str):
    """标记处理失败"""
    await _set_all_steps(doc_id, "error", message)


async def _set_all_steps(doc_id: int, status: str, message: str):
    """统一更新所有步骤状态"""
    cache = await _get_cache()
    if cache is None:
        return
    key = f"doc_progress:{doc_id}"
    data = await cache.get_json(key)
    if data is None:
        return
    data["status"] = status
    data["percent"] = 100 if status == "done" else data.get("percent", 0)
    for step_key in data.get("steps", {}):
        step = data["steps"][step_key]
        if step["status"] in ("running", "pending"):
            step["status"] = status
            step["percent"] = 100 if status == "done" else step["percent"]
        step["message"] = message
    await cache.set_json(key, data, ex=PROGRESS_TTL)


async def clear_progress(doc_id: int):
    """清除进度数据"""
    cache = await _get_cache()
    if cache is None:
        return
    await cache.delete(f"doc_progress:{doc_id}")
