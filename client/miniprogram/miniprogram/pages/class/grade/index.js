// 成绩分析页 — 详细成绩走向 + 各题型错误占比
const api = require('../../../utils/api.js');

Page({
  data: {
    classId: '',
    className: '',
    loading: true,
    // 成绩数据
    scores: [],
    typeStats: [],
    examCount: 0,
    avgScore: 0,
  },

  onLoad(options) {
    const classId = options.classId || '';
    const className = decodeURIComponent(options.className || '成绩分析');
    this.setData({ classId, className });
    this.loadData();
  },

  async loadData() {
    try {
      wx.showLoading({ title: '加载中...' });
      const stats = await api.getGradeStats(this.data.classId);
      wx.hideLoading();

      this.setData({
        scores: stats.scores || [],
        typeStats: stats.type_stats || [],
        examCount: stats.exam_count || 0,
        avgScore: stats.avg_score || 0,
        loading: false,
      });
    } catch (err) {
      wx.hideLoading();
      console.error('加载成绩统计失败', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onBack() {
    wx.navigateBack();
  },

  // 查看某次考试详情
  onScoreTap(e) {
    const index = parseInt(e.currentTarget.dataset.index);
    // 这里可以跳转到对应考试的结果页
    wx.navigateTo({
      url: `/pages/exam/result/index?examId=${this.data.scores[index]?.exam_id || ''}`,
    });
  },
});
