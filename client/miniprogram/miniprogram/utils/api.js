/**
 * 数据访问抽象层 — 统一管理 CloudBase / 自建后端切换
 * USE_CLOUDBASE = true  → 使用微信云开发
 * USE_CLOUDBASE = false → 使用自建后端 HTTP API
 */

const USE_CLOUDBASE = false;
const BASE_URL = 'http://47.106.80.147:18000/api/v1';

// Web 管理后台地址 — 教师端浏览器打开
const WEB_ADMIN_URL = 'https://dbgraph.bond';

// JWT Token 存储（内存中，退出小程序即失效）
let _authToken = null;

// 阶段中文名称 → 数字 stage（精简为四个阶段: 1=小学,2=初中,3=高中,4=四六级）
const PHASE_TO_STAGE = {
  '小学': 1, '英语启蒙': 1, '小学三年级': 1, '小学英语': 1,
  '小学四年级': 1, '小学五年级': 1,
  '初中': 2, '初中一年级': 2, '初中英语': 2,
  '初中二年级': 2, '初中三年级': 2,
  '高中': 3, '高中英语': 3, '高中一年级': 3, '高中二年级': 3, '高中三年级': 3,
  '四六级': 4, '英语四级': 4, '英语六级': 4, '考研英语': 4,
  '雅思': 4, '托福': 4, 'GRE': 4,
};
function phaseToStage(phase) {
  return PHASE_TO_STAGE[phase] || 2;  // 默认初中
}

// 阶段中文名称 → 考试标签 tag（直接筛选 DictWord.tag 字段，更精确）
const PHASE_TO_TAG = {
  '小学': '', '英语启蒙': '', '小学三年级': '', '小学英语': '',
  '小学四年级': '', '小学五年级': '',
  '初中': 'zk', '初中一年级': 'zk', '初中英语': 'zk',
  '初中二年级': 'zk', '初中三年级': 'zk',
  '高中': 'gk', '高中英语': 'gk', '高中一年级': 'gk',
  '高中二年级': 'gk', '高中三年级': 'gk',
  '四六级': 'cet4', '英语四级': 'cet4', '英语六级': 'cet6',
  '考研英语': 'cet6', '雅思': 'cet6', '托福': 'cet6', 'GRE': 'cet6',
};
function phaseToTag(phase) {
  return PHASE_TO_TAG[phase] || '';
}

function setAuthToken(token) {
  _authToken = token;
  // 同步持久化，确保模块重载后仍可恢复
  if (token) {
    try { wx.setStorageSync('auth_token', token); } catch (e) { /* ignore */ }
  }
}

function getAuthToken() {
  // 内存中无 Token 时从 Storage 兜底恢复
  if (!_authToken) {
    const saved = wx.getStorageSync('auth_token');
    if (saved) {
      _authToken = saved;
    }
  }
  return _authToken;
}

/** 获取带 Token 的请求头，内存无 Token 时从 Storage 兜底 */
function _getAuthHeader() {
  if (!_authToken) {
    const saved = wx.getStorageSync('auth_token');
    if (saved) {
      _authToken = saved;
    }
  }
  const header = {};
  if (_authToken) {
    header['Authorization'] = `Bearer ${_authToken}`;
  }
  return header;
}

// 云开发数据库（仅 USE_CLOUDBASE=true 时初始化）
let db, _;
if (USE_CLOUDBASE) {
  db = wx.cloud.database();
  _ = db.command;
}

// ========== 通用请求封装 ==========

function callCloudFunction(name, data = {}) {
  return wx.cloud.callFunction({ name, data }).then(res => {
    if (res.result && res.result.code === 0) {
      return res.result.data;
    }
    throw new Error(res.result?.message || '云函数调用失败');
  });
}

function callHttpAPI(path, data = {}, method = 'POST') {
  return new Promise((resolve, reject) => {
    const header = { 'content-type': 'application/json', ..._getAuthHeader() };
    wx.request({
      url: `${BASE_URL}${path}`,
      method,
      data,
      header,
      timeout: 60000,
      success(res) {
        // 请求成功到达（非网络层错误）
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data && res.data.code === 0) {
          resolve(res.data.data);
        } else {
          const statusCode = res.statusCode || 0;
          // 处理认证失败：清除过期 Token 并跳转登录
          if (statusCode === 401) {
            _authToken = null;
            try { wx.removeStorageSync('auth_token'); } catch (e) { /* ignore */ }
            // 防止多个请求同时弹出跳转提示
            if (!callHttpAPI._redirecting) {
              callHttpAPI._redirecting = true;
              wx.showModal({
                title: '登录已过期',
                content: '请重新登录',
                showCancel: false,
                success: () => {
                  callHttpAPI._redirecting = false;
                  wx.reLaunch({ url: '/pages/login/index' });
                }
              });
            }
            reject(new Error('登录已过期，请重新登录'));
            return;
          }
          // 根据 HTTP 状态码和响应体构造更详细的错误信息
          var errMsg = res.data?.message || (typeof res.data?.detail === 'string' ? res.data.detail : '');
          if (!errMsg) {
            if (statusCode === 404) {
              errMsg = res.data?.detail || '请求的资源不存在';
            } else if (statusCode >= 500) {
              errMsg = '服务器内部错误';
            } else {
              errMsg = '接口调用失败';
            }
          }
          console.error(`[API Error] ${method} ${path} → ${statusCode}:`, res.data)
          reject(new Error(errMsg));
        }
      },
      fail: reject
    });
  });
}

function callAPI(name, data = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction(name, data);
  }
  return callHttpAPI(`/${name}`, data);
}

