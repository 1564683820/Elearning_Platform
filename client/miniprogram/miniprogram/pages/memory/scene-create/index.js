// 情景记忆视频创建页 — 选文段→生成视频
const api = require('../../../utils/api.js');

Page({
  data: {
    scenarios: [],         // 情景文段列表
    activeIndex: -1,       // 选中项索引
    loading: true,
    creating: false
  },

  onLoad() {
    this.loadScenarios();
  },

  // 加载情景文段列表
  async loadScenarios() {
    try {
      const data = await api.getScenarioList({ page: 1, pageSize: 50 });
      this.setData({
        scenarios: data.list || data || [],
        loading: false
      });
    } catch (err) {
      console.error('加载情景文段失败', err);
      this.setData({ loading: false });
    }
  },

  // 选择情景文段
  onSelectScenario(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ activeIndex: index });
  },

  // 跳转到情景记忆页生成文段
  onGoCreateScenario() {
    wx.switchTab({
      url: '/pages/memory/word/index'
    });
  },

  // 创建记忆视频
  async onCreateVideo() {
    if (this.data.activeIndex < 0) {
      wx.showToast({ title: '请先选择一个文段', icon: 'none' });
      return;
    }

    this.setData({ creating: true });

    try {
      const scenario = this.data.scenarios[this.data.activeIndex];
      await api.createScenarioVideo(scenario.id);
      wx.showToast({ title: '视频生成任务已提交', icon: 'success' });

      // 跳转到视频播放页
      wx.navigateTo({
        url: `/pages/memory/scene-video/index?scenarioId=${scenario.id}`
      });
    } catch (err) {
      console.error('创建视频失败', err);
      wx.showToast({ title: '创建失败，请重试', icon: 'none' });
    } finally {
      this.setData({ creating: false });
    }
  }
});