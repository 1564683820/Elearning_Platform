#!/usr/bin/env python3
"""
导入记忆金句（巧记口诀）+ 扩展例句 + 近义词种子数据

从 seed_data/mnemonics.json 导入记忆金句到 dict_word 的 detail_json 字段，
从 seed_data/synonyms.json 导入近义词辨析数据，
以及从 seed_data/examples.json 导入精选例句。

用法:
    python scripts/import_enrichment.py [--skip-mnemonics] [--skip-synonyms] [--skip-examples]
"""
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings

SCRIPT_DIR = Path(__file__).parent
SEED_DIR = SCRIPT_DIR / "seed_data"
BATCH_SIZE = 200


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def escape_sql(val):
    if val is None:
        return "NULL"
    s = str(val)
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\0", "\\0")
    return "'" + s + "'"


def step1_import_mnemonics(engine):
    """导入记忆金句到 detail_json.idiom 字段"""
    mnemonics_path = SEED_DIR / "mnemonics.json"
    if not mnemonics_path.exists():
        log(f"记忆金句文件不存在: {mnemonics_path}, 跳过")
        return 0

    with open(mnemonics_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    log(f"读取到 {len(data)} 条记忆金句数据")

    # 先查询 word → id 映射（只查询一次）
    word_id_map = {}
    with engine.connect() as conn:
        words = conn.execute(text("SELECT id, word FROM dict_word")).fetchall()
        for w in words:
            word_id_map[w[1].lower()] = w[0]
    log(f"dict_word 共有 {len(word_id_map)} 个单词")

    updated = 0
    batch = []

    for item in data:
        word_text = item.get("word", "").strip().lower()
        word_id = word_id_map.get(word_text)
        if word_id is None:
            log(f"  未找到单词 '{item.get('word')}', 跳过")
            continue

        idiom_data = {
            "en": item.get("en", ""),
            "zh": item.get("zh", ""),
            "mnemonic": item.get("mnemonic", ""),
        }

        # 批量构建 SQL：用 JSON_OBJECT 设置 detail_json 的 idiom 字段
        idiom_json_str = json.dumps(idiom_data, ensure_ascii=False)
        idiom_escaped = escape_sql(idiom_json_str)

        batch.append((word_id, idiom_json_str))
        updated += 1

        if len(batch) >= BATCH_SIZE:
            _flush_mnemonics(engine, batch, len(word_id_map))
            log(f"已更新 {updated} 条...")
            batch = []

    if batch:
        _flush_mnemonics(engine, batch, len(word_id_map))

    log(f"记忆金句导入完成: 共更新 {updated} 个单词")
    return updated


def _flush_mnemonics(engine, batch, total_words):
    """使用 JSON_SET 更新 detail_json.idiom"""
    for word_id, idiom_json_str in batch:
        idiom_escaped = escape_sql(idiom_json_str)
        sql = (
            f"UPDATE dict_word SET "
            f"detail_json = CASE "
            f"  WHEN detail_json IS NULL THEN JSON_OBJECT('idiom', CAST({idiom_escaped} AS JSON)) "
            f"  ELSE JSON_SET(detail_json, '$.idiom', CAST({idiom_escaped} AS JSON)) "
            f"END "
            f"WHERE id = {word_id};"
        )
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(sql)
                conn.commit()
        except Exception as e:
            log(f"更新 word_id={word_id} 失败: {e}")


def step2_import_synonyms(engine):
    """导入近义词辨析数据到 word_synonyms 表"""
    synonyms_path = SEED_DIR / "synonyms.json"
    if not synonyms_path.exists():
        log(f"近义词文件不存在: {synonyms_path}, 跳过")
        return 0

    with open(synonyms_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    log(f"读取到 {len(data)} 条近义词数据")

    # 查询 word → id 映射
    word_id_map = {}
    with engine.connect() as conn:
        words = conn.execute(text("SELECT id, word FROM dict_word")).fetchall()
        for w in words:
            word_id_map[w[1].lower()] = w[0]

    # 清空 word_synonyms 表
    with engine.connect() as conn:
        conn.exec_driver_sql("TRUNCATE TABLE word_synonyms")
        conn.commit()
    log("已清空 word_synonyms 表")

    inserted = 0
    batch = []

    for item in data:
        word_text = item.get("word", "").strip().lower()
        word_id = word_id_map.get(word_text)
        if word_id is None:
            continue

        synonyms = item.get("synonyms", [])
        for syn in synonyms:
            syn_word = syn.get("word", "")
            tag = syn.get("tag", "")
            usage = syn.get("usage_desc", "")
            example = syn.get("example", "")

            batch.append(
                f"({word_id}, {escape_sql(syn_word)}, {escape_sql(tag)}, "
                f"{escape_sql(usage)}, {escape_sql(example)})"
            )

        if len(batch) >= BATCH_SIZE:
            sql = (
                "INSERT IGNORE INTO word_synonyms (word_id, synonym_word, tag, usage_desc, example) VALUES "
                + ",".join(batch) + ";"
            )
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql(sql)
                    conn.commit()
                inserted += len(batch)
            except Exception as e:
                log(f"近义词批次写入失败: {e}")
            batch = []
            log(f"已导入 {inserted} 条近义词...")

    if batch:
        sql = ("INSERT IGNORE INTO word_synonyms (word_id, synonym_word, tag, usage_desc, example) VALUES "
               + ",".join(batch) + ";")
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(sql)
                conn.commit()
            inserted += len(batch)
        except Exception as e:
            log(f"最后批次失败: {e}")

    log(f"近义词导入完成: 共 {inserted} 条")
    return inserted


def step3_import_examples(engine):
    """导入精选例句到 detail_json.example 字段"""
    examples_path = SEED_DIR / "examples.json"
    if not examples_path.exists():
        log(f"例句文件不存在: {examples_path}, 跳过")
        return 0

    with open(examples_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    log(f"读取到 {len(data)} 条例句数据")

    word_id_map = {}
    with engine.connect() as conn:
        words = conn.execute(text("SELECT id, word FROM dict_word")).fetchall()
        for w in words:
            word_id_map[w[1].lower()] = w[0]

    updated = 0
    batch = []

    for item in data:
        word_text = item.get("word", "").strip().lower()
        word_id = word_id_map.get(word_text)
        if word_id is None:
            log(f"  未找到单词 '{item.get('word')}', 跳过")
            continue

        example_data = {
            "en": item.get("en", ""),
            "zh": item.get("zh", ""),
        }
        example_json_str = json.dumps(example_data, ensure_ascii=False)
        example_escaped = escape_sql(example_json_str)

        batch.append((word_id, example_escaped))
        updated += 1

        if len(batch) >= BATCH_SIZE:
            _flush_examples(engine, batch)
            print(f"\r已更新 {updated} 条例句...", end="", flush=True)
            batch = []

    if batch:
        _flush_examples(engine, batch)

    print()
    log(f"例句导入完成: 共更新 {updated} 个单词")
    return updated


def _flush_examples(engine, batch):
    """用 JSON_SET 更新 detail_json.example"""
    for word_id, example_json_str in batch:
        sql = (
            f"UPDATE dict_word SET "
            f"detail_json = CASE "
            f"  WHEN detail_json IS NULL THEN JSON_OBJECT('example', {example_json_str}) "
            f"  ELSE JSON_SET(detail_json, '$.example', {example_json_str}) "
            f"END "
            f"WHERE id = {word_id};"
        )
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(sql)
                conn.commit()
        except Exception as e:
            log(f"更新例句 word_id={word_id} 失败: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="导入巧记增强数据(金句/例句/近义词)")
    parser.add_argument("--skip-mnemonics", action="store_true", help="跳过记忆金句导入")
    parser.add_argument("--skip-synonyms", action="store_true", help="跳过近义词导入")
    parser.add_argument("--skip-examples", action="store_true", help="跳过例句导入")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)

    log("=== 导入巧记增强数据 ===")

    if not args.skip_mnemonics:
        step1_import_mnemonics(engine)
    else:
        log("跳过记忆金句导入 (--skip-mnemonics)")

    if not args.skip_synonyms:
        step2_import_synonyms(engine)
    else:
        log("跳过近义词导入 (--skip-synonyms)")

    if not args.skip_examples:
        step3_import_examples(engine)
    else:
        log("跳过例句导入 (--skip-examples)")

    engine.dispose()
    log("全部完成!")


if __name__ == "__main__":
    main()