// ========== 用户模块 ==========

function login() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('login', {});
  }
  // 自建后端：先通过 wx.login 获取临时 code，再传给后端换取 JWT
  return new Promise((resolve, reject) => {
    wx.login({
      success(loginRes) {
        if (!loginRes.code) {
          reject(new Error('微信登录失败: 未获取到临时 code'));
          return;
        }
        callHttpAPI('/auth/login', { code: loginRes.code }).then(data => {
          if (data && data.token) {
            setAuthToken(data.token);
          }
          resolve(data);
        }).catch(reject);
      },
      fail: reject
    });
  });
}

/** 账号+密码登录（替代一键微信登录）
 *  @param {string} role - 'student' 或 'teacher'，决定调用不同后端入口
 */
function loginWithPassword(account, password, role = 'student') {
  if (role === 'teacher') {
    return callHttpAPI('/auth/teacher/login', { account, password });
  }
  return callHttpAPI('/auth/login', { account, password });
}

/** 邀请码注册（支持角色选择） */
function registerWithInviteCode(account, username, password, role, inviteCode) {
  return callHttpAPI('/auth/register', {
    account,
    username,
    password,
    role: role || 'student',
    inviteCode,
  });
}

function getUserProfile() {
  if (USE_CLOUDBASE) {
    return db.collection('users').where({}).get().then(res => res.data[0] || null);
  }
  // 后端路由为 GET /api/v1/auth/profile（auth 路由前缀）
  return callHttpAPI('/auth/profile', {}, 'GET');
}

function updateUserProfile(data) {
  if (USE_CLOUDBASE) {
    return db.collection('users').where({}).update({ data });
  }
  return callHttpAPI('/auth/profile', data, 'PUT');
}

/** 获取用户所有 API Key（按 type 分类） */
function getUserApiKeys() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('user', { action: 'listKeys' });
  }
  return callHttpAPI('/apikeys/', {}, 'GET');
}

/** 保存/更新 API Key（key_type: 'chat' | 'video'） */
function saveUserApiKey({ chatApiKey, chatBaseUrl, chatModelName, videoApiKey, videoBaseUrl, videoModelName }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('user', {
      action: 'saveApiKey',
      keys: { chat: { key: chatApiKey, baseUrl: chatBaseUrl, model: chatModelName },
              video: { key: videoApiKey, baseUrl: videoBaseUrl, model: videoModelName } }
    });
  }
  // 后端按 key_type 分别存储，发起两次请求
  const promises = [];
  if (chatApiKey) {
    promises.push(callHttpAPI('/apikeys/', {
      key_type: 'chat',
      encrypted_key: chatApiKey,
      api_base: chatBaseUrl,
      model_name: chatModelName
    }, 'POST'));
  }
  if (videoApiKey) {
    promises.push(callHttpAPI('/apikeys/', {
      key_type: 'video',
      encrypted_key: videoApiKey,
      api_base: videoBaseUrl,
      model_name: videoModelName
    }, 'POST'));
  }
  return Promise.all(promises);
}

// ========== 单词模块 ==========

function getWordList({ phase, page = 1, pageSize = 20, sortBy = 'importance' }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'getWordList', phase, page, pageSize, sortBy });
  }
  // 后端 words 路由仅接受 GET 方法
  const stage = phaseToStage(phase);
  const tag = phaseToTag(phase);
  const params = { page, page_size: pageSize, sort_by: sortBy };
  // tag 非空时传递，让后端按考试标签精确筛选；stage 仍保留做 fallback
  if (tag) {
    params.tag = tag;
  } else if (stage > 0) {
    params.stage = stage;
  }
  return callHttpAPI('/words/', params, 'GET');
}

function getWordDetail(wordId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'getWordDetail', word: wordId });
  }
  // 后端 /words/{word_id} 需要整数 word_id，不是单词文本
  return callHttpAPI(`/words/${wordId}`, {}, 'GET');
}

// ========== 收藏模块 ==========

function getFavorites(type = 'words') {
  if (USE_CLOUDBASE) {
    return db.collection('favorites')
      .where({ type })
      .orderBy('createdAt', 'desc')
      .get()
      .then(res => res.data);
  }
  return callHttpAPI('/favorites', { target_type: type }, 'GET');
}

function addFavorite({ target_type, target_id, data = {} }) {
  if (USE_CLOUDBASE) {
    return db.collection('favorites').add({
      data: { type: target_type, refId: target_id, ...data, createdAt: db.serverDate() }
    });
  }
  return callHttpAPI('/favorites', { target_type, target_id, ...data });
}

// 按 target_type + target_id 取消收藏（内部查找 favorite_id 再删除）
async function removeFavorite(target_type, target_id) {
  if (USE_CLOUDBASE) {
    const res = await db.collection('favorites')
      .where({ type: target_type, refId: target_id })
      .get();
    if (res.data.length) {
      await db.collection('favorites').doc(res.data[0]._id).remove();
    }
    return;
  }
  const checkData = await callHttpAPI('/favorites/check', { target_type, target_id }, 'GET');
  if (checkData && checkData.favorite_id) {
    await callHttpAPI(`/favorites/${checkData.favorite_id}`, {}, 'DELETE');
  }
}

// 批量删除收藏（按 favorite.id）
async function batchRemoveFavorites(ids) {
  if (ids.length === 0) return;
  if (USE_CLOUDBASE) {
    const tasks = ids.map(id => db.collection('favorites').doc(id).remove());
    await Promise.all(tasks);
    return;
  }
  await callHttpAPI('/favorites/batch', { ids }, 'DELETE');
}

