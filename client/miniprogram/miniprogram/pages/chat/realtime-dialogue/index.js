/**
 * 情景语音对话页面（REST 模式）
 *
 * 流程：点按录音 → 松手停止 → 上传音频 → 后端 STT+AI+TTS → 返回音频 URL
 * 小程序端：RecorderManager.start(duration:60000) / stop → wx.uploadFile → InnerAudioContext 播放
 * 优点：无需维护 WebSocket 长连接，无 RecorderManager 全局单例死循环问题
 */
var api = require('../../../utils/api.js');

var SCENE_LIST = [
  { id: 'coffee', name: '咖啡店点餐', icon: '' },
  { id: 'restaurant', name: '餐厅用餐', icon: '' },
  { id: 'shopping', name: '购物逛街', icon: '' },
  { id: 'travel', name: '旅行问路', icon: '' },
  { id: 'hotel', name: '酒店入住', icon: '' },
  { id: 'airport', name: '机场出行', icon: '' },
  { id: 'interview', name: '面试求职', icon: '' },
  { id: 'hospital', name: '看医生', icon: '' },
  { id: 'library', name: '图书馆', icon: '' },
  { id: 'friends', name: '结识朋友', icon: '' },
];

/** 格式化当前时间 HH:mm */
function now() {
  try {
    var d = new Date();
    var h = String(d.getHours());
    var m = String(d.getMinutes());
    if (h.length < 2) h = '0' + h;
    if (m.length < 2) m = '0' + m;
    return h + ':' + m;
  } catch (e) { return ''; }
}

