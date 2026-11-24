'use strict';

/**
 * 云函数：import-dict
 * 批量导入词条数据到 MySQL dict_word 表
 * 
 * 调用方式：
 * - action = 'import': 批量插入 (rows = [{word, sw, ...}])
 * - action = 'importFromUrl': 从 URL 下载 JSON 数据并导入 (url, batchSize)
 * - action = 'count': 查询当前总数
 */

const cloudbase = require('@cloudbase/node-sdk');
const app = cloudbase.init({
  env: cloudbase.SYMBOL_CURRENT_ENV
});

const ENV_ID = 'cloud1-d0g0f3q7g8d2bb58f';

// phase 中文 → MySQL stage 映射（精简为四个阶段）
const PHASE_STAGE_MAP = {
  '启蒙': 1, '英语启蒙': 1,
  '小学三年级': 1, '小学英语': 1, '小学四年级': 1, '小学五年级': 1,
  '初中一年级': 2, '初中英语': 2, '初中二年级': 2,
  '初中三年级': 2,
  '高中英语': 3, '高中一年级': 3, '高中二年级': 3, '高中三年级': 3,
  '英语四级': 4, '英语六级': 4, '考研英语': 4,
  '托福': 4, '雅思': 4, 'GRE': 4,
};

function phaseToStage(phase) {
  return PHASE_STAGE_MAP[phase] || 4;
}

exports.main = async (event, context) => {
  const { action, rows, url, batchSize, phase, stage, word, page, pageSize, limit, offset } = event;

  switch (action) {
    case 'import':
      return await batchImport(rows);
    case 'importFromUrl':
      return await importFromUrl(url, batchSize);
    case 'count':
      return await countWords();
    case 'getWordList':
      return await getWordList(phase || '英语四级', page || 1, pageSize || 20);
    case 'getWordDetail':
      return await getWordDetail(word);
    case 'enrichWord':
      return await enrichWord(word);
    case 'getQuizWords':
      return await getQuizWords(phase || '英语四级', limit || 20);
    default:
      return { code: -1, message: `Unknown action: ${action}` };
  }
};

/**
 * 从 URL 下载 JSON 数据并分批导入
 */
async function importFromUrl(dataUrl, batchSize = 20) {
  if (!dataUrl) {
    return { code: -1, message: 'url is required' };
  }

  try {
    // 下载 JSON 数据
    const https = require('https');
    const http = require('http');
    const client = dataUrl.startsWith('https') ? https : http;
    
    const data = await new Promise((resolve, reject) => {
      client.get(dataUrl, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(new Error(`Failed to parse JSON: ${e.message}`));
          }
        });
        res.on('error', reject);
      }).on('error', reject);
    });

    if (!Array.isArray(data)) {
      return { code: -1, message: 'JSON data must be an array' };
    }

    console.log(`Downloaded ${data.length} records from ${dataUrl}`);
    
    // 分批导入
    const result = await batchImport(data, batchSize);
    return { ...result, totalDownloaded: data.length };
  } catch (e) {
    return { code: -1, message: e.message, stack: e.stack };
  }
}

/**
 * 批量导入词条 - 使用 REST API POST
 */
async function batchImport(rows, batchSize = 20) {
  if (!rows || !Array.isArray(rows) || rows.length === 0) {
    return { code: -1, message: 'rows is required and must be a non-empty array' };
  }

  const BATCH_SIZE = batchSize || 20;
  let inserted = 0;
  let failed = 0;
  let skipped = 0;
  let errors = [];

  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);
    
    const records = batch.map(row => ({
      _openid: '',
      word: (row.word || '').substring(0, 128),
      sw: (row.sw || '').substring(0, 128),
      phonetic: (row.phonetic || '').substring(0, 128),
      definition: row.definition || '',
      translation: row.translation || '',
      pos: (row.pos || '').substring(0, 64),
      collins: parseInt(row.collins, 10) || 0,
      oxford: parseInt(row.oxford, 10) || 0,
      tag: (row.tag || '').substring(0, 128),
      bnc: parseFloat(row.bnc) || 0,
      frq: parseFloat(row.frq) || 0,
      exchange: row.exchange || '',
      audio_url: ''
    }));

    try {
      const db = app.rdb();
      const table = db.from('dict_word');
      
      const response = await table.fetch(table.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Prefer': 'return=representation',
          'Prefer': 'resolution=merge-duplicates'
        },
        body: JSON.stringify(records)
      });
      
      if (response.ok || response.status === 201) {
        inserted += records.length;
      } else if (response.status === 409) {
        // 重复词条 - 逐条插入，跳过已有的
        for (const record of records) {
          try {
            const singleResp = await table.fetch(table.url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(record)
            });
            if (singleResp.ok || singleResp.status === 201) {
              inserted++;
            } else {
              skipped++;
            }
          } catch (e) {
            skipped++;
          }
        }
      } else {
        const text = await response.text();
        failed += records.length;
        errors.push(`HTTP ${response.status}: ${text.substring(0, 200)}`);
        if (errors.length > 5) break;
      }
    } catch (e) {
      failed += records.length;
      errors.push(e.message);
      if (errors.length > 5) break;
    }
  }

  return { code: 0, inserted, failed, skipped, errors: errors.slice(0, 5) };
}