// 检查收藏状态，返回 { is_favorite, favorite_id }
async function checkFavorite(target_type, target_id) {
  if (USE_CLOUDBASE) {
    const res = await db.collection('favorites')
      .where({ type: target_type, refId: target_id })
      .get();
    return { is_favorite: res.data.length > 0, favorite_id: res.data.length ? res.data[0]._id : null };
  }
  const result = await callHttpAPI('/favorites/check', { target_type, target_id }, 'GET');
  return result;
}

// ========== 训练模块 ==========

/** 生成训练题目：从 question_bank 题库抽题 */
function generateTrainingQuestions({ questionTypes, stage, count, mode = 'infinite' }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'generateQuestions', questionTypes, stage, count, mode });
  }
  return callHttpAPI('/quiz/generate', { question_types: questionTypes, stage, count, mode }, 'POST');
}

/** 提交答案：判题 + 错题入库 */
function submitAnswer({ questionId, answer, timeSpent = 0 }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'submitAnswer', questionId, answer, timeSpent });
  }
  return callHttpAPI('/quiz/submit', { question_id: questionId, answer, time_spent: timeSpent }, 'POST');
}

function getMistakes() {
  if (USE_CLOUDBASE) {
    return db.collection('mistakes')
      .orderBy('errors', 'desc')
      .limit(50)
      .get()
      .then(res => res.data);
  }
  return callHttpAPI('/quiz/mistakes', {}, 'GET');
}

function getQuizStats() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'getStats' });
  }
  return callHttpAPI('/quiz/stats', {}, 'GET');
}

// ========== AI 模块 ==========

function chatWithAI({ messages, scenario, provider = 'cloudbase', model, level = 'intermediate' }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'chat', messages, scenario, provider, model, level });
  }
  return callHttpAPI('/ai/chat', { messages, scenario, provider, model, level });
}

function getScenarioPresets() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'scenarioPresets' });
  }
  return callHttpAPI('/ai/scenarios', {}, 'GET');
}

function getScenarioDetail(scenarioId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'scenarioDetail', scenarioId });
  }
  return callHttpAPI(`/ai/scenario-detail?scenario_id=${scenarioId}`, {}, 'GET');
}

function translateText({ text, direction, provider = 'cloudbase', model }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'translate', text, direction, provider, model });
  }
  return callHttpAPI('/ai/translate', { text, direction, provider, model });
}

/**
 * 语音对话 — 上传音频文件进行 STT + AI 场景对话 + 纠错分析 + TTS
 * 返回: { transcription, ai_content, analysis, audio_url, audio_base64 }
 */
function voiceChat({ tempFilePath, scenarioId, level, conversationHistory }) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.uploadFile({
      url: `${BASE_URL}/ai/voice-chat`,
      filePath: tempFilePath,
      name: 'file',
      formData: {
        scenario_id: scenarioId || '',
        level: level || 'intermediate',
        conversation_history: JSON.stringify(conversationHistory || []),
      },
      header,
      timeout: 120000,
      success(res) {
        try {
          const data = JSON.parse(res.data);
          if (data.code === 0) {
            resolve(data.data);
          } else {
            reject(new Error(data.message || '语音对话失败'));
          }
        } catch (e) {
          reject(new Error('响应解析失败'));
        }
      },
      fail: reject,
    });
  });
}

/**
 * 对话评分 — 对整个场景对话进行 AI 综合评分
 * 返回: { score, feedback, strengths, improvements }
 */
function voiceEvaluate({ scenarioId, level, conversationHistory }) {
  return callHttpAPI('/ai/voice-evaluate', {
    scenario_id: scenarioId || '',
    level: level || 'intermediate',
    conversation_history: conversationHistory || [],
  });
}

function generateScenario({ wordIds, textType, timeRange }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'scenario', words: wordIds, textType, timeRange });
  }
  return callHttpAPI('/scenario/generate', { word_ids: wordIds, passage_type: textType, time_range: timeRange });
}

function getEmbedding({ texts }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'embedding', texts });
  }
  return callHttpAPI('/ai/embedding', { texts });
}

/** 测试 API Key（key_type: 'chat' | 'video'） */
function testApiKey(keyType) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'testKey', keyType });
  }
  return callHttpAPI('/apikeys/test', { key_type: keyType }, 'POST');
}

// ========== 每日内容 ==========

function getDailyContent(phase) {
  if (USE_CLOUDBASE) {
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    return db.collection('daily_content')
      .where({ date: dateStr })
      .get()
      .then(res => res.data[0] || null);
  }
  // 后端路径为 /words/daily，stage 需为数字
  const stage = phaseToStage(phase) || 5;
  return callHttpAPI('/words/daily', { stage, limit: 20 }, 'GET');
}

/** 记录单词学习进度 (mastery_level: 0=未学, 1=认识, 2=熟悉, 3=掌握) */
function recordWordProgress(wordId, masteryLevel = 1) {
  return callHttpAPI(`/words/${wordId}/progress`, { mastery_level: masteryLevel }, 'POST');
}

// ========== 学习统计 ==========

function getUserStats() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'getUserStats' });
  }
  // 后端 stats 路由为 /stats/dashboard，不是裸 /stats
  return callHttpAPI('/stats/dashboard', {}, 'GET');
}

// ========== 情景记忆视频模块 ==========

function getScenarioList({ page = 1, pageSize = 20 } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('scenario', { action: 'list', page, pageSize });
  }
  return callHttpAPI('/scenario/history', { page, page_size: pageSize }, 'GET');
}

