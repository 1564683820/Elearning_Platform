// 学习报告页
const api = require('../../../utils/api.js');

Page({
  data: {
    loading: true,
    error: '',
    report: null,
    periodStart: '',
    periodEnd: '',
    maxDailyCount: 0,
  },

  onLoad() {
    this.initDateRange();
    this.onLoadReport();
  },

  onPullDownRefresh() {
    this.onLoadReport().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  // 初始化日期范围：最近30天
  initDateRange() {
    const now = new Date();
    const end = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    const s = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
    this.setData({ periodStart: s, periodEnd: end });
  },

  // 加载学习报告
  async onLoadReport() {
    this.setData({ loading: true, error: '' });
    try {
      const report = await api.getPersonalReport({
        periodStart: this.data.periodStart,
        periodEnd: this.data.periodEnd,
      });
      if (report) {
        // 计算每日趋势最大值
        let maxCount = 0;
        if (report.daily_trend && report.daily_trend.length > 0) {
          report.daily_trend.forEach(d => {
            if (d.count > maxCount) maxCount = d.count;
          });
        }
        this.setData({ report, maxDailyCount: maxCount, loading: false });
      } else {
        this.setData({ report: null, loading: false });
      }
    } catch (err) {
      console.error('加载学习报告失败', err);
      this.setData({ error: err.message || '加载失败，请稍后重试', loading: false });
    }
  },
});