-- ============================================================
-- 阶段 7：数据库索引优化 — 提升查询性能
-- 执行时间预估：dict_word 约 340 万行，加索引约 30-120 秒
-- ================================================
-- ======================================================

-- 1. dict_word 表 — 质量门槛过滤索引（OR 条件用 MySQL Index Merge）
-- ============================================================
USE elearnword;

-- bnc：用于 BNC 范围过滤 (bnc>0 AND bnc<20000) 和 stage 1-4 阶段筛选
ALTER TABLE dict_word ADD INDEX idx_bnc (bnc) COMMENT 'BNC词频排名索引';

-- oxford：用于质量门槛 (oxford=1)
ALTER TABLE dict_word ADD INDEX idx_oxford (oxford) COMMENT '牛津核心词标记索引';

-- frq：用于质量门槛 (frq>0 AND frq<30000) 和 ORDER BY 排序
ALTER TABLE dict_word ADD INDEX idx_frq (frq) COMMENT '当代语料库词频索引';

-- translation：用于 WHERE translation!='' 和 translation NOT LIKE '[%' 的过滤
-- 加前缀索引（前 10 字符足够区分非空/非标签开头）
ALTER TABLE dict_word ADD INDEX idx_translation_prefix (translation(10)) COMMENT '翻译字段前缀索引';


-- ============================================================
-- 2. stage_word 表 — JOIN 和阶段筛选索引
-- ============================================================
-- word_id：用于 JOIN dict_word.id（字典核心 JOIN 键）
ALTER TABLE elearnword.stage_word ADD INDEX idx_sw_word_id (word_id) COMMENT '关联单词ID索引';

-- stage：用于 WHERE stage=N 的阶段筛选
ALTER TABLE elearnword.stage_word ADD INDEX idx_sw_stage (stage) COMMENT '学习阶段索引';

-- 复合索引：覆盖 stage + JOIN word_id 的最常见查询模式
-- load_stage_words：WHERE stage=N JOIN dict_word，按 mastery_order 排序
ALTER TABLE elearnword.stage_word ADD INDEX idx_sw_stage_mastery (stage, mastery_order) COMMENT '阶段+掌握顺序复合索引';


-- ============================================================
-- 3. question_bank 表 — 出题/筛选索引
-- ============================================================
USE elearningtest;

-- word_id：用于 JOIN dict_word.id（清理/验证时使用）
ALTER TABLE question_bank ADD INDEX idx_qb_word_id (word_id) COMMENT '关联单词ID索引';

-- stage + type：用于 generateQuestions 的 WHERE stage=N AND type=M AND is_active=1
ALTER TABLE question_bank ADD INDEX idx_qb_stage_type (stage, type) COMMENT '阶段+题型复合索引';

-- word_id + stage + type：覆盖 skip_exist 检查
ALTER TABLE question_bank ADD INDEX idx_qb_word_stage_type (word_id, stage, type) COMMENT '单词+阶段+题型复合索引';
