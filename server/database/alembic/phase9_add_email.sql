-- Phase 9: 添加 email 字段 & 高中阶段 stage 重映射
-- 运行: mysql -u root -p elearningtest < phase9_add_email.sql

-- 1. 添加 email 列
ALTER TABLE `user`
  ADD COLUMN `email` VARCHAR(128) DEFAULT '' NOT NULL COMMENT '邮箱'
  AFTER `nickname`;

-- 2. 高中阶段重映射：stage 8=英语四级→11, 9=英语六级→12, 10=雅思→13
--    为高中一~三年级腾出 stage 8-10
UPDATE `user` SET `stage` = `stage` + 3 WHERE `stage` >= 8;
