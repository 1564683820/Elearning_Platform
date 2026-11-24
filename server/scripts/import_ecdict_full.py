#!/usr/bin/env python3
"""
ECDICT 全量导入脚本 — 导入到 elearnword.dict_word

功能:
  1. 从 ECDICT SQLite (340 万词条) 读取数据
  2. 自动建表（WordBase → dict_word 表）
  3. 默认清空后重导（--no-truncate 跳过清空）
  4. 参数化批量写入，支持断点续传（--no-truncate）

导入字段:
  word / sw / phonetic / definition / translation / pos
  collins / oxford / tag / bnc / frq / exchange
  audio_url(空) / detail_json(NULL)

用法:
    python scripts/import_ecdict_full.py
    python scripts/import_ecdict_full.py --no-truncate --batch-size 5000
"""
import argparse
import sys
import time
import sqlite3
import itertools
from pathlib import Path
from tqdm import tqdm

# 将项目根目录加入 sys.path，以便导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from app.core.config import get_settings
from app.db.database import WordBase
# 注册 DictWord 等 model 到 WordBase.metadata
from app.models import word  # noqa: F401

# ── 配置 ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "ecdict-data"
DB_PATH = DATA_DIR / "stardict.db"          # ECDICT SQLite 路径

# 14 个 INSERT 字段
INSERT_FIELDS = (
    "word", "sw", "phonetic", "definition", "translation",
    "pos", "collins", "oxford", "tag", "bnc", "frq",
    "exchange", "audio_url", "detail_json"
)
FIELD_COUNT = len(INSERT_FIELDS)
FIELD_NAMES = ", ".join(INSERT_FIELDS)
PLACEHOLDER_ROW = "(" + ",".join(["%s"] * FIELD_COUNT) + ")"


def generate_sw(word: str) -> str:
    """生成 sw 字段：去除非字母数字字符并转小写"""
    return "".join(c for c in word.lower() if c.isalnum())


def log(msg: str):
    """带时间戳的日志输出"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="ECDICT 全量导入工具 — elearnword.dict_word")
    parser.add_argument("--no-truncate", action="store_true",
                        help="不清空表，追加导入（可用于断点续传）")
    parser.add_argument("--batch-size", type=int, default=2000,
                        help="每批插入条数 (默认 2000)")
    args = parser.parse_args()

    settings = get_settings()
    db_url = settings.SYNC_WORDS_DATABASE_URL
    log(f"目标数据库: {settings.WORDS_DATABASE} (表: dict_word)")

    # ── 检查 SQLite 数据源 ──
    if not DB_PATH.exists():
        log(f"错误: ECDICT SQLite 文件不存在: {DB_PATH}")
        log("请先运行 python scripts/import_ecdict.py 下载并解压")
        sys.exit(1)

    # ── 第 1 步：连接 SQLite 并获取总数 ──
    log(f"连接 ECDICT SQLite: {DB_PATH}")
    sqldb = sqlite3.connect(str(DB_PATH))
    sqldb.row_factory = sqlite3.Row
    total = sqldb.execute("SELECT COUNT(*) FROM stardict").fetchone()[0]
    log(f"ECDICT 总词条数: {total:,}")

    # ── 第 2 步：连接 MySQL ──
    engine = create_engine(db_url, echo=False, pool_pre_ping=True)

    # ── 第 2a 步：确保 dict_word 表已存在 ──
    log("检查/创建 dict_word 表...")
    WordBase.metadata.create_all(engine)
    log("表结构已就绪")

    # ── 第 2b 步：清空（默认）或跳过 ──
    if not args.no_truncate:
        log("清空 dict_word 表 (TRUNCATE)...")
        with engine.connect() as conn:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
            conn.exec_driver_sql("TRUNCATE TABLE dict_word")
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
            conn.commit()
        log("TRUNCATE 完成")
    else:
        log("跳过清空 (--no-truncate)，追加导入")

    # ── 第 3 步：批量导入 ──
    log("开始从 SQLite 读取并导入 MySQL...")
    stmt = sqldb.execute("SELECT * FROM stardict ORDER BY id")

    batch = []            # 当前批次的元组列表 [(word, sw, ...), ...]
    imported = 0          # 成功条数
    errors = 0            # 失败条数
    start_time = time.time()

    pbar = tqdm(total=total, unit="条", desc="导入进度",
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]")

    for row in stmt:
        word_text = (row["word"] or "").strip()
        if not word_text:
            pbar.update(1)
            continue

        # 构建本行元组（14 个字段，位置与 INSERT_FIELDS 严格对应）
        batch.append((
            word_text,                           # word
            generate_sw(word_text),              # sw
            row["phonetic"] or "",               # phonetic
            row["definition"],                   # definition (可为 None)
            row["translation"],                  # translation (可为 None)
            row["pos"] or "",                    # pos
            row["collins"] or 0,                 # collins
            row["oxford"] or 0,                  # oxford
            row["tag"] or "",                    # tag
            row["bnc"] or 0,                     # bnc
            row["frq"] or 0,                     # frq
            row["exchange"] or "",               # exchange
            "",                                  # audio_url（暂空）
            None,                                # detail_json（NULL）
        ))
        pbar.update(1)

        # 达到批次大小时写入 MySQL
        if len(batch) >= args.batch_size:
            err = _flush_batch(engine, batch)
            imported += len(batch) - err
            errors += err
            batch = []

    # 处理最后一批
    if batch:
        err = _flush_batch(engine, batch)
        imported += len(batch) - err
        errors += err

    pbar.close()
    elapsed = time.time() - start_time
    log(f"导入完成! 成功: {imported:,}, 失败: {errors:,}, 耗时: {elapsed:.0f}s")

    sqldb.close()
    engine.dispose()
    log("全部完成!")


def _flush_batch(engine, rows: list[tuple]) -> int:
    """将一批行写入 dict_word 表（多行 INSERT IGNORE），返回失败条数"""
    count = len(rows)
    err = 0
    # 多行 VALUES 需要扁平参数列表，但 SQLAlchemy exec_driver_sql 会校验要求列表元素为元组/字典
    # 因此绕过 SQLAlchemy，直接操作底层 pymysql cursor
    raw_conn = engine.raw_connection()
    try:
        values_clause = ",".join([PLACEHOLDER_ROW] * count)
        sql = f"INSERT IGNORE INTO dict_word ({FIELD_NAMES}) VALUES {values_clause}"
        flat_params = tuple(itertools.chain.from_iterable(rows))

        cursor = raw_conn.cursor()
        cursor.execute(sql, flat_params)
        raw_conn.commit()
        cursor.close()
    except Exception as e:
        raw_conn.rollback()
        err = count
        log(f"批次写入失败 ({count}条): {e}")
        # fallback: 逐条插入
        single_sql = f"INSERT IGNORE INTO dict_word ({FIELD_NAMES}) VALUES ({','.join(['%s'] * FIELD_COUNT)})"
        cursor = raw_conn.cursor()
        for row in rows:
            try:
                cursor.execute(single_sql, row)
            except Exception:
                pass
        raw_conn.commit()
        cursor.close()
    finally:
        raw_conn.close()
    return err


if __name__ == "__main__":
    main()
