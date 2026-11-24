-- ============================================
-- 扫描批卷功能 - 数据库迁移脚本
-- 运行: mysql -h <host> -u <user> -p <database> < migrate_scan_tables.sql
-- ============================================

-- 1. 新增错题本表
CREATE TABLE IF NOT EXISTS wrong_question_book (
    id              BIGINT NOT NULL PRIMARY KEY COMMENT '雪花ID',
    student_id      BIGINT NOT NULL COMMENT '学生用户ID',
    class_id        BIGINT NOT NULL COMMENT '班级ID',
    exam_id         BIGINT NOT NULL COMMENT '试卷ID',
    submission_id   BIGINT NOT NULL COMMENT '提交记录ID',
    question_index  INT NOT NULL COMMENT '题目序号（从1开始）',
    question_type   VARCHAR(32) DEFAULT '' COMMENT '题型: single/multiple/fill/reading等',
    question_stem   TEXT COMMENT '题干',
    correct_answer  VARCHAR(512) DEFAULT '' COMMENT '正确答案',
    student_answer  VARCHAR(512) DEFAULT '' COMMENT '学生填涂的答案',
    knowledge_point VARCHAR(256) DEFAULT '' COMMENT '知识点标签',
    score           INT DEFAULT 0 COMMENT '本题得分',
    max_score       INT DEFAULT 0 COMMENT '本题满分',
    error_category  VARCHAR(32) DEFAULT '' COMMENT '错误分类: knowledge_gap/careless/misunderstanding/other',
    ai_comment      TEXT COMMENT 'AI批改评语',
    rag_indexed     SMALLINT DEFAULT 0 COMMENT '是否已RAG入库: 0=否,1=是',
    rag_chunk_id    VARCHAR(64) DEFAULT '' COMMENT 'RAG知识库中的chunk_id',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_wq_student (student_id),
    INDEX idx_wq_class (class_id),
    INDEX idx_wq_exam (exam_id),
    INDEX idx_wq_knowledge (knowledge_point),
    INDEX idx_wq_rag (rag_indexed),
    UNIQUE KEY uk_wq_sub_qidx (submission_id, question_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='错题本：每道错题一条记录，供RAG教学助手检索';

-- 2. 新增扫描批卷记录表
CREATE TABLE IF NOT EXISTS exam_scan_record (
    id              BIGINT NOT NULL PRIMARY KEY COMMENT '雪花ID',
    exam_id         BIGINT NOT NULL COMMENT '试卷ID',
    teacher_id      BIGINT NOT NULL COMMENT '操作教师ID',
    scan_image_url  VARCHAR(512) DEFAULT '' COMMENT '上传的答题卡图片URL',
    recognized_count INT DEFAULT 0 COMMENT '识别到的答题数',
    matched_student_id BIGINT DEFAULT 0 COMMENT '匹配到的学生ID（考号匹配）',
    exam_number     VARCHAR(64) DEFAULT '' COMMENT '识别到的考号',
    raw_answers     JSON COMMENT 'OMR识别的原始答案 [{question_number, student_answer, confidence}]',
    grading_result  JSON COMMENT '批改结果摘要',
    scan_duration_ms INT DEFAULT 0 COMMENT '扫描处理耗时(毫秒)',
    error_message   TEXT COMMENT '错误信息（如有）',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_esr_exam (exam_id),
    INDEX idx_esr_teacher (teacher_id),
    INDEX idx_esr_student (matched_student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='扫描批卷记录表';

-- 3. exam_submission 表追加字段
ALTER TABLE exam_submission
    ADD COLUMN IF NOT EXISTS scan_image_url VARCHAR(512) DEFAULT '' COMMENT '扫描答题卡图片URL（OMR批卷来源）' AFTER grading_status,
    ADD COLUMN IF NOT EXISTS scan_record_id BIGINT DEFAULT 0 COMMENT '关联的扫描记录ID' AFTER scan_image_url,
    ADD COLUMN IF NOT EXISTS wrong_count INT DEFAULT 0 COMMENT '错题数量' AFTER scan_record_id;
