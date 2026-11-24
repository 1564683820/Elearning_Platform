-- 新增 md_file_path 字段：存储 MinerU 转换后的完整 Markdown 文件路径
ALTER TABLE user_document
  ADD COLUMN md_file_path varchar(512) DEFAULT '' COMMENT 'MinerU 转换后的 Markdown 文件路径' AFTER file_path;
