-- =============================================================================
-- Phase 7 — 协作能力增强 数据库迁移
-- 表: audit_log (操作审计日志), school_admin (学校管理员)
-- =============================================================================

-- 1. 操作审计日志表
CREATE TABLE IF NOT EXISTS `audit_log` (
    `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    `class_id` INT UNSIGNED DEFAULT NULL COMMENT '关联班级ID（可为空）',
    `operator_id` INT UNSIGNED NOT NULL COMMENT '操作人用户ID',
    `operator_role` VARCHAR(20) NOT NULL DEFAULT 'teacher' COMMENT '操作人角色: teacher/assistant/admin/system',
    `action_type` VARCHAR(50) NOT NULL COMMENT '操作类型: exam_grade/exam_review/student_remove/assistant_add/assistant_remove/class_update/exam_publish/report_view 等',
    `target_type` VARCHAR(50) DEFAULT NULL COMMENT '操作对象类型: exam/submission/student/assistant/class',
    `target_id` INT UNSIGNED DEFAULT NULL COMMENT '操作对象ID',
    `detail` JSON DEFAULT NULL COMMENT '操作详情（JSON格式，记录操作前后变化）',
    `ip_address` VARCHAR(45) DEFAULT NULL COMMENT '操作人IP地址',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    INDEX `idx_class_id` (`class_id`),
    INDEX `idx_operator_id` (`operator_id`),
    INDEX `idx_action_type` (`action_type`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作审计日志表 — 记录所有批改/管理操作';

-- 2. 学校管理员表
CREATE TABLE IF NOT EXISTS `school_admin` (
    `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    `user_id` INT UNSIGNED NOT NULL COMMENT '管理员用户ID',
    `school_name` VARCHAR(200) NOT NULL COMMENT '学校名称',
    `contact_phone` VARCHAR(20) DEFAULT NULL COMMENT '联系电话',
    `permissions` JSON DEFAULT NULL COMMENT '权限配置JSON: {view_all_classes: true, export_reports: true, manage_teachers: false}',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY `uk_user_id` (`user_id`),
    INDEX `idx_school_name` (`school_name`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学校管理员表 — 教育局/学校级别的数据管理';

-- 3. learning_report 表（学生学习报告缓存）
CREATE TABLE IF NOT EXISTS `learning_report` (
    `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    `user_id` INT UNSIGNED NOT NULL COMMENT '学生用户ID',
    `class_id` INT UNSIGNED DEFAULT NULL COMMENT '所属班级ID',
    `report_type` VARCHAR(20) NOT NULL DEFAULT 'personal' COMMENT '报告类型: personal/class/semester',
    `period_start` DATE NOT NULL COMMENT '统计开始日期',
    `period_end` DATE NOT NULL COMMENT '统计结束日期',
    `report_data` JSON NOT NULL COMMENT '报告数据JSON（各模块正确率/薄弱点/趋势/建议等）',
    `generated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
    INDEX `idx_user_class` (`user_id`, `class_id`),
    INDEX `idx_report_type` (`report_type`),
    INDEX `idx_generated_at` (`generated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习报告缓存表 — 个人/班级/学期报告';
