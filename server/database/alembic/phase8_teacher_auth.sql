-- 教师后台认证支持：添加用户名和密码哈希字段
-- 日期: 2026-06-05

ALTER TABLE `user`
    ADD COLUMN `username` VARCHAR(64) NULL DEFAULT NULL COMMENT '教师用户名(后台登录用)',
    ADD COLUMN `password_hash` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '密码哈希(后台登录用)',
    ADD UNIQUE INDEX `uk_username` (`username`);
