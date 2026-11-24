-- Phase 6: AI视频教材演绎 - 数据库迁移
-- 目标：学生上传角色图片，AI 生成该角色朗读课文的视频

-- 1. 预设角色表
CREATE TABLE IF NOT EXISTS `preset_character` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '角色ID',
  `character_key` varchar(32) NOT NULL COMMENT '角色标识: cat_teacher/kevin/emma/owl_professor',
  `name` varchar(64) NOT NULL COMMENT '角色显示名称',
  `description` varchar(256) DEFAULT '' COMMENT '角色描述',
  `image_url` text DEFAULT NULL COMMENT '角色预设图片URL',
  `voice_type` varchar(32) DEFAULT '' COMMENT 'TTS音色类型',
  `sort_order` int(11) DEFAULT 0 COMMENT '排序',
  `is_active` tinyint(4) DEFAULT 1 COMMENT '是否启用: 1启用 0禁用',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_character_key` (`character_key`),
  KEY `idx_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='视频演绎预设角色表';

-- 2. AI视频记录表
CREATE TABLE IF NOT EXISTS `ai_video` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '视频ID',
  `user_id` bigint(20) NOT NULL COMMENT '创建用户ID',
  `title` varchar(256) NOT NULL DEFAULT '' COMMENT '视频标题',
  `textbook_version` varchar(32) DEFAULT '' COMMENT '教材版本',
  `textbook_grade` varchar(16) DEFAULT '' COMMENT '年级',
  `textbook_semester` varchar(16) DEFAULT '' COMMENT '学期',
  `unit_id` bigint(20) DEFAULT NULL COMMENT '关联教材单元ID',
  `unit_name` varchar(128) DEFAULT '' COMMENT '单元名称',
  `page_ids` json DEFAULT NULL COMMENT '选中的教材页面ID列表',
  `text_content` text DEFAULT NULL COMMENT '课文文字内容（用于配音）',
  `character_type` varchar(32) NOT NULL DEFAULT 'cat_teacher' COMMENT '角色类型',
  `character_image_url` text DEFAULT NULL COMMENT '自定义角色图片URL',
  `script_json` json DEFAULT NULL COMMENT 'AI生成的分镜脚本JSON',
  `tts_audio_url` text DEFAULT NULL COMMENT 'TTS配音音频URL',
  `video_url` text DEFAULT NULL COMMENT '最终合成视频URL（CDN）',
  `thumbnail_url` text DEFAULT NULL COMMENT '视频缩略图URL',
  `subtitle_url` text DEFAULT NULL COMMENT '字幕文件URL',
  `duration` int(11) DEFAULT 0 COMMENT '视频时长（秒）',
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/processing/completed/failed',
  `error_message` text DEFAULT NULL COMMENT '失败原因',
  `view_count` int(11) DEFAULT 0 COMMENT '观看次数',
  `favorite_count` int(11) DEFAULT 0 COMMENT '收藏次数',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_unit_id` (`unit_id`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI视频教材演绎记录表';

-- 3. 插入默认预设角色数据
INSERT INTO `preset_character` (`character_key`, `name`, `description`, `voice_type`, `sort_order`, `is_active`) VALUES
('cat_teacher', '小猫老师', '可爱的猫咪老师，亲切温柔', 'zh-CN-XiaoxiaoNeural', 1, 1),
('kevin', 'Kevin', '活力阳光的小男孩，发音清晰活泼', 'zh-CN-YunxiNeural', 2, 1),
('emma', 'Emma', '温柔可爱的小女孩，甜美动听', 'zh-CN-XiaoyiNeural', 3, 1),
('owl_professor', '博士猫头鹰', '博学稳重的猫头鹰教授，专业标准', 'zh-CN-YunjianNeural', 4, 1);
