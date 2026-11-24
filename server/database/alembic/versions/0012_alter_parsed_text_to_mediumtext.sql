-- 将 parsed_text 和 ocr_text 从 TEXT 改为 MEDIUMTEXT，支持更大文档内容
ALTER TABLE user_document
  MODIFY COLUMN parsed_text MEDIUMTEXT COMMENT '解析提取的文本内容',
  MODIFY COLUMN ocr_text MEDIUMTEXT COMMENT 'OCR 提取文本(兼容旧字段)';