/**
 * 查询当前词条总数
 */
async function countWords() {
  try {
    const db = app.rdb();
    const table = db.from('dict_word');
    
    const url = new URL(table.url.toString());
    url.searchParams.set('select', 'id');
    url.searchParams.set('limit', '1');
    
    const response = await table.fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Prefer': 'count=exact'
      }
    });
    
    if (response.ok) {
      const contentRange = response.headers.get('content-range');
      let total = 0;
      if (contentRange) {
        const parts = contentRange.split('/');
        total = parseInt(parts[1], 10) || 0;
      }
      const data = await response.json();
      return { code: 0, total, sampleCount: Array.isArray(data) ? data.length : 0 };
    } else {
      const text = await response.text();
      return { code: -1, message: `HTTP ${response.status}: ${text.substring(0, 300)}` };
    }
  } catch (e) {
    return { code: -1, message: e.message };
  }
}

/**
 * 查询单词列表（按 phase/stage 分页）
 */
async function getWordList(phase, page = 1, pageSize = 20) {
  try {
    const targetStage = phaseToStage(phase);
    const rdb = app.rdb();

    // 1. 查 stage_word 获取 word_id 列表
    const stageTable = rdb.from('stage_word');
    const stageUrl = new URL(stageTable.url.toString());
    stageUrl.searchParams.set('stage', `eq.${targetStage}`);
    stageUrl.searchParams.set('select', 'word_id');
    stageUrl.searchParams.set('limit', String(pageSize));
    stageUrl.searchParams.set('offset', String((page - 1) * pageSize));
    stageUrl.searchParams.set('order', 'id.asc');

    const stageResp = await stageTable.fetch(stageUrl.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!stageResp.ok) {
      const text = await stageResp.text();
      return { code: -1, message: `stage_word query failed: HTTP ${stageResp.status}` };
    }

    const stageRows = await stageResp.json();
    if (!stageRows.length) return { code: 0, data: [] };

    // 2. 批量查 dict_word
    const wordIds = stageRows.map(r => r.word_id);
    const dictTable = rdb.from('dict_word');
    const dictUrl = new URL(dictTable.url.toString());
    dictUrl.searchParams.set('id', `in.(${wordIds.join(',')})`);
    dictUrl.searchParams.set('select', 'id,word,phonetic,translation,pos,tag,definition,exchange');

    const dictResp = await dictTable.fetch(dictUrl.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!dictResp.ok) {
      return { code: -1, message: `dict_word query failed: HTTP ${dictResp.status}` };
    }

    const rows = await dictResp.json();
    const data = rows.map(formatWord);
    return { code: 0, data };
  } catch (e) {
    return { code: -1, message: e.message };
  }
}

/**
 * 查询单词详情（含 AI 丰富内容，优先读缓存）
 */
async function getWordDetail(word) {
  try {
    if (!word) return { code: -1, message: 'word is required' };

    // 先查 NoSQL 缓存
    const db = app.database();
    const cacheRes = await db.collection('word_enrichment')
      .where({ word })
      .limit(1)
      .get();

    const baseData = await getWordDetailFromDB(word);
    if (!baseData) return { code: -1, message: '单词未找到' };

    if (cacheRes.data && cacheRes.data.length > 0) {
      // 有缓存，合并返回
      const enrichment = cacheRes.data[0].enrichment || {};
      return { code: 0, data: { ...baseData, ...enrichment } };
    }

    // 无缓存，返回基础数据（前端可按需调用 enrichWord）
    return { code: 0, data: baseData };
  } catch (e) {
    return { code: -1, message: e.message };
  }
}