function createScenario({ wordIds, textType, timeRange, provider, model }) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('ai', { action: 'scenario', words: wordIds, textType, timeRange, provider, model });
  }
  return callHttpAPI('/scenario/generate', { word_ids: wordIds, passage_type: textType, time_range: timeRange });
}

function getScenarioVideoList({ page = 1, pageSize = 20 } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('scenario', { action: 'videoList', page, pageSize });
  }
  return callHttpAPI('/scenario/video/list', { page, page_size: pageSize }, 'GET');
}

function createScenarioVideo(scenarioId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('scenario', { action: 'createVideo', scenarioId });
  }
  return callHttpAPI(`/scenario/${scenarioId}/video`, {}, 'POST');
}

function getVideoStatus(scenarioId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('scenario', { action: 'videoStatus', scenarioId });
  }
  return callHttpAPI(`/scenario/${scenarioId}/video/status`, {}, 'GET');
}

// ========== 班级模块 ==========

function joinClass(inviteCode) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'join', inviteCode });
  }
  return callHttpAPI('/class/join', { invite_code: inviteCode });
}

function getMyClasses() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'myClasses' });
  }
  return callHttpAPI('/class/my', {}, 'GET');
}

function getMyClassDetail(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'detail', classId });
  }
  return callHttpAPI(`/class/${classId}`, {}, 'GET');
}

function getActiveSession(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'activeSession', classId });
  }
  return callHttpAPI(`/class/${classId}/active-session`, {}, 'GET');
}

function getGradeStats(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'gradeStats', classId });
  }
  return callHttpAPI(`/class/${classId}/grade-stats`, {}, 'GET');
}

// ========== 听力/阅读模块（后端对接） ==========

function getListeningMaterials({ stage = 0, page = 1, pageSize = 20 } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'listListening', stage, page, pageSize });
  }
  return callHttpAPI('/listening', { stage, page, page_size: pageSize }, 'GET');
}

function getListeningDetail(materialId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'listeningDetail', materialId });
  }
  return callHttpAPI(`/listening/${materialId}`, {}, 'GET');
}

function getReadingMaterials({ stage = 0, page = 1, pageSize = 20 } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'listReading', stage, page, pageSize });
  }
  return callHttpAPI('/reading', { stage, page, page_size: pageSize }, 'GET');
}

function getReadingDetail(materialId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('quiz', { action: 'readingDetail', materialId });
  }
  return callHttpAPI(`/reading/${materialId}`, {}, 'GET');
}

// ========== 新训练体系 — AI 驱动方法 ==========

/** 从题库获取 AI 题目（优先取未答题，取不到则 AI 生成并入库） */
function fetchFromQuestionBank({ qtype, stage = 5, difficulty = '中级' } = {}) {
  return callHttpAPI('/quiz/ai-question/fetch', { qtype, stage, difficulty }, 'POST');
}

/** AI 生成阅读文章 + 5 道选择题 */
function generateReading({ stage = 5, difficulty = '中级' } = {}) {
  return callHttpAPI(`/quiz/reading/generate?stage=${encodeURIComponent(stage)}&difficulty=${encodeURIComponent(difficulty)}`, {}, 'POST');
}

/** AI 生成翻译练习（中文段落） */
function generateTranslation({ stage = 5 } = {}) {
  return callHttpAPI(`/quiz/translation/generate?stage=${encodeURIComponent(stage)}`, {}, 'POST');
}

/** AI 评分翻译练习（支持传入 questionBankId 以标记题库题目已答） */
function scoreTranslation({ sourceText, userAnswer, reference, questionBankId }) {
  const data = {
    source_text: sourceText,
    user_answer: userAnswer,
    reference: reference,
  };
  if (questionBankId) data.question_id = questionBankId;
  return callHttpAPI('/quiz/translation/score', data, 'POST');
}

/** AI 生成作文题目 */
function generateEssay({ stage = 5 } = {}) {
  return callHttpAPI(`/quiz/essay/generate?stage=${encodeURIComponent(stage)}`, {}, 'POST');
}

/** AI 评分英语作文（支持传入 questionBankId 以标记题库题目已答） */
function scoreEssay({ essayTopic, userAnswer, reference, questionBankId }) {
  const data = {
    essay_topic: essayTopic,
    user_answer: userAnswer,
    reference: reference,
  };
  if (questionBankId) data.question_id = questionBankId;
  return callHttpAPI('/quiz/essay/score', data, 'POST');
}

// ========== 错题本 ==========

/** 获取单词训练错题 */
function getWordTrainingMistakes({ page = 1, pageSize = 50 } = {}) {
  return callHttpAPI(`/mistake-book/word-training?page=${page}&page_size=${pageSize}`, {}, 'GET');
}

/** 获取试卷错题 */
function getExamMistakes({ page = 1, pageSize = 20 } = {}) {
  return callHttpAPI(`/mistake-book/exam-mistakes?page=${page}&page_size=${pageSize}`, {}, 'GET');
}

/** 获取小e总结报告列表 */
function getSummaryReports({ page = 1, pageSize = 20 } = {}) {
  return callHttpAPI(`/mistake-book/summary-reports?page=${page}&page_size=${pageSize}`, {}, 'GET');
}

/** 获取单条总结报告详情 */
function getSummaryReportDetail(reportId) {
  return callHttpAPI(`/mistake-book/summary-reports/${reportId}`, {}, 'GET');
}

/** 导出总结报告为 PDF（返回临时文件路径） */
function exportReportPdf(reportId) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.downloadFile({
      url: `${BASE_URL}/mistake-book/summary-reports/${reportId}/export`,
      header,
      timeout: 60000,
      success(res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error(`导出失败 HTTP ${res.statusCode}`));
        }
      },
      fail: reject,
    });
  });
}

