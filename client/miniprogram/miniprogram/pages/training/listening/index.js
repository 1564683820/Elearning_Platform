// 听力训练页：对接后端API，支持材料选择和听力答题
const api = require('../../../utils/api.js');
const { questionView, submitChoice } = require('../../../utils/material-training.js');

Page({
  data: {
    materials: [],
    currentMaterial: null,
    questions: [],
    currentQIndex: 0,
    isPlaying: false,
    playProgress: 0,
    currentTime: '0:00',
    totalTime: '0:00',
    playCount: 0,
    maxPlayCount: 3,
    speeds: ['0.8x', '1.0x', '1.2x'],
    activeSpeed: 1,
    selectedIndex: -1,
    answered: false,
    submitting: false,
    showAnalysis: false,
    question: null,
    showResult: false,
    correctCount: 0,
    totalCorrect: 0,
    loading: true,
    mode: 'list', // list/question/result
    stage: 0,
  },

  onLoad() {
    this.loadMaterials();
  },

  // 加载听力材料列表
  async loadMaterials() {
    this.setData({ loading: true });
    try {
      const res = await api.getListeningMaterials({ stage: this.data.stage });
      const materials = res.items || [];
      this.setData({ materials, loading: false });
    } catch (err) {
      console.error('加载听力材料失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  // 选择听力材料
  async onSelectMaterial(e) {
    const round = this._round = (this._round || 0) + 1;
    this.stopAudio();
    const id = e.currentTarget.dataset.id;
    this.setData({ loading: true });
    try {
      const detail = await api.getListeningDetail(id);
      if (round !== this._round) return;
      this.setData({
        currentMaterial: detail,
        questions: detail.questions || [],
        question: questionView(detail.questions?.[0]),
        questionStartedAt: Date.now(),
        submitting: false,
        showAnalysis: false,
        currentQIndex: 0,
        mode: 'question',
        selectedIndex: -1,
        answered: false,
        showResult: false,
        playCount: 0,
        correctCount: 0,
        totalCorrect: 0,
        loading: false,
        currentTime: '0:00',
        isPlaying: false,
        playProgress: 0,
        totalTime: detail.duration ? formatDuration(detail.duration) : '0:00',
      });
    } catch (err) {
      console.error('加载听力详情失败', err);
      if (round !== this._round) return;
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onPlayToggle() {
    if (!this.data.currentMaterial?.audio_url) {
      wx.showToast({ title: '该材料暂无可播放音频', icon: 'none' });
      return;
    }
    if (!this._audio) {
      const audio = this._audio = wx.createInnerAudioContext();
      audio.src = this.data.currentMaterial.audio_url;
      audio.playbackRate = [0.8, 1, 1.2][this.data.activeSpeed];
      audio.onPlay(() => {
        if (this._audio === audio) this.setData({ isPlaying: true, playCount: this.data.playCount + 1 });
      });
      const paused = () => { if (this._audio === audio) this.setData({ isPlaying: false }); };
      audio.onPause(paused);
      audio.onEnded(paused);
      audio.onError(() => {
        if (this._audio !== audio) return;
        this.stopAudio();
        wx.showToast({ title: '音频加载失败，请重试', icon: 'none' });
      });
      audio.onTimeUpdate(() => {
        if (this._audio !== audio) return;
        this.setData({ currentTime: formatDuration(audio.currentTime), totalTime: formatDuration(audio.duration),
          playProgress: audio.duration > 0 ? audio.currentTime / audio.duration * 100 : 0 });
      });
    }
    if (this.data.isPlaying) this._audio.pause();
    else this._audio.play();
  },

  stopAudio() {
    const audio = this._audio;
    this._audio = null;
    if (audio) audio.destroy();
    this.setData({ isPlaying: false });
  },

  onSpeedChange(e) {
    const index = Number(e.currentTarget.dataset.index);
    if (![0, 1, 2].includes(index)) return;
    this.setData({ activeSpeed: index });
    if (this._audio) this._audio.playbackRate = [0.8, 1, 1.2][index];
  },

  onSelectOption(e) {
    return submitChoice(this, 'currentQIndex', e, api);
  },

  onNextQuestion() {
    if (!this.data.answered || this.data.submitting) return;
    const nextIndex = this.data.currentQIndex + 1;
    if (nextIndex >= this.data.questions.length) {
      this.stopAudio();
      this.setData({
        mode: 'result',
        showResult: true,
        totalCorrect: this.data.correctCount,
      });
      return;
    }
    this.setData({
      currentQIndex: nextIndex,
      question: questionView(this.data.questions[nextIndex]),
      questionStartedAt: Date.now(),
      showAnalysis: false,
      selectedIndex: -1,
      answered: false,
    });
  },

  onBack() {
    this._round = (this._round || 0) + 1;
    this.stopAudio();
    if (this.data.mode !== 'list') {
      this.setData({ mode: 'list', currentMaterial: null });
    } else {
      wx.navigateBack();
    }
  },
  onSettingsTap() {
    wx.showToast({ title: '请返回列表选择听力材料', icon: 'none' });
  },
  onUnload() {
    this._round = (this._round || 0) + 1;
    this.stopAudio();
  },
  onHide() {
    if (this._audio) this._audio.pause();
  },
});

// 格式化时长
function formatDuration(seconds) {
  seconds = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}