/**
 * 获取随机出题单词（随机偏移量）
 */
async function getQuizWords(phase, limit = 20) {
  try {
    const targetStage = phaseToStage(phase);
    const rdb = app.rdb();
    const stageTable = rdb.from('stage_word');

    // 1. 获取总数
    const countUrl = new URL(stageTable.url.toString());
    countUrl.searchParams.set('stage', `eq.${targetStage}`);
    countUrl.searchParams.set('select', 'id');
    countUrl.searchParams.set('limit', '1');

    const countResp = await stageTable.fetch(countUrl.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json', 'Prefer': 'count=exact' }
    });

    if (!countResp.ok) {
      return { code: -1, message: 'count query failed' };
    }

    let totalCount = 0;
    const contentRange = countResp.headers.get('content-range');
    if (contentRange) {
      totalCount = parseInt(contentRange.split('/')[1], 10) || 0;
    }

    if (totalCount === 0) return { code: 0, data: [] };

    // 2. 随机偏移量
    const maxOffset = Math.max(0, totalCount - limit);
    const randomOffset = Math.floor(Math.random() * (maxOffset + 1));

    // 3. 查询
    const stageUrl = new URL(stageTable.url.toString());
    stageUrl.searchParams.set('stage', `eq.${targetStage}`);
    stageUrl.searchParams.set('select', 'word_id');
    stageUrl.searchParams.set('limit', String(limit));
    stageUrl.searchParams.set('offset', String(randomOffset));
    stageUrl.searchParams.set('order', 'id.asc');

    const stageResp = await stageTable.fetch(stageUrl.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!stageResp.ok) return { code: -1, message: 'stage query failed' };

    const stageRows = await stageResp.json();
    if (!stageRows.length) return { code: 0, data: [] };

    // 4. 查 dict_word
    const wordIds = stageRows.map(r => r.word_id);
    const dictTable = rdb.from('dict_word');
    const dictUrl = new URL(dictTable.url.toString());
    dictUrl.searchParams.set('id', `in.(${wordIds.join(',')})`);
    dictUrl.searchParams.set('select', 'id,word,phonetic,translation,pos,tag,definition,exchange');

    const dictResp = await dictTable.fetch(dictUrl.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!dictResp.ok) return { code: -1, message: 'dict query failed' };

    const rows = await dictResp.json();
    const data = rows.map(formatWord);
    return { code: 0, data };
  } catch (e) {
    return { code: -1, message: e.message };
  }
}

/**
 * 解析 pos 字段为可读词性标签
 * 格式: "n:100" / "v:96" / "j:100" (j=adj)
 */
function parsePos(posStr) {
  if (!posStr) return '';
  const posMap = { n: 'n.', v: 'v.', j: 'adj.', a: 'adj.', r: 'adv.', d: 'adv.' };
  const parts = posStr.split('/').filter(Boolean);
  const labels = [];
  for (const part of parts) {
    const [code] = part.split(':');
    if (posMap[code]) labels.push(posMap[code]);
  }
  return labels.length ? labels.join(' ') : '';
}

/**
 * 解析 exchange 字段为词形变化
 * 格式: "d:abandoned/p:abandoned/i:abandoning/3:abandons/s:abandons"
 */
function parseExchange(exchangeStr) {
  if (!exchangeStr) return [];
  const labelMap = { p: '过去式', d: '过去分词', i: '现在分词', '3': '第三人称单数', s: '复数', r: '比较级', t: '最高级' };
  const results = [];
  for (const part of exchangeStr.split('/')) {
    const [code, form] = part.split(':');
    if (form && labelMap[code]) {
      results.push({ pos: labelMap[code], word: form });
    }
  }
  return results;
}

/**
 * 提取主要中文释义（取第一条，去除括号标注）
 */
function extractMainMeaning(translation) {
  if (!translation) return '';
  const firstLine = translation.split('\n')[0];
  return firstLine.replace(/\[.*?\]/g, '').trim();
}

/**
 * 格式化 MySQL 单词记录（基础版，不含AI丰富内容）
 */
function formatWord(row) {
  const meaning = row.translation || row.definition || '';
  const cleanPos = parsePos(row.pos);
  const derivatives = parseExchange(row.exchange);
  return {
    word: row.word,
    phonetic: row.phonetic || '',
    meaning,
    pos: cleanPos,
    definition: row.definition || '',
    translation: row.translation || '',
    tag: row.tag || '',
    derivatives,
    example: null,
    roots: null,
    synonyms: null,
    idiom: null
  };
}

