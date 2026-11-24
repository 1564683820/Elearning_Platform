// 云函数 - 登录
const cloud = require('wx-server-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

exports.main = async (event, context) => {
  const wxContext = cloud.getWXContext();
  const openid = wxContext.OPENID;

  try {
    // 查找或创建用户
    const userRes = await db.collection('users').where({ _openid: openid }).get();

    if (userRes.data.length === 0) {
      // 新用户，创建记录
      await db.collection('users').add({
        data: {
          _openid: openid,
          name: '微信用户',
          email: '',
          phase: '英语四级',
          studyDays: 0,
          totalWords: 0,
          totalTraining: 0,
          remindOn: false,
          remindDays: [1, 2, 3, 4, 5],
          remindTime: '09:00',
          createdAt: db.serverDate(),
          updatedAt: db.serverDate()
        }
      });
    }

    return {
      code: 0,
      data: {
        openid,
        isNewUser: userRes.data.length === 0
      }
    };
  } catch (err) {
    return { code: -1, message: err.message };
  }
};
