-- ============================================
-- Phase 5.1: HTML 幻灯片渲染引擎 — 数据库扩展
-- 扩展 lesson_ppt + 新建 ppt_theme / ppt_version
-- ============================================

-- ----------------------------
-- 1. lesson_ppt 表扩展：新增 HTML / 主题 / 版本 / 缩略图字段
-- 通过 INFORMATION_SCHEMA 检查列是否存在，兼容 MySQL 5.7+
-- ----------------------------
DROP PROCEDURE IF EXISTS `sp_add_col_if_not_exists`;
DELIMITER ;;
CREATE PROCEDURE `sp_add_col_if_not_exists`()
BEGIN
  DECLARE db_name VARCHAR(64);
  SET db_name = DATABASE();

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='html_content') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `html_content` MEDIUMTEXT COMMENT 'HTML格式完整幻灯片' AFTER `pages_json`;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='theme_name') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `theme_name` VARCHAR(64) DEFAULT 'classic' COMMENT '当前主题名' AFTER `html_content`;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='version') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `version` INT DEFAULT 1 COMMENT '版本号' AFTER `theme_name`;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='thumbnail_url') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `thumbnail_url` VARCHAR(512) DEFAULT '' COMMENT '缩略图URL' AFTER `version`;
  END IF;
END;;
DELIMITER ;
CALL `sp_add_col_if_not_exists`();
DROP PROCEDURE IF EXISTS `sp_add_col_if_not_exists`;

-- ----------------------------
-- 2. ppt_theme — 幻灯片主题表
-- ----------------------------
CREATE TABLE IF NOT EXISTS `ppt_theme` (
  `id`           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `name`         VARCHAR(64) NOT NULL COMMENT '主题标识名（如 classic, cartoon, academic）',
  `display_name` VARCHAR(128) NOT NULL COMMENT '主题显示名（如 经典简约, 小学卡通）',
  `description`  VARCHAR(256) DEFAULT '' COMMENT '主题描述',
  `css_variables` TEXT NOT NULL COMMENT 'CSS 变量定义（:root { ... } 内的变量）',
  `css_content`  MEDIUMTEXT NOT NULL COMMENT '完整主题 CSS 内容',
  `preview_color` VARCHAR(32) DEFAULT '#2d7d46' COMMENT '预览色（列表/选择器用）',
  `preview_url`  VARCHAR(512) DEFAULT '' COMMENT '预览截图URL',
  `sort_order`   INT DEFAULT 0 COMMENT '排序号',
  `is_builtin`   TINYINT DEFAULT 1 COMMENT '是否为内置主题',
  `teacher_id`   BIGINT UNSIGNED DEFAULT NULL COMMENT '自定义主题的创建教师ID',
  `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX `idx_theme_name` (`name`),
  INDEX `idx_theme_builtin` (`is_builtin`),
  INDEX `idx_theme_teacher` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='幻灯片主题表';

-- ----------------------------
-- 3. ppt_version — 幻灯片版本历史表
-- ----------------------------
CREATE TABLE IF NOT EXISTS `ppt_version` (
  `id`            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `ppt_id`        BIGINT UNSIGNED NOT NULL COMMENT '关联的 PPT ID',
  `version`       INT NOT NULL COMMENT '版本号',
  `html_content`  MEDIUMTEXT NOT NULL COMMENT '该版本的 HTML 完整内容',
  `pages_json`    JSON DEFAULT NULL COMMENT '该版本的 JSON 页面数据（回滚用）',
  `theme_name`    VARCHAR(64) DEFAULT '' COMMENT '该版本使用的主题',
  `change_summary` VARCHAR(512) DEFAULT '' COMMENT '变更摘要',
  `created_at`    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  INDEX `idx_v_ppt` (`ppt_id`),
  INDEX `idx_v_ppt_version` (`ppt_id`, `version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='幻灯片版本历史表';
