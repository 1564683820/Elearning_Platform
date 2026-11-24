-- ============================================
-- Phase 5.2: PPT 主题增强扩展 — 新增布局/动画/设计规范字段
-- 扩展 lesson_ppt + ppt_theme 表字段
-- ============================================

DROP PROCEDURE IF EXISTS `sp_phase5_2_add_cols`;

DELIMITER ;;
CREATE PROCEDURE `sp_phase5_2_add_cols`()
BEGIN
  DECLARE db_name VARCHAR(64);
  SET db_name = DATABASE();

  -- ========================
  -- 1. lesson_ppt 表扩展
  -- ========================

  -- 补充缺少的 stage_category / knowledge_graph_id
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='stage_category') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `stage_category` VARCHAR(16) DEFAULT 'other' COMMENT '学段: preschool/primary/junior/senior/other' AFTER `grade`;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='knowledge_graph_id') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `knowledge_graph_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '关联知识图谱 ID' AFTER `class_id`;
  END IF;

  -- Phase 5.2 新增：布局意图
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='layout_intent') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `layout_intent` VARCHAR(32) DEFAULT 'auto' COMMENT '布局意图: auto/cover/data_focus/comparison/timeline/concept/process/summary/quote/image_focus' AFTER `interaction_config`;
  END IF;

  -- Phase 5.2 新增：页面切换动画类型
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='transition_type') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `transition_type` VARCHAR(16) DEFAULT 'slide' COMMENT '页面切换动画: fade/slide/push' AFTER `layout_intent`;
  END IF;

  -- Phase 5.2 新增：切换动画时长(ms)
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='transition_duration') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `transition_duration` INT DEFAULT 400 COMMENT '切换动画时长(ms)' AFTER `transition_type`;
  END IF;

  -- Phase 5.2 新增：各slide类型的布局覆盖
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='lesson_ppt' AND COLUMN_NAME='layout_overrides') THEN
    ALTER TABLE `lesson_ppt` ADD COLUMN `layout_overrides` JSON DEFAULT NULL COMMENT '各slide type的布局覆盖 e.g. {"vocabulary":"grid"}' AFTER `transition_duration`;
  END IF;

  -- ========================
  -- 2. ppt_theme 表扩展
  -- ========================

  -- Phase 5.2 新增：设计规范 (Style as Skill)
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='ppt_theme' AND COLUMN_NAME='style_skill') THEN
    ALTER TABLE `ppt_theme` ADD COLUMN `style_skill` JSON DEFAULT NULL COMMENT '设计规范: color_scheme/typography/layout_rules/recommended_animations/anti_patterns/best_for' AFTER `teacher_id`;
  END IF;

  -- Phase 5.2 新增：各slide类型推荐布局映射
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='ppt_theme' AND COLUMN_NAME='slide_layouts') THEN
    ALTER TABLE `ppt_theme` ADD COLUMN `slide_layouts` JSON DEFAULT NULL COMMENT '各slide类型的推荐布局 e.g. {"vocabulary":"grid"}' AFTER `style_skill`;
  END IF;

  -- Phase 5.2 新增：字体配对列表
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=db_name AND TABLE_NAME='ppt_theme' AND COLUMN_NAME='font_pairings') THEN
    ALTER TABLE `ppt_theme` ADD COLUMN `font_pairings` JSON DEFAULT NULL COMMENT '可用字体配对列表' AFTER `slide_layouts`;
  END IF;

END;;
DELIMITER ;

CALL `sp_phase5_2_add_cols`();
DROP PROCEDURE IF EXISTS `sp_phase5_2_add_cols`;

-- ============================================
-- 3. 更新现有内置主题记录的设计规范数据
--    从 Python 端 ppt_theme_data.py 的 BUILTIN_THEMES 同步
--    如果记录已存在，仅更新 style_skill/slide_layouts（保留自定义 CSS 不变）
-- ============================================

-- classic
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#2d7d46','primary_light','#e8f5e9','primary_dark','#1b5e20','accent','#1565c0','accent_light','#e3f2fd','bg','#ffffff','text','#2c3e50','text_secondary','#546e7a','border','#e0e0e0'),
    'typography', JSON_OBJECT('title_font','PingFang SC, Microsoft YaHei','title_weight',800,'title_size','2.8vw-3.2vw','title_spacing','-0.02em','body_font','PingFang SC, Microsoft YaHei','body_weight',400,'body_size','1.4vw-1.6vw','line_height',1.7),
    'layout_rules', JSON_OBJECT('card_style','bordered','header_style','left-border','corner_radius','12px','spacing','generous','prefer_grid',false,'max_items_per_page',6),
    'recommended_animations', JSON_OBJECT('transition','slide','duration',400,'entrance','fade-up','stagger',0.05,'emphasis','pulse'),
    'anti_patterns', JSON_ARRAY('不要使用荧光色','不要使用超过3列布局','不要在深色背景使用灰色文字','标题不要超过两行','对话框不要混用太多说话人颜色'),
    'best_for', JSON_ARRAY('小学课堂','日常教学','各学段通用')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','list','grammar','list','practice','list','objective','list','dialogue','list')
WHERE `name` = 'classic' AND `is_builtin` = 1;

-- cartoon
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#ff7043','primary_light','#fff3e0','primary_dark','#e64a19','accent','#42a5f5','accent_light','#e3f2fd','bg','#fff8e1','text','#4e342e','text_secondary','#8d6e63','border','#ffccbc'),
    'typography', JSON_OBJECT('title_font','Comic Sans MS, PingFang SC','title_weight',900,'title_size','2.8vw-3.4vw','title_spacing','0','body_font','Comic Sans MS, PingFang SC','body_weight',400,'body_size','1.6vw-1.8vw','line_height',1.8),
    'layout_rules', JSON_OBJECT('card_style','rounded','header_style','centered-full','corner_radius','20px','spacing','loose','prefer_grid',true,'max_items_per_page',5),
    'recommended_animations', JSON_OBJECT('transition','push','duration',450,'entrance','scale-in','stagger',0.08,'emphasis','grow-shrink'),
    'anti_patterns', JSON_ARRAY('不要使用衬线字体','不要使用深色背景','不要在绿色背景上用红色文字','文字密度不要过高','不要使用专业性太强的术语'),
    'best_for', JSON_ARRAY('小学低年级','幼儿启蒙','趣味教学')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','grid','grammar','cards','practice','list','objective','grid','dialogue','cards')
WHERE `name` = 'cartoon' AND `is_builtin` = 1;

-- academic
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#1976d2','primary_light','#e3f2fd','primary_dark','#0d47a1','accent','#388e3c','accent_light','#e8f5e9','bg','#f5f7fa','text','#2c3e50','text_secondary','#546e7a','border','#cfd8dc'),
    'typography', JSON_OBJECT('title_font','PingFang SC, Microsoft YaHei','title_weight',700,'title_size','2.2vw-2.8vw','title_spacing','0','body_font','PingFang SC, Microsoft YaHei','body_weight',400,'body_size','1.3vw-1.5vw','line_height',1.7),
    'layout_rules', JSON_OBJECT('card_style','flat','header_style','full-bg','corner_radius','8px','spacing','medium','prefer_grid',false,'max_items_per_page',6),
    'recommended_animations', JSON_OBJECT('transition','slide','duration',380,'entrance','fade-up','stagger',0.04,'emphasis','pulse'),
    'anti_patterns', JSON_ARRAY('不要使用过于幼稚的装饰','不要超过4列布局','语法页不要用表格代替列表','练习页不要只放一道题'),
    'best_for', JSON_ARRAY('初中课堂','主题教学','系统性讲解')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','list','grammar','list','practice','list','objective','list','dialogue','list')
WHERE `name` = 'academic' AND `is_builtin` = 1;

-- senior
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#37474f','primary_light','#eceff1','primary_dark','#1a237e','accent','#d32f2f','accent_light','#ffebee','bg','#ffffff','text','#263238','text_secondary','#546e7a','border','#cfd8dc'),
    'typography', JSON_OBJECT('title_font','Noto Sans SC, PingFang SC','title_weight',800,'title_size','2.0vw-2.6vw','title_spacing','-0.5px','body_font','Noto Sans SC, PingFang SC','body_weight',400,'body_size','1.2vw-1.4vw','line_height',1.8),
    'layout_rules', JSON_OBJECT('card_style','minimal','header_style','left-border','corner_radius','4px','spacing','compact','prefer_grid',false,'max_items_per_page',8),
    'recommended_animations', JSON_OBJECT('transition','fade','duration',350,'entrance','fade','stagger',0.03,'emphasis','pulse'),
    'anti_patterns', JSON_ARRAY('不要使用emoji装饰','不要用卡通字体','不要用渐变背景','词汇页不要少于6个词','内容不要太稀松'),
    'best_for', JSON_ARRAY('高中课堂','雅思备考','学术英语')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','list','grammar','list','practice','list','objective','list','dialogue','list')
WHERE `name` = 'senior' AND `is_builtin` = 1;

-- blackboard
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#a5d6a7','primary_light','#4caf50','primary_dark','#1b5e20','accent','#fff176','accent_light','#ffee58','bg','#2e7d32','text','#ffffff','text_secondary','#e8f5e9','border','#4caf50'),
    'typography', JSON_OBJECT('title_font','Ma Shan Zheng, KaiTi, STKaiti','title_weight',700,'title_size','2.8vw-3.2vw','title_spacing','0.02em','body_font','KaiTi, STKaiti, PingFang SC','body_weight',400,'body_size','1.6vw-1.8vw','line_height',1.8),
    'layout_rules', JSON_OBJECT('card_style','chalk-border','header_style','underline','corner_radius','0px','spacing','generous','prefer_grid',false,'max_items_per_page',5),
    'recommended_animations', JSON_OBJECT('transition','push','duration',500,'entrance','fade-up','stagger',0.06,'emphasis','pulse'),
    'anti_patterns', JSON_ARRAY('不要使用彩色背景','不要使用圆角卡片','不要使用现代简约风排版','文字不要太小（至少1.6vw）','不要用衬线标题字体'),
    'best_for', JSON_ARRAY('传统课堂氛围','古诗词教学','文学赏析')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','list','grammar','list','practice','list','objective','list','dialogue','list')
WHERE `name` = 'blackboard' AND `is_builtin` = 1;

-- warm
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#ff7043','primary_light','#fff3e0','primary_dark','#bf360c','accent','#ec407a','accent_light','#fce4ec','bg','linear-gradient(135deg,#fff3e0,#fce4ec)','text','#4e342e','text_secondary','#8d6e63','border','#ffab91'),
    'typography', JSON_OBJECT('title_font','PingFang SC, Microsoft YaHei','title_weight',800,'title_size','2.8vw-3.2vw','title_spacing','0','body_font','PingFang SC, Microsoft YaHei','body_weight',400,'body_size','1.5vw-1.7vw','line_height',1.8),
    'layout_rules', JSON_OBJECT('card_style','glass','header_style','centered-blur','corner_radius','16px','spacing','loose','prefer_grid',false,'max_items_per_page',5),
    'recommended_animations', JSON_OBJECT('transition','fade','duration',500,'entrance','fade-up','stagger',0.06,'emphasis','grow-shrink'),
    'anti_patterns', JSON_ARRAY('不要使用冷色调','不要用尖锐边角','不要使用粗黑字体','文字密度要低','不要放超过6个词汇'),
    'best_for', JSON_ARRAY('幼儿启蒙','亲子课堂','温暖主题')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','cards','grammar','cards','practice','list','objective','list','dialogue','cards')
WHERE `name` = 'warm' AND `is_builtin` = 1;

-- tech
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#42a5f5','primary_light','#bbdefb','primary_dark','#0d47a1','accent','#00e5ff','accent_light','#80deea','bg','linear-gradient(135deg,#0a1628,#0d47a1)','text','#e8f0ff','text_secondary','#90caf9','border','#1565c0'),
    'typography', JSON_OBJECT('title_font','Segoe UI, Microsoft YaHei','title_weight',800,'title_size','2.4vw-2.8vw','title_spacing','0.05em','body_font','Segoe UI, Microsoft YaHei','body_weight',400,'body_size','1.3vw-1.5vw','line_height',1.7),
    'layout_rules', JSON_OBJECT('card_style','glass','header_style','left-accent','corner_radius','8px','spacing','medium','prefer_grid',true,'max_items_per_page',6),
    'recommended_animations', JSON_OBJECT('transition','slide','duration',350,'entrance','slide-up','stagger',0.04,'emphasis','pulse'),
    'anti_patterns', JSON_ARRAY('不要使用暖色系','不要用过大的圆角','不要在亮背景上放白色文字','不要使用手写字体','不要密集排版'),
    'best_for', JSON_ARRAY('科普课程','科技主题','数字素养')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','grid','grammar','list','practice','list','objective','grid','dialogue','list')
WHERE `name` = 'tech' AND `is_builtin` = 1;

-- nature
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#43a047','primary_light','#e8f5e9','primary_dark','#1b5e20','accent','#ef6c00','accent_light','#fff3e0','bg','linear-gradient(135deg,#e8f5e9,#c8e6c9)','text','#1b5e20','text_secondary','#33691e','border','#81c784'),
    'typography', JSON_OBJECT('title_font','PingFang SC, Microsoft YaHei','title_weight',800,'title_size','2.4vw-2.8vw','title_spacing','0','body_font','PingFang SC, Microsoft YaHei','body_weight',400,'body_size','1.4vw-1.6vw','line_height',1.7),
    'layout_rules', JSON_OBJECT('card_style','bordered','header_style','bottom-accent','corner_radius','12px','spacing','generous','prefer_grid',false,'max_items_per_page',6),
    'recommended_animations', JSON_OBJECT('transition','fade','duration',500,'entrance','fade-up','stagger',0.05,'emphasis','grow-shrink'),
    'anti_patterns', JSON_ARRAY('不要用荧光色','不要用纯黑文字','不要用过于工业化的排版','背景不要用纯白','标题不要用粗黑体'),
    'best_for', JSON_ARRAY('自然科学','环保主题','生物地理')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','cards','grammar','list','practice','list','objective','list','dialogue','cards')
WHERE `name` = 'nature' AND `is_builtin` = 1;

-- business
UPDATE `ppt_theme` SET
  `style_skill`    = JSON_OBJECT(
    'color_scheme', JSON_OBJECT('primary','#607d8b','primary_light','#eceff1','primary_dark','#37474f','accent','#e65100','accent_light','#fff3e0','bg','#fafafa','text','#37474f','text_secondary','#607d8b','border','#bdbdbd'),
    'typography', JSON_OBJECT('title_font','Segoe UI, PingFang SC','title_weight',700,'title_size','2.2vw-2.6vw','title_spacing','1px','body_font','Segoe UI, PingFang SC','body_weight',400,'body_size','1.3vw-1.5vw','line_height',1.7),
    'layout_rules', JSON_OBJECT('card_style','flat','header_style','full-bg-uppercase','corner_radius','4px','spacing','compact','prefer_grid',false,'max_items_per_page',7),
    'recommended_animations', JSON_OBJECT('transition','fade','duration',300,'entrance','fade','stagger',0.03,'emphasis','pulse'),
    'anti_patterns', JSON_ARRAY('不要使用emoji/装饰符号','不要用彩色渐变背景','不要用圆体/手写字体','排版不要太松散','不要使用过亮的强调色'),
    'best_for', JSON_ARRAY('成人英语','商务英语','企业培训')
  ),
  `slide_layouts`  = JSON_OBJECT('vocabulary','list','grammar','list','practice','list','objective','list','dialogue','list')
WHERE `name` = 'business' AND `is_builtin` = 1;
