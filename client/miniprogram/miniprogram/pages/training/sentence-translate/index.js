// 翻译对照练习：使用题库中的原文及参考译文，支持切换方向。
const api = require('../../../utils/api.js');

Page({
  data: {
    question: null,
    currentIndex: 0,
    direction: 'zh2en', // zh2en or en2zh
    inputText: '',
    showReference: false,
    referenceText: '',
    loading: false,
    error: '',
  },

  onLoad() {
    this.loadQuestions();
  },

  // 加载翻译题目
  async loadQuestions() {
    const request = this._request = (this._request || 0) + 1;
    this.setData({ loading: true, error: '', question: null, inputText: '', showReference: false, referenceText: '' });
    try {
      const res = await api.fetchFromQuestionBank({ qtype: 'translation', stage: getApp().globalData.stage || 4 });
      if (request !== this._request) return;
      if (typeof res?.stem !== 'string' || !res.stem.trim()
          || typeof res.reference !== 'string' || !res.reference.trim()) {
        throw new Error('题目缺少原文或参考译文');
      }
      this.setData({
        question: { id: res.question_bank_id, zh: res.stem, en: res.reference, hints: res.hints || '' },
        loading: false,
      });
    } catch (err) {
      if (request !== this._request) return;
      console.error('加载翻译题失败', err);
      this.setData({ question: null, error: '暂时无法加载翻译题，请重试', loading: false });
    }
  },

  onToggleDirection() {
    this.changeDirection(this.data.direction === 'zh2en' ? 'en2zh' : 'zh2en');
  },

  onDirectionChange(e) {
    this.changeDirection(e.currentTarget.dataset.dir);
  },

  changeDirection(direction) {
    if (!['zh2en', 'en2zh'].includes(direction) || direction === this.data.direction) return;
    this.setData({
      direction,
      inputText: '',
      showReference: false,
      referenceText: '',
    });
  },

  onInput(e) {
    this.setData({ inputText: e.detail.value });
  },

  // 只展示当前题目对应的参考译文，不把查看参考记为判分成功。
  onSubmit() {
    if (this.data.loading || !this.data.question) return;
    if (!this.data.inputText.trim()) {
      wx.showToast({ title: '请先输入翻译', icon: 'none' });
      return;
    }

    const question = this.data.question;
    this.setData({ showReference: true,
      referenceText: this.data.direction === 'zh2en' ? question.en : question.zh });
  },

  onNextQuestion() {
    if (this.data.loading || !this.data.showReference) return;
    this.setData({ currentIndex: this.data.currentIndex + 1 });
    return this.loadQuestions();
  },

  onBack() {
    this._request = (this._request || 0) + 1;
    wx.navigateBack();
  },
  onUnload() {
    this._request = (this._request || 0) + 1;
  },
  onSettingsTap() {
    wx.showToast({ title: '输入翻译后可对照参考译文', icon: 'none' });
  },
});
