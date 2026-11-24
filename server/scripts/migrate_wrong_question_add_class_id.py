"""为 wrong_question 表添加 class_id 列（ORM模型已定义，但数据库表缺失）"""
import pymysql

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings

settings = get_settings()
conn = pymysql.connect(
    **settings.mysql_connection_kwargs(), database=settings.MYSQL_DATABASE, charset='utf8mb4'
)
cur = conn.cursor()

sql = "ALTER TABLE wrong_question ADD COLUMN class_id BIGINT DEFAULT NULL COMMENT '所属班级ID，null=全局错题'"
try:
    cur.execute(sql)
    conn.commit()
    print("SUCCESS: class_id 列已添加到 wrong_question 表")
except pymysql.err.OperationalError as e:
    if "Duplicate column name" in str(e):
        print("SKIP: class_id 列已存在，无需重复添加")
    else:
        print(f"ERROR: {e}")

# 验证
cur.execute("SHOW COLUMNS FROM wrong_question")
cols = [r[0] for r in cur.fetchall()]
print(f"当前列: {cols}")

conn.close()
