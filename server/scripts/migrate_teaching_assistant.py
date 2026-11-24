# 教学助手数据库迁移脚本
# 使用 SQLAlchemy 执行增量迁移，兼容低版本 MySQL
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.SYNC_DATABASE_URL)

def column_exists(conn, table, column):
    """检查 MySQL 表中是否存在指定列"""
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
    ), {"db": settings.MYSQL_DATABASE, "tbl": table, "col": column})
    return result.scalar() > 0

def add_column(conn, table, col_def):
    """安全添加列（仅当不存在时）"""
    col_name = col_def.split()[0]
    if column_exists(conn, table, col_name):
        print(f"  [SKIP] {table}: {col_name} 已存在")
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
    print(f"  [OK] {table}: ADD {col_name}")

with engine.connect() as conn:
    print("[INFO] 开始教学助手数据库迁移...")

    # 1. chat_conversation 扩展字段
    # 注意: MySQL 严格模式下 TEXT/BLOB/JSON 列不能有 DEFAULT 值
    add_column(conn, "chat_conversation", "summary TEXT COMMENT '对话摘要(LLM自动生成)'")
    add_column(conn, "chat_conversation", "class_id BIGINT DEFAULT NULL COMMENT '关联班级ID'")
    add_column(conn, "chat_conversation", "status SMALLINT DEFAULT 1 COMMENT '1=活跃 0=已归档'")
    add_column(conn, "chat_conversation", "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

    # 2. teacher_memory 表（仅创建不存在的列）
    # 先检查表是否存在
    tbl_exists = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'teacher_memory'"
    ), {"db": settings.MYSQL_DATABASE}).scalar() > 0

    if not tbl_exists:
        create_sql = """
        CREATE TABLE teacher_memory (
            id BIGINT NOT NULL PRIMARY KEY,
            teacher_id BIGINT NOT NULL COMMENT '教师ID',
            memory_type VARCHAR(32) NOT NULL COMMENT 'preference/topic_summary/class_note/teaching_style',
            memory_key VARCHAR(128) NOT NULL COMMENT '记忆键',
            memory_value TEXT NOT NULL COMMENT '记忆值',
            importance FLOAT DEFAULT 0.5 COMMENT '重要性 0-1',
            trigger_keywords JSON COMMENT '触发关键词列表',
            access_count INT DEFAULT 0 COMMENT '被引用次数',
            last_accessed_at DATETIME DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_tm_teacher_type (teacher_id, memory_type),
            INDEX idx_tm_teacher_key (teacher_id, memory_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教师长期记忆表'
        """
        conn.execute(text(create_sql))
        print("  [OK] teacher_memory 表创建成功")
    else:
        print("  [SKIP] teacher_memory 表已存在")

    conn.commit()
    print("[SUCCESS] 教学助手数据库迁移完成！")
