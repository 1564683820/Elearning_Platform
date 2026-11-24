# -*- coding: utf-8 -*-
"""运行 exam_submission 表扩展字段的 ALTER TABLE"""
import pymysql
import warnings
warnings.filterwarnings('ignore')

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings

settings = get_settings()
conn = pymysql.connect(**settings.mysql_connection_kwargs(), database=settings.MYSQL_DATABASE)
cur = conn.cursor()

for col, col_def in [
    ('scan_image_url', 'VARCHAR(512) DEFAULT "" COMMENT "扫描答题卡图片URL（OMR批卷来源）"'),
    ('scan_record_id', 'BIGINT DEFAULT 0 COMMENT "关联的扫描记录ID"'),
    ('wrong_count', 'INT DEFAULT 0 COMMENT "错题数量"'),
]:
    cur.execute("SHOW COLUMNS FROM exam_submission LIKE %s", (col,))
    if not cur.fetchone():
        cur.execute(f"ALTER TABLE exam_submission ADD COLUMN `{col}` {col_def} AFTER grading_status")
        print(f"[OK] 添加 {col} 字段")
    else:
        print(f"[OK] {col} 字段已存在")

conn.commit()
cur.close()
conn.close()
print("exam_submission 扩展字段迁移完成!")