/** 批量删除单词训练错题 */
function batchDeleteWordMistakes(ids) {
  return callHttpAPI('/mistake-book/word-training/batch', { ids }, 'DELETE');
}

/** 批量删除小e总结报告 */
function batchDeleteSummaryReports(ids) {
  return callHttpAPI('/mistake-book/summary-reports/batch', { ids }, 'DELETE');
}

// ========== 考试模块（学生端） ==========

function getExamList({ status, class_id, page = 1, pageSize = 20 } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'list', status, page, pageSize });
  }
  let path = `/exam/list?page=${page}&page_size=${pageSize}`;
  if (status) path += `&status=${status}`;
  if (class_id) path += `&class_id=${class_id}`;
  return callHttpAPI(path, {}, 'GET');
}

function getExamDetail(examId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'detail', examId });
  }
  return callHttpAPI(`/exam/${examId}`, {}, 'GET');
}

function doExam(examId, answers) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'submit', examId, answers });
  }
  return callHttpAPI(`/exam/submit`, { exam_id: examId, answers }, 'POST');
}

function getExamResult(examId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'result', examId });
  }
  return callHttpAPI(`/exam/${examId}/result`, {}, 'GET');
}

// ========== 教师端 ==========

/** 教师获取自己管理的所有班级（通过 class_teacher 关联，与学生端 getMyClasses 不同） */
function getTeacherClasses() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'teacherList' });
  }
  return callHttpAPI('/teacher/classes', {}, 'GET');
}

function getTeacherDashboard(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'dashboard', classId });
  }
  return callHttpAPI(`/teacher/classes/${classId}/dashboard`, {}, 'GET');
}

function getTeacherStudents(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'students', classId });
  }
  return callHttpAPI(`/teacher/classes/${classId}/students`, {}, 'GET');
}

function removeStudentFromClass(classId, studentId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'removeStudent', classId, studentId });
  }
  return callHttpAPI(`/teacher/classes/${classId}/students/${studentId}`, {}, 'DELETE');
}

function regenerateInviteCode(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('class', { action: 'regenerateInviteCode', classId });
  }
  return callHttpAPI(`/teacher/classes/${classId}/invite-code`, {}, 'POST');
}

function getTeacherExamList(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'teacherList', classId });
  }
  return callHttpAPI(`/teacher/exam/list?class_id=${classId}`, {}, 'GET');
}

function getExamSubmissions(examId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'submissions', examId });
  }
  return callHttpAPI(`/teacher/exam/${examId}/submissions`, {}, 'GET');
}

function reviewSubmission(examId, submissionId, adjustments) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'review', examId, submissionId, adjustments });
  }
  return callHttpAPI(`/teacher/exam/${examId}/submissions/${submissionId}/review`, { adjustments });
}

function generateExamForClass(data) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('exam', { action: 'generate', ...data });
  }
  return callHttpAPI('/teacher/exam/generate', data);
}

// ========== 教师端 — 试卷管理（PRD模块C） ==========
// 后端路由前缀统一使用单数 /teacher/exam

function createExam(data) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'create', ...data });
  return callHttpAPI('/teacher/exam/manual-save', data);
}

function updateExam(examId, data) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'update', examId, ...data });
  return callHttpAPI(`/teacher/exam/${examId}`, data, 'PUT');
}

function deleteTeacherExam(examId) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'delete', examId });
  return callHttpAPI(`/teacher/exam/${examId}`, {}, 'DELETE');
}

function uploadExamPaper(examId, filePath) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.uploadFile({
      url: `${BASE_URL}/teacher/exam/${examId}/ocr-paper`,
      filePath,
      name: 'file',
      formData: {},
      header,
      timeout: 120000,
      success(res) {
        try {
          resolve(JSON.parse(res.data));
        } catch (e) {
          resolve(res.data);
        }
      },
      fail: reject,
    });
  });
}

function getAnswerSheetTemplate(examId) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'answerSheet', examId });
  return callHttpAPI(`/teacher/exam/${examId}/answer-sheet-template`, {}, 'GET');
}

/** 导出试卷对应的答题卡 PDF（直接下载文件） */
function exportAnswerSheetPdf(examId) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.downloadFile({
      url: `${BASE_URL}/teacher/exam/${examId}/answer-sheet-pdf`,
      header,
      timeout: 60000,
      success(res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error(`下载失败 HTTP ${res.statusCode}`));
        }
      },
      fail: reject,
    });
  });
}

/** 导出试卷对应的答题卡 PNG 图片（可直接保存到相册） */
function exportAnswerSheetPng(examId) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.downloadFile({
      url: `${BASE_URL}/teacher/exam/${examId}/answer-sheet-png`,
      header,
      timeout: 60000,
      success(res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error(`下载失败 HTTP ${res.statusCode}`));
        }
      },
      fail: reject,
    });
  });
}

/** 导出通用答题卡模板 PDF（不依赖具体试卷） */
function exportGenericAnswerSheetPdf({
  question_count = 100,
  option_count = 4,
  id_digits = 6,
  title = '标准答题卡',
  page_size = 'A4',
} = {}) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    const params = [
      `question_count=${question_count}`,
      `option_count=${option_count}`,
      `id_digits=${id_digits}`,
      `title=${encodeURIComponent(title)}`,
      `page_size=${page_size}`,
    ].join('&');
    wx.downloadFile({
      url: `${BASE_URL}/teacher/exam/answer-sheet-template-pdf?${params}`,
      header,
      timeout: 60000,
      success(res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error(`下载失败 HTTP ${res.statusCode}`));
        }
      },
      fail: reject,
    });
  });
}

