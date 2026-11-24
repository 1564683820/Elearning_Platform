// 短语语法训练页 — 对接后端 API
const api = require('../../../utils/api.js');
const { questionView, submitChoice } = require('../../../utils/material-training.js');

Page({
  data: {
    question: null,
    questions: [],
    questionIndex: 0,
    mode: 'question',
    submitting: false,
    error: '',
    loading: true,
    currentIndex: 0,
    correctCount: 0,
    wrongCount: 0,
    selectedIndex: -1,
    answered: false,
    showAnalysis: false
  },

  onLoad() {
    this.loadQuestion();
  },

  // 加载题目
  async loadQuestion() {
    const round = this._round = (this._round || 0) + 1;
    this.setData({ loading: true, question: null, questions: [], submitting: false, error: '',
      selectedIndex: -1, answered: false, showAnalysis: false });
    try {
      const app = getApp();
      const questions = await api.generateTrainingQuestions({ questionTypes: [4], stage: app.globalData.stage || 4, count: 1 });
      if (round !== this._round) return;
      this.setData({
        questions,
        question: questions.length ? questionView(questions[0]) : null,
        questionStartedAt: Date.now(),
        loading: false,
        selectedIndex: -1,
        answered: false,
        showAnalysis: false
      });
    } catch (err) {
      if (round !== this._round) return;
      console.error('加载短语语法题失败', err);
      this.setData({ loading: false, error: '加载失败，请重试' });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onSelectOption(e) {
    return submitChoice(this, 'questionIndex', e, api);
  },

  onNextQuestion() {
    if (!this.data.answered || this.data.submitting) return;
    this.setData({
      selectedIndex: -1,
      answered: false,
      showAnalysis: false,
      currentIndex: this.data.currentIndex + 1
    });
    this.loadQuestion();
  },

  onSettingsTap() {
    wx.showToast({ title: '训练设置', icon: 'none' });
  },

  onBack() {
    this._round = (this._round || 0) + 1;
    wx.navigateBack();
  },
  onUnload() {
    this._round = (this._round || 0) + 1;
  }
});
