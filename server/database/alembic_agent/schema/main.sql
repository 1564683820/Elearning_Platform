CREATE TABLE agent_skill (
	id BIGINT NOT NULL,
	teacher_id BIGINT NOT NULL COMMENT '所属教师ID',
	skill_type VARCHAR(32) COMMENT '技能类型: ppt=PPT设计, exam=试卷设计',
	name VARCHAR(128) NOT NULL COMMENT '技能名称（取自 SKILL.md frontmatter name）',
	description TEXT COMMENT '技能描述（取自 SKILL.md frontmatter description）',
	raw_content TEXT NOT NULL COMMENT '原始 SKILL.md 完整内容',
	design_tokens JSON COMMENT '解析后的设计令牌: {colors, typography, spacing, rounded, components}',
	prompt_snippet TEXT COMMENT '用于注入Agent系统提示词的压缩版设计规范',
	is_active SMALLINT COMMENT '是否当前激活: 1=是,0=否（同一教师每类技能可激活一个）',
	status SMALLINT COMMENT '状态: 1=正常,0=已删除',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='Agent自定义技能表' CHARSET=utf8mb4;
CREATE INDEX idx_askill_active ON agent_skill (teacher_id, skill_type, is_active);
CREATE INDEX idx_askill_teacher ON agent_skill (teacher_id);
CREATE INDEX idx_askill_teacher_type ON agent_skill (teacher_id, skill_type);
CREATE TABLE ai_video (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '创建用户ID',
	title VARCHAR(256) COMMENT '视频标题',
	textbook_version VARCHAR(32) COMMENT '教材版本',
	textbook_grade VARCHAR(16) COMMENT '年级',
	textbook_semester VARCHAR(16) COMMENT '学期',
	unit_id BIGINT COMMENT '关联教材单元ID',
	unit_name VARCHAR(128) COMMENT '单元名称',
	page_ids JSON COMMENT '选中的教材页面ID列表',
	text_content TEXT COMMENT '课文文字内容（用于配音）',
	character_type VARCHAR(32) NOT NULL COMMENT '角色类型',
	character_image_url TEXT COMMENT '自定义角色图片URL',
	script_json JSON COMMENT 'AI生成的分镜脚本JSON',
	tts_audio_url TEXT COMMENT 'TTS配音音频URL',
	video_url TEXT COMMENT '最终合成视频URL（CDN）',
	thumbnail_url TEXT COMMENT '视频缩略图URL',
	subtitle_url TEXT COMMENT '字幕文件URL',
	duration INTEGER COMMENT '视频时长（秒）',
	status VARCHAR(16) NOT NULL COMMENT '状态: pending/processing/completed/failed',
	error_message TEXT COMMENT '失败原因',
	view_count INTEGER COMMENT '观看次数',
	favorite_count INTEGER COMMENT '收藏次数',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	updated_at DATETIME COMMENT '更新时间' DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='AI视频教材演绎记录表' CHARSET=utf8mb4;
CREATE INDEX idx_av_created ON ai_video (created_at);
CREATE INDEX idx_av_status ON ai_video (status);
CREATE INDEX idx_av_unit ON ai_video (unit_id);
CREATE INDEX idx_av_user ON ai_video (user_id);
CREATE TABLE answer_sheet_template (
	id BIGINT NOT NULL,
	teacher_id BIGINT NOT NULL COMMENT '创建教师ID',
	name VARCHAR(128) NOT NULL COMMENT '模板名称',
	grade VARCHAR(16) COMMENT '适用年级',
	description VARCHAR(512) COMMENT '模板描述',
	choice_questions JSON NOT NULL COMMENT '选择题配置JSON（SKILL.md格式）',
	question_count INTEGER COMMENT '总题数',
	total_score INTEGER COMMENT '总分',
	is_default SMALLINT COMMENT '是否默认模板: 0=否,1=是',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='答题卡模板表' CHARSET=utf8mb4;
CREATE INDEX idx_as_template_teacher ON answer_sheet_template (teacher_id);
CREATE TABLE audit_log (
	id BIGINT NOT NULL,
	class_id BIGINT COMMENT '关联班级ID',
	operator_id BIGINT NOT NULL COMMENT '操作人用户ID',
	operator_role VARCHAR(20) NOT NULL COMMENT '操作人角色: teacher/assistant/admin/system',
	action_type VARCHAR(50) NOT NULL COMMENT '操作类型',
	target_type VARCHAR(50) COMMENT '操作对象类型',
	target_id BIGINT COMMENT '操作对象ID',
	detail JSON COMMENT '操作详情 JSON',
	ip_address VARCHAR(45) COMMENT '操作人IP地址',
	created_at DATETIME COMMENT '操作时间' DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='操作审计日志表' CHARSET=utf8mb4;
CREATE INDEX idx_audit_action ON audit_log (action_type);
CREATE INDEX idx_audit_class ON audit_log (class_id);
CREATE INDEX idx_audit_created ON audit_log (created_at);
CREATE INDEX idx_audit_operator ON audit_log (operator_id);
CREATE TABLE chat_conversation (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	type SMALLINT NOT NULL COMMENT '1=情景对话,2=智能问答,3=智能翻译,4=教学助手',
	scene_desc VARCHAR(512) COMMENT '场景描述(情景对话)',
	user_role VARCHAR(128) COMMENT '用户身份(情景对话)',
	evaluation JSON COMMENT 'AI 评价结果',
	created_at DATETIME DEFAULT now(),
	title VARCHAR(256) COMMENT '会话标题',
	summary TEXT COMMENT '对话摘要（LLM自动生成）',
	class_id BIGINT COMMENT '关联班级ID',
	status SMALLINT COMMENT '1=活跃 0=已归档',
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='对话会话表' CHARSET=utf8mb4;
CREATE INDEX idx_chat_teacher_type ON chat_conversation (user_id, type, status);
CREATE INDEX idx_user_type ON chat_conversation (user_id, type);
CREATE TABLE chat_message (
	id BIGINT NOT NULL,
	conversation_id BIGINT NOT NULL COMMENT '会话ID',
	`role` VARCHAR(16) NOT NULL COMMENT 'user/assistant/system',
	content TEXT NOT NULL COMMENT '消息内容',
	sources JSON COMMENT '引用来源(智能问答返回的链接列表)',
	created_at DATETIME DEFAULT now(),
	message_type VARCHAR(32) COMMENT 'text/image/file',
	PRIMARY KEY (id)
)COMMENT='对话消息表' CHARSET=utf8mb4;
CREATE INDEX ix_chat_message_conversation_id ON chat_message (conversation_id);
CREATE TABLE class (
	id BIGINT NOT NULL,
	name VARCHAR(128) NOT NULL COMMENT '班级名称',
	description VARCHAR(512) COMMENT '班级描述',
	invite_code VARCHAR(32) NOT NULL COMMENT '邀请码(唯一)',
	created_by BIGINT NOT NULL COMMENT '创建者教师ID',
	stage SMALLINT COMMENT '默认学习阶段',
	student_count INTEGER COMMENT '学生人数(冗余)',
	is_active SMALLINT COMMENT '是否启用 0/1',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (invite_code)
)COMMENT='班级表' CHARSET=utf8mb4;
CREATE INDEX idx_created_by ON class (created_by);
CREATE INDEX idx_stage ON class (stage);
CREATE TABLE class_student (
	id BIGINT NOT NULL,
	class_id BIGINT NOT NULL COMMENT '班级ID',
	student_id BIGINT NOT NULL COMMENT '学生ID',
	joined_at DATETIME COMMENT '加入时间' DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_class_student UNIQUE (class_id, student_id)
)COMMENT='班级-学生关联表' CHARSET=utf8mb4;
CREATE INDEX idx_student ON class_student (student_id);
CREATE TABLE class_student_info (
	id BIGINT NOT NULL,
	class_id BIGINT NOT NULL COMMENT '班级ID',
	student_number INTEGER NOT NULL COMMENT '学生序号',
	student_name VARCHAR(64) NOT NULL COMMENT '学生姓名',
	exam_number VARCHAR(64) NOT NULL COMMENT '考号/学号',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_csi_class_exam UNIQUE (class_id, exam_number)
)COMMENT='班级学生信息表(Excel导入)' CHARSET=utf8mb4;
CREATE INDEX idx_csi_class ON class_student_info (class_id);
CREATE TABLE class_teacher (
	id BIGINT NOT NULL,
	class_id BIGINT NOT NULL COMMENT '班级ID',
	teacher_id BIGINT NOT NULL COMMENT '教师ID',
	`role` VARCHAR(16) NOT NULL COMMENT '角色: teacher/assistant',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_class_teacher UNIQUE (class_id, teacher_id)
)COMMENT='班级-教师关联表' CHARSET=utf8mb4;
CREATE INDEX idx_teacher ON class_teacher (teacher_id);
CREATE TABLE classroom_session (
	id BIGINT NOT NULL,
	ppt_id BIGINT NOT NULL COMMENT '关联的 PPT ID',
	teacher_id BIGINT NOT NULL COMMENT '授课教师ID',
	title VARCHAR(256) COMMENT '课堂标题',
	status VARCHAR(16) COMMENT '状态: active/paused/ended',
	current_page INTEGER COMMENT '当前播放页索引',
	student_count INTEGER COMMENT '参与学生数',
	interaction_data JSON COMMENT '互动汇总数据',
	started_at DATETIME NOT NULL COMMENT '课堂开始时间',
	ended_at DATETIME COMMENT '课堂结束时间',
	PRIMARY KEY (id)
)COMMENT='课堂会话表' CHARSET=utf8mb4;
CREATE INDEX idx_ws_ppt ON classroom_session (ppt_id);
CREATE INDEX idx_ws_status ON classroom_session (status);
CREATE INDEX idx_ws_teacher ON classroom_session (teacher_id);
CREATE TABLE exam_grading_log (
	id BIGINT NOT NULL,
	submission_id BIGINT NOT NULL COMMENT '提交记录ID',
	grader_type VARCHAR(16) NOT NULL COMMENT '批改者类型: ai/teacher/assistant',
	grader_id BIGINT COMMENT '批改者用户ID(教师/助教)',
	action VARCHAR(32) NOT NULL COMMENT '操作: auto_grade/teacher_review/teacher_adjust',
	detail JSON COMMENT '操作详情 JSON',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='批改日志表' CHARSET=utf8mb4;
CREATE INDEX idx_log_grader ON exam_grading_log (grader_id);
CREATE INDEX idx_log_submission ON exam_grading_log (submission_id);
CREATE TABLE exam_submission (
	id BIGINT NOT NULL,
	exam_id BIGINT NOT NULL COMMENT '试卷ID',
	student_id BIGINT COMMENT '学生ID（扫描批卷未识别考号时可为NULL）',
	answers JSON NOT NULL COMMENT '学生答案 JSON',
	score INTEGER COMMENT 'AI 评分总得分',
	max_score INTEGER COMMENT '满分',
	ai_grade_detail JSON COMMENT 'AI 逐题评分详情',
	teacher_adjustment JSON COMMENT '教师调整记录',
	adjusted_score INTEGER COMMENT '教师调整后分数',
	exam_number VARCHAR(64) COMMENT '考号/学号（OCR批卷匹配用）',
	started_at DATETIME COMMENT '开始作答时间',
	submitted_at DATETIME COMMENT '提交时间',
	duration_seconds INTEGER COMMENT '作答用时(秒)',
	grading_status VARCHAR(32) COMMENT '批改状态: pending/ai_done/teacher_reviewed/omr_*',
	scan_image_url VARCHAR(512) COMMENT '扫描答题卡图片URL（OMR批卷来源）',
	scan_record_id BIGINT COMMENT '关联的扫描记录ID',
	wrong_count INTEGER COMMENT '错题数量',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_exam_student UNIQUE (exam_id, student_id)
)COMMENT='学生提交表' CHARSET=utf8mb4;
CREATE INDEX idx_sub_exam ON exam_submission (exam_id);
CREATE INDEX idx_sub_student ON exam_submission (student_id);
CREATE TABLE favorite (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	target_type SMALLINT NOT NULL COMMENT '1=单词,2=文章,3=情景文段,4=歌曲',
	target_id BIGINT NOT NULL COMMENT '目标ID',
	word VARCHAR(255) COMMENT '单词文本（单词收藏）',
	phonetic VARCHAR(255) COMMENT '音标（单词收藏）',
	meaning VARCHAR(1024) COMMENT '释义（单词收藏）',
	content TEXT COMMENT '文段内容（情景文段收藏）',
	passage_type VARCHAR(50) COMMENT '文段类型（情景文段收藏）',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_user_target UNIQUE (user_id, target_type, target_id)
)COMMENT='收藏表' CHARSET=utf8mb4;
CREATE INDEX idx_user_type ON favorite (user_id, target_type);
CREATE TABLE feedback (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	type VARCHAR(16) NOT NULL COMMENT '类型: bug/suggestion',
	content TEXT NOT NULL COMMENT '反馈内容',
	screenshot_url VARCHAR(512) COMMENT '截图 URL',
	created_at DATETIME DEFAULT now(),
	contact VARCHAR(128) COMMENT '联系方式',
	status VARCHAR(16) COMMENT 'pending/processing/resolved',
	PRIMARY KEY (id)
)COMMENT='用户反馈表' CHARSET=utf8mb4;
CREATE INDEX idx_user ON feedback (user_id);
CREATE TABLE invite_code (
	id BIGINT NOT NULL,
	code VARCHAR(32) NOT NULL COMMENT '邀请码',
	`role` VARCHAR(16) NOT NULL COMMENT '邀请码角色: student/teacher',
	is_used SMALLINT COMMENT '0=未使用, 1=已使用',
	used_by BIGINT COMMENT '使用者用户ID',
	used_at DATETIME COMMENT '使用时间',
	created_by BIGINT NOT NULL COMMENT '创建人ID（管理员）',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	is_deleted SMALLINT COMMENT '0=正常, 1=已删除',
	deleted_at DATETIME COMMENT '删除时间',
	PRIMARY KEY (id)
)COMMENT='邀请码表' CHARSET=utf8mb4;
CREATE UNIQUE INDEX ix_invite_code_code ON invite_code (code);
CREATE TABLE knowledge_graph (
	id BIGINT NOT NULL,
	ppt_id BIGINT COMMENT '关联 PPT ID（生成后填充）',
	teacher_id BIGINT NOT NULL COMMENT '教师 ID',
	title VARCHAR(256) NOT NULL COMMENT '课程标题',
	lesson_type VARCHAR(32) NOT NULL COMMENT '课型',
	subject VARCHAR(128) COMMENT '主题/单元',
	grade VARCHAR(16) COMMENT '适用年级',
	content JSON NOT NULL COMMENT '图谱内容 {sections: [...]}',
	status VARCHAR(16) COMMENT '状态: draft/confirmed',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='知识图谱表' CHARSET=utf8mb4;
CREATE INDEX idx_kg_ppt ON knowledge_graph (ppt_id);
CREATE INDEX idx_kg_teacher ON knowledge_graph (teacher_id);
CREATE TABLE learning_behavior_log (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	action_type VARCHAR(32) NOT NULL COMMENT '行为类型: start_quiz/submit_answer/start_listening/finish_listening/start_reading/finish_reading/translate/watch_video/create_scenario',
	target_type VARCHAR(32) COMMENT '目标类型: question/material/scenario/video',
	target_id BIGINT COMMENT '目标ID',
	detail JSON COMMENT '行为详情(JSON): 正确率/得分/用时等',
	session_duration INTEGER COMMENT '行为持续时长(秒)',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='学习行为日志表' CHARSET=utf8mb4;
CREATE INDEX idx_target ON learning_behavior_log (target_type, target_id);
CREATE INDEX idx_user_action ON learning_behavior_log (user_id, action_type);
CREATE INDEX idx_user_created ON learning_behavior_log (user_id, created_at);
CREATE TABLE learning_report (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '学生用户ID',
	class_id BIGINT COMMENT '所属班级ID',
	report_type VARCHAR(20) NOT NULL COMMENT '报告类型: personal/class/semester',
	period_start DATE NOT NULL COMMENT '统计开始日期',
	period_end DATE NOT NULL COMMENT '统计结束日期',
	report_data JSON NOT NULL COMMENT '报告数据JSON',
	generated_at DATETIME COMMENT '生成时间' DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='学习报告缓存表' CHARSET=utf8mb4;
CREATE INDEX idx_report_generated ON learning_report (generated_at);
CREATE INDEX idx_report_type ON learning_report (report_type);
CREATE INDEX idx_report_user_class ON learning_report (user_id, class_id);
CREATE TABLE lesson_ppt (
	id BIGINT NOT NULL,
	teacher_id BIGINT NOT NULL COMMENT '创建教师ID',
	class_id BIGINT COMMENT '目标班级ID（可为空）',
	knowledge_graph_id BIGINT COMMENT '关联知识图谱 ID',
	title VARCHAR(256) NOT NULL COMMENT 'PPT 标题',
	lesson_type VARCHAR(32) NOT NULL COMMENT '课型: new_lesson/review/exercise/conversation',
	subject VARCHAR(128) COMMENT '主题/单元',
	grade VARCHAR(16) COMMENT '适用年级',
	stage_category VARCHAR(16) COMMENT '学段: preschool/primary/junior/senior/other',
	outline JSON COMMENT 'AI 生成的大纲',
	pages_json JSON NOT NULL COMMENT '所有页面内容 JSON',
	html_content TEXT COMMENT '完整 HTML 格式幻灯片（含主题 CSS）',
	theme_name VARCHAR(64) COMMENT '当前主题名',
	version INTEGER COMMENT '版本号',
	thumbnail_url VARCHAR(512) COMMENT '缩略图URL',
	slide_count INTEGER COMMENT '幻灯片页数',
	interaction_config JSON COMMENT '互动配置',
	layout_intent VARCHAR(32) COMMENT '布局意图: auto/cover/data_focus等',
	transition_type VARCHAR(16) COMMENT '页面切换动画: fade/slide/push',
	transition_duration INTEGER COMMENT '切换动画时长(ms)',
	layout_overrides JSON COMMENT '各slide type的布局覆盖',
	spec_lock JSON COMMENT '设计规格锁定 Phase3.3（视觉风格/配色/字体/布局/节奏）',
	status VARCHAR(16) COMMENT '状态: draft/published/archived',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='备课PPT主表' CHARSET=utf8mb4;
CREATE INDEX idx_ppt_class ON lesson_ppt (class_id);
CREATE INDEX idx_ppt_status ON lesson_ppt (status);
CREATE INDEX idx_ppt_teacher ON lesson_ppt (teacher_id);
CREATE TABLE listening_material (
	id BIGINT NOT NULL,
	stage SMALLINT NOT NULL COMMENT '学习阶段: 1=小学,2=初中,3=高中,4=四六级',
	title VARCHAR(256) NOT NULL COMMENT '标题',
	audio_url VARCHAR(512) NOT NULL COMMENT '音频 URL',
	transcript TEXT COMMENT '听力原文',
	transcript_cn TEXT COMMENT '中文翻译',
	duration INTEGER COMMENT '时长(秒)',
	type VARCHAR(16) COMMENT '类型: article/story/news',
	source VARCHAR(128) COMMENT '来源',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='听力材料表' CHARSET=utf8mb4;
CREATE INDEX idx_stage_type ON listening_material (stage, type);
CREATE TABLE mistake_summary_report (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	title VARCHAR(256) COMMENT '报告标题',
	content TEXT NOT NULL COMMENT '报告内容(Markdown)',
	exam_name VARCHAR(256) COMMENT '关联考试名称',
	days INTEGER COMMENT '覆盖天数(0=全部)',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='错题总结报告表' CHARSET=utf8mb4;
CREATE TABLE ppt_theme (
	id BIGINT NOT NULL,
	name VARCHAR(64) NOT NULL COMMENT '主题标识名（如 classic, cartoon）',
	display_name VARCHAR(128) NOT NULL COMMENT '主题显示名（如 经典简约）',
	description VARCHAR(256) COMMENT '主题描述',
	css_variables TEXT NOT NULL COMMENT 'CSS 变量定义（:root {...}）',
	css_content TEXT NOT NULL COMMENT '完整主题 CSS 内容',
	preview_color VARCHAR(32) COMMENT '预览色',
	preview_url VARCHAR(512) COMMENT '预览截图URL',
	sort_order INTEGER COMMENT '排序号',
	is_builtin INTEGER COMMENT '是否为内置主题',
	teacher_id BIGINT COMMENT '自定义主题创建教师ID',
	style_skill JSON COMMENT '设计规范: color_scheme/typography/layout_rules等',
	slide_layouts JSON COMMENT '各slide类型的推荐布局映射',
	font_pairings JSON COMMENT '字体配对列表',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='幻灯片主题表' CHARSET=utf8mb4;
CREATE INDEX idx_theme_builtin ON ppt_theme (is_builtin);
CREATE INDEX idx_theme_name ON ppt_theme (name);
CREATE INDEX idx_theme_teacher ON ppt_theme (teacher_id);
CREATE TABLE ppt_version (
	id BIGINT NOT NULL,
	ppt_id BIGINT NOT NULL COMMENT '关联的 PPT ID',
	version INTEGER NOT NULL COMMENT '版本号',
	html_content TEXT NOT NULL COMMENT '该版本的 HTML 完整内容',
	pages_json JSON COMMENT '该版本的 JSON 页面数据',
	theme_name VARCHAR(64) COMMENT '该版本使用的主题',
	change_summary VARCHAR(512) COMMENT '变更摘要',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='幻灯片版本历史表' CHARSET=utf8mb4;
CREATE INDEX idx_v_ppt ON ppt_version (ppt_id);
CREATE INDEX idx_v_ppt_version ON ppt_version (ppt_id, version);
CREATE TABLE preset_character (
	id BIGINT NOT NULL,
	character_key VARCHAR(32) NOT NULL COMMENT '角色标识',
	name VARCHAR(64) NOT NULL COMMENT '角色显示名称',
	description VARCHAR(256) COMMENT '角色描述',
	image_url TEXT COMMENT '角色预设图片URL',
	voice_type VARCHAR(32) COMMENT 'TTS音色类型',
	sort_order INTEGER COMMENT '排序',
	is_active INTEGER COMMENT '是否启用: 1启用 0禁用',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (character_key)
)COMMENT='视频演绎预设角色表' CHARSET=utf8mb4;
CREATE INDEX idx_pc_active ON preset_character (is_active);
CREATE TABLE question_bank (
	id BIGINT NOT NULL,
	stage SMALLINT NOT NULL COMMENT '适用学习阶段: 1=小学,2=初中,3=高中,4=四六级',
	type SMALLINT NOT NULL COMMENT '题型: 1=选择填空,2=选择翻译,3=听力选择,4=短语语法,5=句子翻译,6=阅读理解,7=听力训练,8=句子翻译(填空),9=作文写作',
	difficulty SMALLINT COMMENT '难度 1-3',
	content JSON NOT NULL COMMENT '题目内容(题干/选项/答案/解析)',
	source VARCHAR(128) COMMENT '来源(试卷名/教材/AI生成)',
	audio_url VARCHAR(512) COMMENT '听力题音频 URL',
	reading_id BIGINT COMMENT '关联阅读材料 ID',
	word_id INTEGER COMMENT '关联单词 ID',
	created_at DATETIME DEFAULT now(),
	is_active SMALLINT COMMENT '是否启用 0/1',
	PRIMARY KEY (id)
)COMMENT='题库表' CHARSET=utf8mb4;
CREATE INDEX idx_stage_type ON question_bank (stage, type);
CREATE INDEX idx_word_id ON question_bank (word_id);
CREATE TABLE reading_material (
	id BIGINT NOT NULL,
	stage SMALLINT NOT NULL COMMENT '学习阶段: 1=小学,2=初中,3=高中,4=四六级',
	title VARCHAR(256) NOT NULL COMMENT '标题',
	content TEXT NOT NULL COMMENT '英文正文',
	content_cn TEXT COMMENT '中文翻译',
	type VARCHAR(16) COMMENT '素材类型: article/story/news',
	source VARCHAR(256) COMMENT '来源',
	word_count INTEGER COMMENT '字数',
	difficulty SMALLINT COMMENT '难度 1-5',
	audio_url VARCHAR(512) COMMENT '配套音频 URL',
	PRIMARY KEY (id)
)COMMENT='阅读材料表' CHARSET=utf8mb4;
CREATE INDEX idx_stage_type ON reading_material (stage, type);
CREATE TABLE redeem_code (
	id BIGINT NOT NULL,
	code VARCHAR(32) NOT NULL COMMENT '兑换码',
	plan VARCHAR(32) NOT NULL COMMENT '对应套餐',
	duration_months INTEGER NOT NULL COMMENT '时长(月)',
	status VARCHAR(16) COMMENT 'active/used/expired/disabled',
	created_by BIGINT NOT NULL COMMENT '创建人ID',
	batch_no VARCHAR(64) COMMENT '批次号',
	used_by BIGINT COMMENT '使用者ID',
	used_at DATETIME COMMENT '使用时间',
	expire_at DATETIME COMMENT '兑换码过期时间',
	remark VARCHAR(256) COMMENT '备注',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (code)
)COMMENT='兑换码表' CHARSET=utf8mb4;
CREATE TABLE scenario_passage (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	word_ids JSON NOT NULL COMMENT '涉及的错题单词 ID 列表',
	passage_type VARCHAR(16) NOT NULL COMMENT '文段类型: report/story/rhyme',
	content TEXT NOT NULL COMMENT '文段内容(单词高亮标记)',
	video_url VARCHAR(512) COMMENT '生成的视频 URL',
	video_status SMALLINT COMMENT '视频状态: 0=未生成,1=生成中,2=已完成,3=失败',
	expires_at DATETIME NOT NULL COMMENT '过期时间(30天)',
	created_at DATETIME DEFAULT now(),
	model_used VARCHAR(128) COMMENT '使用的模型',
	PRIMARY KEY (id)
)COMMENT='情景文段表' CHARSET=utf8mb4;
CREATE INDEX idx_user_expires ON scenario_passage (user_id, expires_at);
CREATE TABLE school_admin (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '管理员用户ID',
	school_name VARCHAR(200) NOT NULL COMMENT '学校名称',
	contact_phone VARCHAR(20) COMMENT '联系电话',
	permissions JSON COMMENT '权限配置JSON',
	is_active INTEGER COMMENT '是否启用',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (user_id)
)COMMENT='学校管理员表' CHARSET=utf8mb4;
CREATE INDEX idx_school_active ON school_admin (is_active);
CREATE INDEX idx_school_name ON school_admin (school_name);
CREATE TABLE song (
	id INTEGER NOT NULL AUTO_INCREMENT,
	title VARCHAR(128) NOT NULL COMMENT '歌名',
	artist VARCHAR(128) NOT NULL COMMENT '歌手',
	cover_url VARCHAR(512) COMMENT '封面图 URL',
	lyrics_en TEXT COMMENT '英文歌词',
	lyrics_cn TEXT COMMENT '中文歌词',
	audio_url VARCHAR(512) COMMENT '音频 URL',
	stage SMALLINT COMMENT '适合阶段(0=全阶段)',
	recommend_date DATE NOT NULL COMMENT '推荐日期',
	PRIMARY KEY (id)
)COMMENT='推荐歌曲表' CHARSET=utf8mb4;
CREATE INDEX idx_date ON song (recommend_date);
CREATE TABLE study_record (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	word_id INTEGER NOT NULL COMMENT '单词ID(dict_word.id)',
	action SMALLINT NOT NULL COMMENT '动作: 1=浏览,2=收藏,3=取消收藏,4=发音播放',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='学习记录表' CHARSET=utf8mb4;
CREATE INDEX idx_user_created ON study_record (user_id, created_at);
CREATE INDEX idx_user_word ON study_record (user_id, word_id);
CREATE TABLE teacher_exam (
	id BIGINT NOT NULL,
	teacher_id BIGINT NOT NULL COMMENT '创建教师ID',
	class_id BIGINT NOT NULL COMMENT '目标班级ID',
	title VARCHAR(256) NOT NULL COMMENT '试卷标题',
	description VARCHAR(512) COMMENT '试卷描述',
	questions JSON NOT NULL COMMENT '题目列表 JSON',
	total_score INTEGER COMMENT '总分',
	difficulty SMALLINT COMMENT '难度: 1=简单,2=中等,3=困难',
	duration_minutes INTEGER COMMENT '建议用时(分钟)',
	knowledge_points VARCHAR(512) COMMENT '知识点标签,逗号分隔',
	grade VARCHAR(16) COMMENT '适用年级，如：五年级、七年级',
	submission_count INTEGER COMMENT '提交人数',
	avg_score INTEGER COMMENT '平均分',
	status VARCHAR(16) COMMENT '状态: draft/published/grading/done/archived',
	published_at DATETIME COMMENT '发布时间',
	done_at DATETIME COMMENT '批改完成时间',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	stage_category VARCHAR(16) COMMENT '学段: preschool/primary/junior/senior/other',
	source_exam_ids VARCHAR(255) COMMENT '组卷来源试卷ID列表，逗号分隔',
	answer_sheet_config JSON COMMENT '答题卡配置: {total_questions, option_count, options, regions, coordinate_config, html_url, pdf_url}',
	PRIMARY KEY (id)
)COMMENT='试卷主表' CHARSET=utf8mb4;
CREATE INDEX idx_exam_class ON teacher_exam (class_id);
CREATE INDEX idx_exam_stage ON teacher_exam (stage_category);
CREATE INDEX idx_exam_status ON teacher_exam (status);
CREATE INDEX idx_exam_teacher ON teacher_exam (teacher_id);
CREATE TABLE teacher_memory (
	id BIGINT NOT NULL,
	teacher_id BIGINT NOT NULL COMMENT '教师ID',
	memory_type VARCHAR(32) NOT NULL COMMENT 'preference/topic_summary/class_note/teaching_style',
	memory_key VARCHAR(128) NOT NULL COMMENT '记忆键',
	memory_value TEXT NOT NULL COMMENT '记忆值',
	importance FLOAT COMMENT '重要性 0-1',
	trigger_keywords JSON COMMENT '触发关键词列表',
	access_count INTEGER COMMENT '被引用次数',
	last_accessed_at DATETIME COMMENT '最后访问时间',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='教师长期记忆表' CHARSET=utf8mb4;
CREATE INDEX idx_tm_teacher_key ON teacher_memory (teacher_id, memory_key);
CREATE INDEX idx_tm_teacher_type ON teacher_memory (teacher_id, memory_type);
CREATE TABLE teaching_task (
	id BIGINT NOT NULL,
	teacher_id BIGINT NOT NULL,
	class_id BIGINT NOT NULL,
	objective TEXT NOT NULL,
	status VARCHAR(32) NOT NULL,
	checkpoint JSON NOT NULL,
	artifact JSON NOT NULL,
	artifact_version INTEGER NOT NULL,
	approved_version INTEGER,
	published_exam_id BIGINT,
	error_code VARCHAR(64),
	lease_owner VARCHAR(64),
	lease_until DATETIME,
	attempts INTEGER NOT NULL,
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (published_exam_id)
);
CREATE INDEX idx_teaching_task_owner ON teaching_task (teacher_id, created_at);
CREATE TABLE teaching_task_outbox (
	id BIGINT NOT NULL,
	task_id BIGINT NOT NULL,
	delivered_at DATETIME,
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id)
);
CREATE INDEX ix_teaching_task_outbox_task_id ON teaching_task_outbox (task_id);
CREATE TABLE textbook_page (
	id BIGINT NOT NULL,
	unit_id BIGINT COMMENT '关联单元ID(textbook_unit.id)',
	textbook_version VARCHAR(64) NOT NULL COMMENT '教材版本 e.g. PEP',
	grade VARCHAR(16) NOT NULL COMMENT '年级',
	semester VARCHAR(8) COMMENT '学期',
	unit_number VARCHAR(16) NOT NULL COMMENT '单元号',
	page_number INTEGER NOT NULL COMMENT '页码',
	text_content TEXT NOT NULL COMMENT '课文文字全文',
	sentences_json JSON COMMENT '分句 [{en,cn,start_sec,end_sec,speaker,animation_url}]',
	image_url VARCHAR(512) COMMENT '静态插图 URL',
	image_thumbnail VARCHAR(512) COMMENT '缩略图 URL',
	animation_url VARCHAR(512) COMMENT '微动图 URL(Lottie/GIF, 整页)',
	background_anim_url VARCHAR(512) COMMENT '背景持续微动图 URL（动态图书增强）',
	audio_url VARCHAR(512) COMMENT '课文朗读音频 URL',
	audio_duration INTEGER COMMENT '音频时长(秒)',
	words_json JSON COMMENT '页面单词列表 [{word,phonetic,translation,audio_url}]',
	exercises_json JSON COMMENT '页面练习题(optional)',
	is_active INTEGER COMMENT '是否启用 0/1',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_textbook_page UNIQUE (textbook_version, grade, semester, unit_number, page_number)
)COMMENT='教材页面表' CHARSET=utf8mb4;
CREATE INDEX idx_unit ON textbook_page (unit_id);
CREATE INDEX idx_version_grade ON textbook_page (textbook_version, grade);
CREATE TABLE textbook_unit (
	id BIGINT NOT NULL,
	textbook_version VARCHAR(64) NOT NULL COMMENT '教材版本 e.g. PEP',
	grade VARCHAR(16) NOT NULL COMMENT '年级 e.g. 3,4,5,6',
	semester VARCHAR(8) COMMENT '学期: 上/下',
	unit_number VARCHAR(16) NOT NULL COMMENT '单元号 e.g. Unit1, Recycle1',
	title VARCHAR(128) COMMENT '单元标题',
	sub_title VARCHAR(128) COMMENT '副标题',
	cover_image VARCHAR(512) COMMENT '单元封面图 URL',
	page_start INTEGER COMMENT '起始页码',
	page_end INTEGER COMMENT '结束页码',
	sort_order INTEGER COMMENT '排序',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_textbook_unit UNIQUE (textbook_version, grade, semester, unit_number)
)COMMENT='教材单元表' CHARSET=utf8mb4;
CREATE INDEX idx_version_grade ON textbook_unit (textbook_version, grade);
CREATE TABLE textbook_upload (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '上传用户ID',
	filename VARCHAR(256) NOT NULL COMMENT '原始文件名',
	file_key VARCHAR(256) NOT NULL COMMENT '存储路径（相对 uploads/）',
	file_size INTEGER COMMENT '文件大小(字节)',
	textbook_version VARCHAR(64) COMMENT '教材版本 e.g. PEP',
	grade VARCHAR(16) COMMENT '年级 e.g. 3,4,5,6',
	semester VARCHAR(8) COMMENT '学期: 上/下',
	parse_status INTEGER COMMENT '解析状态: 0=待处理,1=解析中,2=已完成,3=失败',
	total_pages INTEGER COMMENT 'PDF总页数',
	parsed_pages INTEGER COMMENT '已解析页数',
	error_msg VARCHAR(512) COMMENT '错误信息',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='教材上传记录表' CHARSET=utf8mb4;
CREATE TABLE training_session (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	type SMALLINT NOT NULL COMMENT '训练类型(同 question_bank.type)',
	total_count INTEGER NOT NULL COMMENT '总题数',
	correct_count INTEGER COMMENT '正确数',
	duration_sec INTEGER COMMENT '用时(秒)',
	finished_at DATETIME COMMENT '完成时间',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='训练会话表' CHARSET=utf8mb4;
CREATE INDEX idx_user_created ON training_session (user_id, created_at);
CREATE TABLE user (
	id BIGINT NOT NULL,
	openid VARCHAR(64) NOT NULL COMMENT '微信 openid',
	union_id VARCHAR(64) COMMENT '微信 unionid',
	account VARCHAR(64) NOT NULL COMMENT '登录账号(唯一)',
	username VARCHAR(64) COMMENT '用户名(显示用，不唯一)',
	password_hash VARCHAR(128) COMMENT '密码哈希',
	nickname VARCHAR(64) COMMENT '昵称',
	email VARCHAR(128) COMMENT '邮箱',
	avatar_url VARCHAR(512) COMMENT '头像 URL(CDN 地址)',
	stage SMALLINT NOT NULL COMMENT '学习阶段: 1=小学,2=初中,3=高中,4=四六级',
	api_key_encrypted VARCHAR(256) COMMENT 'AES 加密后的 API Key',
	api_key_iv VARCHAR(64) COMMENT 'AES 加密 IV',
	`role` VARCHAR(16) COMMENT '角色: student/teacher/admin',
	membership VARCHAR(32) COMMENT '会员类型: free/vip/pro',
	membership_expire DATETIME COMMENT '会员到期时间',
	api_base_url VARCHAR(256) COMMENT 'Base URL',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (openid),
	UNIQUE (account)
)COMMENT='用户表' CHARSET=utf8mb4;
CREATE TABLE user_api_keys (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	key_type VARCHAR(32) NOT NULL COMMENT 'llm/multimodal/embedding',
	encrypted_key VARCHAR(1024) NOT NULL COMMENT 'AES 加密后的 API Key',
	api_base VARCHAR(512) COMMENT '自定义 API Base URL',
	model_name VARCHAR(128) COMMENT '自定义模型名',
	is_valid SMALLINT COMMENT '是否验证通过 0/1',
	created_at DATETIME DEFAULT now(),
	updated_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='用户 API Key 表' CHARSET=utf8mb4;
CREATE INDEX ix_user_api_keys_user_id ON user_api_keys (user_id);
CREATE TABLE user_daily_stats (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	stat_date DATE NOT NULL COMMENT '统计日期',
	words_learned INTEGER COMMENT '学习单词数',
	words_reviewed INTEGER COMMENT '复习单词数',
	quiz_count INTEGER COMMENT '做题数',
	quiz_correct INTEGER COMMENT '正确数',
	study_minutes INTEGER COMMENT '学习时长(分钟)',
	PRIMARY KEY (id)
)COMMENT='每日学习统计表' CHARSET=utf8mb4;
CREATE UNIQUE INDEX uk_user_date ON user_daily_stats (user_id, stat_date);
CREATE TABLE user_document (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	filename VARCHAR(256) NOT NULL COMMENT '原始文件名',
	file_type VARCHAR(16) NOT NULL COMMENT '文件类型: pdf/ppt/word/txt/image',
	file_size INTEGER NOT NULL COMMENT '文件大小(字节)',
	storage_key VARCHAR(512) NOT NULL COMMENT 'MinIO/云存储 对象 key',
	parse_status SMALLINT COMMENT '解析状态: 0=待处理,1=解析中,2=已完成,3=失败',
	parsed_text TEXT COMMENT '解析提取的文本内容',
	vector_status SMALLINT COMMENT '向量化状态: 0=未开始,1=进行中,2=已完成,3=失败',
	chunk_count INTEGER COMMENT '分块数量',
	created_at DATETIME DEFAULT now(),
	file_path VARCHAR(512) COMMENT '本地存储路径(开发用)',
	md_file_path VARCHAR(512) COMMENT 'MinerU 转换后的 Markdown 文件路径',
	ocr_text TEXT COMMENT 'OCR 提取文本(兼容旧字段)',
	doc_category VARCHAR(32) COMMENT '文档分类: exam/teaching_plan/courseware/textbook/reference/other',
	stage_category VARCHAR(16) COMMENT '学段: preschool/primary/junior/senior/other',
	doc_tags VARCHAR(255) COMMENT '自定义标签，逗号分隔，如: 月考,期中,Unit1',
	class_id BIGINT COMMENT '所属班级ID，null=教师私有',
	PRIMARY KEY (id)
)COMMENT='用户上传文档表' CHARSET=utf8mb4;
CREATE INDEX idx_user ON user_document (user_id);
CREATE INDEX idx_user_category ON user_document (user_id, doc_category);
CREATE INDEX idx_user_stage ON user_document (user_id, stage_category);
CREATE INDEX idx_user_type ON user_document (user_id, file_type);
CREATE TABLE user_membership_order (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	plan VARCHAR(32) NOT NULL COMMENT '套餐: vip_student/vip_teacher/vip_teacher_pro',
	order_no VARCHAR(64) NOT NULL COMMENT '商户订单号',
	amount DECIMAL(8, 2) NOT NULL COMMENT '支付金额(元)',
	duration_months INTEGER NOT NULL COMMENT '时长(月)',
	payment_status VARCHAR(16) COMMENT 'pending/paid/refunded/cancelled',
	pay_type VARCHAR(16) COMMENT 'wxpay/redeem',
	paid_at DATETIME COMMENT '支付时间',
	expire_at DATETIME COMMENT '会员到期时间',
	created_at DATETIME COMMENT '创建时间' DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (order_no)
)COMMENT='会员订单表' CHARSET=utf8mb4;
CREATE INDEX ix_user_membership_order_user_id ON user_membership_order (user_id);
CREATE TABLE user_quiz_log (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	session_id BIGINT COMMENT '训练会话ID(training_session.id)',
	question_id BIGINT NOT NULL COMMENT '题目ID',
	question_type SMALLINT NOT NULL COMMENT '题型',
	is_correct SMALLINT NOT NULL COMMENT '0错/1对',
	user_answer JSON COMMENT '用户答案',
	time_spent INTEGER COMMENT '用时(秒)',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id)
)COMMENT='答题记录表' CHARSET=utf8mb4;
CREATE INDEX idx_question ON user_quiz_log (question_id);
CREATE INDEX idx_user_session ON user_quiz_log (user_id, session_id);
CREATE TABLE user_reminders (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	weekdays VARCHAR(20) COMMENT '周一到周日 1-7',
	remind_time VARCHAR(8) COMMENT '提醒时间',
	enabled SMALLINT COMMENT '是否启用 0/1',
	PRIMARY KEY (id),
	UNIQUE (user_id)
);
CREATE TABLE wrong_question (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	question_id BIGINT NOT NULL COMMENT '题目ID',
	question_type SMALLINT NOT NULL COMMENT '题型: 1=单词,2=语法',
	category VARCHAR(64) COMMENT '错题分类: vocabulary/grammar/reading/listening/translation',
	knowledge_point VARCHAR(256) COMMENT '涉及知识点标签，逗号分隔',
	class_id BIGINT COMMENT '所属班级ID，null=全局错题',
	related_word_id INTEGER COMMENT '关联单词ID(dict_word.id)',
	wrong_count INTEGER COMMENT '错误次数',
	last_wrong_at DATETIME NOT NULL COMMENT '最近错误时间',
	mastered SMALLINT COMMENT '是否已掌握 0/1',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_user_question UNIQUE (user_id, question_id)
)COMMENT='错题表' CHARSET=utf8mb4;
CREATE INDEX idx_category ON wrong_question (user_id, category);
CREATE INDEX idx_user_type_mastered ON wrong_question (user_id, question_type, mastered);
