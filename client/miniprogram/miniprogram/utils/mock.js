// Mock 数据 — 纯静态 UI 开发用

module.exports = {
  // ===== 首页 =====
  proverb: {
    en: '"Every dog has his day."',
    zh: '人人皆有得意之日',
    days: 42
  },

  songRecommend: {
    title: 'Shape of You',
    artist: 'Ed Sheeran',
    duration: '3:54',
    cover: '/images/song-cover.png'
  },

  stats: {
    todayWords: 28,
    weekWords: 156,
    accuracy: '82%'
  },

  mistakeCategories: [
    { name: '单词错题', bg: '#EEF2FF', color: '#5B9E6F', count: 3 },
    { name: '语法错题', bg: '#FFF7ED', color: '#F97316', count: 2 }
  ],

  mistakes: [
    { word: 'ephemeral', type: '单词', typeTag: 'tag-primary', errors: 3, time: '今天' },
    { word: 'proficient', type: '单词', typeTag: 'tag-primary', errors: 2, time: '昨天' },
    { word: '虚拟语气', type: '语法', typeTag: 'tag-warning', errors: 4, time: '本周' }
  ],

  // ===== 单词记忆 =====

  // mock 单词列表（与后端 getWordList 返回结构一致）
  wordListData: {
    items: [
      { id: 1, word: 'ephemeral' },
      { id: 2, word: 'proficient' },
      { id: 3, word: 'eloquent' },
      { id: 4, word: 'ambiguous' },
      { id: 5, word: 'resilient' },
      { id: 6, word: 'serendipity' },
      { id: 7, word: 'ubiquitous' },
      { id: 8, word: 'pragmatic' },
      { id: 9, word: 'whimsical' },
      { id: 10, word: 'tenacious' },
    ],
    total: 10,
    total_pages: 1,
  },

  // mock 单词详情映射（id → detail，与后端 getWordDetail 返回结构一致）
  wordDetailMap: {
    1: {
      id: 1, word: 'ephemeral', phonetic: '/ɪˈfem.ər.əl/',
      translation: '短暂的，转瞬即逝的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'The beauty of cherry blossoms is ephemeral, lasting only a few days.', zh: '樱花之美是短暂的，只持续几天。' } },
      synonyms: [
        { synonym_word: 'temporary', tag: '常用', usage_desc: '最常用的"暂时"表达', example: 'a temporary solution' },
        { synonym_word: 'fleeting', tag: '文学', usage_desc: '强调稍纵即逝', example: 'a fleeting moment' },
      ],
      idiom: { en: 'Life is ephemeral, so cherish every moment.', zh: '生命是短暂的，所以要珍惜每一刻。' },
      tag: 'cet6 gre',
    },
    2: {
      id: 2, word: 'proficient', phonetic: '/prəˈfɪʃ.ənt/',
      translation: '熟练的，精通的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'She is proficient in three languages.', zh: '她精通三种语言。' } },
      synonyms: [
        { synonym_word: 'skilled', tag: '常用', usage_desc: '强调具备技能', example: 'a skilled worker' },
      ],
      idiom: { en: 'Practice makes proficient.', zh: '熟能生巧。' },
      tag: 'cet4 cet6',
    },
    3: {
      id: 3, word: 'eloquent', phonetic: '/ˈel.ə.kwənt/',
      translation: '雄辩的，有口才的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'He gave an eloquent speech at the ceremony.', zh: '他在典礼上发表了雄辩的演讲。' } },
      synonyms: [
        { synonym_word: 'articulate', tag: '常用', usage_desc: '表达清晰的', example: 'an articulate speaker' },
      ],
      idiom: { en: 'An eloquent tongue wins hearts.', zh: '雄辩的口才赢得人心。' },
      tag: 'cet6 gre',
    },
    4: {
      id: 4, word: 'ambiguous', phonetic: '/æmˈbɪɡ.ju.əs/',
      translation: '模糊的，含糊不清的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'His reply was deliberately ambiguous.', zh: '他的回答故意含糊其辞。' } },
      synonyms: [
        { synonym_word: 'vague', tag: '常用', usage_desc: '模糊不清的', example: 'a vague description' },
      ],
      idiom: { en: 'Ambiguous words lead to misunderstandings.', zh: '含糊的话会导致误解。' },
      tag: 'cet6 gre',
    },
    5: {
      id: 5, word: 'resilient', phonetic: '/rɪˈzɪl.i.ənt/',
      translation: '有韧性的，能迅速恢复的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'Children are remarkably resilient.', zh: '孩子们有惊人的恢复力。' } },
      synonyms: [
        { synonym_word: 'tough', tag: '口语', usage_desc: '坚韧的', example: 'a tough cookie' },
      ],
      idiom: { en: 'A resilient spirit overcomes all obstacles.', zh: '坚韧的精神克服一切障碍。' },
      tag: 'cet6',
    },
    6: {
      id: 6, word: 'serendipity', phonetic: '/ˌser.ənˈdɪp.ə.ti/',
      translation: '意外发现珍奇事物的本领，机缘巧合',
      pos: 'n.',
      exchange: 'd:/',
      detail_json: { example: { en: 'Finding that book was pure serendipity.', zh: '发现那本书纯属机缘巧合。' } },
      idiom: { en: 'Serendipity is the art of finding what you are not looking for.', zh: '机缘巧合是发现你并未寻找之物的艺术。' },
      tag: 'gre',
    },
    7: {
      id: 7, word: 'ubiquitous', phonetic: '/juːˈbɪk.wɪ.təs/',
      translation: '无处不在的，普遍存在的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'Smartphones have become ubiquitous in modern life.', zh: '智能手机在现代生活中已无处不在。' } },
      idiom: { en: 'Change is ubiquitous; embrace it.', zh: '变化无处不在，拥抱它。' },
      tag: 'cet6 gre',
    },
    8: {
      id: 8, word: 'pragmatic', phonetic: '/præɡˈmæt.ɪk/',
      translation: '务实的，实用主义的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'We need a pragmatic approach to solve this problem.', zh: '我们需要一个务实的方法来解决这个问题。' } },
      idiom: { en: 'Pragmatic thinking turns ideas into reality.', zh: '务实思维将想法变为现实。' },
      tag: 'cet6 gre',
    },
    9: {
      id: 9, word: 'whimsical', phonetic: '/ˈwɪm.zɪ.kəl/',
      translation: '异想天开的，古怪的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'The garden has a whimsical charm.', zh: '这座花园有一种异想天开的魅力。' } },
      idiom: { en: 'A whimsical mind creates the most beautiful art.', zh: '异想天开的头脑创造最美的艺术。' },
      tag: 'gre',
    },
    10: {
      id: 10, word: 'tenacious', phonetic: '/tɪˈneɪ.ʃəs/',
      translation: '坚韧的，顽强的',
      pos: 'adj.',
      exchange: 'd:/',
      detail_json: { example: { en: 'She is a tenacious defender of human rights.', zh: '她是一位坚韧的人权捍卫者。' } },
      idiom: { en: 'Tenacity is the mother of success.', zh: '坚韧是成功之母。' },
      tag: 'cet6 gre',
    },
  },

  // 旧字段保留兼容
  wordList: ['ephemeral', 'proficient', 'eloquent', 'ambiguous', 'resilient'],

  // ===== 情景记忆 =====
  scenarioWords: ['ephemeral', 'proficient', 'eloquent', 'ambiguous', 'resilient'],

  scenarioText: 'In the {ephemeral} glow of sunset, a {proficient} musician played a haunting melody. Her {eloquent} performance captivated everyone, making the {ambiguous} lyrics feel deeply personal. Like a {resilient} flower blooming in harsh conditions, her art reminded us that beauty can thrive anywhere.',

  // ===== 收藏 =====
  favorites: {
    words: [
      { word: 'ephemeral', phonetic: '/ɪˈfem.ər.əl/', meaning: '短暂的' },
      { word: 'proficient', phonetic: '/prəˈfɪʃ.ənt/', meaning: '熟练的' },
      { word: 'resilient', phonetic: '/rɪˈzɪl.i.ənt/', meaning: '有韧性的' }
    ],
    articles: [],
    passages: [],
    songs: []
  },

  // ===== 训练 =====
  quizQuestion: {
    type: '翻译题',
    question: '"ephemeral" 的意思是？',
    options: ['永久的', '短暂的', '重要的', '复杂的'],
    correctIndex: 1,
    analysis: {
      meaning: 'ephemeral 意为"短暂的、转瞬即逝的"',
      example: 'The ephemeral beauty of cherry blossoms reminds us to appreciate the present.',
      tip: '联想记忆：ephemer- (短暂) + -al (形容词后缀)'
    }
  },

  phraseQuestion: {
    type: '语法题',
    subType: '固定搭配',
    question: 'She is interested ____ learning foreign languages.',
    hint: '请选择正确的介词填空',
    options: ['at', 'in', 'on', 'for'],
    correctIndex: 1,
    analysis: {
      rule: 'be interested in 是固定搭配，表示"对……感兴趣"',
      example: 'She is interested in photography and painting.',
      similar: ['be keen on', 'be fond of', 'be enthusiastic about']
    }
  },

  sentenceQuestion: {
    direction: '中译英',
    chinese: '尽管天气恶劣，他们还是按时完成了任务。',
    keywords: [
      { word: 'despite', bg: '#FFF7ED', color: '#F97316' },
      { word: 'on time', bg: '#EEF2FF', color: '#5B9E6F' }
    ],
    reference: 'Despite the bad weather, they completed the task on time.',
    keyPoints: [
      'despite + 名词/动名词，不接 of',
      'on time 准时，in time 及时',
      'complete the task 完成任务',
      'bad weather 恶劣天气'
    ],
    alternative: 'In spite of the terrible weather, they finished the work on schedule.'
  },

  readingArticle: {
    source: '2023年英语六级真题 · Passage 1',
    paragraphs: [
      'The global shift towards renewable energy has accelerated dramatically in recent years. According to the International Energy Agency, renewable energy sources now account for nearly 30% of global electricity generation, a figure that has doubled in just one decade.',
      'Solar and wind power have been the primary drivers of this transformation. The cost of solar energy has dropped by 73% since 2010, making it one of the most cost-effective energy sources available today. Similarly, wind power capacity has expanded rapidly, with offshore wind farms becoming increasingly common.',
      'Despite these positive trends, challenges remain. Energy storage technology needs further development to address the intermittent nature of renewable sources. Grid infrastructure must be upgraded to handle the distributed generation model that renewables require.'
    ],
    highlight: 'renewable energy sources now account for nearly 30% of global electricity generation',
    question: 'According to the passage, what percentage of global electricity generation comes from renewable sources?',
    options: ['53%', '63%', '73%', '83%'],
    correctIndex: 2,
    analysis: {
      answer: 'C. 73%',
      explanation: '原文指出 "renewable energy sources now account for nearly 30% of global electricity generation"，题目问的是太阳能成本下降百分比（73%），注意区分。'
    }
  },

  listeningQuestion: {
    type: '听力选择题',
    level: '六级听力',
    question: 'What is the main topic of the conversation?',
    options: [
      'The benefits of studying abroad',
      'How to apply for a scholarship',
      'The challenges of living in a foreign country',
      'Tips for learning a new language'
    ],
    correctIndex: 0,
    duration: '2:35'
  },

  // ===== 智能对话 =====
  chatMessages: [
    {
      role: 'ai',
      content: '你好！我是你的英语学习助手 E-Learning\n\n请输入你想了解的英语知识点，我来帮你解答～'
    },
    {
      role: 'user',
      content: '我想学习虚拟语气的用法'
    },
    {
      role: 'ai',
      content: '**虚拟语气 (Subjunctive Mood)**\n\n虚拟语气用来表达假设、愿望、建议等非真实情况。\n\n**基本结构：**\n1. 与现在事实相反：If + 过去式, would + 动词原形\n2. 与过去事实相反：If + had + 过去分词, would have + 过去分词\n\n**例句：**\n• If I were you, I would study harder.\n• If she had known, she would have come earlier.'
    }
  ],

  translateResult: {
    input: '学习英语不仅仅是关于语法和词汇，更重要的是培养一种思维方式。',
    output: 'Learning English is not just about grammar and vocabulary, but more importantly about developing a way of thinking.'
  },

  // ===== 个人中心 =====
  profile: {
    name: '小明同学',
    email: 'xiaoming@example.com',
    phase: '四六级',
    days: 42,
    totalWords: 1280,
    totalTraining: 56
  },

  // 学习阶段列表（四个阶段）
  studyPhases: ['小学', '初中', '高中', '四六级'],

  // 星期
  weekdays: [
    { label: '一', active: true },
    { label: '二', active: true },
    { label: '三', active: true },
    { label: '四', active: true },
    { label: '五', active: true },
    { label: '六', active: false },
    { label: '日', active: false }
  ]
};