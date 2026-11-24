"""
系统状态检查路由 — 检查各服务连接状态 + 运行时编辑 LLM/MySQL 配置
"""
import logging
import time
import httpx
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_db
from app.utils.redis_client import get_redis
from app.api.deps import get_current_admin
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/system", tags=["系统状态"])

# ---------- 运行时配置覆盖（仅影响检查 / 测试连接，不修改 .env） ----------
_config_overrides: dict = {}


def get_effective(key: str, fallback: str = "") -> str:
    """获取生效的配置值：优先使用运行时覆盖，回退到 .env"""
    val = _config_overrides.get(key)
    return val if val is not None else getattr(settings, key, fallback)


class ConfigPatch(BaseModel):
    """运行时配置更新项"""
    MYSQL_HOST: Optional[str] = None
    MYSQL_PORT: Optional[int] = None
    MYSQL_USER: Optional[str] = None
    MYSQL_PASSWORD: Optional[str] = None
    MYSQL_DATABASE: Optional[str] = None
    LLM_API_BASE: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: Optional[int] = None
    REDIS_PASSWORD: Optional[str] = None
    MILVUS_HOST: Optional[str] = None
    MILVUS_PORT: Optional[int] = None
    MILVUS_DATABASE: Optional[str] = None
    EMBEDDING_API_BASE: Optional[str] = None
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: Optional[str] = None


@router.get("/config")
async def get_system_config(
    admin: User = Depends(get_current_admin),
):
    """获取当前生效的系统配置（仅超级管理员可查看）"""
    return {
        "effective": {
            "MYSQL_HOST": get_effective("MYSQL_HOST"),
            "MYSQL_PORT": int(get_effective("MYSQL_PORT", "3306")),
            "MYSQL_USER": get_effective("MYSQL_USER"),
            "MYSQL_DATABASE": get_effective("MYSQL_DATABASE"),
            "LLM_API_BASE": get_effective("LLM_API_BASE"),
            "LLM_API_KEY": "****" + get_effective("LLM_API_KEY")[-4:] if get_effective("LLM_API_KEY") else "",
            "LLM_MODEL": get_effective("LLM_MODEL"),
            "REDIS_HOST": get_effective("REDIS_HOST"),
            "REDIS_PORT": int(get_effective("REDIS_PORT", "6379")),
            "MILVUS_HOST": get_effective("MILVUS_HOST"),
            "MILVUS_PORT": int(get_effective("MILVUS_PORT", "19530")),
            "MILVUS_DATABASE": get_effective("MILVUS_DATABASE"),
            "EMBEDDING_API_BASE": get_effective("EMBEDDING_API_BASE"),
            "EMBEDDING_MODEL": get_effective("EMBEDDING_MODEL"),
        },
        "overrides": dict(_config_overrides),
    }


@router.patch("/config")
async def update_system_config(
    patch: ConfigPatch,
    admin: User = Depends(get_current_admin),
):
    """更新运行时配置覆盖（仅超级管理员可操作）"""
    global _config_overrides
    updated = {}
    for k, v in patch.model_dump(exclude_unset=True).items():
        if v is None:
            # 显式传 null → 清除覆盖，回退到 .env
            _config_overrides.pop(k, None)
            updated[k] = None
        else:
            _config_overrides[k] = v
            updated[k] = v
    # 失效缓存，保证 get_settings() 新建实例但覆盖仍生效
    get_settings.cache_clear()
    # 重建全局 settings
    global settings
    settings = get_settings()
    return {"message": "配置已更新", "updated": updated, "overrides": dict(_config_overrides)}


# ---------- 各服务连接检查函数 ----------

async def check_mysql(db: AsyncSession) -> dict:
    """检查 MySQL 连接状态"""
    start = time.time()
    host = get_effective("MYSQL_HOST")
    port = int(get_effective("MYSQL_PORT", "3306"))
    user = get_effective("MYSQL_USER")
    password = _config_overrides.get("MYSQL_PASSWORD", settings.MYSQL_PASSWORD)
    database = get_effective("MYSQL_DATABASE")
    try:
        # 使用当前会话测试（如果连接参数与运行时一致）
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            elapsed = round((time.time() - start) * 1000, 1)
            return {
                "name": "MySQL", "status": "ok", "latency_ms": elapsed,
                "detail": "连接正常",
                "config": {"host": host, "port": port, "user": user, "database": database},
            }
        return {"name": "MySQL", "status": "error", "latency_ms": None, "detail": "查询返回异常"}
    except Exception as e:
        elapsed = round((time.time() - start) * 1000, 1) if (time.time() - start) < 10 else None
        return {
            "name": "MySQL", "status": "error", "latency_ms": elapsed,
            "detail": f"连接失败: {e}",
            "config": {"host": host, "port": port, "user": user, "database": database},
        }


