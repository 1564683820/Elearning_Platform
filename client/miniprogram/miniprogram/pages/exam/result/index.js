// 学生端 — 考试结果页
const { getExamResult } = require('../../../utils/api');

Page({
  data: {
    examTitle: '',
    score: 0,
    totalScore: 100,
    gradeClass: 'pass',
    gradeText: '',
    details: [],
    loaded: false,
    error: '',
  },

  onLoad(options) {
    const examId = options.examId;

    if (examId) {
      // 新逻辑：通过 API 获取结果
      this.fetchResult(examId);
    } else {
      // 兼容旧 URL（直接从参数读取）
      this.parseFromOptions(options);
    }
  },

  async fetchResult(examId) {
    wx.showLoading({ title: '加载中...' });
    try {
      const res = await getExamResult(examId);
      const data = res?.data || res;

      if (!data) {
        this.setData({ error: '未找到考试结果', loaded: true });
        return;
      }

      // 计算等级
      const totalScore = data.max_score || 100;
      const score = data.total_score || 0;
      const pct = totalScore > 0 ? score / totalScore : 0;
      let gradeClass = 'fail';
      let gradeText = '不及格，继续加油！';
      if (pct >= 0.9) { gradeClass = 'excellent'; gradeText = '优秀！太棒了！'; }
      else if (pct >= 0.75) { gradeClass = 'good'; gradeText = '良好，继续保持！'; }
      else if (pct >= 0.6) { gradeClass = 'pass'; gradeText = '及格，还需努力！'; }

      // 映射后端字段名到 WXML 需要的格式
      const details = (data.details || []).map(item => ({
        type: item.type,
        question: item.stem || '',
        student_answer: item.user_answer || '',
        correct_answer: item.correct_answer || '',
        score: item.score || 0,
        max_score: item.max_score || 0,
        comment: item.ai_comment || '',
        is_correct: item.is_correct,
      }));

      this.setData({
        examTitle: data.exam_title || '考试结果',
        score,
        totalScore,
        gradeClass,
        gradeText,
        details,
        loaded: true,
      });
    } catch (e) {
      this.setData({ error: '加载失败：' + (e.message || ''), loaded: true });
    } finally {
      wx.hideLoading();
    }
  },

  parseFromOptions(options) {
    const score = Number(options.score) || 0;
    const totalScore = Number(options.totalScore) || 100;
    let gradeClass = 'fail';
    let gradeText = '不及格，继续加油！';
    const pct = totalScore > 0 ? score / totalScore : 0;
    if (pct >= 0.9) { gradeClass = 'excellent'; gradeText = '优秀！太棒了！'; }
    else if (pct >= 0.75) { gradeClass = 'good'; gradeText = '良好，继续保持！'; }
    else if (pct >= 0.6) { gradeClass = 'pass'; gradeText = '及格，还需努力！'; }

    let details = [];
    try {
      if (options.details) {
        details = JSON.parse(decodeURIComponent(options.details));
      }
    } catch (e) { /* ignore */ }

    this.setData({
      examTitle: options.examTitle || '考试结果',
      score,
      totalScore,
      gradeClass,
      gradeText,
      details,
      loaded: true,
    });
  },

  goBack() {
    wx.navigateBack({ delta: 2 });
  },
});
