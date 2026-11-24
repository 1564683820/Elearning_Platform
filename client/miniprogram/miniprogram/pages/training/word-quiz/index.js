const api = require('../../../utils/api.js');
const { questionView } = require('../../../utils/material-training.js');

Page({
  data: {
    activeTab: 0,
    menuItems: ['单词训练', '短语语法', '阅读理解', '翻译', '作文'],
    showSidebar: false,
    showSettings: false,
    loading: false,
    tabLoading: false,

    questionCount: 10,

    navBarTop: 0,
    navBarHeight: 44,
    navPadLeft: 16,
    navPadRight: 16,

    // 收藏映射表（localStorage 持久化）：{ favKey: { stem, type, timestamp } }
    favorites: {},
    currentFavKey: '',     // 当前题目的收藏 key

    // ---- 单词训练 (tab 0) ----
    wordQuiz: {
      questions: [],
      question: null,
      currentIndex: 0,
      correctCount: 0,
      wrongCount: 0,
      selectedIndex: -1,
      answered: false,
      showAnalysis: false,
      loading: false,
    },

    // ---- 短语语法 (tab 1) ----
    phrase: {
      questions: [],
      question: null,
      currentIndex: 0,
      correctCount: 0,
      wrongCount: 0,
      selectedIndex: -1,
      answered: false,
      showAnalysis: false,
      loading: false,
    },

    // ---- 阅读理解 (tab 2) ----
    reading: {
      article: null,
      questions: [],
      currentQuestion: null,
      currentQIndex: 0,
      selectedIndex: -1,
      answered: false,
      showAnalysis: false,
      correctCount: 0,
      wrongCount: 0,
      loading: false,
      questionBankId: 0,
    },

    // ---- 翻译 (tab 3) ----
    translation: {
      stem: '',
      topic: '',
      keyVocab: [],
      reference: '',
      hints: '',
      userAnswer: '',
      submitted: false,
      scoreResult: null,
      loading: false,
      questionBankId: 0,
    },

    // ---- 作文 (tab 4) ----
    essay: {
      stem: '',
      topic: '',
      wordLimit: '',
      reference: '',
      keyPoints: [],
      userAnswer: '',
      submitted: false,
      scoreResult: null,
      loading: false,
      questionBankId: 0,
    },
  },

  onLoad() {
    this._disposed = false;
    try {
      this.initNavBar();
      this.loadFavorites();
      // 单词训练默认加载
      this.loadWordQuestions();
    } catch (e) {
      console.error('[word-quiz] onLoad error:', e);
      this.setData({ loading: false });
    }
  },

  // ===== 收藏功能（localStorage 持久化） =====
  FAVORITES_KEY: 'trainingFavorites',

  loadFavorites() {
    try {
      const saved = wx.getStorageSync(this.FAVORITES_KEY);
      if (saved && typeof saved === 'object') {
        this.setData({ favorites: saved });
      }
    } catch (e) {
      console.error('加载收藏失败', e);
    }
  },

  _saveFavorites() {
    try {
      wx.setStorageSync(this.FAVORITES_KEY, this.data.favorites);
    } catch (e) {
      console.error('保存收藏失败', e);
    }
  },

  _getFavKey() {
    const tab = this.data.activeTab;
    if (tab === 0) {
      const q = this.data.wordQuiz.question;
      return q ? 'w_' + (q.id || q.question?.slice(0, 20)) : '';
    }
    if (tab === 1) {
      const q = this.data.phrase.question;
      return q ? 'p_' + (q.id || q.question?.slice(0, 20)) : '';
    }
    if (tab === 2) {
      const q = this.data.reading.currentQuestion;
      return q ? 'r_' + this.data.reading.currentQIndex + '_' + (q.question || q.stem || '').slice(0, 20) : '';
    }
    if (tab === 3) {
      return this.data.translation.stem ? 't_' + this.data.translation.stem.slice(0, 30) : '';
    }
    if (tab === 4) {
      return this.data.essay.stem ? 'e_' + this.data.essay.stem.slice(0, 30) : '';
    }
    return '';
  },

  /** 刷新当前题目的收藏状态（在切换题目后调用） */
  refreshFavStatus() {
    const key = this._getFavKey();
    this.setData({ currentFavKey: key });
  },

  onToggleFavorite() {
    const key = this.data.currentFavKey;
    if (!key) return;
    const fav = { ...this.data.favorites };
    if (fav[key]) {
      delete fav[key];
      wx.showToast({ title: '已取消收藏', icon: 'none' });
    } else {
      const tab = this.data.activeTab;
      let stem = '', typeLabel = '';
      if (tab === 0) { stem = this.data.wordQuiz.question?.question || ''; typeLabel = '单词'; }
      else if (tab === 1) { stem = this.data.phrase.question?.question || ''; typeLabel = '短语语法'; }
      else if (tab === 2) { stem = this.data.reading.currentQuestion?.question || ''; typeLabel = '阅读理解'; }
      else if (tab === 3) { stem = this.data.translation.stem || ''; typeLabel = '翻译'; }
      else if (tab === 4) { stem = this.data.essay.stem || ''; typeLabel = '作文'; }
      fav[key] = { stem: stem.slice(0, 80), type: typeLabel, timestamp: Date.now() };
      wx.showToast({ title: '已收藏', icon: 'success' });
    }
    this.setData({ favorites: fav, currentFavKey: key });
    this._saveFavorites();
  },

  // ===== 导航栏 =====
  initNavBar() {
    try {
      let sysInfo;
      if (typeof wx.getAppBaseInfoSync === 'function') {
        sysInfo = { ...wx.getAppBaseInfoSync(), ...wx.getWindowInfoSync() };
      } else {
        sysInfo = wx.getSystemInfoSync();
      }
      const btnRect = wx.getMenuButtonBoundingClientRect();
      const statusBarHeight = sysInfo.statusBarHeight || 44;
      const navBarHeight = (btnRect.top - statusBarHeight) * 2 + btnRect.height;
      this.setData({
        navBarTop: statusBarHeight,
        navBarHeight: navBarHeight,
        navPadLeft: Math.max(btnRect.left > 100 ? 16 : btnRect.left - 8, 8),
        navPadRight: Math.max(sysInfo.windowWidth - btnRect.left + 8, 16),
      });
    } catch (e) {
      console.error('获取系统信息失败', e);
    }
  },

  // ===== 侧边栏 =====
  onMenuTap() { this.setData({ showSidebar: true }); },
  onCloseSidebar() { this.setData({ showSidebar: false }); },
  onMenuSelect(e) {
    const tab = Number(e.currentTarget.dataset.tab);
    this.setData({ activeTab: tab, showSidebar: false });
    // 切换时加载对应模式数据
    this.loadTabData(tab);
  },

  loadTabData(tab) {
    switch (tab) {
      case 0: if (this.data.wordQuiz.questions.length === 0) this.loadWordQuestions(); break;
      case 1: if (this.data.phrase.questions.length === 0) this.loadPhraseQuestions(); break;
      case 2: if (!this.data.reading.article) this.loadReadingArticle(); break;
      case 3: if (!this.data.translation.stem) this.loadTranslationQuestion(); break;
      case 4: if (!this.data.essay.stem) this.loadEssayQuestion(); break;
    }
  },

  /** 刷新阅读理解题目 */
  onReadingRefresh() {
    wx.showToast({ title: '重新获取题目...', icon: 'none' });
    this.loadReadingArticle();
  },

  /** 刷新翻译题目 */
  onTranslationRefresh() {
    wx.showToast({ title: '重新获取题目...', icon: 'none' });
    this.loadTranslationQuestion();
  },

  /** 刷新作文题目 */
  onEssayRefresh() {
    wx.showToast({ title: '重新获取题目...', icon: 'none' });
    this.loadEssayQuestion();
  },

  getStage() {
    const app = getApp();
    return app.globalData.stage || 4;  // 默认四六级
  },

  // ============================================================
  //  模式 0: 单词训练（选择题）
  // ============================================================
  async loadWordQuestions() {
    return this.loadBankQuestions('wordQuiz', [1, 2]);
  },

  bankView(question, result) {
    return { ...question, ...questionView(question, result), analysis: result?.analysis || null };
  },

  async loadBankQuestions(key, types) {
    this._bankVersions = this._bankVersions || {};
    const version = this._bankVersions[key] = (this._bankVersions[key] || 0) + 1;
    this.setData({ [`${key}.loading`]: true, [`${key}.questions`]: [], [`${key}.question`]: null,
      [`${key}.attempts`]: {}, [`${key}.submitting`]: false, [`${key}.answered`]: false,
      [`${key}.showAnalysis`]: false, [`${key}.selectedIndex`]: -1, [`${key}.error`]: '' });
    try {
      const questions = await api.generateTrainingQuestions({ questionTypes: types, stage: this.getStage(),
        count: this.data.questionCount, mode: 'infinite' });
      if (this._disposed || version !== this._bankVersions[key]) return;
      this.setData({ [`${key}.questions`]: questions || [], [`${key}.currentIndex`]: 0,
        [`${key}.loading`]: false, loading: false });
      if (questions?.length) this.showBankQuestion(key, 0);
    } catch (error) {
      if (this._disposed || version !== this._bankVersions[key]) return;
      this.setData({ [`${key}.loading`]: false, loading: false, [`${key}.error`]: '加载失败，请重试' });
    }
  },

  showBankQuestion(key, index) {
    const state = this.data[key];
    const question = state.questions[index];
    if (!question) return;
    const saved = state.attempts?.[question.id];
    this.setData({ [`${key}.currentIndex`]: index,
      [`${key}.question`]: this.bankView(question, saved?.result),
      [`${key}.selectedIndex`]: saved ? saved.index : -1,
      [`${key}.answered`]: !!saved, [`${key}.showAnalysis`]: !!saved,
      [`${key}.startedAt`]: Date.now() });
    this.refreshFavStatus();
  },

  async submitBankAnswer(key, index) {
    const state = this.data[key];
    const question = state.questions[state.currentIndex];
    if (this._disposed || state.loading || state.submitting || state.answered || !question
        || !Number.isInteger(index) || index < 0 || index >= (question.content?.options || []).length) return;
    const version = this._bankVersions?.[key];
    const isCurrent = () => !this._disposed && version === this._bankVersions?.[key]
      && this.data[key].questions[this.data[key].currentIndex] === question;
    this.setData({ [`${key}.submitting`]: true, [`${key}.selectedIndex`]: index });
    try {
      const result = await api.submitAnswer({ questionId: question.id, answer: index,
        timeSpent: Math.max(0, Math.floor((Date.now() - (state.startedAt || Date.now())) / 1000)) });
      if (!isCurrent()) return;
      const current = this.data[key];
      this.setData({ [`${key}.attempts`]: { ...current.attempts, [question.id]: { index, result } },
        [`${key}.answered`]: true, [`${key}.showAnalysis`]: true,
        [`${key}.question`]: this.bankView(question, result),
        [`${key}.correctCount`]: current.correctCount + (result.is_correct ? 1 : 0),
        [`${key}.wrongCount`]: current.wrongCount + (result.is_correct ? 0 : 1) });
    } catch (error) {
      if (isCurrent()) {
        this.setData({ [`${key}.selectedIndex`]: -1 });
        wx.showToast({ title: '提交失败，请重试', icon: 'none' });
      }
    } finally {
      if (isCurrent()) this.setData({ [`${key}.submitting`]: false });
    }
  },

  onWordQuizSelect(index) {
    return this.submitBankAnswer('wordQuiz', index);
  },

  onWordQuizNext() {
    if (this.data.wordQuiz.loading || this.data.wordQuiz.submitting) return;
    const nextIdx = this.data.wordQuiz.currentIndex + 1;
    if (nextIdx >= this.data.wordQuiz.questions.length) {
      // 刷新更多题目
      this.loadWordQuestions();
      return;
    }
    this.showBankQuestion('wordQuiz', nextIdx);
  },

  onWordQuizPrev() {
    if (this.data.wordQuiz.loading || this.data.wordQuiz.submitting) return;
    if (this.data.wordQuiz.currentIndex <= 0) return;
    const prevIdx = this.data.wordQuiz.currentIndex - 1;
    this.showBankQuestion('wordQuiz', prevIdx);
  },

  onSelectOption(e) {
    const index = Number(e.currentTarget.dataset.index);
    const tabIndex = Number(e.currentTarget.dataset.tabIndex);
    if (tabIndex === 0) return this.onWordQuizSelect(index);
    else if (tabIndex === 1) return this.onPhraseSelect(index);
    else if (tabIndex === 2) return this.onReadingSelect(index);
  },

  // ============================================================
  //  模式 1: 短语语法（选择题）
  // ============================================================
  async loadPhraseQuestions() {
    return this.loadBankQuestions('phrase', [4]);
  },

  onPhraseSelect(index) {
    return this.submitBankAnswer('phrase', index);
  },

  onPhraseNext() {
    if (this.data.phrase.loading || this.data.phrase.submitting) return;
    const nextIdx = this.data.phrase.currentIndex + 1;
    if (nextIdx >= this.data.phrase.questions.length) {
      this.loadPhraseQuestions();
      return;
    }
    this.showBankQuestion('phrase', nextIdx);
  },

  // ============================================================
  //  模式 2: 阅读理解（AI生成文章 + 5题选择题）
  // ============================================================
  async loadReadingArticle() {
    const stage = this.getStage();
    this.setData({ 'reading.loading': true, 'reading.article': null, 'reading.questions': [] });
    try {
      const res = await api.fetchFromQuestionBank({ qtype: 'reading', stage, difficulty: '中级' });
      if (res) {
        const questions = (res.questions || []).map((q, i) => ({
          ...q,
          index: i,
        }));
        this.setData({
          'reading.article': {
            title: res.title || '',
            content: res.content || '',
            content_cn: res.content_cn || '',
            word_count: res.word_count || 0,
          },
          'reading.questions': questions,
          'reading.currentQuestion': questions[0],
          'reading.currentQIndex': 0,
          'reading.correctCount': 0,
          'reading.wrongCount': 0,
          'reading.questionBankId': res.question_bank_id || 0,
          'reading.loading': false,
          loading: false,
        });
        this.refreshFavStatus();
      }
    } catch (e) {
      console.error('加载阅读文章失败', e);
      this.setData({ 'reading.loading': false, loading: false });
    }
  },

  onReadingSelect(index) {
    if (this.data.reading.answered) return;
    const q = this.data.reading.questions[this.data.reading.currentQIndex];
    if (!q) return;
    const isCorrect = index === q.correct;
    this.setData({
      'reading.selectedIndex': index,
      'reading.answered': true,
      'reading.showAnalysis': true,
      'reading.correctCount': isCorrect ? this.data.reading.correctCount + 1 : this.data.reading.correctCount,
      'reading.wrongCount': isCorrect ? this.data.reading.wrongCount : this.data.reading.wrongCount + 1,
    });
  },

  onReadingPrev() {
    const prevIdx = this.data.reading.currentQIndex - 1;
    if (prevIdx < 0) return;
    this.setData({
      'reading.selectedIndex': -1,
      'reading.answered': false,
      'reading.showAnalysis': false,
      'reading.currentQIndex': prevIdx,
      'reading.currentQuestion': this.data.reading.questions[prevIdx],
    });
    this.refreshFavStatus();
  },

  onReadingNext() {
    const nextIdx = this.data.reading.currentQIndex + 1;
    if (nextIdx >= this.data.reading.questions.length) {
      // 全部答完，加载新文章
      wx.showToast({ title: '已完成所有题目', icon: 'success' });
      this.loadReadingArticle();
      return;
    }
    this.setData({
      'reading.selectedIndex': -1,
      'reading.answered': false,
      'reading.showAnalysis': false,
      'reading.currentQIndex': nextIdx,
      'reading.currentQuestion': this.data.reading.questions[nextIdx],
    });
    this.refreshFavStatus();
  },

  // ============================================================
  //  模式 3: 翻译（AI生成中文 → 用户写英文 → AI评分）
  // ============================================================
  beginWritingLoad(key) {
    if (this._disposed || this.data[key].scoring) return null;
    this._writingVersions = this._writingVersions || {};
    const version = this._writingVersions[key] = (this._writingVersions[key] || 0) + 1;
    this.setData({ [`${key}.loading`]: true, [`${key}.stem`]: '', [`${key}.reference`]: '',
      [`${key}.userAnswer`]: '', [`${key}.submitted`]: false, [`${key}.scoreResult`]: null,
      [`${key}.questionBankId`]: 0, [`${key}.error`]: '' });
    return version;
  },

  isWritingCurrent(key, version) {
    return !this._disposed && (this._writingVersions?.[key] || 0) === version;
  },

  async loadTranslationQuestion() {
    const version = this.beginWritingLoad('translation');
    if (version === null) return;
    const stage = this.getStage();
    try {
      const res = await api.fetchFromQuestionBank({ qtype: 'translation', stage });
      if (!this.isWritingCurrent('translation', version)) return;
      if (typeof res?.stem !== 'string' || !res.stem.trim()) throw new Error('翻译题目为空');
      if (res) {
        this.setData({
          'translation.stem': res.stem || '',
          'translation.topic': res.topic || '',
          'translation.keyVocab': res.key_vocab || [],
          'translation.reference': res.reference || '',
          'translation.hints': res.hints || '',
          'translation.userAnswer': '',
          'translation.submitted': false,
          'translation.scoreResult': null,
          'translation.questionBankId': res.question_bank_id || 0,
          'translation.loading': false,
          loading: false,
        });
        this.refreshFavStatus();
      }
    } catch (e) {
      if (!this.isWritingCurrent('translation', version)) return;
      console.error('加载翻译题失败', e);
      this.setData({ 'translation.loading': false, loading: false, 'translation.error': '加载失败，请重试' });
    }
  },

  onTranslationInput(e) {
    if (this.data.translation.loading || this.data.translation.submitted) return;
    this.setData({ 'translation.userAnswer': e.detail.value });
  },

  async onTranslationSubmit() {
    const t = this.data.translation;
    if (this._disposed || t.loading || t.submitted || !t.stem) return;
    if (!t.userAnswer.trim()) {
      wx.showToast({ title: '请先输入翻译', icon: 'none' });
      return;
    }
    const version = this._writingVersions?.translation || 0;
    this.setData({ 'translation.loading': true, 'translation.scoring': true });
    try {
      const res = await api.scoreTranslation({
        sourceText: t.stem,
        userAnswer: t.userAnswer,
        reference: t.reference,
        questionBankId: t.questionBankId,
      });
      if (!this.isWritingCurrent('translation', version)) return;
      this.setData({
        'translation.scoreResult': res,
        'translation.submitted': true,
        'translation.loading': false,
        'translation.scoring': false,
      });
    } catch (e) {
      if (!this.isWritingCurrent('translation', version)) return;
      console.error('评分失败', e);
      wx.showToast({ title: '评分失败，请重试', icon: 'none' });
      this.setData({ 'translation.loading': false, 'translation.scoring': false });
    }
  },

  onTranslationNext() {
    if (this.data.translation.loading) return;
    return this.loadTranslationQuestion();
  },

  onTranslationRetry() {
    if (this.data.translation.loading) return;
    this._writingVersions = this._writingVersions || {};
    this._writingVersions.translation = (this._writingVersions.translation || 0) + 1;
    this.setData({
      'translation.userAnswer': '',
      'translation.submitted': false,
      'translation.scoreResult': null,
    });
  },

  // ============================================================
  //  模式 4: 作文（AI生成情景 → 用户写作文 → AI评分）
  // ============================================================
  async loadEssayQuestion() {
    const version = this.beginWritingLoad('essay');
    if (version === null) return;
    const stage = this.getStage();
    try {
      const res = await api.fetchFromQuestionBank({ qtype: 'essay', stage });
      if (!this.isWritingCurrent('essay', version)) return;
      if (typeof res?.stem !== 'string' || !res.stem.trim()) throw new Error('作文题目为空');
      if (res) {
        this.setData({
          'essay.stem': res.stem || '',
          'essay.topic': res.topic || '',
          'essay.wordLimit': res.word_limit || '',
          'essay.reference': res.reference || '',
          'essay.keyPoints': res.key_points || [],
          'essay.userAnswer': '',
          'essay.submitted': false,
          'essay.scoreResult': null,
          'essay.questionBankId': res.question_bank_id || 0,
          'essay.loading': false,
          loading: false,
        });
        this.refreshFavStatus();
      }
    } catch (e) {
      if (!this.isWritingCurrent('essay', version)) return;
      console.error('加载作文题失败', e);
      this.setData({ 'essay.loading': false, loading: false, 'essay.error': '加载失败，请重试' });
    }
  },

  onEssayInput(e) {
    if (this.data.essay.loading || this.data.essay.submitted) return;
    this.setData({ 'essay.userAnswer': e.detail.value });
  },

  async onEssaySubmit() {
    const e = this.data.essay;
    if (this._disposed || e.loading || e.submitted || !e.stem) return;
    if (!e.userAnswer.trim()) {
      wx.showToast({ title: '请先写作文', icon: 'none' });
      return;
    }
    const version = this._writingVersions?.essay || 0;
    this.setData({ 'essay.loading': true, 'essay.scoring': true });
    try {
      const res = await api.scoreEssay({
        essayTopic: e.stem,
        userAnswer: e.userAnswer,
        reference: e.reference,
        questionBankId: e.questionBankId,
      });
      if (!this.isWritingCurrent('essay', version)) return;
      this.setData({
        'essay.scoreResult': res,
        'essay.submitted': true,
        'essay.loading': false,
        'essay.scoring': false,
      });
    } catch (err) {
      if (!this.isWritingCurrent('essay', version)) return;
      console.error('作文评分失败', err);
      wx.showToast({ title: '评分失败，请重试', icon: 'none' });
      this.setData({ 'essay.loading': false, 'essay.scoring': false });
    }
  },

  onEssayNext() {
    if (this.data.essay.loading) return;
    return this.loadEssayQuestion();
  },

  onEssayRetry() {
    if (this.data.essay.loading) return;
    this._writingVersions = this._writingVersions || {};
    this._writingVersions.essay = (this._writingVersions.essay || 0) + 1;
    this.setData({
      'essay.userAnswer': '',
      'essay.submitted': false,
      'essay.scoreResult': null,
    });
  },

  // ===== 设置 =====
  onSettingsTap() { this.setData({ showSettings: true }); },
  onCloseSettings() { this.setData({ showSettings: false }); },

  onDecreaseCount() {
    this.setData({ questionCount: Math.max(5, this.data.questionCount - 5) });
  },
  onIncreaseCount() {
    this.setData({ questionCount: Math.min(100, this.data.questionCount + 5) });
  },
  onQuickCount(e) {
    this.setData({ questionCount: Number(e.currentTarget.dataset.count) });
  },

  onStartTraining() {
    this.setData({ showSettings: false });
    // 重新加载当前模式
    this.loadTabData(this.data.activeTab);
  },
  onUnload() {
    this._disposed = true;
  },
});