/** 导出答题卡模板 PDF（基于已保存的模板 ID） */
function exportAnswerSheetTemplatePdf(templateId) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.downloadFile({
      url: `${BASE_URL}/teacher/exam/answer-sheet-templates/${templateId}/pdf`,
      header,
      timeout: 60000,
      success(res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error(`下载失败 HTTP ${res.statusCode}`));
        }
      },
      fail: reject,
    });
  });
}

// ========== 教师端 — 批卷（PRD模块D/E） ==========

function submitScanResult(examId, data) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'submitScan', examId, ...data });
  return callHttpAPI(`/teacher/exam/${examId}/scan`, data, 'POST');
}

function getScanProgress(examId) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'scanProgress', examId });
  return callHttpAPI(`/teacher/exam/${examId}/scan-progress`, {}, 'GET');
}

function getStudentExamDetail(examId, studentId) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'studentDetail', examId, studentId });
  return callHttpAPI(`/teacher/exam/${examId}/student/${studentId}`, {}, 'GET');
}

// ========== 教师端 — 扫描批卷（新服务端 OMR） ==========

/** 生成可打印答题卡 PNG（后端 Pillow 绘制） */
function generatePrintableSheet(examId) {
  return callHttpAPI(`/teacher/exam/${examId}/generate-printable-sheet`, {}, 'POST');
}

/** 服务端 OMR 扫描批卷 — 上传答题卡图片进行识别 */
function scanGrade(examId, filePath, classId = '') {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.uploadFile({
      url: `${BASE_URL}/teacher/exam/${examId}/scan-grade`,
      filePath,
      name: 'image',
      formData: classId ? { class_id: String(classId) } : {},
      header,
      timeout: 120000,
      success(res) {
        try {
          const data = JSON.parse(res.data);
          if (res.statusCode >= 200 && res.statusCode < 300 && data.code === 0) {
            resolve(data.data);
          } else {
            const detail = typeof data.detail === 'string' ? data.detail : data.message;
            reject(new Error(detail || `扫描批卷失败（HTTP ${res.statusCode}）`));
          }
        } catch (e) {
          reject(new Error('响应解析失败'));
        }
      },
      fail: reject,
    });
  });
}

// ========== 教师端 — 报告（PRD模块F） ==========

function getExamReport(examId) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'report', examId });
  return callHttpAPI(`/teacher/exam/${examId}/report`, {}, 'GET');
}

function getQuestionDetail(examId, questionNumber) {
  if (USE_CLOUDBASE) return callCloudFunction('exam', { action: 'questionDetail', examId, questionNumber });
  return callHttpAPI(`/teacher/exam/${examId}/report/question/${questionNumber}`, {}, 'GET');
}

// ========== 教师端 — 我的（PRD模块G） ==========

function changePassword(oldPassword, newPassword) {
  if (USE_CLOUDBASE) return callCloudFunction('user', { action: 'changePassword', oldPassword, newPassword });
  return callHttpAPI('/user/change-password', { old_password: oldPassword, new_password: newPassword }, 'POST');
}

// ========== 会员模块 ==========

function getPlans() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('membership', { action: 'plans' });
  }
  return callHttpAPI('/membership/plans', {}, 'GET');
}

function getMembershipInfo() {
  if (USE_CLOUDBASE) {
    return callCloudFunction('membership', { action: 'myMembership' });
  }
  return callHttpAPI('/membership/my-membership', {}, 'GET');
}

function createMembershipOrder(plan, durationMonths) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('membership', { action: 'createOrder', plan, durationMonths });
  }
  return callHttpAPI('/membership/create-order', { plan, duration_months: durationMonths });
}

function redeemMembershipCode(code) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('membership', { action: 'redeem', code });
  }
  return callHttpAPI('/membership/redeem', { code });
}

// ========== 学习行为记录 ==========

function logLearningBehavior(actionType, detail = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('stats', { action: 'logBehavior', actionType, detail });
  }
  return callHttpAPI('/stats/behavior', { action_type: actionType, ...detail });
}

// ========== 教材点读模块 ==========

function getTextbookVersions() {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'versions' });
  return callHttpAPI('/textbook/versions', {}, 'GET');
}

function getTextbookGrades(version) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'grades', version });
  return callHttpAPI(`/textbook/${version}/grades`, {}, 'GET');
}

function getTextbookSemesters(version, grade) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'semesters', version, grade });
  return callHttpAPI(`/textbook/${version}/${grade}/semesters`, {}, 'GET');
}

function getTextbookUnits(version, grade, semester) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'units', version, grade, semester });
  return callHttpAPI(`/textbook/${version}/${grade}/${semester}/units`, {}, 'GET');
}

function getTextbookPages(version, grade, semester, unit) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'pages', version, grade, semester, unit });
  return callHttpAPI(`/textbook/${version}/${grade}/${semester}/${unit}/pages`, {}, 'GET');
}

function getTextbookPageDetail({ pageId, version, grade, semester, unit, pageNumber }) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'pageDetail', pageId, version, grade, semester, unit, pageNumber });
  if (pageId) return callHttpAPI(`/textbook/page/${pageId}`, {}, 'GET');
  return callHttpAPI(`/textbook/page/${version}/${grade}/${semester}/${unit}/${pageNumber}`, {}, 'GET');
}

function getTextbookWordDetail(word) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'wordDetail', word });
  return callHttpAPI(`/textbook/word/${word}`, {}, 'GET');
}

// ========== 教材批量处理 ==========

