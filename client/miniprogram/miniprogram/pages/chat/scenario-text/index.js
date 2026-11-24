/**
 * 文字场景对话页面
 *
 * 选择场景后，与小e进行文字角色扮演对话。
 * 使用 POST /api/v1/ai/chat 接口，scenario 参数控制 AI 角色。
 */
const api = require('../../../utils/api.js');

// 场景预设列表（与后端 SCENARIO_PRESETS 一致）
const SCENE_LIST = [
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
];

Page({
  data: {
    // 导航栏
    statusBarHeight: 44,
    navBarHeight: 44,
    headerHeight: 100,
    safeBottom: 0,
    // 场景
    sceneName: '',
    sceneIcon: '',
    sceneId: '',
    // 消息
    messages: [],
    inputValue: '',
    sending: false,
    scrollToId: '',
    level: 'intermediate',
  },

  _typewriterTimer: null,

  onLoad(options) {
    this.initNavBar();
    // 从 URL 参数获取场景
    const sceneId = options.scene || '';
    if (sceneId) {
      const scene = SCENE_LIST.find(s => s.id === sceneId);
      if (scene) {
        this.setData({
          sceneId: scene.id,
          sceneName: scene.name,
          sceneIcon: scene.icon,
        });
        // 自动开场
        setTimeout(() => this.sendMessage('', true), 300);
      }
    }
  },

  onUnload() {
    if (this._typewriterTimer) {
      clearInterval(this._typewriterTimer);
      this._typewriterTimer = null;
    }
  },

  initNavBar() {
    try {
      const sysInfo = typeof wx.getWindowInfoSync === 'function'
        ? { ...wx.getAppBaseInfoSync(), ...wx.getWindowInfoSync() }
        : wx.getSystemInfoSync();
      const btnRect = wx.getMenuButtonBoundingClientRect();
      const statusBarHeight = sysInfo.statusBarHeight || 44;
      const navBarHeight = (btnRect.top - statusBarHeight) * 2 + btnRect.height;
      const headerHeight = statusBarHeight + navBarHeight + 16;
      const safeBottom = sysInfo.safeArea
        ? (sysInfo.screenHeight - sysInfo.safeArea.bottom)
        : 0;
      this.setData({ statusBarHeight, navBarHeight, headerHeight, safeBottom });
    } catch (e) {
      console.error('获取系统信息失败', e);
      this.setData({ headerHeight: 120, safeBottom: 0 });
    }
  },

  /** 返回 */
  onBack() {
    wx.navigateBack({ delta: 1 });
  },

  /** 输入 */
  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  /** 发送 */
  onSend() {
    const text = this.data.inputValue.trim();
    if (!text || this.data.sending) return;
    this.sendMessage(text);
  },

  /** 通用发送消息 */
  async sendMessage(userText, isInit = false) {
    const { messages, sceneId, level } = this.data;

    if (isInit) {
      // 开场：发送空消息触发 AI 自我介绍
      messages.push({ role: 'ai', content: '', thinking: true });
    } else {
      messages.push({ role: 'user', content: userText });
      messages.push({ role: 'ai', content: '', thinking: true });
    }

    this.setData({
      messages,
      inputValue: '',
      sending: true,
    });
    this.scrollToBottom();

    // 构造消息历史（最近 20 条，过滤 thinking）
    const chatHistory = messages
      .filter(m => m.role !== 'ai' || !m.thinking)
      .slice(-20)
      .map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }));

    try {
      const result = await api.chatWithAI({
        messages: chatHistory,
        scenario: sceneId,
        level: level || 'intermediate',
        provider: 'cloudbase',
      });
      this.typewriterOutput(result.content);
    } catch (err) {
      console.error('场景对话失败', err);
      const msgs = [...this.data.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'ai' && msgs[i].thinking) {
          msgs[i] = { role: 'ai', content: '抱歉，回复生成失败，请稍后重试。', thinking: false };
          break;
        }
      }
      this.setData({ messages: msgs, sending: false });
    }
  },

  /** 打字机效果 */
  typewriterOutput(fullText) {
    const msgs = [...this.data.messages];
    let targetIdx = -1;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'ai' && msgs[i].thinking) {
        targetIdx = i;
        msgs[i] = { role: 'ai', content: '', thinking: false };
        break;
      }
    }
    if (targetIdx === -1) {
      msgs.push({ role: 'ai', content: fullText, thinking: false });
      this.setData({ messages: msgs, sending: false });
      return;
    }
    this.setData({ messages: msgs });

    let index = 0;
    const step = 3;
    const speed = 25;
    this._typewriterTimer = setInterval(() => {
      if (index >= fullText.length) {
        clearInterval(this._typewriterTimer);
        this._typewriterTimer = null;
        this.setData({ sending: false });
        this.scrollToBottom();
        return;
      }
      const end = Math.min(index + step, fullText.length);
      const partial = fullText.slice(0, end);
      const latestMsgs = [...this.data.messages];
      latestMsgs[targetIdx].content = partial;
      this.setData({ messages: latestMsgs });
      index = end;
      this.scrollToBottom();
    }, speed);
  },

  /** 滚动到底部 */
  scrollToBottom() {
    this.setData({ scrollToId: 'msg-bottom' });
    setTimeout(() => {
      this.setData({ scrollToId: '' });
    }, 100);
  },
});
