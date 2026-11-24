// 云函数 - AI 能力（聊天/翻译/情景生成/Embedding）
// 双模式：CloudBase 内置 AI (deepseek-v4-flash) + SiliconFlow (Qwen/BGE)

const cloud = require('wx-server-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

// @cloudbase/node-sdk 用于 AI 调用
const tcb = require('@cloudbase/node-sdk');
const ENV_ID = 'cloud1-d0g0f3q7g8d2bb58f';
const tcbApp = tcb.init({ env: ENV_ID });
const ai = tcbApp.ai();

// SiliconFlow API 配置
const SILICONFLOW_BASE_URL = 'https://api.siliconflow.cn/v1';
const SILICONFLOW_LLM_KEY = process.env.SILICONFLOW_LLM_KEY || '';
const SILICONFLOW_EMBEDDING_KEY = process.env.SILICONFLOW_EMBEDDING_KEY || '';

// 默认模型配置
const DEFAULT_CLOUDBASE_MODEL = 'deepseek-v4-flash';
const DEFAULT_HUNYUAN_MODEL = 'hunyuan-2.0-instruct-20251111';
const DEFAULT_SILICONFLOW_MODEL = 'Qwen/Qwen2.5-7B-Instruct';
const EMBEDDING_MODEL = 'BAAI/bge-large-zh-v1.5';

// 429 重试配置
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY = 1000; // 1s
// 并发控制：单次最多 1 个 AI 请求
let requestQueue = [];
let processing = false;

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const SYSTEM_PROMPTS = {
  chat: `你是英语学习助手。用中文回答，简洁直接。英语内容保留英文，解释用中文。`,
  translate: `你是一个专业的中英翻译助手。请根据用户提供的文本和翻译方向进行翻译。
规则：
1. 翻译要准确自然
2. 只返回翻译结果，不要解释
3. 保持原文的语气和风格`,
  scenario: `你是一位英语单词记忆专家。用户会给你一组英语单词，请为这些单词创作一段文段，帮助用户通过上下文快速记忆单词。
规则：
1. 全文必须用英文撰写，给定的单词用 **单词** 标记（如 **apple**）
2. 顺口溜/说唱要押韵有节奏感，故事要有逻辑性和画面感
3. 自然地融入所有单词
4. 文章长度 100-150 词
5. 在英文文段下方，空一行后附上对应的中文翻译
6. 中文翻译中，单词对应的译文也用 **译文** 标记加粗凸显（如 **苹果**）`
};

exports.main = async (event, context) => {
  const { action, provider = 'cloudbase' } = event;

  try {
    switch (action) {
      case 'chat':
        return await handleChat(event, provider);
      case 'translate':
        return await handleTranslate(event, provider);
      case 'scenario':
        return await handleScenario(event, provider);
      case 'embedding':
        return await handleEmbedding(event);
      case 'testKey':
        return await handleTestKey(event);
      default:
        return { code: -1, message: '未知操作' };
    }
  } catch (err) {
    console.error('AI function error:', err);
    return { code: -1, message: err.message || 'AI 服务暂时不可用' };
  }
};

// ====== 获取用户的 SiliconFlow API Key ======
async function getUserApiKey(openid) {
  if (!openid) return null;
  try {
    const res = await db.collection('users').where({ _openid: openid }).get();
    if (res.data && res.data.length > 0 && res.data[0].apiKey) {
      return res.data[0].apiKey;
    }
  } catch (e) {
    console.error('获取 API Key 失败', e);
  }
  return null;
}

// ====== CloudBase 内置 AI 调用（流式 + 429 指数退避） ======
async function callCloudBaseAI(messages, model = DEFAULT_CLOUDBASE_MODEL, temperature = 0.7) {
  const tryCall = async (groupName, useModel) => {
    const aiModel = ai.createModel(groupName);
    const stream = await aiModel.streamText({ model: useModel, messages, temperature });
    let fullText = '';
    for await (const text of stream.textStream) {
      fullText += text;
    }
    return fullText;
  };

  // 第 1 轮：尝试 cloudbase 组（最多 MAX_RETRIES 次指数退避）
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await tryCall('cloudbase', model);
    } catch (err) {
      const is429 = err.code === '429' || err.code === 429;
      if (is429 && attempt < MAX_RETRIES) {
        const delay = RETRY_BASE_DELAY * Math.pow(2, attempt - 1);
        console.warn(`cloudbase 组 429 限流，第 ${attempt} 次重试，等待 ${delay}ms`);
        await sleep(delay);
        continue;
      }
      if (is429) {
        console.warn('cloudbase 组 429 重试耗尽，尝试 hunyuan-exp 降级');
      } else {
        console.warn(`cloudbase 组调用失败 (${err.code || err.message})，尝试 hunyuan-exp 降级`);
      }
      // 重试耗尽或非 429 错误 → 降级到 hunyuan-exp
      break;
    }
  }

  // 降级：尝试 hunyuan-exp 组（仅 1 次，无额外重试）
  try {
    return await tryCall('hunyuan-exp', DEFAULT_HUNYUAN_MODEL);
  } catch (err2) {
    console.error('hunyuan-exp 降级也失败:', err2.message || err2);
    throw err2;
  }
}

