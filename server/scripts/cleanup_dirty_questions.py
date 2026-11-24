#!/usr/bin/env python3
"""
清理 question_bank 中存在的脏题

1. 删除所有含脏干扰项的题目（content.options/[xxx]标签），以及关联的 wrong_question
2. 删除 word_id 对应 dirty translation 的题目（写备但可能漏网的）
3. 可选：全量删除后重新生成（--full-reset）
"""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def find_dirty_question_ids(conn, batch_size: int = 5000) -> list[int]:
    """找到所有 content 中选项含 [xxx] 标签的题目 ID"""
    dirty_ids = []
    offset = 0

    # 常见脏标签模式
    dirty_patterns = [
        '[网络]', '[人名]', '[地名]', '[化]', '[法]', '[医]', '[经]',
        '[计]', '[数]', '[物]', '[生化]', '[生物]', '[地质]', '[气象]',
        '[白俄罗斯]', '[俄罗斯]', '[拉脱维亚]', '[杜布纳]',
        '[动]', '[植]',
    ]

    while True:
        sql = text(
            "SELECT id, content FROM question_bank WHERE is_active = 1 "
            "ORDER BY id LIMIT :limit OFFSET :offset"
        )
        rows = conn.execute(sql, {"limit": batch_size, "offset": offset}).fetchall()
        if not rows:
            break

        for row in rows:
            qid, content_json = row
            try:
                content = json.loads(content_json) if isinstance(content_json, str) else {}
                text_to_check = json.dumps(content.get('options', []), ensure_ascii=False)
                for pat in dirty_patterns:
                    if pat in text_to_check:
                        dirty_ids.append(qid)
                        break
            except:
                pass

        offset += batch_size
        log(f"  已扫描 {offset} 条，发现 {len(dirty_ids)} 个脏题ID")
        if len(rows) < batch_size:
            break

    return dirty_ids


def main():
    parser = argparse.ArgumentParser(description="清理 question_bank 脏题")
    parser.add_argument("--full-reset", action="store_true",
                        help="全量重置：删除所有题目后重新生成")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)

    if args.full_reset:
        # 方案1：全量重置
        log("全量重置模式：删除所有题目...")
        BATCH_SIZE = 500

        with engine.connect() as conn:
            # 1. 删除关联错题
            log("删除关联错题记录...")
            conn.execute(text("DELETE FROM wrong_question WHERE question_id IN (SELECT id FROM question_bank)"))
            conn.commit()

            # 2. 分批次删除所有题目
            total = 0
            while True:
                result = conn.execute(
                    text(f"DELETE FROM question_bank LIMIT {BATCH_SIZE}")
                )
                conn.commit()
                total += result.rowcount
                if result.rowcount == 0:
                    break
                log(f"  已删除 {total} 条...")
            log(f"全部删除完成：共 {total} 条")

        engine.dispose()
        log("\n完成！请手动运行以下命令重新生成题目：")
        log("  python scripts/generate_questions.py --words-per-stage 3000")
        return

    # 方案2：仅检测并删除脏干扰项的题目
    log("扫描脏题干扰项...")

    with engine.connect() as conn:
        dirty_ids = find_dirty_question_ids(conn)
        log(f"发现 {len(dirty_ids)} 条含脏干扰项的题目")

        if not dirty_ids:
            log("无需清理")
            engine.dispose()
            return

        # 批量删除（含关联错题）
        BATCH_SIZE = 500
        total_qb = 0
        total_wq = 0

        for i in range(0, len(dirty_ids), BATCH_SIZE):
            batch = dirty_ids[i:i + BATCH_SIZE]
            placeholders = ",".join(str(pid) for pid in batch)

            # 删除关联错题
            wq_result = conn.execute(text(
                f"DELETE FROM wrong_question WHERE question_id IN ({placeholders})"
            ))
            total_wq += wq_result.rowcount

            # 删除题目
            qb_result = conn.execute(text(
                f"DELETE FROM question_bank WHERE id IN ({placeholders})"
            ))
            total_qb += qb_result.rowcount

        conn.commit()
        log(f"已清理错题: {total_wq} 条")
        log(f"已清理脏题: {total_qb} 条")

        # 统计剩余题目
        remain = conn.execute(text("SELECT COUNT(*) FROM question_bank WHERE is_active = 1")).scalar() or 0
        log(f"题库剩余: {remain} 题")

    engine.dispose()
    log("完成！")


if __name__ == "__main__":
    main()
