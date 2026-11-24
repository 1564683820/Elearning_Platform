-- Phase 11: 学习阶段值迁移 — 单词库 elearnword
-- 运行: mysql -u root -p elearnword < phase11_stage_migration_words.sql
--
-- 映射规则:
--   旧 1-4   → 新 1 (小学)
--   旧 5-7   → 新 2 (初中)
--   旧 8-10  → 新 3 (高中)
--   旧 11-13 → 新 4 (四六级)

-- Step 1: 删除因阶段合并导致冲突的重复记录
-- 同一单词在同一个旧阶段范围内有多个记录时，只保留 mastery_order 最高的那条
-- (例如: 单词 33123 同时存在于旧 8 和旧 9，映射后都是新 3=高中，会违反 uk_word_stage)
DELETE sw1 FROM `stage_word` sw1
INNER JOIN `stage_word` sw2
    ON sw1.word_id = sw2.word_id
    AND sw1.id != sw2.id
    AND (
        (sw1.stage BETWEEN 1 AND 4 AND sw2.stage BETWEEN 1 AND 4)
     OR (sw1.stage BETWEEN 5 AND 7 AND sw2.stage BETWEEN 5 AND 7)
     OR (sw1.stage BETWEEN 8 AND 10 AND sw2.stage BETWEEN 8 AND 10)
     OR (sw1.stage BETWEEN 11 AND 13 AND sw2.stage BETWEEN 11 AND 13)
    )
    AND (
        sw1.mastery_order < sw2.mastery_order
        OR (sw1.mastery_order = sw2.mastery_order AND sw1.id < sw2.id)
    );

-- Step 2: 执行阶段值 UPDATE
UPDATE `stage_word`
SET `stage` = CASE
    WHEN `stage` BETWEEN 1 AND 4 THEN 1
    WHEN `stage` BETWEEN 5 AND 7 THEN 2
    WHEN `stage` BETWEEN 8 AND 10 THEN 3
    WHEN `stage` BETWEEN 11 AND 13 THEN 4
    ELSE `stage`
END
WHERE `stage` BETWEEN 1 AND 13;
