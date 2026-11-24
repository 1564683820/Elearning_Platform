#!/usr/bin/env python3
"""
词根词缀 + 单词-词根关联 导入脚本

从 scripts/seed_data/roots.json 导入词根词缀到 dict_root 表，
然后自动匹配已导入的 dict_word 中的单词，建立 dict_word_root 关联。

用法:
    python scripts/import_roots.py [--skip-roots] [--skip-mapping]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.core.config import get_settings

SCRIPT_DIR = Path(__file__).parent
ROOTS_PATH = SCRIPT_DIR / "seed_data" / "roots.json"
BATCH_SIZE = 500


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def step1_import_roots(engine):
    """从 roots.json 导入词根词缀到 dict_root 表"""
    if not ROOTS_PATH.exists():
        log(f"错误: 词根数据文件不存在: {ROOTS_PATH}")
        sys.exit(1)

    with open(ROOTS_PATH, "r", encoding="utf-8") as f:
        roots_data = json.load(f)

    log(f"读取到 {len(roots_data)} 条词根词缀数据")

    # 类型映射
    type_map = {
        "prefix": "prefix",
        "root": "root",
        "suffix": "suffix",
    }

    # 清空现有数据（保留自增ID从1开始）
    with engine.connect() as conn:
        conn.exec_driver_sql("TRUNCATE TABLE dict_root")
        conn.exec_driver_sql("TRUNCATE TABLE dict_word_root")
        conn.commit()
    log("已清空 dict_root 和 dict_word_root 表")

    # 批量插入
    batch = []
    imported = 0
    for item in roots_data:
        root_text = item[0]
        root_type = item[1]
        meaning = item[2]
        origin = item[3] if len(item) > 3 else ""

        batch.append(f"({batch_escape(root_text)}, {batch_escape(root_type)}, "
                     f"{batch_escape(meaning)}, {batch_escape(origin)})")

        if len(batch) >= BATCH_SIZE:
            sql = ("INSERT INTO dict_root (root, root_type, meaning, origin) VALUES "
                   + ",".join(batch) + ";")
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql(sql)
                    conn.commit()
                imported += len(batch)
            except Exception as e:
                log(f"批次写入失败: {e}")
            batch = []
            log(f"已经导入 {imported} 条词根词缀...")

    if batch:
        sql = ("INSERT INTO dict_root (root, root_type, meaning, origin) VALUES "
               + ",".join(batch) + ";")
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(sql)
                conn.commit()
            imported += len(batch)
        except Exception as e:
            log(f"最后批次写入失败: {e}")

    log(f"词根词缀导入完成: 共 {imported} 条")

    # 验证
    with engine.connect() as conn:
        types = conn.execute(
            text("SELECT root_type, COUNT(*) as cnt FROM dict_root GROUP BY root_type")
        ).fetchall()
        for t in types:
            log(f"  - {t[0]}: {t[1]} 条")

    return imported


def step2_build_word_mapping(engine):
    """算法匹配 dict_word 中的单词到已导入的词根/词缀，建立 dict_word_root 关联"""
    log("开始构建单词-词根关联...")

    # 读取所有词根词缀
    with engine.connect() as conn:
        roots = conn.execute(
            text("SELECT id, root, root_type FROM dict_root ORDER BY LENGTH(root) DESC")
        ).fetchall()
    log(f"共 {len(roots)} 条词根词缀参与匹配")

    # 按类型分组
    prefixes = [r for r in roots if r[2] == "prefix"]
    suffixes = [r for r in roots if r[2] == "suffix"]
    mid_roots = [r for r in roots if r[2] == "root"]

    log(f"  前缀: {len(prefixes)}, 后缀: {len(suffixes)}, 词根: {len(mid_roots)}")

    # 读取所有单词（分批处理）
    total_mapped = 0
    offset = 0
    batch_size = 50000
    pair_batch = []

    while True:
        with engine.connect() as conn:
            words = conn.execute(
                text(f"SELECT id, word FROM dict_word LIMIT {batch_size} OFFSET {offset}")
            ).fetchall()

        if not words:
            break

        word_progress = 0
        for word_id, word_text in words:
            word_lower = word_text.lower()
            wn = len(word_lower)
            position = 0

            # 1. 匹配前缀（从开头匹配，最短2字符）
            for root_id, root_text, _ in prefixes:
                rt = root_text.lower()
                if len(rt) >= 2 and word_lower.startswith(rt) and wn > len(rt):
                    pair_batch.append(f"({word_id}, {root_id}, {position})")
                    position += 1

            # 2. 匹配后缀（从结尾匹配，最短2字符）
            for root_id, root_text, _ in suffixes:
                rt = root_text.lower()
                if len(rt) >= 2 and word_lower.endswith(rt) and wn > len(rt):
                    pair_batch.append(f"({word_id}, {root_id}, {position})")
                    position += 1

            # 3. 匹配中间词根（排除开头和结尾，最短3字符）
            for root_id, root_text, _ in mid_roots:
                rt = root_text.lower()
                if len(rt) >= 3 and rt in word_lower:
                    # 不在开头也不在结尾才算真正是"词根"
                    start_idx = word_lower.index(rt)
                    end_idx = start_idx + len(rt)
                    # 允许在开头或结尾（不排除，因为词根本身可能出现在任何位置）
                    pair_batch.append(f"({word_id}, {root_id}, {position})")
                    position += 1

            word_progress += 1

            # 批量写入
            if len(pair_batch) >= BATCH_SIZE:
                _flush_pairs(engine, pair_batch)
                total_mapped += len(pair_batch)
                pair_batch = []

        offset += batch_size
        log(f"已处理 {offset} 个单词, 已建立 {total_mapped} 对关联...")

    # 处理剩余
    if pair_batch:
        _flush_pairs(engine, pair_batch)
        total_mapped += len(pair_batch)

    log(f"单词-词根关联构建完成: 共 {total_mapped} 对")

    # 验证
    with engine.connect() as conn:
        word_count = conn.execute(
            text("SELECT COUNT(DISTINCT word_id) FROM dict_word_root")
        ).scalar() or 0
        log(f"有词根关联的单词数: {word_count}")

    return total_mapped


def _flush_pairs(engine, batch):
    """批量写入 dict_word_root"""
    sql = ("INSERT IGNORE INTO dict_word_root (word_id, root_id, position) VALUES "
           + ",".join(batch) + ";")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(sql)
            conn.commit()
    except Exception as e:
        log(f"dict_word_root 批次写入失败: {e}")


def batch_escape(val):
    """转义 SQL 字符串值"""
    if val is None:
        return "NULL"
    s = str(val)
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\0", "\\0")
    return "'" + s + "'"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="词根词缀导入 + 单词匹配工具")
    parser.add_argument("--skip-roots", action="store_true", help="跳过导入词根词缀")
    parser.add_argument("--skip-mapping", action="store_true", help="跳过单词-词根匹配")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)

    log("=== 词根词缀导入 + 单词-词根匹配 ===")

    if not args.skip_roots:
        step1_import_roots(engine)
    else:
        log("跳过词根词缀导入 (--skip-roots)")

    if not args.skip_mapping:
        step2_build_word_mapping(engine)
    else:
        log("跳过单词-词根匹配 (--skip-mapping)")

    engine.dispose()
    log("全部完成!")


if __name__ == "__main__":
    main()
