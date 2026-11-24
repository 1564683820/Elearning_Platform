const api = require('../../utils/api.js');

Page({
  data: {
    activeTab: 'exam',         // exam / word / summary
    loading: true,
    letters: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],

    // Tab 计数
    tabCounts: { exam: 0, word: 0, summary: 0 },

    // 试卷错题
    examList: [],
    examPage: 1,
    examTotal: 0,

    // 单词训练错题
    wordMistakes: [],
    wordPage: 1,
    wordTotal: 0,

    // 小e总结报告
    summaryReports: [],
    summaryPage: 1,
    summaryTotal: 0,

    // 批量操作
    batchMode: false,
    selectedIds: {},            // { id: true }
    selectedCount: 0,
    selecting: false,           // 正在执行删除请求
  },

  onLoad() {
    this.loadAllData();
  },

  onPullDownRefresh() {
    this.setData({
      examPage: 1, examList: [],
      wordPage: 1, wordMistakes: [],
      summaryPage: 1, summaryReports: [],
      batchMode: false, selectedIds: {},
    });
    this.loadAllData().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  // 一次性加载所有 Tab 数据和计数
  async loadAllData() {
    this.setData({ loading: true });
    try {
      const [examRes, wordRes, summaryRes] = await Promise.all([
        api.getExamMistakes({ page: 1, pageSize: 20 }),
        api.getWordTrainingMistakes({ page: 1, pageSize: 50 }),
        api.getSummaryReports({ page: 1, pageSize: 20 }),
      ]);

      const examList = examRes?.items || [];
      const wordMistakes = (wordRes?.items || []).map(mw => {
        // 预分割文章段落，避免 WXML 中 split('\n') 引号冲突
        if (mw.type === 6 && mw.article_content) {
          mw.article_paragraphs = mw.article_content.split('\n');
        }
        return mw;
      });
      const summaryReports = summaryRes?.items || [];

      this.setData({
        examList, examTotal: examRes?.total || 0, examPage: 1,
        wordMistakes, wordTotal: wordRes?.total || 0, wordPage: 1,
        summaryReports, summaryTotal: summaryRes?.total || 0, summaryPage: 1,
        tabCounts: {
          exam: examRes?.total || 0,
          word: wordRes?.total || 0,
          summary: summaryRes?.total || 0,
        },
        loading: false,
        selectedIds: {},
      });
    } catch (err) {
      console.error('加载错题本数据失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  // 切换 Tab
  onSwitchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.activeTab) return;
    this.setData({ activeTab: tab, batchMode: false, selectedIds: {} });
  },

  // ========== 批量操作 ==========

  onToggleBatch() {
    this.setData({
      batchMode: !this.data.batchMode,
      selectedIds: {},
      selectedCount: 0,
    });
  },

  onSelectItem(e) {
    const id = e.currentTarget.dataset.id;
    const selectedIds = { ...this.data.selectedIds };
    if (selectedIds[id]) {
      delete selectedIds[id];
    } else {
      selectedIds[id] = true;
    }
    const selectedCount = Object.keys(selectedIds).length;
    this.setData({ selectedIds, selectedCount });
  },

  onSelectAll() {
    const { activeTab, wordMistakes, summaryReports, selectedIds } = this.data;
    const list = activeTab === 'word' ? wordMistakes : summaryReports;
    const allSelected = list.every(item => selectedIds[item.id]);
    const newSelected = {};
    if (!allSelected) {
      list.forEach(item => { newSelected[item.id] = true; });
    }
    const selectedCount = Object.keys(newSelected).length;
    this.setData({ selectedIds: newSelected, selectedCount });
  },

  getSelectedIds() {
    return Object.keys(this.data.selectedIds).map(Number);
  },

  async onBatchDelete() {
    const { activeTab } = this.data;
    const ids = this.getSelectedIds();
    if (ids.length === 0) {
      wx.showToast({ title: '请先选择项目', icon: 'none' });
      return;
    }

    const label = activeTab === 'word' ? '单词错题' : '总结报告';
    const res = await new Promise(resolve => {
      wx.showModal({
        title: '确认删除',
        content: `确定删除选中的 ${ids.length} 条${label}吗？`,
        success: resolve,
      });
    });
    if (!res.confirm) return;

    this.setData({ selecting: true });
    try {
      if (activeTab === 'word') {
        await api.batchDeleteWordMistakes(ids);
        const remain = this.data.wordMistakes.filter(item => !ids.includes(item.id));
        this.setData({
          wordMistakes: remain,
          wordTotal: this.data.wordTotal - ids.length,
          tabCounts: { ...this.data.tabCounts, word: this.data.tabCounts.word - ids.length },
        });
      } else {
        await api.batchDeleteSummaryReports(ids);
        const remain = this.data.summaryReports.filter(item => !ids.includes(item.id));
        this.setData({
          summaryReports: remain,
          summaryTotal: this.data.summaryTotal - ids.length,
          tabCounts: { ...this.data.tabCounts, summary: this.data.tabCounts.summary - ids.length },
        });
      }
      this.setData({ selectedIds: {}, selecting: false, batchMode: false });
      wx.showToast({ title: `已删除 ${ids.length} 条`, icon: 'success' });
    } catch (err) {
      console.error('批量删除失败', err);
      this.setData({ selecting: false });
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },

  // ========== 试卷 ==========

  onLoadMoreExam() {
    const nextPage = this.data.examPage + 1;
    api.getExamMistakes({ page: nextPage, pageSize: 20 }).then(res => {
      const items = res?.items || [];
      this.setData({
        examList: [...this.data.examList, ...items],
        examPage: nextPage,
        examTotal: res?.total || 0,
      });
    }).catch(err => {
      console.error('加载更多试卷错题失败', err);
    });
  },

  onExamTap(e) {
    if (this.data.batchMode) return;
    const examId = e.currentTarget.dataset.id;
    if (examId) {
      wx.navigateTo({ url: `/pages/exam/result/index?examId=${examId}` });
    }
  },

  // ========== 单词训练 ==========

  onLoadMoreWord() {
    const nextPage = this.data.wordPage + 1;
    api.getWordTrainingMistakes({ page: nextPage, pageSize: 50 }).then(res => {
      const items = res?.items || [];
      this.setData({
        wordMistakes: [...this.data.wordMistakes, ...items],
        wordPage: nextPage,
        wordTotal: res?.total || 0,
      });
    }).catch(err => {
      console.error('加载更多单词错题失败', err);
    });
  },

  // ========== 小e总结 ==========

  onLoadMoreSummary() {
    const nextPage = this.data.summaryPage + 1;
    api.getSummaryReports({ page: nextPage, pageSize: 20 }).then(res => {
      const items = res?.items || [];
      this.setData({
        summaryReports: [...this.data.summaryReports, ...items],
        summaryPage: nextPage,
        summaryTotal: res?.total || 0,
      });
    }).catch(err => {
      console.error('加载更多报告失败', err);
    });
  },

  onSummaryTap(e) {
    if (this.data.batchMode) return;
    const reportId = e.currentTarget.dataset.id;
    if (reportId) {
      console.log('[错题本] 查看报告详情 reportId:', reportId);
      wx.navigateTo({
        url: `/pages/mistake-book/report-detail/index?reportId=${reportId}`,
      });
    } else {
      console.error('[错题本] 报告ID为空');
    }
  },
});
