-- ============================================================
-- Phase 1 数据库迁移：User 表扩展 + 班级表 + 错题扩展
-- 执行前请备份数据库！
-- 用法: mysql -u root -p elearningtest < phase1_schema_upgrade.sql
-- ============================================================

-- ========== D1.1: User 表扩展 (role / membership) ==========

-- 添加角色字段
ALTER TABLE `user`
  ADD COLUMN `role` VARCHAR(16) NOT NULL DEFAULT 'student'
    COMMENT '角色: student/teacher/personal/admin' AFTER `nickname`;

-- 添加会员字段
ALTER TABLE `user`
  ADD COLUMN `membership` VARCHAR(32) NOT NULL DEFAULT 'free'
    COMMENT '会员等级: free/basic/premium/pro' AFTER `role`,
  ADD COLUMN `membership_expire` DATETIME DEFAULT NULL
    COMMENT '会员到期时间' AFTER `membership`;

-- ========== D1.2: 班级相关表 ==========

-- 班级表
DROP TABLE IF EXISTS `class`;
CREATE TABLE `class` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(128) NOT NULL COMMENT '班级名称',
  `description` VARCHAR(512) DEFAULT '' COMMENT '班级描述',
  `invite_code` VARCHAR(32) NOT NULL UNIQUE COMMENT '邀请码',
  `created_by` BIGINT NOT NULL COMMENT '创建者教师ID(user.id)',
  `stage` TINYINT DEFAULT 0 COMMENT '默认学习阶段',
  `student_count` INT DEFAULT 0 COMMENT '学生人数(冗余)',
  `is_active` TINYINT DEFAULT 1 COMMENT '是否启用 0/1',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY `idx_created_by` (`created_by`),
  KEY `idx_stage` (`stage`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='班级表';

-- 班级-学生关联表
DROP TABLE IF EXISTS `class_student`;
CREATE TABLE `class_student` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `class_id` BIGINT NOT NULL COMMENT '班级ID',
  `student_id` BIGINT NOT NULL COMMENT '学生ID(user.id)',
  `joined_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '加入时间',
  UNIQUE KEY `uk_class_student` (`class_id`, `student_id`),
  KEY `idx_student` (`student_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='班级-学生关联表';

-- 班级-教师关联表（支持多教师）
DROP TABLE IF EXISTS `class_teacher`;
CREATE TABLE `class_teacher` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `class_id` BIGINT NOT NULL COMMENT '班级ID',
  `teacher_id` BIGINT NOT NULL COMMENT '教师ID(user.id)',
  `role` VARCHAR(16) NOT NULL DEFAULT 'teacher' COMMENT '角色: teacher/assistant',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_class_teacher` (`class_id`, `teacher_id`),
  KEY `idx_teacher` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='班级-教师关联表';

-- ========== D1.3: 错题表扩展 ==========

-- 添加分类和知识点字段
ALTER TABLE `wrong_question`
  ADD COLUMN `category` VARCHAR(64) DEFAULT ''
    COMMENT '错题分类: vocabulary/grammar/reading/listening/translation' AFTER `question_type`,
  ADD COLUMN `knowledge_point` VARCHAR(256) DEFAULT ''
    COMMENT '涉及知识点标签，逗号分隔' AFTER `category`,
  ADD COLUMN `related_word_id` INT DEFAULT NULL
    COMMENT '关联单词ID(dict_word.id)' AFTER `knowledge_point`;
