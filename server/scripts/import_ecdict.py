#!/usr/bin/env python3
"""
ECDICT 词典数据导入脚本

从 ECDICT SQLite 读取词典数据，批量导入本地 MySQL (dict_word + stage_word)

数据源: https://github.com/skywind3000/ECDICT
用法:
    python scripts/import_ecdict.py [--skip-download] [--skip-import] [--skip-stage]
"""
import argparse
import os
import sys
import time
import zipfile
import urllib.request
import sqlite3
from pathlib import Path

# 将项目根目录加入 sys.path，以便导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings
from app.db.database import Base

# ── 配置 ──────────────────────────────────────────
ECDICT_URL = "https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip"
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "ecdict-data"
ZIP_PATH = DATA_DIR / "ecdict-sqlite-28.zip"
DB_PATH = DATA_DIR / "stardict.db"          # 解压后的 SQLite 文件名
BATCH_SIZE = 500                            # 每批插入条数

# ── Phase 中文 → stage 映射（精简为四个阶段）─────
PHASE_STAGE_MAP = {
    "启蒙": 1, "英语启蒙": 1,
    "小学三年级": 1, "小学英语": 1, "小学四年级": 1, "小学五年级": 1,
    "初中一年级": 2, "初中英语": 2, "初中二年级": 2,
    "初中三年级": 2,
    "高中英语": 3, "高中一年级": 3, "高中二年级": 3, "高中三年级": 3,
    "英语四级": 4, "英语六级": 4, "考研英语": 4,
    "托福": 4, "雅思": 4, "GRE": 4,
}