/**
 * 使用 AI 丰富单词数据（例句、词根、近义词、记忆金句）
 * 结果缓存到 NoSQL word_enrichment 集合
 */
async function enrichWord(word) {
  if (!word) return { code: -1, message: 'word is required' };

  try {
    // 1. 检查 NoSQL 缓存
    const db = app.database();
    const cacheRes = await db.collection('word_enrichment')
      .where({ word })
      .limit(1)
      .get();

    if (cacheRes.data && cacheRes.data.length > 0) {
      const cached = cacheRes.data[0];
      // 缓存存在，直接返回
      const baseData = await getWordDetailFromDB(word);
      if (baseData) {
        return { code: 0, data: { ...baseData, ...cached.enrichment } };
      }
    }

    // 2. 从 MySQL 获取基础数据
    const baseData = await getWordDetailFromDB(word);
    if (!baseData) return { code: -1, message: '单词未找到' };

    // 3. 调用 AI 生成丰富内容
    const ai = app.ai();
    const model = ai.createModel('cloudbase');

    const mainMeaning = extractMainMeaning(baseData.translation);
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

    // 4. 解析 AI 返回的 JSON
    let enrichment = {};
    try {
      let text = result.text || '';
      // 去除可能的 markdown 代码块标记
      text = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
      enrichment = JSON.parse(text);

      // 验证并补充默认值
      if (!enrichment.example || !enrichment.example.en) {
        enrichment.example = { en: `The word "${word}" is commonly used in daily life.`, zh: `"${word}" 这个词在日常生活中很常用。` };
      }
      if (!Array.isArray(enrichment.roots)) enrichment.roots = [];
      if (!Array.isArray(enrichment.synonyms)) enrichment.synonyms = [];
      if (!enrichment.idiom || !enrichment.idiom.en) {
        enrichment.idiom = { en: `Remember "${word}" - ${mainMeaning}.`, zh: `记住 "${word}" - ${mainMeaning}。` };
      }
    } catch (parseErr) {
      console.error('AI JSON parse failed:', parseErr.message, result.text?.substring(0, 200));
      enrichment = {
        example: { en: `This is an example with "${word}".`, zh: `这是一个包含 "${word}" 的例子。` },
        roots: [],
        synonyms: [],
        idiom: { en: `Remember "${word}" - ${mainMeaning}.`, zh: `记住 "${word}" - ${mainMeaning}。` }
      };
    }

    // 5. 合并 derivatives（从 exchange 解析）到 roots
    if (baseData.derivatives && baseData.derivatives.length > 0) {
      // 将 exchange 解析的词形变化合并到 roots
      const existingRootWords = (enrichment.roots || []).map(r => r.word);
      for (const d of baseData.derivatives) {
        if (!existingRootWords.includes(d.word)) {
          enrichment.roots = enrichment.roots || [];
          enrichment.roots.push({ pos: d.pos, word: d.word });
        }
      }
    }

    // 6. 缓存到 NoSQL
    try {
      await db.collection('word_enrichment').add({
        data: {
          word,
          enrichment,
          createdAt: new Date()
        }
      });
    } catch (cacheErr) {
      console.error('Cache write failed:', cacheErr.message);
    }

    // 7. 返回合并数据
    return { code: 0, data: { ...baseData, ...enrichment } };
  } catch (e) {
    console.error('enrichWord failed:', e.message);
    return { code: -1, message: e.message };
  }
}

/**
 * 从 MySQL 获取单词详情（内部使用，不经过 AI）
 */
async function getWordDetailFromDB(word) {
  try {
    const rdb = app.rdb();
    const table = rdb.from('dict_word');

    const url = new URL(table.url.toString());
    url.searchParams.set('word', `eq.${word}`);
    url.searchParams.set('limit', '1');
    url.searchParams.set('select', 'id,word,phonetic,translation,pos,tag,definition,exchange');

    const resp = await table.fetch(url.toString(), {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!resp.ok) return null;

    const rows = await resp.json();
    if (!rows.length) return null;

    return formatWord(rows[0]);
  } catch (e) {
    console.error('getWordDetailFromDB failed:', e.message);
    return null;
  }
}
