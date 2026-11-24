// 云函数 - 训练/出题（通过 import-dict 查询 MySQL 数据，AI 丰富单词）
const cloud = require('wx-server-sdk');
const tcb = require('@cloudbase/node-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();
const _ = db.command;

// CloudBase Node SDK 初始化（用于 AI）
const cbApp = tcb.init({ env: 'cloud1-d0g0f3q7g8d2bb58f' });

// 题型模板
const QUIZ_TEMPLATES = {
  '单词选择题': (w) => ({
    type: '翻译题',
    question: `"${w.word}" 的意思是？`,
    correctAnswer: w.meaning,
    generateOptions: (allWords) => {
      const others = allWords.filter(x => x.word !== w.word).slice(0, 3).map(x => x.meaning);
      const options = [...others, w.meaning].sort(() => Math.random() - 0.5);
      return { options, correctIndex: options.indexOf(w.meaning) };
    }
  }),
  '英译中选择题': (w) => ({
    type: '英译中',
    question: `将 "${w.word}" 翻译成中文`,
    correctAnswer: w.meaning,
    generateOptions: (allWords) => {
      const others = allWords.filter(x => x.word !== w.word).slice(0, 3).map(x => x.meaning);
      const options = [...others, w.meaning].sort(() => Math.random() - 0.5);
      return { options, correctIndex: options.indexOf(w.meaning) };
    }
  }),
  '中译英选择题': (w) => ({
    type: '中译英',
    question: `"${w.meaning}" 对应的英文是？`,
    correctAnswer: w.word,
    generateOptions: (allWords) => {
      const others = allWords.filter(x => x.word !== w.word).slice(0, 3).map(x => x.word);
      const options = [...others, w.word].sort(() => Math.random() - 0.5);
      return { options, correctIndex: options.indexOf(w.word) };
    }
  }),
  '例句填空题': (w) => ({
    type: '填空题',
    question: w.example ? w.example.en.replace(w.word, '______') : `补全单词：______ 意为"${w.meaning}"`,
    correctAnswer: w.word,
    generateOptions: (allWords) => {
      const others = allWords.filter(x => x.word !== w.word).slice(0, 3).map(x => x.word);
      const options = [...others, w.word].sort(() => Math.random() - 0.5);
      return { options, correctIndex: options.indexOf(w.word) };
    }
  })
};

exports.main = async (event, context) => {
  const wxContext = cloud.getWXContext();
  const openid = wxContext.OPENID;
  const { action } = event;

  try {
    switch (action) {
      case 'getQuestion':
        return await getQuestion(event, openid);
      case 'getStats':
        return await getStats(openid);
      case 'getUserStats':
        return await getUserStats(openid);
      case 'getWordList':
        return await getWordList(event);
      case 'getWordDetail':
        return await getWordDetail(event);
      default:
        return { code: -1, message: '未知操作' };
    }
  } catch (err) {
    console.error('quiz function error:', err);
    return { code: -1, message: err.message };
  }
};

/**
 * 调用 import-dict 云函数查询 MySQL 数据
 */
async function callImportDict(params) {
  const res = await cloud.callFunction({
    name: 'import-dict',
    data: params
  });
  if (res.result && res.result.code === 0) {
    return res.result;
  }
  throw new Error(res.result?.message || 'import-dict 调用失败');
}

async function getQuestion(event, openid) {
  const { quizType = '单词选择题', phase = '英语四级' } = event;

  // 从 MySQL 获取随机单词（通过 import-dict 云函数）
  const result = await callImportDict({
    action: 'getQuizWords',
    phase,
    limit: 20
  });

  const allWords = result.data;

  if (allWords.length < 4) {
    return { code: -1, message: '单词数据不足，请稍后再试' };
  }

  // 获取用户已做错的词，优先出这些题
  let targetWords = allWords;
  try {
    const mistakesRes = await db.collection('mistakes')
      .where({ _openid: openid })
      .orderBy('errors', 'desc')
      .limit(5)
      .get();

    if (mistakesRes.data.length > 0) {
      const mistakeWordTexts = mistakesRes.data.map(m => m.word);
      const mistakeWords = allWords.filter(w => mistakeWordTexts.includes(w.word));
      const normalWords = allWords.filter(w => !mistakeWordTexts.includes(w.word));
      targetWords = Math.random() < 0.6 && mistakeWords.length > 0
        ? mistakeWords
        : normalWords.length > 0 ? normalWords : allWords;
    }
  } catch (e) {
    // mistakes 集合可能不存在，忽略
  }

  // 随机选题
  const randomIndex = Math.floor(Math.random() * targetWords.length);
  const selectedWord = targetWords[randomIndex];

  // 根据题型生成
  const template = QUIZ_TEMPLATES[quizType] || QUIZ_TEMPLATES['单词选择题'];
  const quiz = template(selectedWord);
  const { options, correctIndex } = quiz.generateOptions(allWords);

  return {
    code: 0,
    data: {
      type: quiz.type,
      question: quiz.question,
      options,
      correctIndex,
      analysis: {
        meaning: `${selectedWord.word} ${selectedWord.meaning}`,
        example: '',
        tip: ''
      },
      word: selectedWord.word
    }
  };
}

async function getWordList(event) {
  const { phase = '英语四级', page = 1, pageSize = 20 } = event;

  const result = await callImportDict({
    action: 'getWordList',
    phase,
    page,
    pageSize
  });

  // 只返回小程序需要的字段
  const data = result.data.map(w => ({
    word: w.word,
    phonetic: w.phonetic,
    pos: w.pos,
    meaning: w.meaning
  }));

  return { code: 0, data };
}

async function getWordDetail(event) {
  const { word } = event;
  if (!word) return { code: -1, message: 'word is required' };

  // 1. 先查 NoSQL 缓存
  let enrichment = null;
  try {
    const cacheRes = await db.collection('word_enrichment')
      .where({ word })
      .limit(1)
      .get();
    if (cacheRes.data && cacheRes.data.length > 0) {
      enrichment = cacheRes.data[0].enrichment;
    }
  } catch (e) {
    console.error('cache read error:', e.message);
  }

  // 2. 从 MySQL 获取基础数据
  const result = await callImportDict({
    action: 'getWordDetail',
    word
  });

  if (!enrichment) {
    // 3. 无缓存，调用 AI 丰富
    try {
      enrichment = await aiEnrichWord(word, result.data);
      // 4. 写入缓存
      try {
        await db.collection('word_enrichment').add({
          data: { word, enrichment, createdAt: new Date() }
        });
      } catch (cacheWriteErr) {
        console.error('cache write error:', cacheWriteErr.message);
      }
    } catch (aiErr) {
      console.error('AI enrich failed:', aiErr.message);
      enrichment = buildFallbackEnrichment(result.data);
    }
  }

  return { code: 0, data: { ...result.data, ...enrichment } };
}

/**
 * 使用 CloudBase AI 丰富单词数据
 */
async function aiEnrichWord(word, baseData) {
  const mainMeaning = extractMainMeaning(baseData.translation || baseData.meaning || '');

  const ai = cbApp.ai();
  const model = ai.createModel('cloudbase');

  const prompt = `你是英语学习助手。请为单词 "${word}"（释义：${mainMeaning}）生成以下学习内容，严格按 JSON 格式输出，不要有任何其他文字：

{
  "example": {
    "en": "一句包含该单词的英文例句",
    "zh": "例句的中文翻译"
  },
  "roots": [
    {"pos": "词性缩写", "word": "派生词"}
  ],
  "synonyms": [
    {"word": "近义词", "tag": "常用/文学/正式", "usage": "用法简述", "example": "例句"}
  ],
  "idiom": {
    "en": "一句包含该单词的记忆金句（名人名言或实用句）",
    "zh": "金句的中文翻译"
  }
}

要求：
- example 中的例句要地道、实用，难度适中
- roots 列出2-3个常见派生词（如名词形式、副词形式等）
- synonyms 列出2个近义词，含用法辨析和例句
- idiom 金句要有助记忆，简洁有力
- 严格输出 JSON，不要有 markdown 标记`;

  const result = await model.generateText({
    model: 'deepseek-v4-flash',
    messages: [{ role: 'user', content: prompt }]
  });

  let parsed = {};
  try {
    let text = result.text || '';
    text = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
    parsed = JSON.parse(text);
  } catch (e) {
    console.error('AI JSON parse failed:', e.message);
    return buildFallbackEnrichment(baseData);
  }

  // 验证并补充默认值
  if (!parsed.example || !parsed.example.en) {
    parsed.example = { en: `The word "${word}" is commonly used in daily life.`, zh: `"${word}" 这个词在日常生活中很常用。` };
  }
  if (!Array.isArray(parsed.roots)) parsed.roots = [];
  if (!Array.isArray(parsed.synonyms)) parsed.synonyms = [];
  if (!parsed.idiom || !parsed.idiom.en) {
    parsed.idiom = { en: `Remember "${word}" - ${mainMeaning}.`, zh: `记住 "${word}" - ${mainMeaning}。` };
  }

  // 合并 derivatives（从 exchange 解析）到 roots
  if (baseData.derivatives && baseData.derivatives.length > 0) {
    const existingRootWords = parsed.roots.map(r => r.word);
    for (const d of baseData.derivatives) {
      if (!existingRootWords.includes(d.word)) {
        parsed.roots.push({ pos: d.pos, word: d.word });
      }
    }
  }

  return parsed;
}

/**
 * 提取主要中文释义
 */
function extractMainMeaning(translation) {
  if (!translation) return '';
  const firstLine = translation.split('\n')[0];
  return firstLine.replace(/\[.*?\]/g, '').trim();
}

/**
 * 构建降级版丰富数据（AI 不可用时）
 */
function buildFallbackEnrichment(baseData) {
  const word = baseData.word || '';
  const mainMeaning = extractMainMeaning(baseData.translation || baseData.meaning || '');
  const derivatives = baseData.derivatives || [];
  const roots = derivatives.map(d => ({ pos: d.pos, word: d.word }));

  return {
    example: { en: `This is a sentence with "${word}".`, zh: `这是一个包含 "${word}" 的句子。` },
    roots,
    synonyms: [],
    idiom: { en: `Remember "${word}" - ${mainMeaning}.`, zh: `记住 "${word}" - ${mainMeaning}。` }
  };
}

async function getStats(openid) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const todayRecords = await db.collection('quiz_records')
    .where({
      _openid: openid,
      createdAt: _.gte(today)
    })
    .get();

  const todayTotal = todayRecords.data.length;
  const todayCorrect = todayRecords.data.filter(r => r.isCorrect).length;

  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - weekStart.getDay());

  const weekRecords = await db.collection('quiz_records')
    .where({
      _openid: openid,
      createdAt: _.gte(weekStart)
    })
    .get();

  const weekTotal = weekRecords.data.length;
  const weekCorrect = weekRecords.data.filter(r => r.isCorrect).length;

  return {
    code: 0,
    data: {
      todayWords: todayTotal,
      weekWords: weekTotal,
      accuracy: weekTotal > 0 ? Math.round(weekCorrect / weekTotal * 100) + '%' : '0%'
    }
  };
}

async function getUserStats(openid) {
  const stats = await getStats(openid);

  const mistakes = await db.collection('mistakes')
    .where({ _openid: openid })
    .get();

  const categories = {};
  mistakes.data.forEach(m => {
    const cat = m.type || '单词';
    categories[cat] = (categories[cat] || 0) + 1;
  });

  const mistakeCategories = Object.entries(categories).map(([name, count]) => ({
    name: name + '错题',
    bg: name === '单词' ? '#EEF2FF' : '#FFF7ED',
    color: name === '单词' ? '#5B9E6F' : '#F97316',
    count
  }));

  return {
    code: 0,
    data: {
      ...stats.data,
      mistakeCategories,
      mistakes: mistakes.data.slice(0, 10).map(m => ({
        word: m.word,
        type: m.type || '单词',
        typeTag: m.type === '语法' ? 'tag-warning' : 'tag-primary',
        errors: m.errors,
        time: m.lastTime || '最近'
      }))
    }
  };
}
