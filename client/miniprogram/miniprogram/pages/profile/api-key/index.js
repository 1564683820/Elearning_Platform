const api = require('../../../utils/api.js');

Page({
  data: {
    // 智能对话
    chatApiKey: '',
    chatBaseUrl: 'https://api.siliconflow.cn/v1',
    chatModelName: 'Qwen/Qwen2.5-7B-Instruct',
    showChatKey: false,
    // 视频演绎
    videoApiKey: '',
    videoBaseUrl: 'https://api.siliconflow.cn/v1',
    videoModelName: 'Qwen/Qwen2.5-7B-Instruct',
    showVideoKey: false,
    // 通用
    saving: false,
    testingChat: false,
    testingVideo: false,
    navBarTop: 0,
    navBarHeight: 44,
    navPadLeft: 0,
    navPadRight: 0,
  },

  onLoad() {
    this.initNavBar();
    this.loadApiKeyConfig();
  },

  initNavBar() {
    try {
      let sysInfo;
      if (typeof wx.getAppBaseInfoSync === 'function') {
        sysInfo = { ...wx.getAppBaseInfoSync(), ...wx.getWindowInfoSync() };
      } else {
        sysInfo = wx.getSystemInfoSync();
      }
      const btnRect = wx.getMenuButtonBoundingClientRect();
      const statusBarHeight = sysInfo.statusBarHeight || 44;
      const navBarHeight = (btnRect.top - statusBarHeight) * 2 + btnRect.height;
      this.setData({
        navBarTop: statusBarHeight,
        navBarHeight,
        navPadLeft: btnRect.left || 0,
        navPadRight: sysInfo.windowWidth - (btnRect.right || sysInfo.windowWidth - 10)
      });
    } catch (e) {
      console.error('获取系统信息失败', e);
    }
  },

  onBack() {
    wx.navigateBack();
  },

  async loadApiKeyConfig() {
    try {
      const keys = await api.getUserApiKeys();
      if (keys && Array.isArray(keys)) {
        const chatKey = keys.find(k => k.key_type === 'chat');
        const videoKey = keys.find(k => k.key_type === 'video');
        this.setData({
          chatApiKey: chatKey?.encrypted_key || '',
          chatBaseUrl: chatKey?.api_base || 'https://api.siliconflow.cn/v1',
          chatModelName: chatKey?.model_name || 'Qwen/Qwen2.5-7B-Instruct',
          videoApiKey: videoKey?.encrypted_key || '',
          videoBaseUrl: videoKey?.api_base || 'https://api.siliconflow.cn/v1',
          videoModelName: videoKey?.model_name || 'Qwen/Qwen2.5-7B-Instruct',
        });
      }
    } catch (err) {
      console.error('加载 API Key 配置失败', err);
    }
  },

  // === 智能对话输入 ===
  onChatApiKeyInput(e) {
    this.setData({ chatApiKey: e.detail.value });
  },
  onChatBaseUrlInput(e) {
    this.setData({ chatBaseUrl: e.detail.value });
  },
  onChatModelNameInput(e) {
    this.setData({ chatModelName: e.detail.value });
  },
  onToggleChatKey() {
    this.setData({ showChatKey: !this.data.showChatKey });
  },

  // === 视频演绎输入 ===
  onVideoApiKeyInput(e) {
    this.setData({ videoApiKey: e.detail.value });
  },
  onVideoBaseUrlInput(e) {
    this.setData({ videoBaseUrl: e.detail.value });
  },
  onVideoModelNameInput(e) {
    this.setData({ videoModelName: e.detail.value });
  },
  onToggleVideoKey() {
    this.setData({ showVideoKey: !this.data.showVideoKey });
  },

  // === 测试连接 ===
  async onTestChatConnection() {
    if (!this.data.chatApiKey) {
      wx.showToast({ title: '请先输入对话 API Key', icon: 'none' });
      return;
    }
    this.setData({ testingChat: true });
    wx.showLoading({ title: '测试对话连接...' });
    try {
      const result = await api.testApiKey('chat');
      wx.hideLoading();
      if (result.valid) {
        wx.showToast({ title: '对话连接成功！', icon: 'success' });
      } else {
        wx.showToast({ title: result.message || '连接失败', icon: 'none' });
      }
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '测试失败', icon: 'none' });
    } finally {
      this.setData({ testingChat: false });
    }
  },

  async onTestVideoConnection() {
    if (!this.data.videoApiKey) {
      wx.showToast({ title: '请先输入视频演绎 API Key', icon: 'none' });
      return;
    }
    this.setData({ testingVideo: true });
    wx.showLoading({ title: '测试视频连接...' });
    try {
      const result = await api.testApiKey('video');
      wx.hideLoading();
      if (result.valid) {
        wx.showToast({ title: '视频连接成功！', icon: 'success' });
      } else {
        wx.showToast({ title: result.message || '连接失败', icon: 'none' });
      }
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '测试失败', icon: 'none' });
    } finally {
      this.setData({ testingVideo: false });
    }
  },

  // === 保存 ===
  async onSave() {
    this.setData({ saving: true });
    try {
      await api.saveUserApiKey({
        chatApiKey: this.data.chatApiKey,
        chatBaseUrl: this.data.chatBaseUrl,
        chatModelName: this.data.chatModelName,
        videoApiKey: this.data.videoApiKey,
        videoBaseUrl: this.data.videoBaseUrl,
        videoModelName: this.data.videoModelName,
      });
      wx.showToast({ title: '保存成功', icon: 'success' });
    } catch (err) {
      console.error('保存 API Key 失败', err);
      wx.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  }
});
