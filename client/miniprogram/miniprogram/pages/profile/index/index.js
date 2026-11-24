const api = require('../../../utils/api.js');

Page({
  data: {
    profile: null,

    studyPhases: ['小学', '初中', '高中', '四六级'],
    currentPhaseIndex: 3,  // 默认四六级index=3
    loading: true,
    // 班级信息
    myClasses: [],
    // 角色标签映射
    roleBadge: { student: '学生', teacher: '教师', personal: '个人学习', admin: '管理员' },
    roleColors: { student: '#5B9E6F', teacher: '#F59E0B', personal: '#6366F1', admin: '#EF4444' },
  },

  onLoad() {
    this.loadProfile();
  },

  onShow() {
    this.loadProfile();
  },

  async loadProfile() {
    try {
      const app = getApp();
      // 检查是否已登录
      if (!app.globalData.isLoggedIn) {
        // 尝试用缓存的token加载
        const savedToken = wx.getStorageSync('auth_token');
        if (!savedToken) {
          this.setData({ loading: false, profile: null });
          return;
        }
      }

      const profile = await api.getUserProfile();
      if (profile) {
        // 更新全局数据
        const app = getApp();
        app._applyProfile(profile);

        const phaseIndex = this.data.studyPhases.indexOf(profile.phase);
        this.setData({
          profile: {
            id: profile.id,
            name: profile.name || profile.nickname || '微信用户',
            nickname: profile.nickname || '',
            avatar_url: profile.avatar_url || '',
            email: profile.email || '',
            role: profile.role || 'student',
            phase: profile.phase,
            stage: profile.stage,
            days: profile.studyDays || 0,
            totalWords: profile.totalWords || 0,
            totalTraining: profile.totalTraining || 0,
            membership: profile.membership || 'free',
          },
          myClasses: profile.classes || [],
          currentPhaseIndex: phaseIndex >= 0 ? phaseIndex : 4,

          loading: false
        });
      } else {
        this.setData({ loading: false });
      }
    } catch (err) {
      console.error('加载用户资料失败', err);
      this.setData({ loading: false });
      // Token 失效，提示重新登录
      if (err.message && err.message.includes('401')) {
        wx.showToast({ title: '登录已过期，请重新进入', icon: 'none' });
      }
    }
  },

  // 显示角色对应的中文标签
  _getRoleLabel(role) {
    const map = this.data.roleBadge;
    return map[role] || role || '学生';
  },

  // 获取角色对应的颜色
  _getRoleColor(role) {
    const map = this.data.roleColors;
    return map[role] || '#5B9E6F';
  },

  onEditPhase() {
    this.setData({ showPhasePicker: true });
  },

  onCancelPicker() {
    this.setData({ showPhasePicker: false });
  },

  async onPhaseConfirm(e) {
    const index = Number(e.detail.value);
    const phase = this.data.studyPhases[index];
    this.setData({
      currentPhaseIndex: index,
      showPhasePicker: false
    });
    const profile = { ...this.data.profile, phase };
    this.setData({ profile });

    try {
      // stage = index + 1，与后端一致
      await api.updateUserProfile({ stage: index + 1 });
      // 同步全局数据
      const app = getApp();
      app.globalData.studyPhase = phase;
    } catch (err) {
      console.error('更新学习阶段失败', err);
    }
  },

  onAvatarTap() {
    wx.navigateTo({ url: '/pages/profile/edit-profile/index' });
  },

  onApiKeyTap() {
    wx.navigateTo({ url: '/pages/profile/api-key/index' });
  },

  // 教师管理后台
  onWebAdminTap() {
    if (wx.openUrl) {
      wx.openUrl({ url: api.WEB_ADMIN_URL });
      return;
    }
    wx.navigateTo({
      url: `/pages/webview/index?url=${encodeURIComponent(api.WEB_ADMIN_URL)}`
    });
  },

  // 教师端入口
  onTeacherDashboardTap() {
    wx.switchTab({ url: '/pages/teacher/index/index' });
  },

  // 加入班级
  onJoinClassTap() {
    wx.showModal({
      title: '加入班级',
      content: '请输入老师提供的邀请码',
      editable: true,
      placeholderText: '请输入邀请码',
      success: async (res) => {
        if (res.confirm && res.content) {
          try {
            wx.showLoading({ title: '加入中...' });
            await api.joinClass(res.content.trim());
            wx.hideLoading();
            wx.showToast({ title: '加入成功', icon: 'success' });
            // 重新加载用户信息
            this.loadProfile();
          } catch (err) {
            wx.hideLoading();
            wx.showToast({ title: '邀请码无效或已过期', icon: 'none' });
          }
        }
      }
    });
  },

  // 查看班级详情
  onClassTap(e) {
    const classId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/class/detail/index?classId=${classId}` });
  },

  onAssistantGradeTap() {
    wx.navigateTo({ url: '/pages/teacher/exam-grade/index' });
  },

  onVideoListTap() {
    wx.navigateTo({ url: '/pages/video/list/index' });
  },

  onDocUploadTap() {
    wx.showToast({ title: '文档上传开发中', icon: 'none' });
  },

  onMenuTap(e) {
    const action = e.currentTarget.dataset.action;
    const titles = {
      settings: '系统设置',
      help: '使用说明',
      feedback: '反馈',
      about: '关于'
    };
    if (titles[action]) {
      wx.showToast({ title: titles[action] + '开发中', icon: 'none' });
    }
  },

  onSystemStatusTap() {
    wx.navigateTo({ url: '/pages/profile/system-status/index' });
  },

  // 退出登录
  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号？退出后需重新登录。',
      success: (res) => {
        if (res.confirm) {
          const app = getApp();
          app.logout();  // 清除全局数据 + Token
          this.setData({
            profile: null,
            myClasses: [],
            loading: false
          });
          wx.showToast({ title: '已退出', icon: 'success' });
          // 跳转到账号密码登录页
          setTimeout(() => {
            wx.redirectTo({ url: '/pages/login/index' });
          }, 1000);
        }
      }
    });
  },
});
