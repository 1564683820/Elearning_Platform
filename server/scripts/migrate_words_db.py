"""
迁移单词相关表从 elearningtest 到 elearnword

迁移的表:
  - dict_word, dict_root, dict_word_root
  - stage_word, word_synonyms
  - user_word_progress

保留在主线库:
  - favorite（跨域，保留在 elearningtest）
"""
import pymysql

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings

settings = get_settings()
SRC = dict(settings.mysql_connection_kwargs(), database=settings.MYSQL_DATABASE, charset="utf8mb4")
DST = dict(settings.mysql_connection_kwargs(), database=settings.WORDS_DATABASE, charset="utf8mb4")

TABLES = [
    "dict_word",
    "dict_root",
    "dict_word_root",
    "stage_word",
    "word_synonyms",
    "user_word_progress",
]


def main():
    src = pymysql.connect(**SRC)
    dst = pymysql.connect(**DST)
    sc = src.cursor()
    dc = dst.cursor()

    for table in TABLES:
        print(f"\n=== {table} ===")

        # 1. 获取源表建表 DDL
        sc.execute(f"SHOW CREATE TABLE {table}")
        row = sc.fetchone()
        if not row:
            print(f"  [SKIP] 源库中不存在表 {table}")
            continue
        ddl = row[1]

        # 2. 在目标库建表（先删再建，保证干净）
        dc.execute(f"DROP TABLE IF EXISTS {table}")
        dc.execute(ddl)
        dst.commit()
        print(f"  [OK] 建表完成")

        # 3. 获取源表数据量
        sc.execute(f"SELECT COUNT(*) FROM {table}")
        count = sc.fetchone()[0]
        print(f"  [INFO] 源表记录数: {count}")

        if count == 0:
            continue

        # 4. 获取列名
        sc.execute(f"SELECT * FROM {table} LIMIT 0")
        columns = [desc[0] for desc in sc.description]
        col_names = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        # 5. 分页复制（避免大表内存问题）
        batch_size = 5000
        offset = 0
        total_copied = 0

        while offset < count:
            sc.execute(f"SELECT * FROM {table} LIMIT {batch_size} OFFSET {offset}")
            rows = sc.fetchall()
            if not rows:
                break

            args = []
            for row_data in rows:
                # datetime/timestamp 类型需要保留原始值
                processed = []
                for val in row_data:
                    if hasattr(val, "strftime"):
                        processed.append(val.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        processed.append(val)
                args.append(tuple(processed))

            dc.executemany(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", args)
            dst.commit()

            total_copied += len(rows)
            offset += batch_size
            print(f"  [COPY] 已复制 {total_copied}/{count} 条")

        print(f"  [DONE] 完成，共复制 {total_copied} 条记录")

    sc.close()
    dc.close()
    src.close()
    dst.close()
    print("\n✅ 迁移完成！")


if __name__ == "__main__":
    main()
