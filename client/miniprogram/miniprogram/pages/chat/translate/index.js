const api = require('../../../utils/api.js');

Page({
  data: {
    tabs: ['情景对话', '智能问答', '智能翻译'],
    activeTab: 2,
    statusBarHeight: 44,
    navBarTop: 0,
    navBarHeight: 44,
    headerHeight: 180,
    direction: 'zh2en',
    inputText: '',
    outputText: '',
    translated: false,
    charCount: 0,
    translating: false
  },

  onLoad() {
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
      const headerHeight = statusBarHeight + navBarHeight + 8 + 52 + 44;
      this.setData({
        statusBarHeight,
        navBarTop: statusBarHeight,
        navBarHeight,
        headerHeight
      });
    } catch (e) {
      console.error('获取系统信息失败', e);
    }
  },

  onTabChange(e) {
    const index = e.currentTarget.dataset.index;
    if (index !== 2) {
      wx.navigateTo({ url: '/pages/chat/qa/index' });
      return;
    }
    this.setData({ activeTab: index });
  },

  onToggleDirection() {
    const newDir = this.data.direction === 'zh2en' ? 'en2zh' : 'zh2en';
    this.setData({
      direction: newDir,
      translated: false,
      outputText: ''
    });
  },

  onInput(e) {
    this.setData({
      inputText: e.detail.value,
      charCount: e.detail.value.length
    });
  },

  async onTranslate() {
    if (!this.data.inputText.trim()) {
      wx.showToast({ title: '请输入内容', icon: 'none' });
      return;
    }

    this.setData({ translating: true });
    wx.showLoading({ title: '翻译中...' });

    try {
      const result = await api.translateText({
        text: this.data.inputText,
        direction: this.data.direction,
        provider: 'cloudbase'
      });
      this.setData({
        outputText: result.output,
        translated: true
      });
    } catch (err) {
      console.error('翻译失败', err);
      wx.showToast({ title: '翻译失败，请稍后重试', icon: 'none' });
    } finally {
      wx.hideLoading();
      this.setData({ translating: false });
    }
  },

  onCopy() {
    wx.setClipboardData({
      data: this.data.outputText,
      success: () => {
        wx.showToast({ title: '已复制', icon: 'success' });
      }
    });
  },

  onImageTranslate() {
    wx.showToast({ title: '图片翻译开发中', icon: 'none' });
  },

  onBack() {
    wx.navigateBack();
  }
});