def log(msg: str):
    """带时间戳的日志输出"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ═══════════════════════════════════════════════════
# 步骤 1：下载并解压 ECDICT SQLite 数据库
# ═══════════════════════════════════════════════════

def step1_download(skip_download: bool):
    """下载并解压 ECDICT SQLite 数据库"""
    if skip_download:
        log("跳过下载 (--skip-download)")
        if not DB_PATH.exists():
            log(f"错误：SQLite 文件不存在: {DB_PATH}")
            log("请先手动下载并解压到 scripts/ecdict-data/ 目录")
            sys.exit(1)
        return

    if DB_PATH.exists():
        log(f"SQLite 文件已存在: {DB_PATH}，跳过下载")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1a. 下载 zip
    if not ZIP_PATH.exists():
        log(f"下载 ECDICT SQLite 数据库...")
        log(f"URL: {ECDICT_URL}")

        def _progress(block_count, block_size, total_size):
            if total_size > 0:
                downloaded = block_count * block_size
                pct = downloaded * 100 / total_size
                speed = downloaded / (time.time() - _start_time) / 1024
                print(f"\r下载进度: {pct:.1f}% ({downloaded / 1024 / 1024:.1f}MB / "
                      f"{total_size / 1024 / 1024:.1f}MB) {speed:.0f}KB/s", end="", flush=True)
            else:
                print(f"\r已下载: {block_count * block_size / 1024 / 1024:.1f}MB", end="", flush=True)

        _start_time = time.time()
        urllib.request.urlretrieve(ECDICT_URL, ZIP_PATH, _progress)
        print()
        log(f"下载完成: {ZIP_PATH}")
    else:
        log(f"压缩包已存在: {ZIP_PATH}")

    # 1b. 解压
    log("解压中...")
    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            zf.extractall(DATA_DIR)
        log("解压完成")
    except Exception as e:
        log(f"解压失败: {e}")
        sys.exit(1)

    if not DB_PATH.exists():
        log(f"解压后未找到 {DB_PATH}")
        log("请检查解压后文件名")
        sys.exit(1)


# ═══════════════════════════════════════════════════
# 步骤 2：创建数据库表
# ═══════════════════════════════════════════════════

def ensure_tables():
    """确保 MySQL 中所有表已创建"""
    from app.models import word  # noqa: F401 — 注册 DictWord, StageWord 的 metadata
    settings = get_settings()
    sync_engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    existing = Base.metadata.tables.keys()
    log(f"已注册 {len(existing)} 张表: {', '.join(sorted(existing))}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    log("数据库表初始化完成")


# ═══════════════════════════════════════════════════
# 步骤 3：批量导入 dict_word + 生成 stage_word
# ═══════════════════════════════════════════════════

def generate_sw(word: str) -> str:
    """生成 sw 字段：去除非字母数字字符并转小写"""
    return "".join(c for c in word.lower() if c.isalnum())


def tag_to_stages(tag: str, bnc: int, frq: int, collins: int, oxford: int = 0) -> list[int]:
    """
    根据 tag / bnc / frq / collins / oxford 将单词映射到学习阶段 1-4。
    精简为四个阶段：1=小学, 2=初中, 3=高中, 4=四六级

    过滤规则：无任何质量标记的词（collins=0, bnc=0, oxford=0, frq=0）
    视为低频生僻词，不分配任何阶段（不进 stage_word，不出题）。
    """
    # ── 质量门槛：至少满足一项质量指标才分配阶段 ──
    # 收紧门槛：排除低频词（BNC前15000 / FRQ前15000 才视为常见词）
    has_quality = (
        collins > 0
        or (bnc > 0 and bnc < 15000)
        or oxford == 1
        or (frq > 0 and frq < 15000)
    )
    if not has_quality:
        return []

    stages = set()

    # 基于 bnc 词频的基础阶段映射：BNC前2000 → 小学
    if bnc > 0 and bnc <= 2000:
        stages.add(1)       # 小学

    # 基于 tag 的考试阶段映射
    if tag:
        if "zk" in tag:
            stages.add(2)   # 初中
        if "gk" in tag:
            stages.add(3)   # 高中
        if "cet4" in tag or "cet6" in tag:
            stages.add(4)   # 四六级
        if "ielts" in tag or "toefl" in tag or "gre" in tag:
            stages.add(4)   # 四六级（高阶词汇归入）

    # fallback: 有柯林斯星级但无 tag 的放到四六级
    if not stages and collins >= 1:
        stages.add(4)

    return sorted(stages)


def is_low_quality_word(word: str) -> bool:
    """判断是否为低质量词汇（词缀、化学名、短语、编号等），返回 True 表示应排除"""
    if not word or not word.strip():
        return True
    if not word[0].isalpha():
        # 不以字母开头（词缀 -arsine、化学名 2-furylacrylamine、.idd 等）
        return True
    if " " in word:
        # 含空格（多词短语，如 belt height, Keep it under your hat）
        return True
    if "/" in word:
        # 含斜杠（如 ac/ac converter）
        return True
    if not any(c.isalpha() for c in word):
        # 不含字母，如 232, 149PM
        return True
    return False


def escape_sql(val):
    """转义 SQL 字符串值（处理单引号、反斜杠、百分号等）"""
    if val is None:
        return "NULL"
    s = str(val)
    # 顺序重要：先转义反斜杠，再转义单引号
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\0", "\\0")
    s = s.replace("%", "%%")    # pymysql 会将 % 识别为格式化占位符
    return "'" + s + "'"


def step2_import(skip_import: bool, skip_stage: bool):
    """从 SQLite 读取并批量导入 MySQL"""
    if skip_import and skip_stage:
        log("跳过所有导入步骤 (--skip-import --skip-stage)")
        return

    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)

    # ── 3a. 连接 SQLite ──
    if not DB_PATH.exists():
        log(f"错误: ECDICT SQLite 文件不存在: {DB_PATH}")
        sys.exit(1)

    log("连接 ECDICT SQLite 数据库...")
    sqldb = sqlite3.connect(str(DB_PATH))
    sqldb.row_factory = sqlite3.Row
    total_rows = sqldb.execute("SELECT COUNT(*) as cnt FROM stardict").fetchone()["cnt"]
    log(f"ECDICT 总词条数: {total_rows}")

    # ── 3b. 批量插入 dict_word ──
    if not skip_import:
        log("开始导入 dict_word...")
        stmt = sqldb.execute("SELECT * FROM stardict ORDER BY id")

        imported = 0
        errors = 0
        all_stage_words = []       # 收集用于 stage_word 的数据
        batch_values = []
        start_time = time.time()

        for row in stmt:
            word = (row["word"] or "").strip()
            if not word:
                continue

            sw = generate_sw(word)

            values = (
                escape_sql(word),              # word
                escape_sql(sw),                # sw
                escape_sql(row["phonetic"]),   # phonetic
                escape_sql(row["definition"]), # definition
                escape_sql(row["translation"]),# translation
                escape_sql(row["pos"]),        # pos
                row["collins"] or 0,           # collins
                row["oxford"] or 0,            # oxford
                escape_sql(row["tag"]),        # tag
                row["bnc"] or 0,               # bnc
                row["frq"] or 0,               # frq
                escape_sql(row["exchange"]),   # exchange
                "''",                          # audio_url（暂空）
                "NULL",                        # detail_json
            )
            batch_values.append(f"({','.join(str(v) for v in values)})")

            # 收集 stage_word 映射（跳过低质量词汇）
            if not is_low_quality_word(word):
                tag_s = row["tag"] or ""
                bnc_v = row["bnc"] or 0
                frq_v = row["frq"] or 0
                collins_v = row["collins"] or 0
                oxford_v = row["oxford"] or 0
                stages = tag_to_stages(tag_s, bnc_v, frq_v, collins_v, oxford_v)
                for stage in stages:
                    all_stage_words.append({"word": word, "stage": stage})

            # 批量写入
            if len(batch_values) >= BATCH_SIZE:
                sql = (
                    "INSERT IGNORE INTO dict_word "
                    "(word, sw, phonetic, definition, translation, pos, collins, oxford, "
                    "tag, bnc, frq, exchange, audio_url, detail_json) VALUES "
                    + ",".join(batch_values) + ";"
                )
                try:
                    with engine.connect() as conn:
                        conn.exec_driver_sql(sql)
                        conn.commit()
                    imported += len(batch_values)
                except Exception as e:
                    errors += len(batch_values)
                    log(f"批次写入失败: {e}")
                    # 尝试逐条写入
                    for single_val in batch_values:
                        single_sql = (
                            "INSERT IGNORE INTO dict_word "
                            "(word, sw, phonetic, definition, translation, pos, collins, oxford, "
                            "tag, bnc, frq, exchange, audio_url, detail_json) VALUES "
                            + single_val + ";"
                        )
                        try:
                            with engine.connect() as conn:
                                conn.exec_driver_sql(single_sql)
                                conn.commit()
                            imported += 1
                        except Exception:
                            pass

                batch_values = []
                elapsed = time.time() - start_time
                rate = imported / elapsed if elapsed > 0 else 0
                remaining_sec = (total_rows - imported) / rate if rate > 0 else 0
                print(f"\r已导入: {imported}/{total_rows} ({imported * 100 / total_rows:.1f}%) "
                      f"速度: {rate:.0f}条/秒 剩余: {remaining_sec:.0f}s", end="", flush=True)

        # 处理最后剩余批次
        if batch_values:
            sql = (
                "INSERT IGNORE INTO dict_word "
                "(word, sw, phonetic, definition, translation, pos, collins, oxford, "
                "tag, bnc, frq, exchange, audio_url, detail_json) VALUES "
                + ",".join(batch_values) + ";"
            )
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql(sql)
                    conn.commit()
                imported += len(batch_values)
            except Exception as e:
                log(f"最后批次写入失败: {e}")

        elapsed = time.time() - start_time
        print()
        log(f"dict_word 导入完成: 成功 {imported}, 失败 {errors}, 耗时 {elapsed:.1f}s")
    else:
        log("跳过导入 dict_word (--skip-import)")

        # 即使跳过导入，仍需要从已有数据构建 word_id_map
        log("从已有 dict_word 查询 word → id 映射...")

    # ── 3c. 生成 stage_word 映射 ──
    if not skip_stage and not skip_import:
        log(f"开始生成 stage_word 映射，共 {len(all_stage_words)} 条...")

        # 查询 word → id 映射（从已导入的数据）
        log("查询 word → id 映射...")
        word_id_map = {}
        offset = 0
        map_batch = 5000
        while True:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(f"SELECT id, word FROM dict_word LIMIT {map_batch} OFFSET {offset}")
                ).fetchall()
            if not rows:
                break
            for row in rows:
                word_id_map[row[1]] = row[0]
            offset += map_batch
            if len(rows) < map_batch:
                break

        log(f"word → id 映射完成，共 {len(word_id_map)} 条")

        # 批量插入 stage_word
        stage_batch = []
        stage_imported = 0
        mastery_order = {}
        start_time = time.time()

        for item in all_stage_words:
            word_id = word_id_map.get(item["word"])
            if word_id is None:
                continue

            stage = item["stage"]
            key = f"s{stage}"
            mastery_order[key] = mastery_order.get(key, 0) + 1
            mo = mastery_order[key]

            stage_batch.append(f"({word_id}, {stage}, {mo})")

            if len(stage_batch) >= BATCH_SIZE:
                sql = (
                    "INSERT IGNORE INTO stage_word (word_id, stage, mastery_order) VALUES "
                    + ",".join(stage_batch) + ";"
                )
                try:
                    with engine.connect() as conn:
                        conn.exec_driver_sql(sql)
                        conn.commit()
                    stage_imported += len(stage_batch)
                except Exception as e:
                    log(f"stage_word 批次写入失败: {e}")
                stage_batch = []
                print(f"\rstage_word 已导入: {stage_imported}/{len(all_stage_words)}", end="", flush=True)

        if stage_batch:
            sql = (
                "INSERT IGNORE INTO stage_word (word_id, stage, mastery_order) VALUES "
                + ",".join(stage_batch) + ";"
            )
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql(sql)
                    conn.commit()
                stage_imported += len(stage_batch)
            except Exception as e:
                log(f"stage_word 最后批次写入失败: {e}")

        elapsed = time.time() - start_time
        print()
        log(f"stage_word 导入完成: {stage_imported} 条, 耗时 {elapsed:.1f}s")

    sqldb.close()
    engine.dispose()
    log("全部完成!")


# ═══════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ECDICT 词典数据导入工具")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载和解压 ECDICT 数据")
    parser.add_argument("--skip-import", action="store_true", help="跳过导入 dict_word")
    parser.add_argument("--skip-stage", action="store_true", help="跳过生成 stage_word 映射")
    args = parser.parse_args()

    log("=== ECDICT 数据导入工具 ===")
    log(f"参数: skip_download={args.skip_download}, skip_import={args.skip_import}, skip_stage={args.skip_stage}")

    try:
        step1_download(args.skip_download)
        ensure_tables()
        step2_import(args.skip_import, args.skip_stage)
    except KeyboardInterrupt:
        log("用户中断")
        sys.exit(1)
    except Exception as e:
        log(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
