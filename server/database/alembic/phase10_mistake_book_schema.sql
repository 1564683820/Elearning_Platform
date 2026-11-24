-- Phase 10: 错题本 - 小e总结报告存储表
-- 目标：存储 AI 生成的错题总结报告，在错题本的「小e总结」类展示

-- 1. 错题总结报告表
CREATE TABLE IF NOT EXISTS `mistake_summary_report` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '报告ID',
  `user_id` bigint(20) NOT NULL COMMENT '用户ID',
  `title` varchar(256) DEFAULT '' COMMENT '报告标题',
  `content` text NOT NULL COMMENT '报告内容(Markdown)',
  `exam_name` varchar(256) DEFAULT '' COMMENT '关联考试名称',
  `days` int(11) DEFAULT 0 COMMENT '覆盖天数(0=全部)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_created` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='错题总结报告表';
