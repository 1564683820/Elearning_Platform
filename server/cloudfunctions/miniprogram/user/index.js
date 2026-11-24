// 云函数 - 用户管理
const cloud = require('wx-server-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

exports.main = async (event, context) => {
  const wxContext = cloud.getWXContext();
  const openid = wxContext.OPENID;
  const { action } = event;

  try {
    switch (action) {
      case 'getProfile':
        return await getProfile(openid);
      case 'updateProfile':
        return await updateProfile(openid, event);
      case 'saveApiKey':
        return await saveApiKey(openid, event);
      case 'testApiKey':
        return await testApiKey(event);
      default:
        return { code: -1, message: '未知操作' };
    }
  } catch (err) {
    return { code: -1, message: err.message };
  }
};

async function getProfile(openid) {
  const res = await db.collection('users').where({ _openid: openid }).get();
  const user = res.data[0] || null;

  if (!user) {
    return { code: 0, data: null };
  }

  return {
    code: 0,
    data: {
      name: user.name || '微信用户',
      email: user.email || '',
      phase: user.phase || '英语四级',
      studyDays: user.studyDays || 0,
      totalWords: user.totalWords || 0,
      totalTraining: user.totalTraining || 0,
      remindOn: user.remindOn || false,
      remindDays: user.remindDays || [1, 2, 3, 4, 5],
      remindTime: user.remindTime || '09:00',
      hasApiKey: !!(user.apiKey && user.apiKey.length > 0)
    }
  };
}

async function updateProfile(openid, event) {
  const { name, email, phase, remindOn, remindDays, remindTime } = event;

  const updateData = { updatedAt: db.serverDate() };
  if (name !== undefined) updateData.name = name;
  if (email !== undefined) updateData.email = email;
  if (phase !== undefined) updateData.phase = phase;
  if (remindOn !== undefined) updateData.remindOn = remindOn;
  if (remindDays !== undefined) updateData.remindDays = remindDays;
  if (remindTime !== undefined) updateData.remindTime = remindTime;

  await db.collection('users').where({ _openid: openid }).update({ data: updateData });

  return { code: 0, data: '更新成功' };
}

async function saveApiKey(openid, event) {
  const { apiKey, baseUrl, model } = event;

  await db.collection('users').where({ _openid: openid }).update({
    data: {
      apiKey: apiKey || '',
      baseUrl: baseUrl || 'https://api.siliconflow.cn/v1',
      model: model || 'deepseek-ai/DeepSeek-V3',
      updatedAt: db.serverDate()
    }
  });

  return { code: 0, data: 'API Key 保存成功' };
}

async function testApiKey(event) {
  const { apiKey, baseUrl, model } = event;

  try {
    const response = await fetch(`${baseUrl || 'https://api.siliconflow.cn/v1'}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: model || 'deepseek-ai/DeepSeek-V3',
        messages: [{ role: 'user', content: 'Hi' }],
        max_tokens: 5
      })
    });

    if (response.ok) {
      return { code: 0, data: { success: true, message: '连接成功！' } };
    } else {
      const err = await response.text();
      return { code: 0, data: { success: false, message: `连接失败: ${response.status}` } };
    }
  } catch (err) {
    return { code: 0, data: { success: false, message: `网络错误: ${err.message}` } };
  }
}