function batchTextbookTTS(uploadId) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'batchTTS', uploadId });
  return callHttpAPI(`/textbook/batch/${uploadId}/tts`, {}, 'POST');
}

function batchTextbookSentenceAnalyze(uploadId) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'batchSentenceAnalyze', uploadId });
  return callHttpAPI(`/textbook/batch/${uploadId}/sentence-analyze`, {}, 'POST');
}

function batchTextbookAnimation(uploadId) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'batchAnimation', uploadId });
  return callHttpAPI(`/textbook/batch/${uploadId}/animation`, {}, 'POST');
}

// ========== TTS / 点读 ==========

function requestTTS(pageId, sentenceIndex) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'requestTTS', pageId, sentenceIndex });
  let path = `/textbook/page/${pageId}/tts`;
  if (sentenceIndex !== undefined && sentenceIndex !== null) {
    path += `?sentence_index=${encodeURIComponent(sentenceIndex)}`;
  }
  return callHttpAPI(path, {}, 'POST');
}


function saveTextbookProgress(pageId) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'saveProgress', pageId });
  return callHttpAPI(`/textbook/progress`, { page_id: pageId }, 'POST');
}

// ========== AI 视频教材演绎 ==========

function getVideoCharacters() {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'characters' });
  return callHttpAPI('/video/characters', {}, 'GET');
}

function createVideo(data) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'create', ...data });
  return callHttpAPI('/video/generate', data);
}

function getVideoList(params = {}) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'list', ...params });
  const query = Object.entries(params).filter(([_, v]) => v !== undefined).map(([k, v]) => `${k}=${v}`).join('&');
  return callHttpAPI(`/v1/video/list${query ? '?' + query : ''}`, {}, 'GET');
}

function getVideoDetail(videoId) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'detail', videoId });
  return callHttpAPI(`/v1/video/${videoId}`, {}, 'GET');
}

function getVideoTaskStatus(videoId) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'status', videoId });
  return callHttpAPI(`/v1/video/${videoId}/status`, {}, 'GET');
}

function toggleVideoFavorite(videoId) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'favorite', videoId });
  return callHttpAPI(`/v1/video/${videoId}/favorite`, {}, 'POST');
}

function deleteVideo(videoId) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'delete', videoId });
  return callHttpAPI(`/v1/video/${videoId}`, {}, 'DELETE');
}

function generateVideoScript(data) {
  if (USE_CLOUDBASE) return callCloudFunction('video', { action: 'generateScript', ...data });
  return callHttpAPI('/video/generate-script', data);
}

// ========== 协作增强模块 ==========

function getPersonalReport({ periodStart, periodEnd } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('collaboration', { action: 'personalReport', periodStart, periodEnd });
  }
  const params = new URLSearchParams();
  if (periodStart) params.set('period_start', periodStart);
  if (periodEnd) params.set('period_end', periodEnd);
  const qs = params.toString();
  return callHttpAPI(`/v1/collaboration/reports/personal${qs ? '?' + qs : ''}`, {}, 'GET');
}

function getClassReport(classId, { periodStart, periodEnd } = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('collaboration', { action: 'classReport', classId, periodStart, periodEnd });
  }
  const params = new URLSearchParams();
  if (periodStart) params.set('period_start', periodStart);
  if (periodEnd) params.set('period_end', periodEnd);
  const qs = params.toString();
  return callHttpAPI(`/v1/collaboration/reports/class/${classId}${qs ? '?' + qs : ''}`, {}, 'GET');
}

function listAssistants(classId) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('collaboration', { action: 'listAssistants', classId });
  }
  return callHttpAPI(`/v1/collaboration/assistants/${classId}`, {}, 'GET');
}

function queryAuditLogs(params = {}) {
  if (USE_CLOUDBASE) {
    return callCloudFunction('collaboration', { action: 'auditLogs', ...params });
  }
  const qs = Object.entries(params).filter(([_, v]) => v !== undefined).map(([k, v]) => `${k}=${v}`).join('&');
  return callHttpAPI(`/collaboration/audit-logs${qs ? '?' + qs : ''}`, {}, 'GET');
}

// ========== 系统状态模块 ==========

