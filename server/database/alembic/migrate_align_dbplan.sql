-- ============================================================
-- MySQL 迁移脚本：对齐 DBplan 全部表
-- 执行前请备份数据库！
-- 用法: mysql -u root -p elearningtest < migrate_align_dbplan.sql
-- ============================================================

-- 1. 用户表：users → user，字段对齐
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `openid` VARCHAR(64) NOT NULL,
  `union_id` VARCHAR(64) DEFAULT NULL,
  `nickname` VARCHAR(64) DEFAULT '',
  `avatar_url` VARCHAR(512) DEFAULT '',
  `stage` TINYINT NOT NULL DEFAULT 1 COMMENT '1=启蒙,2=小三,...,10=雅思',
  `api_key_encrypted` VARCHAR(256) DEFAULT NULL,
  `api_key_iv` VARCHAR(64) DEFAULT NULL,
  `api_base_url` VARCHAR(256) DEFAULT 'https://api.openai.com/v1',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_openid` (`openid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 2. 词典主表：words → dict_word，补全 ECDICT 字段
DROP TABLE IF EXISTS `dict_word`;
CREATE TABLE `dict_word` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `word` VARCHAR(128) NOT NULL,
  `sw` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '模糊匹配键',
  `phonetic` VARCHAR(128) DEFAULT '',
  `definition` TEXT,
  `translation` TEXT,
  `pos` VARCHAR(128) DEFAULT '',
  `collins` TINYINT DEFAULT 0 COMMENT '柯林斯星级1-5',
  `oxford` TINYINT DEFAULT 0 COMMENT '牛津三千0/1',
  `tag` VARCHAR(256) DEFAULT '' COMMENT '考试标签 cet4 zk gk',
  `bnc` INT DEFAULT 0 COMMENT 'BNC词频排名',
  `frq` INT DEFAULT 0 COMMENT '当代语料库排名',
  `exchange` VARCHAR(256) DEFAULT '' COMMENT '词形变化',
  `audio_url` VARCHAR(512) DEFAULT '',
  `detail_json` JSON DEFAULT NULL COMMENT '扩展信息',
  UNIQUE KEY `uk_word` (`word`),
  KEY `idx_sw` (`sw`),
  KEY `idx_tag` (`tag`(64)),
  KEY `idx_collins` (`collins`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='词典主表(ECDICT)';

-- 3. 词根表
DROP TABLE IF EXISTS `dict_root`;
CREATE TABLE `dict_root` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `root` VARCHAR(64) NOT NULL,
  `root_type` VARCHAR(16) NOT NULL COMMENT 'prefix/root/suffix',
  `meaning` VARCHAR(256) DEFAULT '',
  `origin` VARCHAR(64) DEFAULT '',
  KEY `idx_root` (`root`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='词根词缀表';

-- 4. 单词-词根关联表
DROP TABLE IF EXISTS `dict_word_root`;
CREATE TABLE `dict_word_root` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `word_id` INT UNSIGNED NOT NULL,
  `root_id` INT UNSIGNED NOT NULL,
  `position` TINYINT DEFAULT 0,
  KEY `idx_word_id` (`word_id`),
  KEY `idx_root_id` (`root_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='单词-词根关联表';

-- 5. 阶段-单词映射表
DROP TABLE IF EXISTS `stage_word`;
CREATE TABLE `stage_word` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `word_id` INT UNSIGNED NOT NULL,
  `stage` TINYINT NOT NULL COMMENT '1-10',
  `mastery_order` INT DEFAULT 0,
  UNIQUE KEY `uk_word_stage` (`word_id`, `stage`),
  KEY `idx_stage_order` (`stage`, `mastery_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='阶段-单词映射表';

-- 6. 近义词表
DROP TABLE IF EXISTS `word_synonyms`;
CREATE TABLE `word_synonyms` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `word_id` BIGINT NOT NULL,
  `synonym_word` VARCHAR(128) NOT NULL,
  `tag` VARCHAR(64) DEFAULT '',
  `usage_desc` TEXT,
  `example` TEXT,
  KEY `idx_word_id` (`word_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='近义词辨析表';

-- 7. 收藏表
DROP TABLE IF EXISTS `favorite`;
CREATE TABLE `favorite` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `target_type` TINYINT NOT NULL COMMENT '1=单词,2=文章,3=情景文段,4=歌曲',
  `target_id` BIGINT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_user_target` (`user_id`, `target_type`, `target_id`),
  KEY `idx_user_type` (`user_id`, `target_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='收藏表';

-- 8. 用户单词进度
DROP TABLE IF EXISTS `user_word_progress`;
CREATE TABLE `user_word_progress` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `word_id` INT NOT NULL,
  `mastery_level` TINYINT DEFAULT 0 COMMENT '0未学/1认识/2熟悉/3掌握',
  `review_count` INT DEFAULT 0,
  `last_reviewed_at` DATETIME DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_user_word` (`user_id`, `word_id`),
  KEY `idx_user_mastery` (`user_id`, `mastery_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户单词学习进度';

-- 9. 题库表
DROP TABLE IF EXISTS `question_bank`;
CREATE TABLE `question_bank` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `stage` TINYINT NOT NULL COMMENT '1-10',
  `type` TINYINT NOT NULL COMMENT '1选择填空2选择翻译3听力选择4短语语法5句子翻译6阅读理解7听力训练',
  `difficulty` TINYINT DEFAULT 1,
  `content` JSON NOT NULL,
  `source` VARCHAR(128) DEFAULT '',
  `audio_url` VARCHAR(512) DEFAULT '',
  `reading_id` BIGINT UNSIGNED DEFAULT NULL,
  `word_id` INT UNSIGNED DEFAULT NULL,
  `is_active` TINYINT DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_stage_type` (`stage`, `type`),
  KEY `idx_word_id` (`word_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题库表';

-- 10. 阅读材料
DROP TABLE IF EXISTS `reading_material`;
CREATE TABLE `reading_material` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `stage` TINYINT NOT NULL,
  `title` VARCHAR(256) NOT NULL,
  `content` TEXT NOT NULL,
  `content_cn` TEXT,
  `type` VARCHAR(16) DEFAULT 'article' COMMENT 'article/story/news',
  `source` VARCHAR(256) DEFAULT '',
  `word_count` INT DEFAULT 0,
  `difficulty` TINYINT DEFAULT 1,
  `audio_url` VARCHAR(512) DEFAULT '',
  KEY `idx_stage_type` (`stage`, `type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='阅读材料表';

-- 11. 听力材料
DROP TABLE IF EXISTS `listening_material`;
CREATE TABLE `listening_material` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `stage` TINYINT NOT NULL,
  `title` VARCHAR(256) NOT NULL,
  `audio_url` VARCHAR(512) NOT NULL,
  `transcript` TEXT,
  `transcript_cn` TEXT,
  `duration` INT DEFAULT 0,
  `type` VARCHAR(16) DEFAULT 'article',
  `source` VARCHAR(128) DEFAULT '',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_stage_type` (`stage`, `type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='听力材料表';

-- 12. 学习记录
DROP TABLE IF EXISTS `study_record`;
CREATE TABLE `study_record` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `word_id` INT NOT NULL,
  `action` TINYINT NOT NULL COMMENT '1浏览2收藏3取消收藏4发音播放',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user_word` (`user_id`, `word_id`),
  KEY `idx_user_created` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学习记录表';

-- 13. 训练会话
DROP TABLE IF EXISTS `training_session`;
CREATE TABLE `training_session` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `type` TINYINT NOT NULL,
  `total_count` INT NOT NULL,
  `correct_count` INT DEFAULT 0,
  `duration_sec` INT DEFAULT 0,
  `finished_at` DATETIME DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user_created` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='训练会话表';

-- 14. 答题记录
DROP TABLE IF EXISTS `user_quiz_log`;
CREATE TABLE `user_quiz_log` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `session_id` BIGINT DEFAULT NULL,
  `question_id` BIGINT NOT NULL,
  `question_type` TINYINT NOT NULL,
  `is_correct` TINYINT NOT NULL,
  `user_answer` JSON DEFAULT NULL,
  `time_spent` INT DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user_session` (`user_id`, `session_id`),
  KEY `idx_question` (`question_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='答题记录表';

-- 15. 错题表
DROP TABLE IF EXISTS `wrong_question`;
CREATE TABLE `wrong_question` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `question_id` BIGINT NOT NULL,
  `question_type` TINYINT NOT NULL COMMENT '1单词2语法',
  `wrong_count` INT DEFAULT 1,
  `last_wrong_at` DATETIME NOT NULL,
  `mastered` TINYINT DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_user_question` (`user_id`, `question_id`),
  KEY `idx_user_type_mastered` (`user_id`, `question_type`, `mastered`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='错题表';

-- 16. 对话会话表
DROP TABLE IF EXISTS `chat_conversation`;
CREATE TABLE `chat_conversation` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `type` TINYINT NOT NULL COMMENT '1情景对话2智能问答3智能翻译',
  `scene_desc` VARCHAR(512) DEFAULT '',
  `user_role` VARCHAR(128) DEFAULT '',
  `evaluation` JSON DEFAULT NULL,
  `title` VARCHAR(256) DEFAULT '',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user_type` (`user_id`, `type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话会话表';

-- 17. 对话消息表
DROP TABLE IF EXISTS `chat_message`;
CREATE TABLE `chat_message` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `conversation_id` BIGINT NOT NULL,
  `role` VARCHAR(16) NOT NULL COMMENT 'user/assistant/system',
  `content` TEXT NOT NULL,
  `sources` JSON DEFAULT NULL,
  `message_type` VARCHAR(32) DEFAULT 'text',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_conversation` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话消息表';

-- 18. 情景文段表
DROP TABLE IF EXISTS `scenario_passage`;
CREATE TABLE `scenario_passage` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `word_ids` JSON NOT NULL,
  `passage_type` VARCHAR(16) NOT NULL COMMENT 'report/story/rhyme',
  `content` TEXT NOT NULL,
  `video_url` VARCHAR(512) DEFAULT '',
  `video_status` TINYINT DEFAULT 0 COMMENT '0未生成1生成中2已完成3失败',
  `expires_at` DATETIME NOT NULL,
  `model_used` VARCHAR(128) DEFAULT '',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user_expires` (`user_id`, `expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='情景文段表';

-- 19. 歌曲表
DROP TABLE IF EXISTS `song`;
CREATE TABLE `song` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `title` VARCHAR(128) NOT NULL,
  `artist` VARCHAR(128) NOT NULL,
  `cover_url` VARCHAR(512) DEFAULT '',
  `lyrics_en` TEXT,
  `lyrics_cn` TEXT,
  `audio_url` VARCHAR(512) DEFAULT '',
  `stage` TINYINT DEFAULT 0 COMMENT '0=全阶段',
  `recommend_date` DATE NOT NULL,
  KEY `idx_date` (`recommend_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='推荐歌曲表';

-- 20. 每日统计
DROP TABLE IF EXISTS `user_daily_stats`;
CREATE TABLE `user_daily_stats` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `stat_date` DATE NOT NULL,
  `words_learned` INT DEFAULT 0,
  `words_reviewed` INT DEFAULT 0,
  `quiz_count` INT DEFAULT 0,
  `quiz_correct` INT DEFAULT 0,
  `study_minutes` INT DEFAULT 0,
  UNIQUE KEY `uk_user_date` (`user_id`, `stat_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日学习统计表';

-- 21. 用户文档
DROP TABLE IF EXISTS `user_document`;
CREATE TABLE `user_document` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `filename` VARCHAR(256) NOT NULL,
  `file_type` VARCHAR(16) NOT NULL COMMENT 'pdf/ppt/word/txt/image',
  `file_size` INT DEFAULT 0,
  `storage_key` VARCHAR(512) NOT NULL,
  `parse_status` TINYINT DEFAULT 0 COMMENT '0待处理1解析中2已完成3失败',
  `parsed_text` TEXT,
  `vector_status` TINYINT DEFAULT 0 COMMENT '0未开始1进行中2已完成3失败',
  `chunk_count` INT DEFAULT 0,
  `file_path` VARCHAR(512) DEFAULT '' COMMENT '本地路径(开发用)',
  `ocr_text` TEXT COMMENT 'OCR文本(兼容旧)',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user` (`user_id`),
  KEY `idx_user_type` (`user_id`, `file_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户上传文档表';

-- 22. 反馈表
DROP TABLE IF EXISTS `feedback`;
CREATE TABLE `feedback` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `type` VARCHAR(16) NOT NULL COMMENT 'bug/suggestion',
  `content` TEXT NOT NULL,
  `screenshot_url` VARCHAR(512) DEFAULT '',
  `contact` VARCHAR(128) DEFAULT '',
  `status` VARCHAR(16) DEFAULT 'pending' COMMENT 'pending/processing/resolved',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户反馈表';

-- 23. 用户API Key（DBplan扩展：支持多Key）
DROP TABLE IF EXISTS `user_api_keys`;
CREATE TABLE `user_api_keys` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `key_type` VARCHAR(32) NOT NULL COMMENT 'llm/multimodal/embedding',
  `encrypted_key` VARCHAR(1024) NOT NULL,
  `api_base` VARCHAR(512) DEFAULT '',
  `model_name` VARCHAR(128) DEFAULT '',
  `is_valid` TINYINT DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户API Key表';

-- 24. 用户提醒
DROP TABLE IF EXISTS `user_reminders`;
CREATE TABLE `user_reminders` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL UNIQUE,
  `weekdays` VARCHAR(20) DEFAULT '1,2,3,4,5',
  `remind_time` VARCHAR(8) DEFAULT '08:00:00',
  `enabled` TINYINT DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户提醒设置表';
