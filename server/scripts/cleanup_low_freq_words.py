#!/usr/bin/env python3
"""
清理低频生僻词脚本

从 stage_word 和 question_bank 中移除无质量指标的低频词。
质量门槛（与 word_service._apply_stage_filter 保持一致）：
  - collins > 0        （柯林斯星级）
  - bnc > 0 AND bnc < 20000 （BNC 前 2 万词）
  - oxford == 1        （牛津核心词）
  - frq > 0 AND frq < 30000 （有词频数据）

用法：
    python scripts/cleanup_low_freq_words.py [--dry-run]

默认 dry-run = True（只统计不删除），加 --no-dry-run 执行实际删除。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── 质量门槛 SQL 条件（取反 = 低频词识别） ──
QUALITY_COND = """
    NOT (
        dw.collins > 0
        OR (dw.bnc > 0 AND dw.bnc < 20000)
        OR dw.oxford = 1
        OR (dw.frq > 0 AND dw.frq < 30000)
    )
"""


def main():
    dry_run = "--no-dry-run" not in sys.argv
    if dry_run:
        log("=== DRY RUN 模式：仅统计，不删除 ===")
        log("如需执行删除，请加 --no-dry-run 参数")
    else:
        log("=== 执行模式：将实际删除低频词数据 ===")

    settings = get_settings()

    words_engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)
    log(f"单词库连接: {settings.SYNC_WORDS_DATABASE_URL}")

    # ── 1. 统计低频词数量 ──
    sql_counts = text(f"""
        SELECT
            COUNT(*) AS total_words,
            SUM(CASE WHEN {QUALITY_COND} THEN 1 ELSE 0 END) AS low_freq_words
        FROM dict_word dw
    """)
    with words_engine.connect() as conn:
        row = conn.execute(sql_counts).fetchone()
    log(f"dict_word 总数: {row[0]}, 低频词数: {row[1]} ({row[1]*100/max(row[0],1):.1f}%)")

    # ── 2. 低频词在 stage_word 中的分布 ──
    sql_stage = text(f"""
        SELECT sw.stage, COUNT(*) AS cnt
        FROM stage_word sw
        JOIN dict_word dw ON sw.word_id = dw.id
        WHERE {QUALITY_COND}
        GROUP BY sw.stage
        ORDER BY sw.stage
    """)
    with words_engine.connect() as conn:
        rows = conn.execute(sql_stage).fetchall()
    total_stage = sum(r[1] for r in rows)
    if total_stage > 0:
        log(f"\nstage_word 中低频词分布（共 {total_stage} 条）:")
        for stage, cnt in rows:
            log(f"  stage {stage}: {cnt} 个")
    else:
        log("\nstage_word 中没有低频词，跳过清理")

    # ── 3. 低频词相关题目在 question_bank 中的分布 ──
    main_engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    log(f"\n主库连接: {settings.SYNC_DATABASE_URL}")

    sql_qb = text(f"""
        SELECT qb.stage, qb.type, COUNT(*) AS cnt
        FROM question_bank qb
        JOIN elearnword.dict_word dw ON qb.word_id = dw.id
        WHERE {QUALITY_COND}
        GROUP BY qb.stage, qb.type
        ORDER BY qb.stage, qb.type
    """)
    with main_engine.connect() as conn:
        qb_rows = conn.execute(sql_qb).fetchall()
    total_qb = sum(r[2] for r in qb_rows)
    if total_qb > 0:
        log(f"question_bank 中低频词题目（共 {total_qb} 道）:")
        for stage, qtype, cnt in qb_rows:
            log(f"  stage {stage}, type {qtype}: {cnt} 题")
    else:
        log("question_bank 中没有低频词题目")

    # ── 4. 执行删除 ──
    if dry_run:
        log(f"\n总计：将删除 stage_word {total_stage} 条 + question_bank {total_qb} 题")
        log("DRY RUN — 未执行任何删除")
    else:
        # 删除低频词关联的题目
        if total_qb > 0:
            del_qb = text(f"""
                DELETE qb FROM question_bank qb
                JOIN elearnword.dict_word dw ON qb.word_id = dw.id
                WHERE {QUALITY_COND}
            """)
            with main_engine.connect() as conn:
                result = conn.execute(del_qb)
                conn.commit()
            log(f"已删除 question_bank: {result.rowcount} 题")
        else:
            log("question_bank 无需清理")

        # 删除低频词关联的 stage_word
        if total_stage > 0:
            del_sw = text(f"""
                DELETE sw FROM stage_word sw
                JOIN dict_word dw ON sw.word_id = dw.id
                WHERE {QUALITY_COND}
            """)
            with words_engine.connect() as conn:
                result = conn.execute(del_sw)
                conn.commit()
            log(f"已删除 stage_word: {result.rowcount} 条")
        else:
            log("stage_word 无需清理")

        # 低频词从 dict_word 中删除（可选 — 保留原始数据，仅标注 is_active 或直接删）
        # 建议仅删除没有任何 stage 引用且低频的词
        sql_orphan = text(f"""
            DELETE dw FROM dict_word dw
            LEFT JOIN stage_word sw ON dw.id = sw.word_id
            WHERE sw.word_id IS NULL
              AND {QUALITY_COND}
        """)
        with words_engine.connect() as conn:
            result = conn.execute(sql_orphan)
            conn.commit()
        log(f"已删除无阶段引用的低频 dict_word: {result.rowcount} 条")

    words_engine.dispose()
    main_engine.dispose()
    log("完成!")


if __name__ == "__main__":
    main()
