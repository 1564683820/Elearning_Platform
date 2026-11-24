// 教材音频播放器组件 — 播放/暂停/进度条/逐句高亮
Component({
  properties: {
    audioUrl: { type: String, value: '' },
    sentences: { type: Array, value: [] },
    title: { type: String, value: '课文朗读' },
    showClose: { type: Boolean, value: true }
  },

  data: {
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    progressPercent: 0,
    currentSentenceIndex: -1,
    isHidden: false
  },

  _audioCtx: null,
  _updateTimer: null,

  lifetimes: {
    detached() {
      this._destroyAudio();
    }
  },

  observers: {
    audioUrl(url) {
      if (url) this.setData({ isHidden: false });
    }
  },

  methods: {
    // 初始化并播放音频
    playAudio() {
      const url = this.properties.audioUrl;
      if (!url || typeof url !== 'string' || !url.startsWith('http')) {
        console.warn('[textbook-audio] 忽略无效音频 URL:', url);
        return;
      }
      this._destroyAudio();
      const ctx = wx.createInnerAudioContext();
      ctx.src = url;
      ctx.autoplay = true;
      ctx.obeyMuteSwitch = false;

      ctx.onError(() => {
        wx.showToast({ title: '音频加载失败', icon: 'none' });
        this.setData({ isPlaying: false });
      });
      ctx.onCanplay(() => {
        if (ctx.duration) this.setData({ duration: ctx.duration });
      });
      ctx.onTimeUpdate(() => {
        const t = ctx.currentTime, d = ctx.duration || 1;
        this.setData({ currentTime: t, progressPercent: (t / d) * 100 });
        this._updateSentenceHighlight(t);
      });
      ctx.onEnded(() => {
        this.setData({ isPlaying: false, currentTime: 0, progressPercent: 0, currentSentenceIndex: -1 });
        this._stopUpdateTimer();
        this.triggerEvent('sentencechange', { index: -1, sentence: null, speaker: '', animationUrl: '' });
      });
      this._audioCtx = ctx;
      this.setData({ isPlaying: true, isHidden: false });
      this._startUpdateTimer();
    },

    // 播放/暂停切换
    onTogglePlay() {
      if (!this._audioCtx) { this.playAudio(); return; }
      if (this.data.isPlaying) {
        this._audioCtx.pause();
        this.setData({ isPlaying: false });
        this._stopUpdateTimer();
      } else {
        this._audioCtx.play();
        this.setData({ isPlaying: true });
        this._startUpdateTimer();
      }
    },

    // 进度条跳转
    onSeek(e) {
      if (!this._audioCtx || !this.data.duration) return;
      const touch = e.touches?.[0] || e.changedTouches?.[0];
      if (!touch) return;
      wx.createSelectorQuery().in(this).select('.progress-track').boundingClientRect(rect => {
        if (!rect) return;
        const ratio = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
        const seekTime = ratio * this.data.duration;
        this._audioCtx.seek(seekTime);
        this.setData({ currentTime: seekTime, progressPercent: ratio * 100 });
      }).exec();
    },

    // 逐句高亮更新 — 触发 sentencechange 事件通知父页面切换角色动画
    _updateSentenceHighlight(time) {
      const sentences = this.properties.sentences;
      if (!sentences || !sentences.length) return;
      for (let i = 0; i < sentences.length; i++) {
        const s = sentences[i];
        if (time >= (s.start || 0) && time <= (s.end || 999)) {
          if (this.data.currentSentenceIndex !== i) {
            this.setData({ currentSentenceIndex: i });
            // 触发句子切换事件，通知父页面更新角色动画
            this.triggerEvent('sentencechange', {
              index: i,
              sentence: s,
              speaker: s.speaker || '',
              animationUrl: s.animation_url || '',
            });
          }
          return;
        }
      }
      // 无匹配句子时重置
      if (this.data.currentSentenceIndex !== -1) {
        this.setData({ currentSentenceIndex: -1 });
        this.triggerEvent('sentencechange', { index: -1, sentence: null, speaker: '', animationUrl: '' });
      }
    },

    // 点击句子跳转
    onSentenceTap(e) {
      const idx = e.currentTarget.dataset.index;
      const s = this.properties.sentences[idx];
      if (!s || !this._audioCtx) return;
      const seekTime = s.start || 0;
      this._audioCtx.seek(seekTime);
      this.setData({ currentTime: seekTime });
      if (!this.data.isPlaying) {
        this._audioCtx.play();
        this.setData({ isPlaying: true });
        this._startUpdateTimer();
      }
    },

    // 上一句
    onPrevSentence() {
      const idx = Math.max(0, this.data.currentSentenceIndex - 1);
      this.onSentenceTap({ currentTarget: { dataset: { index: idx } } });
    },

    // 下一句
    onNextSentence() {
      const idx = Math.min(this.properties.sentences.length - 1, this.data.currentSentenceIndex + 1);
      this.onSentenceTap({ currentTarget: { dataset: { index: idx } } });
    },

    // 关闭
    onClose() {
      this._destroyAudio();
      this.setData({ isHidden: true, isPlaying: false });
    },

    // 时间格式化
    formatTime(t) {
      if (!t || !isFinite(t)) return '00:00';
      const m = Math.floor(t / 60);
      const s = Math.floor(t % 60);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    },

    _startUpdateTimer() {
      this._stopUpdateTimer();
      this._updateTimer = setInterval(() => {
        if (this._audioCtx && this.data.isPlaying) {
          const t = this._audioCtx.currentTime, d = this._audioCtx.duration || 1;
          this.setData({ currentTime: t, progressPercent: (t / d) * 100 });
          this._updateSentenceHighlight(t);
        }
      }, 250);
    },

    _stopUpdateTimer() {
      if (this._updateTimer) { clearInterval(this._updateTimer); this._updateTimer = null; }
    },

    _destroyAudio() {
      this._stopUpdateTimer();
      if (this._audioCtx) { this._audioCtx.destroy(); this._audioCtx = null; }
    }
  }
});
