// 课堂互动页 — PPT居中显示，下方留言和互动
const api = require('../../../utils/api.js');
const { markdownToHtml } = require('../../../utils/markdown.js');
const app = getApp();

Page({
  data: {
    classId: '',
    sessionId: '',
    pptId: '',
    title: '课堂',
    // PPT
    pages: [],            // 所有页面数据
    currentPage: 1,
    totalPages: 1,
    currentSlide: null,   // 当前页对象 { type, title, content }
    // 消息/弹幕
    msgText: '',
    messages: [],         // [{ student_name, content, timestamp }]
    pollTimer: null,
    quizPollTimer: null,  // 答题轮询定时器
    // 选项字母标签
    optionLetters: ['A', 'B', 'C', 'D', 'E', 'F'],
    // 互动
    showInteraction: false,
    interactionType: '',   // 'quiz_list'(答题列表) | 'quiz_answer'(答题) | 'quiz_results'(统计) | 'vote'(投票)
    interactionData: null,
    quizList: [],          // 所有活跃答题列表
    selectedQuizId: null,  // 当前选中的答题ID
    userChoice: null,
    submitted: false,
    quizResults: null,     // 提交后的统计结果
    submitting: false,
    // AI 问答
    showAIChat: false,
    aiMessages: [],        // [{ role: 'user'|'ai', content, thinking }]
    aiInput: '',
    aiSending: false,
    aiScrollToId: '',
  },

  onLoad(options) {
    const classId = options.classId || '';
    const sessionId = options.sessionId || '';
    const pptId = options.pptId || '';
    const title = decodeURIComponent(options.title || '课堂');

    this.setData({ classId, sessionId, pptId, title });
    this.loadPPT();
    // 定时拉取消息
    this.startPolling();
  },

  onUnload() {
    // 页面卸载时清除定时器
    this.clearAllTimers();
    if (this._aiTypewriterTimer) {
      clearInterval(this._aiTypewriterTimer);
      this._aiTypewriterTimer = null;
    }
  },

  clearAllTimers() {
    if (this.data.pollTimer) {
      clearInterval(this.data.pollTimer);
    }
    if (this.data.quizPollTimer) {
      clearInterval(this.data.quizPollTimer);
    }
  },

  // ====== PPT 加载与翻页 ======

  // 加载PPT信息
  async loadPPT() {
    try {
      const pptData = await api.callHttpAPI(`/class/ppt/${this.data.pptId}`, {}, 'GET');
      if (pptData) {
        const pages = pptData.pages || [];
        this.setData({
          pages,
          totalPages: pages.length,
        });
        if (pages.length > 0) {
          this.setData({
            currentPage: 1,
            currentSlide: pages[0],
          });
        }
      }
    } catch (err) {
      console.error('加载PPT失败', err);
      wx.showToast({ title: '加载PPT失败', icon: 'none' });
    }
  },

  // 上一页
  onPrevPage() {
    if (this.data.currentPage > 1) {
      const newIdx = this.data.currentPage - 1;
      this.setData({
        currentPage: newIdx,
        currentSlide: this.data.pages[newIdx - 1] || null,
      });
    }
  },

  // 下一页
  onNextPage() {
    if (this.data.currentPage < this.data.totalPages) {
      const newIdx = this.data.currentPage + 1;
      this.setData({
        currentPage: newIdx,
        currentSlide: this.data.pages[newIdx - 1] || null,
      });
    }
  },

  // 返回到详情页
  onBack() {
    this.clearAllTimers();
    wx.navigateBack();
  },

  // ====== 消息/弹幕 ======

  // 输入框绑定
  onMsgInput(e) {
    this.setData({ msgText: e.detail.value });
  },

  // 发送消息
  async sendMessage() {
    const content = (this.data.msgText || '').trim();
    if (!content) return;
    if (!this.data.sessionId) {
      wx.showToast({ title: '课堂会话不存在', icon: 'none' });
      return;
    }
    try {
      // 使用弹幕 API 发送消息（学生端可用，无需教师权限）
      await api.callHttpAPI(
        `/teacher/ppt/classroom/${this.data.sessionId}/danmaku`,
        { session_id: this.data.sessionId, content, student_name: '' },
        'POST'
      );
      this.setData({ msgText: '' });
    } catch (err) {
      console.error('发送消息失败', err);
    }
  },

  // 拉取消息列表
  async fetchMessages() {
    if (!this.data.sessionId) return;
    try {
      const data = await api.callHttpAPI(
        `/teacher/ppt/classroom/${this.data.sessionId}/danmaku`,
        { limit: 50 },
        'GET'
      );
      if (data && data.items) {
        this.setData({ messages: data.items.reverse() });
      } else if (Array.isArray(data)) {
        this.setData({ messages: data.reverse() });
      }
    } catch (err) {
      // 静默处理，不干扰用户
    }
  },

  // 开始轮询消息
  startPolling() {
    if (this.data.pollTimer) clearInterval(this.data.pollTimer);
    // 首次立即拉取
    this.fetchMessages();
    // 每 5 秒轮询一次
    const timer = setInterval(() => this.fetchMessages(), 5000);
    this.data.pollTimer = timer;
  },

  // ==================== 答题互动 ====================

  // 点击答题按钮：加载活跃答题列表
  async onQuizClick() {
    if (!this.data.sessionId) {
      wx.showToast({ title: '课堂会话不存在', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '加载答题中...' });
    try {
      const data = await api.callHttpAPI(
        `/teacher/ppt/classroom/${this.data.sessionId}/active-quizzes`,
        {},
        'GET'
      );
      const quizzes = (data && data.quizzes) || [];
      wx.hideLoading();
      this.setData({
        showInteraction: true,
        interactionType: 'quiz_list',
        quizList: quizzes,
        selectedQuizId: null,
        interactionData: null,
        userChoice: null,
        submitted: false,
        quizResults: null,
      });
      // 开始轮询答题列表更新
      this.startQuizPolling();
    } catch (err) {
      wx.hideLoading();
      console.error('加载答题列表失败', err);
      wx.showToast({ title: '加载答题列表失败', icon: 'none' });
    }
  },

  // 轮询答题列表
  startQuizPolling() {
    if (this.data.quizPollTimer) clearInterval(this.data.quizPollTimer);
    const timer = setInterval(async () => {
      if (!this.data.sessionId) return;
      try {
        const data = await api.callHttpAPI(
          `/teacher/ppt/classroom/${this.data.sessionId}/active-quizzes`,
          {},
          'GET'
        );
        const quizzes = (data && data.quizzes) || [];
        // 如果答题列表在弹出时才有新数据增加，更新列表
        if (this.data.interactionType === 'quiz_list') {
          this.setData({ quizList: quizzes });
        }
      } catch (err) {
        // 静默处理
      }
    }, 5000);
    this.data.quizPollTimer = timer;
  },

  // 从列表中选择一道答题
  onQuizItemSelect(e) {
    const quizId = e.currentTarget.dataset.id;
    const quizList = this.data.quizList;
    const quiz = quizList.find(q => q.id === quizId);
    if (!quiz) return;

    this.setData({
      interactionType: 'quiz_answer',
      selectedQuizId: quizId,
      interactionData: {
        question: quiz.question,
        options: quiz.options,
      },
      userChoice: null,
      submitted: false,
      quizResults: null,
    });
  },

  // 返回答题列表
  onBackToQuizList() {
    this.setData({
      interactionType: 'quiz_list',
      selectedQuizId: null,
      interactionData: null,
      userChoice: null,
      submitted: false,
      quizResults: null,
    });
  },

  // ==================== 投票（保留原有） ====================

  // 显示投票弹窗
  showVote(options) {
    this.setData({
      showInteraction: true,
      interactionType: 'vote',
      interactionData: {
        question: options?.question || '示例投票：你更喜欢哪种学习方式？',
        options: options?.options || ['线上学习', '线下学习', '混合学习'],
      },
      userChoice: null,
      submitted: false,
    });
  },

  // ==================== 通用选项操作 ====================

  // 选择选项
  onOptionSelect(e) {
    const index = parseInt(e.currentTarget.dataset.index);
    if (this.data.submitted || this.data.submitting) return;
    this.setData({ userChoice: index });
  },

  // 提交选项（答题）
  async onSubmitChoice() {
    if (this.data.userChoice === null) {
      wx.showToast({ title: '请先选择一个选项', icon: 'none' });
      return;
    }
    if (this.data.submitting) return;

    // 判断是答题还是投票
    if (this.data.interactionType === 'quiz_answer') {
      await this.submitQuizAnswer();
    } else {
      // 投票仅本地处理
      this.setData({ submitted: true });
      wx.showToast({ title: '已提交', icon: 'success' });
    }
  },

  // 提交答题到后端
  async submitQuizAnswer() {
    this.setData({ submitting: true });
    try {
      // 后端使用 Query 参数接收 quiz_id 和 selected
      const result = await api.callHttpAPI(
        `/teacher/ppt/classroom/${this.data.sessionId}/quiz/submit?quiz_id=${this.data.selectedQuizId}&selected=${this.data.userChoice}`,
        {},
        'POST'
      );
      this.setData({ submitted: true, submitting: false });

      wx.showToast({ title: '提交成功', icon: 'success' });

      // 立即拉取统计结果
      await this.loadQuizResults();
    } catch (err) {
      this.setData({ submitting: false });
      console.error('提交答题失败', err);
      const msg = (err && err.message) || '';
      if (msg.includes('你已经回答过')) {
        wx.showToast({ title: '你已经回答过了', icon: 'none' });
        // 重复提交时直接展示统计
        await this.loadQuizResults();
      } else {
        wx.showToast({ title: '提交失败，请重试', icon: 'none' });
      }
    }
  },

  // 加载答题统计结果
  async loadQuizResults() {
    try {
      const data = await api.callHttpAPI(
        `/teacher/ppt/classroom/${this.data.sessionId}/quiz/${this.data.selectedQuizId}/student-results`,
        {},
        'GET'
      );
      if (data) {
        // WXML 不支持 .toFixed()，提前计算正确率
        const correctRate = data.total_answers > 0
          ? (data.correct_count / data.total_answers * 100).toFixed(0)
          : '0';
        this.setData({
          quizResults: { ...data, correctRate },
          interactionType: 'quiz_results',
        });
        // 定期刷新统计
        this.startResultsPolling();
      }
    } catch (err) {
      console.error('加载答题统计失败', err);
    }
  },

  // 轮询统计结果更新
  startResultsPolling() {
    if (this.data.quizPollTimer) clearInterval(this.data.quizPollTimer);
    const timer = setInterval(async () => {
      if (this.data.interactionType !== 'quiz_results') return;
      try {
        const data = await api.callHttpAPI(
          `/teacher/ppt/classroom/${this.data.sessionId}/quiz/${this.data.selectedQuizId}/student-results`,
          {},
          'GET'
        );
        if (data) {
          this.setData({ quizResults: data });
        }
      } catch (err) {
        // 静默
      }
    }, 3000);
    this.data.quizPollTimer = timer;
  },

  // 关闭弹窗
  onCloseModal() {
    if (this.data.quizPollTimer) {
      clearInterval(this.data.quizPollTimer);
      this.data.quizPollTimer = null;
    }
    this.setData({
      showInteraction: false,
      interactionType: '',
      interactionData: null,
      quizList: [],
      selectedQuizId: null,
      userChoice: null,
      submitted: false,
      quizResults: null,
      submitting: false,
    });
  },

  // 阻止关闭冒泡
  preventClose() {},

  // ==================== AI 问答 ====================

  // 打开 AI 问答弹窗
  onAIChatClick() {
    if (!this.data.sessionId) {
      wx.showToast({ title: '课堂会话不存在', icon: 'none' });
      return;
    }
    this.setData({ showAIChat: true, aiInput: '' });
    // 首次打开时添加欢迎消息
    if (this.data.aiMessages.length === 0) {
      const welcomeText = '你好！我是小e，你的 AI 学习助手。\n\n有什么关于当前 PPT 页面的问题吗？我可以帮你：\n\n• 解释知识点 — 讲解当前页的语法、词汇\n• 举例说明 — 给出更多实用例句\n• 深入讲解 — 拓展你感兴趣的内容\n• 解答疑问 — 任何英语学习问题\n\n直接在下方输入你的问题吧！';
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

    const currentSlide = this.data.currentSlide;
    const newMessages = [
      ...this.data.aiMessages,
      { role: 'user', content: text, contentRendered: markdownToHtml(text), thinking: false },
      { role: 'ai', content: '', contentRendered: '', thinking: true }
    ];
    this.setData({ aiMessages: newMessages, aiInput: '', aiSending: true });
    this.aiScrollBottom();

    try {
      // 构造消息历史（含 PPT 上下文）
      const chatHistory = [];
      // 将当前 PPT 页面内容作为上下文注入
      if (currentSlide) {
        let slideSummary = `当前PPT页面\n标题：${currentSlide.title || ''}\n类型：${currentSlide.type || ''}`;
        if (currentSlide.content) {
          const contentStr = JSON.stringify(currentSlide.content).slice(0, 400);
          slideSummary += `\n内容：${contentStr}`;
        }
        chatHistory.push({ role: 'user', content: `【PPT页面上下文】\n${slideSummary}\n\n（以上是学生当前正在查看的PPT内容，请根据此回答学生的问题）` });
      }
      // 添加实际对话历史（最近 10 轮，过滤 thinking 占位）
      chatHistory.push(
        ...newMessages
          .filter(m => m.role !== 'ai' || !m.thinking)
          .slice(-10)
          .map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }))
      );

      const result = await api.chatWithAI({ messages: chatHistory });
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
    const step = 3;     // 每次追加 3 个字符
    const speed = 25;   // 25ms 每帧

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
});