function getSystemStatus() {
  // 系统状态接口返回直接 JSON（非 {code, data} 包封格式），故不通过 callHttpAPI
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/system/status`,
      method: 'GET',
      timeout: 60000,
      header: { 'content-type': 'application/json' },
      success(res) {
        if (res.statusCode === 200 && res.data && res.data.services) {
          resolve(res.data);
        } else if (res.statusCode === 200 && res.data) {
          // 兜底：有响应内容但结构不符预期
          reject(new Error('响应格式异常'));
        } else {
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      },
      fail: reject
    });
  });
}

// ========== 教材上传/管理 ==========

/** 上传教材 PDF（使用 wx.uploadFile 上传 multipart/form-data） */
function uploadTextbook({ filePath, textbookVersion, grade, semester }) {
  return new Promise((resolve, reject) => {
    const header = { ..._getAuthHeader() };
    wx.uploadFile({
      url: `${BASE_URL}/textbook/upload`,
      filePath,
      name: 'file',
      formData: {
        textbook_version: textbookVersion || 'PEP',
        grade: grade || '3',
        semester: semester || '上',
      },
      header,
      timeout: 120000,
      success(res) {
        try {
          const data = JSON.parse(res.data);
          if (data.code === 0) {
            resolve(data.data);
          } else {
            reject(new Error(data.message || '上传失败'));
          }
        } catch (e) {
          reject(new Error('上传响应解析失败'));
        }
      },
      fail: reject,
    });
  });
}

/** 获取教材上传记录列表 */
function getTextbookUploads({ page = 1, pageSize = 20 } = {}) {
  if (USE_CLOUDBASE) return callCloudFunction('textbook', { action: 'uploadList', page, pageSize });
  return callHttpAPI(`/textbook/uploads?page=${page}&page_size=${pageSize}`, {}, 'GET');
}

/** 获取单条上传记录详情 */
function getTextbookUploadDetail(uploadId) {
  return callHttpAPI(`/textbook/uploads/${uploadId}`, {}, 'GET');
}

/** 获取某次上传的解析页面列表 */
function getTextbookUploadPages(uploadId) {
  return callHttpAPI(`/textbook/uploads/${uploadId}/pages`, {}, 'GET');
}

/** 删除上传记录 */
function deleteTextbookUpload(uploadId) {
  return callHttpAPI(`/textbook/uploads/${uploadId}`, {}, 'DELETE');
}

/** 重新解析教材 */
function reparseTextbookUpload(uploadId) {
  return callHttpAPI(`/textbook/uploads/${uploadId}/reparse`, {}, 'POST');
}

module.exports = {
  USE_CLOUDBASE,
  BASE_URL,
  WEB_ADMIN_URL,
  // Token 管理
  setAuthToken,
  getAuthToken,
  // 通用
  callAPI,
  callCloudFunction,
  callHttpAPI,
  // 用户
  login,
  loginWithPassword,
  registerWithInviteCode,
  getUserProfile,
  updateUserProfile,
  saveUserApiKey,
  getUserApiKeys,
  // 单词
  getWordList,
  getWordDetail,
  // 收藏
  getFavorites,
  addFavorite,
  removeFavorite,
  checkFavorite,
  batchRemoveFavorites,
  // 训练
  generateTrainingQuestions,
  submitAnswer,
  recordWordProgress,
  getMistakes,
  getQuizStats,
  // AI
  chatWithAI,
  translateText,
  generateScenario,
  getEmbedding,
  testApiKey,
  getScenarioPresets,
  getScenarioDetail,
  voiceChat,          // 语音对话
  voiceEvaluate,      // 对话评分
  // 每日
  getDailyContent,
  // 统计
  getUserStats,
  // 情景记忆视频
  getScenarioList,
  createScenario,
  getScenarioVideoList,
  createScenarioVideo,
  getVideoStatus,
  // 班级
  joinClass,
  getMyClasses,
  getMyClassDetail,
  getActiveSession,
  getGradeStats,
  // 听力阅读
  getListeningMaterials,
  getListeningDetail,
  getReadingMaterials,
  getReadingDetail,
  // 行为记录
  logLearningBehavior,
  // ========== 错题本 ==========
  getWordTrainingMistakes,
  getExamMistakes,
  getSummaryReports,
  getSummaryReportDetail,
  exportReportPdf,
  batchDeleteWordMistakes,
  batchDeleteSummaryReports,
  // ========== 考试模块（学生端） ==========
  getExamList,
  getExamDetail,
  doExam,
  getExamResult,
  // ========== 教师端 ==========
  getTeacherClasses,
  getTeacherDashboard,
  getTeacherStudents,
  removeStudentFromClass,
  regenerateInviteCode,
  getTeacherExamList,
  getExamSubmissions,
  reviewSubmission,
  generateExamForClass,
  // ========== 教师端 — 试卷管理 ==========
  createExam,
  updateExam,
  deleteTeacherExam,
  uploadExamPaper,
  getAnswerSheetTemplate,
  exportAnswerSheetPdf,
  exportAnswerSheetPng,
  exportGenericAnswerSheetPdf,
  exportAnswerSheetTemplatePdf,
  // ========== 教师端 — 批卷 ==========
  submitScanResult,
  getScanProgress,
  getStudentExamDetail,
  // ========== 教师端 — 扫描批卷（新服务端 OMR） ==========
  generatePrintableSheet,
  scanGrade,
  // ========== 教师端 — 报告 ==========
  getExamReport,
  getQuestionDetail,
  // ========== 教师端 — 我的 ==========
  changePassword,
  // ========== 会员模块 ==========
  getPlans,
  getMembershipInfo,
  createMembershipOrder,
  redeemMembershipCode,
  // ========== AI 视频教材演绎 ==========
  getVideoCharacters,
  createVideo,
  getVideoList,
  getVideoDetail,
  getVideoTaskStatus,
  toggleVideoFavorite,
  deleteVideo,
  generateVideoScript,
  // ========== 教材点读 ==========
  getTextbookVersions,
  getTextbookGrades,
  getTextbookSemesters,
  getTextbookUnits,
  getTextbookPages,
  getTextbookPageDetail,
  getTextbookWordDetail,
  requestTTS,
  saveTextbookProgress,
  // ========== 协作增强 ==========
  getPersonalReport,
  getClassReport,
  listAssistants,
  queryAuditLogs,
  // ========== 新训练体系 ==========
  fetchFromQuestionBank,
  generateReading,
  generateTranslation,
  scoreTranslation,
  generateEssay,
  scoreEssay,
  // ========== 错题本 ==========
  getWordTrainingMistakes,
  getExamMistakes,
  getSummaryReports,
  getSummaryReportDetail,
  // ========== 教材上传/管理 ==========
  uploadTextbook,
  getTextbookUploads,
  getTextbookUploadDetail,
  getTextbookUploadPages,
  deleteTextbookUpload,
  reparseTextbookUpload,
  batchTextbookTTS,
  batchTextbookSentenceAnalyze,
  batchTextbookAnimation,
  // ========== 系统状态 ==========
  getSystemStatus,
};
