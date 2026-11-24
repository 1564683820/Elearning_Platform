-- 邀请码表新增软删除字段
ALTER TABLE invite_code
  ADD COLUMN is_deleted smallint DEFAULT 0 COMMENT '0=正常, 1=已删除',
  ADD COLUMN deleted_at datetime DEFAULT NULL COMMENT '删除时间';

-- 为 is_deleted 建立索引以优化查询
ALTER TABLE invite_code ADD INDEX idx_invite_code_is_deleted (is_deleted);
