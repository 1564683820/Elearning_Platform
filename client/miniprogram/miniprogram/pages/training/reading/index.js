// 阅读训练页：对接后端API，支持文章展示+题目作答
const api = require('../../../utils/api.js');
const { questionView, submitChoice } = require('../../../utils/material-training.js');

Page({
  data: {
    materials: [],
    currentArticle: null,
    questions: [],
    currentIndex: 0,
    totalArticles: 0,
    currentQuestion: 0,
    totalQuestions: 0,
    selectedIndex: -1,
    answered: false,
    submitting: false,
    question: null,
    showAnalysis: false,
    correctCount: 0,
    loading: true,
    mode: 'list', // article/question/result
    stage: 0,
    timer: '00:00',
    timerSeconds: 0,
    timerInterval: null,
  },

  onLoad() {
    this.loadMaterials();
  },

  // 加载阅读材料列表
  async loadMaterials() {
    this.setData({ loading: true });
    try {
      const res = await api.getReadingMaterials({ stage: this.data.stage });
      this.setData({
        materials: res.items || [],
        totalArticles: res.total || 0,
        loading: false,
      });
    } catch (err) {
      console.error('加载阅读材料失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  // 选择阅读材料
  async onSelectArticle(e) {
    const round = this._round = (this._round || 0) + 1;
    const id = e.currentTarget.dataset.id;
    this.setData({ loading: true });
    try {
      const detail = await api.getReadingDetail(id);
      if (round !== this._round) return;
      this.setData({
        currentArticle: detail,
        questions: detail.questions || [],
        question: questionView(detail.questions?.[0]),
        submitting: false,
        totalQuestions: (detail.questions || []).length,
        currentQuestion: 0,
        selectedIndex: -1,
        answered: false,
        showAnalysis: false,
        correctCount: 0,
        mode: 'article',
        loading: false,
        timer: '00:00',
        timerSeconds: 0,
      });

      // 记录学习行为
      api.logLearningBehavior('start_reading', {
        material_id: detail.id,
      }).catch(() => {});

      // 启动计时
      this.startTimer();
    } catch (err) {
      console.error('加载阅读详情失败', err);
      if (round !== this._round) return;
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  startTimer() {
    if (this.data.timerInterval) clearInterval(this.data.timerInterval);
    const interval = setInterval(() => {
      const secs = this.data.timerSeconds + 1;
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      this.setData({
        timerSeconds: secs,
        timer: `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`,
      });
    }, 1000);
    this.setData({ timerInterval: interval });
  },

  onStartQuiz() {
    if (!this.data.questions.length) return;
    this.setData({ mode: 'question', questionStartedAt: Date.now() });
  },

  onSelectOption(e) {
    return submitChoice(this, 'currentQuestion', e, api);
  },

  onNextQuestion() {
    if (!this.data.answered || this.data.submitting) return;
    const nextIdx = this.data.currentQuestion + 1;
    if (nextIdx >= this.data.totalQuestions) {
      // 完成
      if (this.data.timerInterval) clearInterval(this.data.timerInterval);
      api.logLearningBehavior('finish_reading', {
        material_id: this.data.currentArticle?.id,
        duration_sec: this.data.timerSeconds,
        correct_count: this.data.correctCount,
        total_questions: this.data.totalQuestions,
      }).catch(() => {});
      this.setData({ mode: 'result' });
      return;
    }
    this.setData({
      currentQuestion: nextIdx,
      question: questionView(this.data.questions[nextIdx]),
      questionStartedAt: Date.now(),
      selectedIndex: -1,
      answered: false,
      showAnalysis: false,
    });
  },

  onBack() {
    this._round = (this._round || 0) + 1;
    if (this.data.timerInterval) clearInterval(this.data.timerInterval);
    if (this.data.mode !== 'list') {
      this.setData({ mode: 'list', currentArticle: null });
    } else {
      wx.navigateBack();
    }
  },
  onSettingsTap() {
    wx.showToast({ title: '请返回列表选择阅读材料', icon: 'none' });
  },
  onUnload() {
    this._round = (this._round || 0) + 1;
    if (this.data.timerInterval) clearInterval(this.data.timerInterval);
  },
});
