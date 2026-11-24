CREATE TABLE dict_root (
	id INTEGER NOT NULL AUTO_INCREMENT,
	root VARCHAR(64) NOT NULL COMMENT '词根/词缀',
	root_type VARCHAR(16) NOT NULL COMMENT 'prefix/root/suffix',
	meaning VARCHAR(256) COMMENT '含义',
	origin VARCHAR(64) COMMENT '语源(拉丁/希腊等)',
	PRIMARY KEY (id)
)COMMENT='词根词缀表' CHARSET=utf8mb4;
CREATE INDEX ix_dict_root_root ON dict_root (root);
CREATE TABLE dict_word (
	id INTEGER NOT NULL AUTO_INCREMENT,
	word VARCHAR(128) NOT NULL COMMENT '单词',
	sw VARCHAR(128) NOT NULL COMMENT '模糊匹配键',
	phonetic VARCHAR(128) COMMENT '音标',
	definition TEXT COMMENT '英文释义',
	translation TEXT COMMENT '中文释义',
	pos VARCHAR(128) COMMENT '词性占比, 如 n:46/v:54',
	collins SMALLINT COMMENT '柯林斯星级 1-5',
	oxford SMALLINT COMMENT '牛津三千核心词 0/1',
	tag VARCHAR(256) COMMENT '考试标签, 如 cet4 zk gk',
	bnc INTEGER COMMENT '英国国家语料库词频排名',
	frq INTEGER COMMENT '当代语料库词频排名',
	exchange VARCHAR(256) COMMENT '词形变化, 如 d:perceived/p:perceived',
	audio_url VARCHAR(512) COMMENT '发音音频 URL',
	detail_json JSON COMMENT '扩展信息（词根、近义词、记忆金句等）',
	PRIMARY KEY (id),
	UNIQUE (word)
)COMMENT='词典主表(ECDICT)' CHARSET=utf8mb4;
CREATE INDEX idx_collins ON dict_word (collins);
CREATE INDEX idx_sw ON dict_word (sw);
CREATE INDEX idx_tag ON dict_word (tag(64));
CREATE INDEX ix_dict_word_sw ON dict_word (sw);
CREATE TABLE dict_word_root (
	id INTEGER NOT NULL AUTO_INCREMENT,
	word_id INTEGER NOT NULL COMMENT '关联 dict_word.id',
	root_id INTEGER NOT NULL COMMENT '关联 dict_root.id',
	position SMALLINT COMMENT '在单词中的位置顺序',
	PRIMARY KEY (id)
)COMMENT='单词-词根关联表' CHARSET=utf8mb4;
CREATE INDEX ix_dict_word_root_root_id ON dict_word_root (root_id);
CREATE INDEX ix_dict_word_root_word_id ON dict_word_root (word_id);
CREATE TABLE stage_word (
	id BIGINT NOT NULL,
	word_id INTEGER NOT NULL COMMENT '关联 dict_word.id',
	stage SMALLINT NOT NULL COMMENT '学习阶段: 1=小学,2=初中,3=高中,4=四六级',
	mastery_order INTEGER COMMENT '同阶段内掌握顺序',
	PRIMARY KEY (id),
	CONSTRAINT uk_word_stage UNIQUE (word_id, stage)
)COMMENT='阶段-单词映射表' CHARSET=utf8mb4;
CREATE INDEX idx_stage_order ON stage_word (stage, mastery_order);
CREATE TABLE user_word_progress (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL COMMENT '用户ID',
	word_id INTEGER NOT NULL COMMENT '单词ID(dict_word.id)',
	mastery_level SMALLINT COMMENT '0未学/1认识/2熟悉/3掌握',
	review_count INTEGER COMMENT '复习次数',
	last_reviewed_at DATETIME COMMENT '最后复习时间',
	created_at DATETIME DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_user_word UNIQUE (user_id, word_id)
)COMMENT='用户单词学习进度' CHARSET=utf8mb4;
CREATE INDEX idx_user_mastery ON user_word_progress (user_id, mastery_level);
CREATE TABLE word_synonyms (
	id BIGINT NOT NULL,
	word_id BIGINT NOT NULL COMMENT '单词ID',
	synonym_word VARCHAR(128) NOT NULL COMMENT '近义词',
	tag VARCHAR(64) COMMENT '辨析标签',
	usage_desc TEXT COMMENT '用法说明',
	example TEXT COMMENT '辨析例句',
	PRIMARY KEY (id)
)COMMENT='近义词辨析表' CHARSET=utf8mb4;
CREATE INDEX ix_word_synonyms_word_id ON word_synonyms (word_id);
