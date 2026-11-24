#!/usr/bin/env python3
"""
数据库索引优化脚本
直接执行，无需 MySQL 命令行客户端。

用法：
    cd server
    python scripts/add_indexes.py

分析：为 dict_word / stage_word / question_bank 添加关键索引，
覆盖质量门槛过滤、JOIN 关联、阶段筛选、排序等核心查询模式。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def timer_start():
    return time.time()


def timer_end(t0, label: str):
    elapsed = time.time() - t0
    log(f"  {label} ({elapsed:.1f}s)")


# ── 要添加的索引列表 ──────────────────────────────────
# 每项：(库名, 表名, 索引名, 列/表达式, 是否唯一)
INDEXES = [
    # ── dict_word (单词库) ──
    ("elearnword", "dict_word", "idx_bnc", "bnc", False),
    ("elearnword", "dict_word", "idx_oxford", "oxford", False),
    ("elearnword", "dict_word", "idx_frq", "frq", False),
    ("elearnword", "dict_word", "idx_translation_prefix", "translation(10)", False),

    # ── stage_word (阶段映射) ──
    ("elearnword", "stage_word", "idx_sw_word_id", "word_id", False),
    ("elearnword", "stage_word", "idx_sw_stage", "stage", False),
    ("elearnword", "stage_word", "idx_sw_stage_mastery", "stage, mastery_order", False),

    # ── question_bank (题库) ──
    ("elearningtest", "question_bank", "idx_qb_word_id", "word_id", False),
    ("elearningtest", "question_bank", "idx_qb_stage_type", "stage, type", False),
    ("elearningtest", "question_bank", "idx_qb_word_stage_type", "word_id, stage, type", False),
]


def main():
    settings = get_settings()

    # 需要连接两个库（单词库 + 主库）
    words_engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)
    main_engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)

    engine_map = {
        "elearnword": words_engine,
        "elearningtest": main_engine,
    }

    log("=" * 60)
    log("开始添加数据库索引...")
    log(f"单词库: {settings.SYNC_WORDS_DATABASE_URL}")
    log(f"主库:   {settings.SYNC_DATABASE_URL}")
    log("=" * 60)

    added = 0
    skipped = 0
    errors = 0

    for db_name, table, idx_name, columns, unique in INDEXES:
        engine = engine_map.get(db_name)
        if not engine:
            log(f"  [ERR] 未知数据库: {db_name}")
            errors += 1
            continue

        # 检查索引是否已存在
        with engine.connect() as conn:
            existing = conn.execute(
                text(f"SHOW INDEX FROM {table} WHERE Key_name = '{idx_name}'")
            ).fetchall()

        if existing:
            log(f"  - {db_name}.{table}.{idx_name} 已存在，跳过")
            skipped += 1
            continue

        # 添加索引
        unique_clause = "UNIQUE INDEX" if unique else "INDEX"
        sql = f"ALTER TABLE {db_name}.{table} ADD {unique_clause} {idx_name} ({columns})"
        t0 = timer_start()
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
            timer_end(t0, f"[OK] 添加 {db_name}.{table}.{idx_name} ({columns})")
            added += 1
        except Exception as e:
            timer_end(t0, f"[ERR] 添加 {db_name}.{table}.{idx_name} 失败: {e}")
            errors += 1

    log("=" * 60)
    log(f"完成: 新增 {added} 个, 已存在跳过 {skipped} 个, 失败 {errors} 个")
    log("=" * 60)
    log("提示: 缓存版本已为 v10，新索引生效后重启后端即可提速。")

    words_engine.dispose()
    main_engine.dispose()


if __name__ == "__main__":
    main()
