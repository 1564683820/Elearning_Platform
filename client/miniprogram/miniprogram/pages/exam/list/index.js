// 学生端 — 考试/练习列表（支持分页、状态筛选、下拉刷新）
const api = require('../../../utils/api');

Page({
  data: {
    exams: [],
    loading: false,
    loadingMore: false,
    refreshing: false,
    error: false,
    errorMsg: '',
    // 分页
    page: 1,
    pageSize: 20,
    hasMore: true,
    total: 0,
    // 筛选
    statusFilter: '',           // ''=全部, pending=未提交, submitted=已提交
    filterTabs: [
      { key: '', label: '全部' },
      { key: 'pending', label: '未提交' },
      { key: 'submitted', label: '已提交' },
    ],
  },

  onLoad() {
    this.loadExams(true);
  },

  // 下拉刷新
  async onPullDownRefresh() {
    this.setData({ refreshing: true, page: 1, hasMore: true });
    await this.loadExams(true);
    wx.stopPullDownRefresh();
    this.setData({ refreshing: false });
  },

  // 上拉加载更多
  async onReachBottom() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    const nextPage = this.data.page + 1;
    this.setData({ loadingMore: true });
    await this.loadExams(false, nextPage);
    this.setData({ loadingMore: false });
  },

  async loadExams(reset = false, page) {
    const p = page || this.data.page;
    const { statusFilter, pageSize } = this.data;

    if (reset) {
      this.setData({ loading: true, error: false, errorMsg: '' });
    }

    try {
      const result = await api.getExamList({
        status: statusFilter || undefined,
        page: p,
        pageSize,
      });

      const items = result?.items || result || [];
      const total = result?.total || items.length;
      const hasMore = items.length >= pageSize;

      if (reset) {
        this.setData({
          exams: items,
          page: p,
          total,
          hasMore,
          loading: false,
          error: false,
        });
      } else {
        this.setData({
          exams: [...this.data.exams, ...items],
          page: p,
          total,
          hasMore,
        });
      }
    } catch (err) {
      console.error('加载考试列表失败', err);
      this.setData({
        error: true,
        errorMsg: err?.message || '网络异常，请检查连接后重试',
        loading: false,
      });
    }
  },

  // 切换状态筛选
  onFilterTap(e) {
    const { key } = e.currentTarget.dataset;
    if (key === this.data.statusFilter) return;
    this.setData({ statusFilter: key, page: 1, hasMore: true }, () => {
      this.loadExams(true);
    });
  },

  // 重试
  onRetry() {
    this.setData({ page: 1, hasMore: true });
    this.loadExams(true);
  },

  // 进入答题
  startExam(e) {
    const examId = e.currentTarget.dataset.id;
    const exam = this.data.exams.find(item => item.id === examId);
    if (exam?.my_submission?.score != null) {
      // 已提交 → 查看结果
      wx.navigateTo({
        url: `/pages/exam/result/index?examId=${exam.id}`,
      });
      return;
    }
    wx.navigateTo({ url: `/pages/exam/do-exam/index?examId=${examId}` });
  },
});
