const mock = require('../../../utils/mock.js');

Page({
  data: {
    timeRanges: ['一天', '一周', '一个月'],
    activeTimeRange: 1,
    textTypes: ['报道', '故事', '顺口溜'],
    activeTextType: 1,
    words: mock.scenarioWords,
    scenarioText: mock.scenarioText,
    generated: true
  },

  onSelectTimeRange(e) {
    this.setData({ activeTimeRange: e.currentTarget.dataset.index });
  },

  onSelectTextType(e) {
    this.setData({ activeTextType: e.currentTarget.dataset.index });
  },

  onGenerate() {
    this.setData({ generated: true });
  },

  onBookmark() {
    wx.showToast({ title: '已收藏', icon: 'success' });
  },

  onGenerateVideo() {
    wx.showToast({ title: '视频生成功能开发中', icon: 'none' });
  }
});