async def check_redis() -> dict:
    """检查 Redis 连接状态"""
    start = time.time()
    host = get_effective("REDIS_HOST")
    port = int(get_effective("REDIS_PORT", "6379"))
    try:
        r = await get_redis()
        if r is None:
            return {
                "name": "Redis", "status": "error", "latency_ms": None,
                "detail": "Redis 不可用（可能未启动或连接拒绝）",
                "config": {"host": host, "port": port},
            }
        await r.ping()
        elapsed = round((time.time() - start) * 1000, 1)
        return {
            "name": "Redis", "status": "ok", "latency_ms": elapsed,
            "detail": "连接正常",
            "config": {"host": host, "port": port},
        }
    except Exception as e:
        elapsed = round((time.time() - start) * 1000, 1) if (time.time() - start) < 10 else None
        return {
            "name": "Redis", "status": "error", "latency_ms": elapsed,
            "detail": f"连接失败: {e}",
            "config": {"host": host, "port": port},
        }


async def check_milvus() -> dict:
    """检查 Milvus 连接状态"""
    start = time.time()
    host = get_effective("MILVUS_HOST")
    port = int(get_effective("MILVUS_PORT", "19530"))
    db_name = get_effective("MILVUS_DATABASE")
    try:
        from pymilvus import connections as milvus_con, db as milvus_db
        milvus_con.connect(alias="_status_check", host=host, port=port, timeout=5)
        dbs = milvus_db.list_database(using="_status_check")
        milvus_con.disconnect(alias="_status_check")
        elapsed = round((time.time() - start) * 1000, 1)
        db_exists = db_name in dbs
        return {
            "name": "Milvus",
            "status": "ok" if db_exists else "degraded",
            "latency_ms": elapsed,
            "detail": "连接正常" if db_exists else f"连接正常，但目标数据库 '{db_name}' 不存在",
            "extras": {"databases": dbs, "active_db": db_name},
            "config": {"host": host, "port": port, "database": db_name},
        }
    except ImportError:
        return {"name": "Milvus", "status": "warning", "latency_ms": None, "detail": "pymilvus 未安装"}
    except Exception as e:
        elapsed = round((time.time() - start) * 1000, 1) if (time.time() - start) < 10 else None
        return {
            "name": "Milvus", "status": "error", "latency_ms": elapsed,
            "detail": f"连接失败: {e}",
            "config": {"host": host, "port": port, "database": db_name},
        }


async def _check_openai_compatible_api(name: str, api_base: str, api_key: str, model: str) -> dict:
    """检查 OpenAI 兼容 API 连接状态"""
    start = time.time()
    if not api_key:
        return {"name": name, "status": "warning", "latency_ms": None, "detail": "API Key 未配置", "config": {"api_base": api_base, "model": model}}
    try:
        url = api_base.rstrip("/") + "/models"
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        elapsed = round((time.time() - start) * 1000, 1)
        if resp.status_code == 200:
            data = resp.json()
            models = [m["id"] for m in data.get("data", [])]
            model_available = model in models
            return {
                "name": name, "status": "ok", "latency_ms": elapsed, "detail": "API 连接正常",
                "extras": {"model": model, "model_available": model_available, "total_models": len(models)},
                "config": {"api_base": api_base, "model": model},
            }
        else:
            return {
                "name": name, "status": "error" if resp.status_code >= 500 else "warning",
                "latency_ms": elapsed, "detail": f"API 返回错误 ({resp.status_code})",
                "config": {"api_base": api_base, "model": model},
            }
    except httpx.TimeoutException:
        return {"name": name, "status": "error", "latency_ms": None, "detail": "连接超时（8秒）", "config": {"api_base": api_base, "model": model}}
    except Exception as e:
        elapsed = round((time.time() - start) * 1000, 1) if (time.time() - start) < 10 else None
        return {
            "name": name, "status": "error", "latency_ms": elapsed,
            "detail": f"连接异常: {type(e).__name__}",
            "config": {"api_base": api_base, "model": model},
        }


async def check_llm() -> dict:
    """检查 LLM API 连接状态"""
    api_base = get_effective("LLM_API_BASE")
    api_key = _config_overrides.get("LLM_API_KEY", settings.LLM_API_KEY)
    model = get_effective("LLM_MODEL")
    return await _check_openai_compatible_api("LLM 服务", api_base, api_key, model)


async def check_embedding() -> dict:
    """检查 Embedding API 连接状态"""
    api_base = get_effective("EMBEDDING_API_BASE")
    api_key = _config_overrides.get("EMBEDDING_API_KEY", settings.EMBEDDING_API_KEY)
    model = get_effective("EMBEDDING_MODEL")
    return await _check_openai_compatible_api("Embedding 服务", api_base, api_key, model)


@router.get("/status")
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取所有服务的连接状态（仅超级管理员可查看）"""
    import asyncio

    results = await asyncio.gather(
        check_mysql(db),
        check_redis(),
        check_milvus(),
        check_llm(),
        check_embedding(),
    )

    # 汇总整体状态
    status_map = {"ok": 0, "degraded": 1, "warning": 1, "error": 2}
    overall = "ok"
    for r in results:
        if status_map.get(r["status"], 2) > status_map.get(overall, 0):
            overall = r["status"]

    return {
        "overall": overall,
        "services": results,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
