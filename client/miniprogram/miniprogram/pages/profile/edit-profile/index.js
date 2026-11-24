const api = require('../../../utils/api.js');

Page({
  data: {
    // 导航栏
    statusBarHeight: 44,
    navBarTop: 0,
    navBarHeight: 44,
    // 表单
    name: '',
    email: '',
    phaseIndex: 3,  // 默认四六级 index=3
    avatarUrl: '',
    initials: '?',
    studyPhases: ['小学', '初中', '高中', '四六级'],
    saving: false
  },

  onLoad() {
    this.initNavBar();
    this.loadProfile();
  },

  initNavBar() {
    try {
      let sys;
      if (typeof wx.getAppBaseInfoSync === 'function') {
        sys = { ...wx.getAppBaseInfoSync(), ...wx.getWindowInfoSync() };
      } else {
        sys = wx.getSystemInfoSync();
      }
      const btn = wx.getMenuButtonBoundingClientRect();
      this.setData({
        statusBarHeight: sys.statusBarHeight || 44,
        navBarTop: sys.statusBarHeight || 44,
        navBarHeight: (btn.top - sys.statusBarHeight) * 2 + btn.height,
      });
    } catch (e) {
      console.error('获取系统信息失败', e);
    }
  },

  async loadProfile() {
    try {
      const profile = await api.getUserProfile();
      if (profile) {
        const idx = this.data.studyPhases.indexOf(profile.phase);
        this.setData({
          name: profile.name || profile.nickname || '',
          email: profile.email || '',
          avatarUrl: profile.avatar_url || '',
          initials: this._getInitials(profile.name || profile.nickname || '?'),
          phaseIndex: idx >= 0 ? idx : 4,
        });
      }
    } catch (err) {
      console.error('加载用户资料失败', err);
    }
  },

  // 取名字首字作为头像占位
  _getInitials(name) {
    if (!name || name === '?' || name === '微信用户') return '?';
    return name.charAt(0);
  },

  onNameInput(e) {
    this.setData({ name: e.detail.value });
  },

  onEmailInput(e) {
    this.setData({ email: e.detail.value });
  },

  onPhaseChange(e) {
    this.setData({ phaseIndex: Number(e.detail.value) });
  },

  // 更换头像
  onChangeAvatar() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success: (res) => {
        const tempPath = res.tempFiles[0].tempFilePath;
        this.setData({ avatarUrl: tempPath });
        wx.showToast({ title: '头像已更新（本地）', icon: 'none' });
        // TODO: 上传到云存储/后端
        // const cloudPath = 'avatars/' + Date.now() + '.jpg';
        // api.uploadAvatar(tempPath, cloudPath);
      },
      fail: (err) => {
        if (err.errMsg && err.errMsg.includes('cancel')) return;
        wx.showToast({ title: '选择图片失败', icon: 'none' });
      }
    });
  },

  async onSave() {
    const { name, email, phaseIndex, saving } = this.data;
    if (saving) return;
    if (!name.trim()) {
      wx.showToast({ title: '请输入昵称', icon: 'none' });
      return;
    }
    // 邮箱格式校验（非空时）
    const emailTrimmed = email.trim();
    if (emailTrimmed && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailTrimmed)) {
      wx.showToast({ title: '邮箱格式不正确', icon: 'none' });
      return;
    }
    this.setData({ saving: true });
    wx.showLoading({ title: '保存中...', mask: true });
    try {
      await api.updateUserProfile({
        nickname: name.trim(),
        email: emailTrimmed,
        stage: phaseIndex + 1,  // 0-based 数组索引 → 1-based DB stage
      });
      wx.hideLoading();
      wx.showToast({ title: '保存成功', icon: 'success' });
      setTimeout(() => { wx.navigateBack(); }, 800);
    } catch (err) {
      wx.hideLoading();
      console.error('保存失败', err);
      if (err.errMsg && err.errMsg.includes('timeout')) {
        wx.showToast({ title: '请求超时，请检查网络后重试', icon: 'none', duration: 2000 });
      } else {
        wx.showToast({ title: '保存失败，请重试', icon: 'none' });
      }
    } finally {
      this.setData({ saving: false });
    }
  },

  onBack() {
    wx.navigateBack();
  }
});
