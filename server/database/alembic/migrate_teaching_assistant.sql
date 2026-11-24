-- ============================================================
-- 增量迁移：教学助手 Agent 数据库变更
-- 执行前请确保已备份数据库！
-- 用法: mysql -u root -p elearningtest < migrate_teaching_assistant.sql
-- ============================================================

-- 1. chat_conversation 扩展字段
ALTER TABLE chat_conversation 
    ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT '' COMMENT '对话摘要（LLM自动生成）',
    ADD COLUMN IF NOT EXISTS class_id BIGINT DEFAULT NULL COMMENT '关联班级ID',
    ADD COLUMN IF NOT EXISTS status SMALLINT DEFAULT 1 COMMENT '1=活跃 0=已归档',
    ADD COLUMN IF NOT EXISTS updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- 2. teacher_memory 表
CREATE TABLE IF NOT EXISTS teacher_memory (
    id BIGINT NOT NULL PRIMARY KEY,
    teacher_id BIGINT NOT NULL COMMENT '教师ID',
    memory_type VARCHAR(32) NOT NULL COMMENT 'preference/topic_summary/class_note/teaching_style',
    memory_key VARCHAR(128) NOT NULL COMMENT '记忆键',
    memory_value TEXT NOT NULL COMMENT '记忆值',
    importance FLOAT DEFAULT 0.5 COMMENT '重要性 0-1',
    trigger_keywords JSON DEFAULT NULL COMMENT '触发关键词列表',
    access_count INT DEFAULT 0 COMMENT '被引用次数',
    last_accessed_at DATETIME DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tm_teacher_type (teacher_id, memory_type),
    INDEX idx_tm_teacher_key (teacher_id, memory_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教师长期记忆表';
