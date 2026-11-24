-- Phase 11: 学习阶段值迁移 — 主库 elearningtest
-- 运行: mysql -u root -p elearningtest < phase11_stage_migration_main.sql
--
-- 映射规则:
--   旧 1-4   → 新 1 (小学)
--   旧 5-7   → 新 2 (初中)
--   旧 8-10  → 新 3 (高中)
--   旧 11-13 → 新 4 (四六级)

-- 1. user.stage
UPDATE `user`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;

-- 2. class.stage (保留 0 = 未指定)
UPDATE `class`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;

-- 3. question_bank.stage
UPDATE `question_bank`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;

-- 4. reading_material.stage
UPDATE `reading_material`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;

-- 5. listening_material.stage
UPDATE `listening_material`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;

-- 6. song.stage (保留 0 = 全阶段)
UPDATE `song`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;
