-- ============================================
-- Phase 4 — 教材点读 数据库迁移
-- ============================================

-- 教材单元表
CREATE TABLE IF NOT EXISTS `textbook_unit` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `textbook_version` VARCHAR(64) NOT NULL COMMENT '教材版本 e.g. PEP',
  `grade` VARCHAR(16) NOT NULL COMMENT '年级 e.g. 3,4,5,6',
  `semester` VARCHAR(8) DEFAULT '上' COMMENT '学期: 上/下',
  `unit_number` VARCHAR(16) NOT NULL COMMENT '单元号 e.g. Unit1, Recycle1',
  `title` VARCHAR(128) DEFAULT '' COMMENT '单元标题',
  `sub_title` VARCHAR(128) DEFAULT '' COMMENT '副标题',
  `cover_image` VARCHAR(512) DEFAULT '' COMMENT '单元封面图 URL',
  `page_start` INT DEFAULT 1 COMMENT '起始页码',
  `page_end` INT DEFAULT 1 COMMENT '结束页码',
  `sort_order` INT DEFAULT 0 COMMENT '排序',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_textbook_unit` (`textbook_version`, `grade`, `semester`, `unit_number`),
  KEY `idx_version_grade` (`textbook_version`, `grade`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教材单元表';

-- 教材页面表
CREATE TABLE IF NOT EXISTS `textbook_page` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `unit_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '关联单元ID(textbook_unit.id)',
  `textbook_version` VARCHAR(64) NOT NULL COMMENT '教材版本 e.g. PEP',
  `grade` VARCHAR(16) NOT NULL COMMENT '年级',
  `semester` VARCHAR(8) DEFAULT '上' COMMENT '学期',
  `unit_number` VARCHAR(16) NOT NULL COMMENT '单元号',
  `page_number` INT NOT NULL COMMENT '页码',
  `text_content` TEXT NOT NULL COMMENT '课文文字全文',
  `sentences_json` JSON DEFAULT NULL COMMENT '分句 [{en,cn,start_sec,end_sec}]',
  `image_url` VARCHAR(512) DEFAULT '' COMMENT '静态插图 URL',
  `image_thumbnail` VARCHAR(512) DEFAULT '' COMMENT '缩略图 URL',
  `animation_url` VARCHAR(512) DEFAULT '' COMMENT '微动图 URL(Lottie/GIF)',
  `audio_url` VARCHAR(512) DEFAULT '' COMMENT '课文朗读音频 URL',
  `audio_duration` INT DEFAULT 0 COMMENT '音频时长(秒)',
  `words_json` JSON DEFAULT NULL COMMENT '页面单词列表 [{word,phonetic,translation,audio_url}]',
  `exercises_json` JSON DEFAULT NULL COMMENT '页面练习题(optional)',
  `is_active` TINYINT DEFAULT 1 COMMENT '是否启用 0/1',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_textbook_page` (`textbook_version`, `grade`, `semester`, `unit_number`, `page_number`),
  KEY `idx_unit` (`unit_id`),
  KEY `idx_version_grade` (`textbook_version`, `grade`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='教材页面表';
