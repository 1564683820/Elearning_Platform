-- Phase 2 数据库迁移：试卷模块
-- 包含 teacher_exam / exam_submission / exam_grading_log 三张表

-- D2.1: 试卷主表
CREATE TABLE IF NOT EXISTS `teacher_exam` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `teacher_id` BIGINT NOT NULL COMMENT '创建教师ID',
    `class_id` BIGINT NOT NULL COMMENT '目标班级ID',
    `title` VARCHAR(256) NOT NULL COMMENT '试卷标题',
    `description` VARCHAR(512) DEFAULT '' COMMENT '试卷描述',
    `questions` JSON NOT NULL COMMENT '题目列表 JSON',
    `total_score` INT DEFAULT 100 COMMENT '总分',
    `difficulty` SMALLINT DEFAULT 1 COMMENT '难度: 1=简单,2=中等,3=困难',
    `duration_minutes` INT DEFAULT 60 COMMENT '建议用时(分钟)',
    `status` VARCHAR(16) DEFAULT 'draft' COMMENT '状态: draft/published/grading/done/archived',
    `published_at` DATETIME DEFAULT NULL COMMENT '发布时间',
    `done_at` DATETIME DEFAULT NULL COMMENT '批改完成时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_exam_teacher` (`teacher_id`),
    INDEX `idx_exam_class` (`class_id`),
    INDEX `idx_exam_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='试卷主表';

-- D2.2: 学生提交表
CREATE TABLE IF NOT EXISTS `exam_submission` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `exam_id` BIGINT NOT NULL COMMENT '试卷ID',
    `student_id` BIGINT NOT NULL COMMENT '学生ID',
    `answers` JSON NOT NULL COMMENT '学生答案 JSON',
    `score` INT DEFAULT NULL COMMENT 'AI 评分总得分',
    `max_score` INT DEFAULT NULL COMMENT '满分',
    `ai_grade_detail` JSON DEFAULT NULL COMMENT 'AI 逐题评分详情',
    `teacher_adjustment` JSON DEFAULT NULL COMMENT '教师调整记录',
    `adjusted_score` INT DEFAULT NULL COMMENT '教师调整后分数',
    `started_at` DATETIME DEFAULT NULL COMMENT '开始作答时间',
    `submitted_at` DATETIME DEFAULT NULL COMMENT '提交时间',
    `duration_seconds` INT DEFAULT 0 COMMENT '作答用时(秒)',
    `grading_status` VARCHAR(16) DEFAULT 'pending' COMMENT '批改状态: pending/ai_done/teacher_reviewed',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_exam_student` (`exam_id`, `student_id`),
    INDEX `idx_sub_exam` (`exam_id`),
    INDEX `idx_sub_student` (`student_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学生提交表';

-- D2.3: 批改日志表
CREATE TABLE IF NOT EXISTS `exam_grading_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `submission_id` BIGINT NOT NULL COMMENT '提交记录ID',
    `grader_type` VARCHAR(16) NOT NULL COMMENT '批改者类型: ai/teacher/assistant',
    `grader_id` BIGINT DEFAULT 0 COMMENT '批改者用户ID(教师/助教)',
    `action` VARCHAR(32) NOT NULL COMMENT '操作: auto_grade/teacher_review/teacher_adjust',
    `detail` JSON DEFAULT NULL COMMENT '操作详情 JSON',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_log_submission` (`submission_id`),
    INDEX `idx_log_grader` (`grader_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='批改日志表';

-- D2.4: 已有表索引补充
ALTER TABLE `class` ADD INDEX IF NOT EXISTS `idx_class_invite` (`invite_code`);
ALTER TABLE `class_teacher` ADD INDEX IF NOT EXISTS `idx_ct_teacher_role` (`teacher_id`, `role`);

-- D2.5: 答题卡模板表
CREATE TABLE IF NOT EXISTS `answer_sheet_template` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `teacher_id` BIGINT NOT NULL COMMENT '创建教师ID',
    `name` VARCHAR(128) NOT NULL COMMENT '模板名称',
    `grade` VARCHAR(16) DEFAULT '' COMMENT '适用年级',
    `description` VARCHAR(512) DEFAULT '' COMMENT '模板描述',
    `choice_questions` JSON NOT NULL COMMENT '选择题配置JSON（SKILL.md格式）',
    `question_count` INT DEFAULT 0 COMMENT '总题数',
    `total_score` INT DEFAULT 0 COMMENT '总分',
    `is_default` SMALLINT DEFAULT 0 COMMENT '是否默认模板: 0=否,1=是',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_as_template_teacher` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='答题卡模板表';
