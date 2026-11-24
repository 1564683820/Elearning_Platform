// 教师端首页 — 支持多班级选择、班级概览、高频错题、快捷操作
const app = getApp();
const api = require('../../../utils/api');
const { markdownToHtml } = require('../../../utils/markdown');
const { getTeacherDashboard, getMyClasses, WEB_ADMIN_URL } = api;

Page({
  data: {
    // 班级列表及选择
    classList: [],
    classIndex: 0,
    selectedClassId: null,
    className: '',
    // 看板数据
    stats: [
      { label: '学生人数', value: 0 },
      { label: '单词量', value: 0 },
      { label: '平均正确率', value: '0%' },
      { label: '今日活跃', value: 0 },
    ],
    mistakes: [],
    hasClasses: false,
    // AI 问答
    showAIChat: false,
    aiMessages: [],
    aiInput: '',
    aiSending: false,
    aiScrollToId: '',
  },

  onLoad() {
    this.loadClasses();
  },

  onShow() {
    // 如果已有班级列表，重新加载当前班级数据
    if (this.data.selectedClassId) {
      this.loadDashboard(this.data.selectedClassId);
    }
  },

  async loadClasses() {
    try {
      const result = await getMyClasses();
      const classList = result.classes || [];
      if (classList.length > 0) {
        const first = classList[0];
        this.setData({
          classList,
          className: first.name,
          selectedClassId: first.id,
          hasClasses: true,
        });
        await this.loadDashboard(first.id);
      } else {
        this.setData({ hasClasses: false });
      }
    } catch (err) {
      console.error('加载班级列表失败', err);
      this.setData({ hasClasses: false });
    }
  },

  onClassChange(e) {
    const index = e.detail.value;
    const cls = this.data.classList[index];
    this.setData({ classIndex: index, className: cls.name, selectedClassId: cls.id });
    this.loadDashboard(cls.id);
  },

  async loadDashboard(classId) {
    try {
      const dash = await getTeacherDashboard(classId);
      if (dash) {
        this.setData({
          stats: [
            { label: '学生人数', value: dash.student_count || 0 },
            { label: '单词量', value: dash.total_words || 0 },
            { label: '平均正确率', value: (dash.avg_accuracy || 0) + '%' },
            { label: '今日活跃', value: dash.active_today || 0 },
          ],
          mistakes: dash.top_mistakes || [],
        });
      }
    } catch (err) {
      console.error('加载看板数据失败', err);
    }
  },

  goStudents() {
    if (!this.data.selectedClassId) return;
    wx.navigateTo({
      url: `/pages/teacher/students/index?classId=${this.data.selectedClassId}&className=${encodeURIComponent(this.data.className)}`,
    });
  },

  goExams() {
    if (!this.data.selectedClassId) return;
    wx.navigateTo({
      url: `/pages/teacher/exam-grade/index?classId=${this.data.selectedClassId}`,
    });
  },

  goGrade() {
    this.goExams();
  },

  openAdmin() {
    wx.setClipboardData({
      data: WEB_ADMIN_URL,
      success: () => wx.showToast({ title: '已复制管理后台地址', icon: 'none' }),
    });
  },

  // ==================== AI 问答 ====================

  // 打开 AI 问答弹窗
  onAIChatClick() {
    this.setData({ showAIChat: true, aiInput: '' });
    if (this.data.aiMessages.length === 0) {
      const welcomeText = '你好！我是教学助手。\n\n我可以帮你：\n\n• 备课建议 — 根据班级学情推荐教学方法\n• 题目设计 — 生成课堂练习或考试题目\n• 数据分析 — 解读学生成绩和错题报告\n• 教学咨询 — 回答英语教学相关问题\n\n请告诉我你的需求！';
      this.setData({
        aiMessages: [{ role: 'ai', content: welcomeText, contentRendered: markdownToHtml(welcomeText), thinking: false }]
      });
    }
    this.aiScrollBottom();
  },

  // AI 输入框绑定
  onAIInput(e) {
    this.setData({ aiInput: e.detail.value });
  },

  // 发送 AI 问题
  async onAISend() {
    const text = (this.data.aiInput || '').trim();
    if (!text || this.data.aiSending) return;

    const stats = this.data.stats;
    const newMessages = [
      ...this.data.aiMessages,
      { role: 'user', content: text, contentRendered: markdownToHtml(text), thinking: false },
      { role: 'ai', content: '', contentRendered: '', thinking: true }
    ];
    this.setData({ aiMessages: newMessages, aiInput: '', aiSending: true });
    this.aiScrollBottom();

    try {
      // 构造消息历史（含班级上下文）
      const chatHistory = [];
      if (stats && stats[0] && stats[0].value) {
        const className = this.data.className || '';
        const studentCount = stats[0].value;
        const avgAccuracy = stats[2] ? stats[2].value : '0%';
        chatHistory.push({
          role: 'user',
          content: `【班级上下文】\n班级：${className}\n学生人数：${studentCount}\n平均正确率：${avgAccuracy}\n\n（以上是教师当前班级概况，请根据此回答教师的问题）`
        });
      }
      chatHistory.push(
        ...newMessages
          .filter(m => m.role !== 'ai' || !m.thinking)
          .slice(-10)
          .map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }))
      );

      const result = await api.chatWithAI({ messages: chatHistory, scenario: 'teacher' });
      // 打字机效果逐字输出
      this.aiTypewriterOutput(result.content);
    } catch (err) {
      console.error('AI 回复失败', err);
      const msgs = [...this.data.aiMessages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'ai' && msgs[i].thinking) {
          const errText = '抱歉，回复生成失败，请稍后重试。';
          msgs[i] = { role: 'ai', content: errText, contentRendered: markdownToHtml(errText), thinking: false };
          break;
        }
      }
      this.setData({ aiMessages: msgs, aiSending: false });
    }
  },

  // AI 打字机流式输出（每步同时生成 Markdown 渲染版本）
  aiTypewriterOutput(fullText) {
    const msgs = [...this.data.aiMessages];
    let targetIdx = -1;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'ai' && msgs[i].thinking) {
        targetIdx = i;
        msgs[i] = { role: 'ai', content: '', contentRendered: '', thinking: false };
        break;
      }
    }
    if (targetIdx === -1) {
      msgs.push({ role: 'ai', content: fullText, contentRendered: markdownToHtml(fullText), thinking: false });
      this.setData({ aiMessages: msgs, aiSending: false });
      return;
    }
    this.setData({ aiMessages: msgs });

    let index = 0;
    const step = 3;
    const speed = 25;

    this._aiTypewriterTimer = setInterval(() => {
      if (index >= fullText.length) {
        clearInterval(this._aiTypewriterTimer);
        this._aiTypewriterTimer = null;
        this.setData({ aiSending: false });
        return;
      }
      const end = Math.min(index + step, fullText.length);
      const partial = fullText.slice(0, end);
      const latestMsgs = [...this.data.aiMessages];
      latestMsgs[targetIdx].content = partial;
      latestMsgs[targetIdx].contentRendered = markdownToHtml(partial);
      this.setData({ aiMessages: latestMsgs });
      index = end;
      this.aiScrollBottom();
    }, speed);
  },

  // AI 聊天自动滚动到底部
  aiScrollBottom() {
    this.setData({ aiScrollToId: 'ai-msg-bottom' });
    setTimeout(() => {
      this.setData({ aiScrollToId: '' });
    }, 100);
  },

  // 关闭 AI 问答
  onCloseAIChat() {
    if (this._aiTypewriterTimer) {
      clearInterval(this._aiTypewriterTimer);
      this._aiTypewriterTimer = null;
    }
    this.setData({ showAIChat: false, aiSending: false });
  },

  // 阻止关闭冒泡
  preventClose() {},
});
