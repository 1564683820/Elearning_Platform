// 教师端 — 批卷（试卷列表、提交查看、教师复核）
const app = getApp();
const { getMyClasses, getTeacherExamList, getExamSubmissions, reviewSubmission } = require('../../../utils/api');

Page({
  data: {
    activeTab: 'exams',
    classId: null,
    exams: [],
    selectedExamId: null,
    submissions: [],
    showReview: false,
    reviewStudent: '',
    reviewScore: 0,
    reviewTotal: 0,
    reviewSubmissionId: null,
    adjustments: [],
  },

  onLoad(options) {
    if (options.classId) {
      this.setData({ classId: options.classId });
      this.loadExams(options.classId);
    }
  },

  onShow() {
    if (!this.data.classId) {
      this.loadExams();
    }
  },

  async loadExams(classId) {
    try {
      // 如果没有传入 classId，尝试加载第一个班级
      if (!classId) {
        const result = await getMyClasses();
        const classList = result.classes || [];
        if (classList.length === 0) return;
        classId = String(classList[0].id);
      }
      const exams = await getTeacherExamList(classId);
      this.setData({ exams: exams?.items || exams || [] });
    } catch (err) {
      console.error('加载试卷失败', err);
    }
  },

  switchTab(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  },

  async selectExam(e) {
    const examId = e.currentTarget.dataset.id;
    this.setData({ selectedExamId: examId, activeTab: 'submissions' });
    try {
      const subs = await getExamSubmissions(examId);
      this.setData({ submissions: subs?.items || subs || [] });
    } catch (err) {
      console.error('加载提交列表失败', err);
    }
  },

  backToExams() {
    this.setData({ selectedExamId: null, activeTab: 'exams' });
  },

  openReview(e) {
    const item = e.currentTarget.dataset.item;
    this.setData({
      showReview: true,
      reviewStudent: item.student_name,
      reviewScore: item.score,
      reviewTotal: item.total_score,
      reviewSubmissionId: item.id,
      adjustments: [],
    });
  },

  closeReview() {
    this.setData({ showReview: false });
  },

  addAdjustment() {
    const adj = this.data.adjustments;
    adj.push({ index: adj.length, score: 0, comment: '' });
    this.setData({ adjustments: adj });
  },

  onAdjScore(e) {
    const idx = e.currentTarget.dataset.index;
    const adj = this.data.adjustments;
    adj[idx].score = Number(e.detail.value);
    this.setData({ adjustments: adj });
  },

  onAdjComment(e) {
    const idx = e.currentTarget.dataset.index;
    const adj = this.data.adjustments;
    adj[idx].comment = e.detail.value;
    this.setData({ adjustments: adj });
  },

  async submitReview() {
    try {
      await reviewSubmission(
        this.data.selectedExamId,
        this.data.reviewSubmissionId,
        this.data.adjustments
      );
      wx.showToast({ title: '复核完成' });
      this.closeReview();
      // 刷新提交列表
      const subs = await getExamSubmissions(this.data.selectedExamId);
      this.setData({ submissions: subs?.items || subs || [] });
    } catch (err) {
      wx.showToast({ title: '复核失败', icon: 'none' });
    }
  },
});
