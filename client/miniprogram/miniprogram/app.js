// app.js
const api = require('./utils/api.js');
const phaseMode = require('./utils/phase-mode.js');

App({
  onLaunch: function () {
    this.globalData = {
      env: 'cloud1-d0g0f3q7g8d2bb58f',
      studyPhase: '',
      studyDays: 0,
      openid: null,
      userRole: '',
      userId: null,
      isLoggedIn: false,
      isNewUser: false,  // 首次登录用户（未选角色）
      currentMode: '',   // 当前界面模式：child/student/adult
    };

    // 自建后端模式：无需初始化 wx.cloud
    if (api.USE_CLOUDBASE) {
      if (!wx.cloud) {
        console.error('请使用 2.2.3 或以上的基础库以使用云能力');
      } else {
        wx.cloud.init({
          env: this.globalData.env,
          traceUser: true
        });
      }
    }

    // 检查已保存的 Token，决定是否跳转登录页
    this.checkLogin();
  },

  async checkLogin() {
    const savedToken = wx.getStorageSync('auth_token');
    if (savedToken) {
      api.setAuthToken(savedToken);
      try {
        const profile = await api.getUserProfile();
        if (profile) {
          this._applyProfile(profile);
          // 教师角色直接跳转教师工作台
          if (profile.role === 'teacher') {
            this.globalData.currentMode = 'teacher';
            wx.redirectTo({ url: '/pages/teacher/class/index' });
            return;
          }
          // 已选角色？新用户跳转角色选择
          if (!profile.role || profile.role === '') {
            this.globalData.isNewUser = true;
            wx.navigateTo({ url: '/pages/auth/role-select/index' });
          }
          return;
        }
      } catch (err) {
        console.warn('Token 已过期，请重新登录', err);
        wx.removeStorageSync('auth_token');
        api.setAuthToken(null);
      }
    }

    // 无有效 Token，跳转登录页
    // 避免在 tab 页上无限跳转，只在小程序启动时跳转
    wx.redirectTo({ url: '/pages/login/index' });
  },

  // 切换到教师端
  switchToTeacher() {
    this.globalData.currentMode = 'teacher';
    wx.redirectTo({ url: '/pages/teacher/class/index' });
  },

  // 切换到学生端
  switchToStudent() {
    this.globalData.currentMode = '';
    wx.redirectTo({ url: '/pages/home/index' });
  },

  // 应用用户资料到全局状态
  _applyProfile(profile) {
    const phase = profile.phase || '';
    const phaseObj = phaseMode.findPhaseByName(phase);
    const idx = phaseObj ? phaseObj.index : 0;
    phaseMode.savePhaseIndex(idx);
    this.globalData.studyPhase = phase;
    this.globalData.currentMode = phaseMode.getModeByPhase(idx);
    this.globalData.studyDays = profile.studyDays || 0;
    this.globalData.userRole = profile.role || '';
    this.globalData.userId = profile.id;
    this.globalData.isLoggedIn = true;
    this.globalData.userProfile = profile;
  },

  // 登出
  logout() {
    wx.removeStorageSync('auth_token');
    api.setAuthToken(null);
    this.globalData.isLoggedIn = false;
    this.globalData.userRole = '';
    this.globalData.userId = null;
    this.globalData.userProfile = null;
    this.globalData.currentMode = '';
  }
});
