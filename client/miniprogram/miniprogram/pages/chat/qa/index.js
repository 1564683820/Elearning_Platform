const api = require('../../../utils/api.js');
const { markdownToHtml } = require('../../../utils/markdown.js');

Page({
  data: {
    tabs: [{name: '情景对话', icon: ''}, {name: '智能问答', icon: ''}, {name: '智能翻译', icon: ''}],
    activeTab: 1,
    // 导航栏安全区
    statusBarHeight: 44,
    navBarTop: 0,
    navBarHeight: 44,
    headerHeight: 0,
    inputBarHeight: 56,
    // 智能问答数据
    messages: [],
    inputValue: '',
    sending: false,
    scrollToId: '',
    // 智能翻译数据
    direction: 'zh2en',
    inputText: '',
    outputText: '',
    translated: false,
    charCount: 0,
    translating: false,
    // 情景对话入口（选择 + 跳转模式）
    scenarioPresets: [],          // 预设场景列表
    selectedMode: '',             // 选择的模式: 'realtime' | 'text'
    selectedScene: null,          // 选中的场景对象
    // 麦克风测试
    micTestVisible: false,        // 是否展开麦克风测试面板
    micTestRecording: false,      // 是否正在测试录音
    micTestTempPath: '',          // 测试录音临时文件路径
    micTestPlaying: false,        // 是否正在播放测试录音
    // 兼容旧字段
    scenarioText: '',
    scenarioWords: [],
    // 英语水平等级
    level: 'intermediate',
    // AI 提供商
    provider: 'cloudbase',
    providerLabel: 'CloudBase AI'
  },

  onLoad() {
    this.initNavBar();
    // 初始化欢迎消息（同时生成 Markdown 渲染版）
    const welcomeText = '👋 你好呀，我是**小e**，你的专属 AI 英语学习助手！\n\n我可以帮你：\n- 📖 **讲解知识点** — 输入你想了解的英语语法、词汇、句型\n- 📝 **分析错题** — 告诉我「帮我总结错题」，我会检索你的错题并生成详细报告\n- 🗣️ **情景对话** — 切换到「情景对话」Tab，选择场景进行角色扮演练习\n- 💬 **句子润色** — 发来你的英文句子，我帮你检查和改进\n\n有什么需要帮助的吗？';
    this.setData({
      messages: [{
        role: 'ai',
        content: welcomeText,
        contentHtml: markdownToHtml(welcomeText)
      }]
    });
    // 加载情景对话场景列表
    this.loadScenarios();
    // 加载用户 AI 配置
    this.loadProviderConfig();
  },

  onUnload() {
    // 清理打字机定时器
    if (this._typewriterTimer) {
      clearInterval(this._typewriterTimer);
      this._typewriterTimer = null;
    }
    // 清理麦克风测试资源（避免 RecorderManager 全局单例残留导致下次卡死）
    if (this._micTestRecorder && this.data.micTestRecording) {
      try { this._micTestRecorder.stop(); } catch (e) { /* ignore */ }
    }
    if (this._micTestAudio) {
      try { this._micTestAudio.stop(); } catch (e) { /* ignore */ }
      this._micTestAudio = null;
    }
    this._micTestStarting = false;
  },

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
      // header总高度 = 状态栏 + 导航行 + sparkle行 + tab行
      const headerHeight = statusBarHeight + navBarHeight + 8 + 52 + 44;
      // 输入栏高度约 = 上padding(12px) + 输入框(~20px) + 下padding(12px) + 安全区
      const safeBottom = sysInfo.safeArea ? (sysInfo.screenHeight - sysInfo.safeArea.bottom) : 0;
      const inputBarHeight = 44 + safeBottom;
      this.setData({
        statusBarHeight: statusBarHeight,
        navBarTop: statusBarHeight,
        navBarHeight: navBarHeight,
        headerHeight: headerHeight,
        inputBarHeight: inputBarHeight
      });
    } catch (e) {
      console.error('获取系统信息失败', e);
      this.setData({ headerHeight: 180, inputBarHeight: 56 });
    }
  },

  async loadProviderConfig() {
    try {
      const profile = await api.getUserProfile();
      if (profile && profile.apiKey) {
        this.setData({ provider: 'siliconflow', providerLabel: 'SiliconFlow' });
      }
    } catch (err) {
      console.error('加载 AI 配置失败', err);
    }
  },

  onSwitchProvider() {
    const newProvider = this.data.provider === 'cloudbase' ? 'siliconflow' : 'cloudbase';
    const newLabel = newProvider === 'cloudbase' ? 'CloudBase AI' : 'SiliconFlow';
    this.setData({ provider: newProvider, providerLabel: newLabel });
    wx.showToast({ title: `已切换到 ${newLabel}`, icon: 'none' });
  },

  onTabChange(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ activeTab: index });
  },

  // ===== 智能问答 =====
  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  async onSend() {
    if (!this.data.inputValue.trim() || this.data.sending) return;
    const userMsg = this.data.inputValue.trim();
    const userMessages = [...this.data.messages, { role: 'user', content: userMsg }];

    // 添加用户消息 + 占位的「正在思考…」AI 消息
    const messagesWithThinking = [...userMessages, { role: 'ai', content: '', thinking: true }];
    this.setData({ messages: messagesWithThinking, inputValue: '', sending: true });
    this.scrollToBottom();

    try {
      // 构造消息历史（最近 10 条，过滤 thinking 占位）
      const chatHistory = messagesWithThinking
        .filter(m => m.role !== 'ai' || !m.thinking)
        .slice(-10)
        .map(m => ({
          role: m.role === 'ai' ? 'assistant' : 'user',
          content: m.content
        }));

      const result = await api.chatWithAI({ messages: chatHistory, provider: this.data.provider });

      // 用打字机效果逐字输出
      this.typewriterOutput(result.content);
    } catch (err) {
      console.error('AI 回复失败', err);
      // 发生错误时把 thinking 占位替换为错误提示
      const msgs = [...this.data.messages];
      const errText = '抱歉，回复生成失败，请稍后重试。';
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'ai' && msgs[i].thinking) {
          msgs[i] = { role: 'ai', content: errText, contentHtml: markdownToHtml(errText), thinking: false };
          break;
        }
      }
      this.setData({ messages: msgs, sending: false });
    }
  },

  /**
   * 打字机效果 — 逐字展示 AI 回复
   */
  typewriterOutput(fullText) {
    const msgs = [...this.data.messages];
    // 找到 thinking 占位，替换为实际内容（空字符串开始）
    let targetIdx = -1;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'ai' && msgs[i].thinking) {
        targetIdx = i;
        msgs[i] = { role: 'ai', content: '', contentHtml: '', thinking: false };
        break;
      }
    }
    if (targetIdx === -1) {
      // 异常情况：没找到 thinking 占位，直接追加
      msgs.push({ role: 'ai', content: fullText, contentHtml: markdownToHtml(fullText), thinking: false });
      this.setData({ messages: msgs, sending: false });
      return;
    }

    this.setData({ messages: msgs });

    // 流式逐字输出（同时生成 Markdown HTML）
    let index = 0;
    const step = 3; // 每次追加 3 个字符
    const speed = 25; // 25ms 每帧

    this._typewriterTimer = setInterval(() => {
      if (index >= fullText.length) {
        clearInterval(this._typewriterTimer);
        this._typewriterTimer = null;
        this.setData({ sending: false });
        return;
      }
      const end = Math.min(index + step, fullText.length);
      const partial = fullText.slice(0, end);
      const latestMsgs = [...this.data.messages];
      latestMsgs[targetIdx].content = partial;
      latestMsgs[targetIdx].contentHtml = markdownToHtml(partial);
      this.setData({ messages: latestMsgs });
      index = end;
      // 每次更新后自动滚到底部
      this.scrollToBottom();
    }, speed);
  },

  scrollToBottom() {
    // 触发 scroll-view 滚动到底部：设置 scrollToId 触发 scroll-into-view
    this.setData({ scrollToId: 'msg-bottom' });
    // 重置以便下次再次触发
    setTimeout(() => {
      this.setData({ scrollToId: '' });
    }, 100);
  },

  onAddAttachment() {
    wx.showToast({ title: '附件功能开发中', icon: 'none' });
  },

  // ===== 智能翻译 =====
  onToggleDirection() {
    const newDir = this.data.direction === 'zh2en' ? 'en2zh' : 'zh2en';
    this.setData({
      direction: newDir,
      translated: false,
      outputText: ''
    });
  },

  onTranslateInput(e) {
    this.setData({
      inputText: e.detail.value,
      charCount: e.detail.value.length
    });
  },

  async onTranslate() {
    if (!this.data.inputText.trim()) {
      wx.showToast({ title: '请输入内容', icon: 'none' });
      return;
    }
    this.setData({ translating: true });
    wx.showLoading({ title: '翻译中...' });

    try {
      const result = await api.translateText({
        text: this.data.inputText,
        direction: this.data.direction,
        provider: this.data.provider
      });
      this.setData({
        outputText: result.output,
        translated: true
      });
    } catch (err) {
      console.error('翻译失败', err);
      wx.showToast({ title: '翻译失败，请稍后重试', icon: 'none' });
    } finally {
      wx.hideLoading();
      this.setData({ translating: false });
    }
  },

  onCopy() {
    wx.setClipboardData({
      data: this.data.outputText,
      success: () => {
        wx.showToast({ title: '已复制', icon: 'success' });
      }
    });
  },

  onImageTranslate() {
    wx.showToast({ title: '图片翻译开发中', icon: 'none' });
  },

  // ===== 情景对话 =====

  async loadScenarios() {
    try {
      const result = await api.getScenarioPresets();
      if (result && result.presets) {
        this.setData({ scenarioPresets: result.presets });
      }
    } catch (err) {
      console.error('加载场景列表失败', err);
      // 本地兜底场景列表（含图标）
      this.setData({
        scenarioPresets: [
          { id: 'coffee', name: '咖啡店点餐', icon: '☕' },
          { id: 'restaurant', name: '餐厅用餐', icon: '🍽️' },
          { id: 'shopping', name: '购物逛街', icon: '🛍️' },
          { id: 'travel', name: '旅行问路', icon: '🗺️' },
          { id: 'hotel', name: '酒店入住', icon: '🏨' },
          { id: 'airport', name: '机场出行', icon: '✈️' },
          { id: 'interview', name: '面试求职', icon: '💼' },
          { id: 'hospital', name: '看医生', icon: '🏥' },
          { id: 'library', name: '图书馆', icon: '📚' },
          { id: 'friends', name: '结识朋友', icon: '🤝' },
        ]
      });
    }
  },

  // ===== 麦克风测试 =====

  /** 切换麦克风测试面板 */
  onToggleMicTest() {
    // 关闭时清理资源
    if (this.data.micTestVisible) {
      if (this.data.micTestRecording && this._micTestRecorder) {
        this._micTestRecorder.stop();
      }
      if (this._micTestAudio) {
        this._micTestAudio.stop();
        this._micTestAudio = null;
      }
    }
    this.setData({
      micTestVisible: !this.data.micTestVisible,
      micTestRecording: false,
      micTestTempPath: '',
      micTestPlaying: false,
    });
    // 关闭面板时重置防重入标记
    if (!this.data.micTestVisible) {
      this._micTestStarting = false;
    }
  },

  /** 开始测试录音（防重入） */
  startMicTestRecord() {
    // ★ 防重入：防止快速双击导致两次 start() → RecorderManager 内部状态混乱 → 卡死
    if (this._micTestStarting || this.data.micTestRecording) return;
    this._micTestStarting = true;
    this.setData({ micTestRecording: true });

    const recorderManager = wx.getRecorderManager();
    this._micTestRecorder = recorderManager;

    recorderManager.onStart(() => {
      // 录音已启动，状态由 _micTestStarting 和 data.micTestRecording 控制
    });

    recorderManager.onError((err) => {
      console.error('麦克风测试录音失败', err);
      this._micTestStarting = false;
      this.setData({ micTestRecording: false });
      wx.showToast({ title: '录音失败，请检查麦克风权限', icon: 'none' });
    });

    recorderManager.onStop((res) => {
      this._micTestStarting = false;
      this.setData({
        micTestRecording: false,
        micTestTempPath: res.tempFilePath || '',
      });
    });

    try {
      recorderManager.start({
        duration: 30000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 48000,
        format: 'mp3',
      });
    } catch (e) {
      console.error('启动录音发生异常', e);
      this._micTestStarting = false;
      this.setData({ micTestRecording: false });
      wx.showToast({ title: '启动录音失败', icon: 'none' });
    }
  },

  /** 停止测试录音 */
  stopMicTestRecord() {
    if (this._micTestRecorder && this.data.micTestRecording) {
      this._micTestRecorder.stop();
    }
  },

  /** 播放测试录音 */
  playMicTestAudio() {
    const { micTestTempPath, micTestPlaying } = this.data;
    if (!micTestTempPath) return;

    if (micTestPlaying) {
      if (this._micTestAudio) {
        this._micTestAudio.stop();
        this._micTestAudio = null;
      }
      this.setData({ micTestPlaying: false });
      return;
    }

    const audioContext = wx.createInnerAudioContext();
    this._micTestAudio = audioContext;
    audioContext.src = micTestTempPath;

    audioContext.onPlay(() => {
      this.setData({ micTestPlaying: true });
    });

    audioContext.onEnded(() => {
      this.setData({ micTestPlaying: false });
      this._micTestAudio = null;
    });

    audioContext.onError((err) => {
      console.error('播放测试录音失败', err);
      this.setData({ micTestPlaying: false });
      this._micTestAudio = null;
      wx.showToast({ title: '播放失败', icon: 'none' });
    });

    audioContext.play();
  },

  // ===== 情景对话入口：模式选择 + 场景选择 + 跳转 =====

  /** 选择对话模式 */
  onSelectMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ selectedMode: mode });
  },

  /** 选择场景 */
  onSelectScene(e) {
    const id = e.currentTarget.dataset.id;
    const name = e.currentTarget.dataset.name;
    const icon = e.currentTarget.dataset.icon;
    this.setData({
      selectedScene: { id, name, icon }
    });
  },

  /** 进入对话 */
  onEnterDialogue() {
    const { selectedMode, selectedScene } = this.data;
    if (!selectedMode || !selectedScene) {
      wx.showToast({ title: '请先选择方式和场景', icon: 'none' });
      return;
    }

    if (selectedMode === 'realtime') {
      // 实时语音对话 → 跳转到实时语音页面
      wx.navigateTo({
        url: `/pages/chat/realtime-dialogue/index?scene=${selectedScene.id}`,
      });
    } else {
      // 文字场景对话 → 跳转到文字场景对话页面
      wx.navigateTo({
        url: `/pages/chat/scenario-text/index?scene=${selectedScene.id}`,
      });
    }
  },
});
