-- ============================================
-- Phase 5: AI 备课 PPT + 课堂互动 数据库迁移
-- 创建 lesson_ppt 表和 classroom_session 表
-- ============================================

-- ----------------------------
-- 1. lesson_ppt — 备课 PPT 主表
-- ----------------------------
CREATE TABLE IF NOT EXISTS `lesson_ppt` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `teacher_id`      BIGINT UNSIGNED NOT NULL        COMMENT '创建教师ID',
  `class_id`        BIGINT UNSIGNED DEFAULT NULL    COMMENT '目标班级ID（可为空，不限定班级使用）',
  `title`           VARCHAR(256) NOT NULL            COMMENT 'PPT 标题',
  `lesson_type`     VARCHAR(32) NOT NULL             COMMENT '课型: new_lesson/review/exercise/conversation',
  `subject`         VARCHAR(128) DEFAULT ''          COMMENT '主题/单元（如 Unit3 My Friends）',
  `grade`           VARCHAR(16) DEFAULT ''           COMMENT '适用年级（如 4）',
  `outline`         JSON DEFAULT NULL                COMMENT 'AI 生成的大纲（页面标题列表）',
  `pages_json`      JSON NOT NULL                    COMMENT '所有页面内容（JSON 数组，每页含 type/title/content）',
  `slide_count`     INT DEFAULT 0                    COMMENT '幻灯片页数',
  `interaction_config` JSON DEFAULT NULL             COMMENT '互动配置（投票/提问/游戏等预设）',
  `status`          VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT '状态: draft/published/archived',
  `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX `idx_ppt_teacher` (`teacher_id`),
  INDEX `idx_ppt_class`   (`class_id`),
  INDEX `idx_ppt_status`  (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='备课PPT主表';


-- ----------------------------
-- 2. classroom_session — 课堂会话表
-- ----------------------------
CREATE TABLE IF NOT EXISTS `classroom_session` (
  `id`                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `ppt_id`            BIGINT UNSIGNED NOT NULL        COMMENT '关联的 PPT ID',
  `teacher_id`        BIGINT UNSIGNED NOT NULL        COMMENT '授课教师ID',
  `title`             VARCHAR(256) DEFAULT ''          COMMENT '课堂标题（默认复用 PPT 标题）',
  `status`            VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态: active/paused/ended',
  `current_page`      INT DEFAULT 0                    COMMENT '当前播放页索引',
  `student_count`     INT DEFAULT 0                    COMMENT '参与学生数',
  `interaction_data`  JSON DEFAULT NULL                COMMENT '互动汇总数据（JSON：投票结果/答题统计/弹幕/提问）',
  `started_at`        DATETIME NOT NULL                COMMENT '课堂开始时间',
  `ended_at`          DATETIME DEFAULT NULL             COMMENT '课堂结束时间',

  INDEX `idx_ws_ppt`     (`ppt_id`),
  INDEX `idx_ws_teacher` (`teacher_id`),
  INDEX `idx_ws_status`  (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课堂会话表';