Page({
  data: {
    statusBarHeight: 44, navBarHeight: 44, headerHeight: 100,
    bottomBarHeight: 160, safeBottom: 0,
    // idle / recording / uploading / playing / error
    pageStatus: 'idle',
    errorMsg: '',
    sceneList: SCENE_LIST, sceneIndex: -1,
    sceneName: '', sceneIcon: '', selectedScene: null,
    messages: [], scrollToId: '',
    isRecording: false,
    isPlaying: false,
    recordingDuration: 0,
    statusText: '准备就绪',
    micHintText: '请先选择场景',
    hasConversed: false,       // 一旦有过对话，不再展示场景选择
    evaluateResult: null,      // 评分结果 { score, feedback, strengths, improvements }
  },

  // 非响应式属性
  _recorderManager: null,
  _recorderReady: false,
  _recording: false,   // 同步守卫，防止重复 startRec
  _audioCtx: null,
  _conversationHistory: [],
  _recordingTimer: null,
  _evaluating: false,   // 是否正在评分

  // ═══════════════════════════════════════════
  // 生命周期
  // ═══════════════════════════════════════════

  onLoad: function (options) {
    this.initNavBar();
    if (options.scene) {
      var idx = SCENE_LIST.findIndex(function (s) { return s.id === options.scene; });
      this._applyScene(idx);
    } else {
      this.setData({ micHintText: '请先选择场景' });
    }
  },
  onUnload: function () { this.destroyAll(); },
  onHide: function () { this.destroyAll(); },

  initNavBar: function () {
    try {
      var sysInfo = typeof wx.getWindowInfoSync === 'function'
        ? Object.assign({}, wx.getAppBaseInfoSync(), wx.getWindowInfoSync())
        : wx.getSystemInfoSync();
      var btnRect = wx.getMenuButtonBoundingClientRect();
      var sb = sysInfo.statusBarHeight || 44;
      var nb = (btnRect.top - sb) * 2 + btnRect.height;
      var safe = sysInfo.safeArea ? (sysInfo.screenHeight - sysInfo.safeArea.bottom) : 0;
      this.setData({
        statusBarHeight: sb, navBarHeight: nb, headerHeight: sb + nb + 16,
        bottomBarHeight: 160 + safe, safeBottom: safe,
      });
    } catch (e) {
      this.setData({ headerHeight: 120, bottomBarHeight: 180 });
    }
  },

  destroyAll: function () {
    this._recording = false;
    this.stopRec();
    this.stopAudio();
    if (this._recordingTimer) { clearInterval(this._recordingTimer); this._recordingTimer = null; }
  },

  // ═══════════════════════════════════════════
  // 录音 — 点按开始 / 松手即传
  // ═══════════════════════════════════════════

  startRec: function () {
    if (this._recording || this.data.isRecording || this.data.pageStatus === 'uploading') return;
    this._recording = true; // 同步守卫，先于 onStart 设置
    this.errorClear();

    if (!this._recorderReady) {
      var r = wx.getRecorderManager();
      this._recorderManager = r;
      this._recorderReady = true;
      var self = this;

      r.onStart(function () {
        self.setData({ isRecording: true, pageStatus: 'recording', statusText: '录音中', micHintText: '松手发送' });
        self._startDurationTimer();
      });

      r.onStop(function (res) {
        self._recording = false;
        self._stopDurationTimer();
        self.setData({ isRecording: false, recordingDuration: 0 });
        if (res.tempFilePath) {
          self._uploadAudio(res.tempFilePath);
        }
      });

      r.onError(function (err) {
        self._recording = false;
        self._stopDurationTimer();
        self.setData({ isRecording: false, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
        var msg = (err.errMsg || '').toLowerCase();
        if (msg.includes('permission') || msg.includes('denied')) {
          wx.showToast({ title: '请授予麦克风权限', icon: 'none' });
        } else {
          wx.showToast({ title: '录音失败', icon: 'none' });
        }
      });
    }

    this._recorderManager.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      format: 'mp3',
    });
  },

  stopRec: function () {
    this._recording = false;
    if (this._recorderManager) {
      try { this._recorderManager.stop(); } catch (e) { /* ignore */ }
    }
    this._stopDurationTimer();
    this.setData({ isRecording: false, recordingDuration: 0, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
  },

  // ═══════════════════════════════════════════
  // 上传 & 对话
  // ═══════════════════════════════════════════

  _uploadAudio: function (tempFilePath) {
    var self = this;
    this.setData({ pageStatus: 'uploading', statusText: '处理中', micHintText: '等待回复...' });

    // 添加"小e正在听..."气泡
    var msgs = this.data.messages.slice();
    msgs.push({ role: 'ai', content: '', thinking: true, time: now() });
    this.setData({ messages: msgs });
    this.scrollBot();

    api.voiceChat({
      tempFilePath: tempFilePath,
      scenarioId: this.data.selectedScene ? this.data.selectedScene.id : '',
      level: 'intermediate',
      conversationHistory: this._conversationHistory,
    }).then(function (res) {
      // 移除 thinking 气泡
      msgs = self.data.messages.slice();
      var ti = self._lastThinkingIdx(msgs);
      if (ti >= 0) msgs.splice(ti, 1);

      // 标记已有对话（场景选择不再显示）
      if (!self.data.hasConversed) {
        self.setData({ hasConversed: true });
      }

      // 添加用户消息（默认折叠文字，因为主打听和说）
      if (res.transcription) {
        msgs.push({ role: 'user', content: res.transcription, time: now(), collapsed: true });
      }

      // 添加 AI 回复（含纠错分析）
      var displayContent = res.ai_content || '';
      if (res.analysis) {
        displayContent = res.ai_content + '\n\n纠错分析\n' + res.analysis;
      }
      msgs.push({ role: 'ai', content: displayContent, time: now(), collapsed: true });

      self.setData({ messages: msgs, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
      self.scrollBot();

      // 保存对话历史
      if (res.transcription) {
        self._conversationHistory.push({ role: 'user', content: res.transcription });
      }
      self._conversationHistory.push({ role: 'assistant', content: res.ai_content || '' });

      // 播放 TTS 音频
      if (res.audio_url) {
        self._playAudio(res.audio_url);
      } else if (res.audio_base64) {
        self._playAudioFromBase64(res.audio_base64);
      }
    }).catch(function (err) {
      msgs = self.data.messages.slice();
      var ti = self._lastThinkingIdx(msgs);
      if (ti >= 0) msgs.splice(ti, 1);
      self.setData({
        messages: msgs, pageStatus: 'error',
        statusText: '出错了', micHintText: '出错了',
        errorMsg: err.message || '语音对话失败，请重试',
      });
    });
  },

  _lastThinkingIdx: function (msgs) {
    for (var i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].thinking) return i;
    }
    return -1;
  },

  // ═══════════════════════════════════════════
  // TTS 音频播放
  // ═══════════════════════════════════════════

  _playAudio: function (audioUrl) {
    var self = this;
    this.stopAudio();

    var fullUrl = audioUrl;
    if (audioUrl.startsWith('/')) {
      fullUrl = require('../../../utils/api.js').BASE_URL.replace('/api/v1', '') + audioUrl;
    }

    var ctx = wx.createInnerAudioContext();
    this._audioCtx = ctx;
    ctx.obeyMuteSwitch = false;
    ctx.src = fullUrl;
    ctx.autoplay = true;
    this.setData({ isPlaying: true, pageStatus: 'playing', statusText: '播放中', micHintText: '小e说话中' });

    ctx.onEnded(function () {
      self._audioCtx = null;
      self.setData({ isPlaying: false, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
    });
    ctx.onError(function (err) {
      console.error('[RT] 播放错误:', err);
      self._audioCtx = null;
      self.setData({ isPlaying: false, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
    });
    ctx.play();
  },

  _playAudioFromBase64: function (b64) {
    var self = this;
    this.stopAudio();

    var fs = wx.getFileSystemManager();
    var path = wx.env.USER_DATA_PATH + '/tts_' + Date.now() + '.mp3';
    var binary = base64ToArrayBuffer(b64);
    try { fs.writeFileSync(path, binary); } catch (e) {
      console.error('[RT] 写文件失败:', e);
      self.setData({ isPlaying: false, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
      return;
    }

    var ctx = wx.createInnerAudioContext();
    this._audioCtx = ctx;
    ctx.obeyMuteSwitch = false;
    ctx.src = path;
    ctx.autoplay = true;
    this.setData({ isPlaying: true, pageStatus: 'playing', statusText: '播放中', micHintText: '小e说话中' });

    ctx.onEnded(function () {
      try { fs.unlinkSync(path); } catch (e) { /* ignore */ }
      self._audioCtx = null;
      self.setData({ isPlaying: false, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
    });
    ctx.onError(function (err) {
      console.error('[RT] 播放错误:', err);
      try { fs.unlinkSync(path); } catch (e) { /* ignore */ }
      self._audioCtx = null;
      self.setData({ isPlaying: false, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
    });
    ctx.play();
  },

  stopAudio: function () {
    if (this._audioCtx) {
      try { this._audioCtx.stop(); this._audioCtx.destroy(); } catch (e) { /* ignore */ }
      this._audioCtx = null;
    }
    this.setData({ isPlaying: false });
  },

  // ═══════════════════════════════════════════
  // 计时器
  // ═══════════════════════════════════════════

  _startDurationTimer: function () {
    var self = this;
    this._recordingDuration = 0;
    this._recordingTimer = setInterval(function () {
      self._recordingDuration++;
      self.setData({ recordingDuration: self._recordingDuration, statusText: '录音中 ' + self._recordingDuration + 's' });
    }, 1000);
  },

  _stopDurationTimer: function () {
    if (this._recordingTimer) {
      clearInterval(this._recordingTimer);
      this._recordingTimer = null;
    }
    this.setData({ recordingDuration: 0 });
  },

  // ═══════════════════════════════════════════
  // 场景选择
  // ═══════════════════════════════════════════

  onSceneSelect: function (e) {
    var idx = e.currentTarget.dataset.idx;
    if (idx === undefined) return;
    this._applyScene(idx);
  },

  _applyScene: function (idx) {
    if (idx < 0 || idx >= SCENE_LIST.length) return;
    this.setData({
      sceneIndex: idx, sceneName: SCENE_LIST[idx].name,
      sceneIcon: SCENE_LIST[idx].icon || '',
      selectedScene: SCENE_LIST[idx],
      micHintText: '按住说话',
    });
  },

  noop: function () {},

  // ═══════════════════════════════════════════
  // 页面交互
  // ═══════════════════════════════════════════

  onBack: function () { wx.navigateBack({ delta: 1 }); },

  onRecordStart: function () { this.startRec(); },
  onRecordEnd: function () { this.stopRec(); },

  onRecordTap: function () {
    if (this._evaluating) return; // 评分中不可操作
    if (this.data.isRecording) this.stopRec();
    else this.startRec();
  },

  onRetry: function () {
    this.errorClear();
    this.setData({ pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
  },

  errorClear: function () {
    this.setData({ errorMsg: '', pageStatus: 'idle' });
  },

  // ═══════════════════════════════════════════
  // 文字折叠 — 主打听和说，文字默认隐藏
  // ═══════════════════════════════════════════

  onToggleText: function (e) {
    var idx = e.currentTarget.dataset.idx;
    if (idx === undefined) return;
    var msgs = this.data.messages.slice();
    if (!msgs[idx]) return;
    msgs[idx] = Object.assign({}, msgs[idx], { collapsed: !msgs[idx].collapsed });
    this.setData({ messages: msgs });
  },

  // ═══════════════════════════════════════════
  // 结束对话 + AI 评分
  // ═══════════════════════════════════════════

  onEndConversation: function () {
    var self = this;
    if (this._evaluating) return;
    if (this._conversationHistory.length < 2) {
      wx.showToast({ title: '对话太短，再多聊几句吧', icon: 'none' });
      return;
    }

    wx.showModal({
      title: '结束对话',
      content: '确定结束本次口语练习，让 AI 对你的表现评分吗？',
      success: function (res) {
        if (res.confirm) self._doEvaluate();
      },
    });
  },

  _doEvaluate: function () {
    var self = this;
    self._evaluating = true;
    self.stopAudio();
    self.setData({ pageStatus: 'uploading', statusText: '评分中', micHintText: '评分中...', evaluateResult: null });

    // 添加评分中气泡
    var msgs = self.data.messages.slice();
    msgs.push({ role: 'ai', content: '', thinking: true, time: now() });
    self.setData({ messages: msgs });
    self.scrollBot();

    api.voiceEvaluate({
      scenarioId: self.data.selectedScene ? self.data.selectedScene.id : '',
      level: 'intermediate',
      conversationHistory: self._conversationHistory,
    }).then(function (res) {
      self._evaluating = false;
      // 移除 thinking 气泡
      msgs = self.data.messages.slice();
      var ti = self._lastThinkingIdx(msgs);
      if (ti >= 0) msgs.splice(ti, 1);
      msgs.push({ role: 'ai', content: '', time: now(), isScoreCard: true });
      self.setData({
        messages: msgs, pageStatus: 'idle', statusText: '已完成',
        micHintText: '开始新对话', evaluateResult: res,
      });
      self.scrollBot();
    }).catch(function (err) {
      self._evaluating = false;
      msgs = self.data.messages.slice();
      var ti = self._lastThinkingIdx(msgs);
      if (ti >= 0) msgs.splice(ti, 1);
      self.setData({ messages: msgs, pageStatus: 'idle', statusText: '准备就绪', micHintText: '按住说话' });
      wx.showToast({ title: '评分失败，请重试', icon: 'none' });
    });
  },

  onClear: function () {
    var self = this;
    wx.showModal({
      title: '清空对话',
      content: '确定要清空当前对话记录吗？',
      success: function (res) {
        if (res.confirm) {
          self._conversationHistory = [];
          self.stopAudio();
          self.setData({
            messages: [], pageStatus: 'idle', statusText: '准备就绪',
            micHintText: '按住说话', evaluateResult: null,
          });
        }
      },
    });
  },

  scrollBot: function () {
    var self = this;
    setTimeout(function () { self.setData({ scrollToId: 'msg-bottom' }); }, 50);
  },
});

/** Base64 → ArrayBuffer */
function base64ToArrayBuffer(b64) {
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var lookup = new Uint8Array(256);
  for (var i = 0; i < chars.length; i++) lookup[chars.charCodeAt(i)] = i;
  var str = b64.replace(/=+$/, '');
  var bytes = [];
  for (var i = 0; i < str.length; i += 4) {
    var a = lookup[str.charCodeAt(i)], b = lookup[str.charCodeAt(i + 1)];
    var c = lookup[str.charCodeAt(i + 2)], d = lookup[str.charCodeAt(i + 3)];
    bytes.push((a << 2) | (b >> 4));
    if (c !== undefined) bytes.push(((b & 0xf) << 4) | (c >> 2));
    if (d !== undefined) bytes.push(((c & 0x3) << 6) | d);
  }
  return new Uint8Array(bytes).buffer;
}