// ====== SiliconFlow API 调用（流式） ======
async function callSiliconFlow(apiKey, messages, model = DEFAULT_SILICONFLOW_MODEL, temperature = 0.7) {
  const endpoint = `${SILICONFLOW_BASE_URL}/chat/completions`;

  // 先用非流式请求
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model,
      messages,
      temperature,
      max_tokens: 4096
    })
  });

  if (response.status === 429) {
    // SiliconFlow 429 错误，等待后自动重试 1 次
    await sleep(2000);
    const retryResponse = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        messages,
        temperature,
        max_tokens: 4096
      })
    });
    if (!retryResponse.ok) {
      const errText = await retryResponse.text();
      throw new Error(`SiliconFlow API error: ${retryResponse.status} - ${errText}`);
    }
    const retryData = await retryResponse.json();
    return retryData.choices?.[0]?.message?.content || '';
  }

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`SiliconFlow API error: ${response.status} - ${errText}`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || '';
}

// ====== Embedding 调用（SiliconFlow） ======
async function callEmbedding(apiKey, texts) {
  const endpoint = `${SILICONFLOW_BASE_URL}/embeddings`;
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: EMBEDDING_MODEL,
      input: texts,
      encoding_format: 'float'
    })
  });

  if (!response.ok) {
    throw new Error(`Embedding API error: ${response.status}`);
  }

  const data = await response.json();
  return data.data?.map(d => d.embedding) || [];
}

// ====== 统一 LLM 调用入口 ======
async function callLLM(event, messages, temperature = 0.7) {
  const { provider = 'cloudbase' } = event;

  if (provider === 'siliconflow') {
    const apiKey = await getUserApiKey(event.openid || event._openid) || SILICONFLOW_LLM_KEY;
    return await callSiliconFlow(apiKey, messages, event.model || DEFAULT_SILICONFLOW_MODEL, temperature);
  }

  // 默认使用 CloudBase 内置 AI
  return await callCloudBaseAI(messages, event.model || DEFAULT_CLOUDBASE_MODEL, temperature);
}

// ====== 业务处理器 ======

async function handleChat(event, provider) {
  const { messages = [] } = event;
  const allMessages = [
    { role: 'system', content: SYSTEM_PROMPTS.chat },
    ...messages
  ];

  try {
    const reply = await callLLM(event, allMessages);
    return { code: 0, data: { content: reply, provider } };
  } catch (err) {
    // CloudBase 失败时尝试兜底
    if (provider === 'cloudbase') {
      const fallback = getFallbackResponse(messages);
      return { code: 0, data: { content: fallback, provider: 'fallback' } };
    }
    throw err;
  }
}

async function handleTranslate(event, provider) {
  const { text, direction = 'zh2en' } = event;
  const prompt = direction === 'zh2en'
    ? `请将以下中文翻译成英文：\n${text}`
    : `请将以下英文翻译成中文：\n${text}`;

  const result = await callLLM(event, [
    { role: 'system', content: SYSTEM_PROMPTS.translate },
    { role: 'user', content: prompt }
  ]);
  return { code: 0, data: { input: text, output: result, provider } };
}

async function handleScenario(event, provider) {
  const { words = [], textType = '故事', timeRange = '现代' } = event;
  const wordsStr = words.join(', ');
  const prompt = `请用以下单词创作一个${timeRange}背景的${textType}：\n${wordsStr}\n\n用 {单词} 格式标记每个目标单词。`;

  const result = await callLLM(event, [
    { role: 'system', content: SYSTEM_PROMPTS.scenario },
    { role: 'user', content: prompt }
  ]);
  return { code: 0, data: { text: result, provider } };
}

async function handleEmbedding(event) {
  const { texts = [] } = event;
  // 优先使用全局 Embedding Key，其次用用户自带 Key
  const apiKey = SILICONFLOW_EMBEDDING_KEY || await getUserApiKey(event.openid || event._openid);

  if (!apiKey) {
    return { code: -1, message: 'Embedding 需要配置 SiliconFlow API Key' };
  }

  const embeddings = await callEmbedding(apiKey, texts);
  return { code: 0, data: { embeddings, model: EMBEDDING_MODEL } };
}

async function handleTestKey(event) {
  const { apiKey } = event;
  if (!apiKey) {
    return { code: -1, message: '请提供 API Key' };
  }

  try {
    const response = await fetch(`${SILICONFLOW_BASE_URL}/models`, {
      headers: { 'Authorization': `Bearer ${apiKey}` }
    });

    if (response.ok) {
      return { code: 0, data: { valid: true, message: 'API Key 验证通过' } };
    } else {
      return { code: 0, data: { valid: false, message: 'API Key 无效' } };
    }
  } catch (err) {
    return { code: -1, message: '验证失败：' + err.message };
  }
}

// 兜底回复（CloudBase AI 不可用时使用）
function getFallbackResponse(messages) {
  const lastMsg = messages[messages.length - 1]?.content || '';

  if (lastMsg.includes('翻译') || lastMsg.includes('translate')) {
    return '翻译功能需要配置 API Key 后使用。请在"我的"→"API Key 设置"中配置。';
  }

  if (lastMsg.includes('虚拟语气')) {
    return '**虚拟语气 (Subjunctive Mood)**\n\n虚拟语气用来表达假设、愿望、建议等非真实情况。\n\n📌 **基本结构：**\n1. 与现在事实相反：If + 过去式, would + 动词原形\n2. 与过去事实相反：If + had + 过去分词, would have + 过去分词\n\n📝 **例句：**\n• If I were you, I would study harder.\n• If she had known, she would have come earlier.';
  }

  return '你好！我是 E-Learning 英语学习助手，请问有什么可以帮你？';
}
