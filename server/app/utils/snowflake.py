"""
雪花ID生成器 — 生成全局唯一、趋势递增的 64 位整数 ID
格式: 0 | 41-bit 时间戳 | 10-bit 机器ID | 12-bit 序列号

多进程部署：通过环境变量 SNOWFLAKE_WORKER_ID 或自动根据 PID 取模分配 worker_id，
避免多 worker 进程生成相同 ID 导致主键冲突。
"""
import time
import os
import logging

logger = logging.getLogger("snowflake")

# 纪元起始时间（2024-01-01 00:00:00 UTC）
EPOCH = 1704067200000

# 各段位数
TIMESTAMP_BITS = 41
WORKER_BITS = 10
SEQUENCE_BITS = 12

# 各段最大值
MAX_WORKER_ID = -1 ^ (-1 << WORKER_BITS)      # 1023
MAX_SEQUENCE = -1 ^ (-1 << SEQUENCE_BITS)      # 4095

# 偏移量
WORKER_SHIFT = SEQUENCE_BITS                   # 12
TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_BITS  # 22


def _resolve_worker_id() -> int:
    """解析 worker_id：优先环境变量，否则根据 PID 取模自动分配"""
    env_val = os.environ.get("SNOWFLAKE_WORKER_ID")
    if env_val is not None:
        try:
            wid = int(env_val)
            if 0 <= wid <= MAX_WORKER_ID:
                return wid
            logger.warning("SNOWFLAKE_WORKER_ID=%s 超出范围 0~%d，回退为 PID 取模", env_val, MAX_WORKER_ID)
        except ValueError:
            logger.warning("SNOWFLAKE_WORKER_ID=%s 不是合法整数，回退为 PID 取模", env_val)
    # 自动分配：PID 取模，避免同机多进程碰撞
    return os.getpid() % (MAX_WORKER_ID + 1)


class SnowflakeIDGenerator:
    """雪花ID生成器（单进程安全，多进程需不同 worker_id）"""

    def __init__(self, worker_id: int = 1):
        if not (0 <= worker_id <= MAX_WORKER_ID):
            raise ValueError(f"worker_id 必须在 0~{MAX_WORKER_ID} 之间")
        self._worker_id = worker_id
        self._last_ts = -1
        self._sequence = 0
        logger.info("SnowflakeIDGenerator 初始化 | worker_id=%d", worker_id)

    def _next_timestamp(self) -> int:
        """获取当前毫秒时间戳"""
        return int(time.time() * 1000)

    def _wait_next_ms(self, last_ts: int) -> int:
        """自旋等待下一毫秒"""
        ts = self._next_timestamp()
        while ts <= last_ts:
            ts = self._next_timestamp()
        return ts

    def next_id(self) -> int:
        """生成下一个唯一 ID（线程安全由 GIL 保障）"""
        ts = self._next_timestamp()

        # 同一毫秒内，递增序列号
        if ts == self._last_ts:
            self._sequence = (self._sequence + 1) & MAX_SEQUENCE
            # 序列号用完，等待下一毫秒
            if self._sequence == 0:
                ts = self._wait_next_ms(self._last_ts)
        else:
            # 不同毫秒，序列号重置
            self._sequence = 0

        self._last_ts = ts

        # 拼装 ID
        _id = ((ts - EPOCH) << TIMESTAMP_SHIFT) \
            | (self._worker_id << WORKER_SHIFT) \
            | self._sequence
        return _id


# 全局单例：多进程时每个 worker 进程通过 PID 取模自动获得不同 worker_id
default_generator = SnowflakeIDGenerator(worker_id=_resolve_worker_id())


def next_id() -> int:
    """快捷函数：生成下一个雪花ID"""
    return default_generator.next_id()
