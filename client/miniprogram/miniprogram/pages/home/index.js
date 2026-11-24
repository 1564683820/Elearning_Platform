const api = require('../../utils/api.js');
const phaseMode = require('../../utils/phase-mode.js');

Page({
  data: {
    currentPhase: '',
    savedPhaseIndex: 0,
    showPhaseSelector: false,
    showSaveTip: false,
    savedPhaseName: '',
    stats: { todayWords: 0, accuracy: '0%', streakDays: '0' },
    notices: [],
    pendingExamCount: 0,
    loading: true
  },

  onLoad() {
    this.loadPhaseInfo();
    this.loadUserData();
  },

  onShow() {
    // Tab 页切换回来时重新加载用户数据
    this.loadUserData();
  },

  // 加载当前阶段信息
  loadPhaseInfo() {
    const idx = phaseMode.getSavedPhaseIndex();
    const name = phaseMode.PHASES[idx].name;
    this.setData({ currentPhase: name, savedPhaseIndex: idx });
  },

  async loadUserData() {
    try {
      const token = wx.getStorageSync('auth_token');
      if (token) api.setAuthToken(token);
      const profile = await api.getUserProfile();
      if (profile) {
        // 同步后端阶段到本地 storage
        const phaseObj = phaseMode.findPhaseByName(profile.phase);
        if (phaseObj) {
          const idx = phaseObj.index;
          phaseMode.savePhaseIndex(idx);
          this.setData({ currentPhase: profile.phase, savedPhaseIndex: idx });
        }
        getApp().globalData.studyPhase = profile.phase;
      }
      await this.loadStats();
      await this.loadNotices();
    } catch (err) {
      console.error('加载用户数据失败', err);
    } finally {
      this.setData({ loading: false });
    }
  },

  // 加载统计数据
  async loadStats() {
    try {
      const statsData = await api.getUserStats();
      this.setData({
        stats: {
          todayWords: statsData.words_learned_today || 0,
          accuracy: typeof statsData.quiz_accuracy === 'number' ? statsData.quiz_accuracy : 0,
          streakDays: '0'
        }
      });
    } catch (err) {
      console.error('加载统计失败', err);
    }
  },

  // 加载班级通知 — 从后端获取学生所属班级的待完成考试
  async loadNotices() {
    try {
      const result = await api.getExamList({ status: 'pending', pageSize: 10 });
      const examList = result?.items || [];
      const notices = examList.map(exam => ({
        examId: exam.id,
        icon: '📝',
        content: `「${exam.class_name || '班级'}」发布了新试卷：${exam.title}`,
        title: exam.title,
        class_name: exam.class_name,
        totalScore: exam.total_score,
        durationMinutes: exam.duration_minutes,
        difficulty: exam.difficulty,
        questionCount: exam.question_count
      }));
      this.setData({ notices, pendingExamCount: notices.length });
    } catch (err) {
      console.error('加载考试通知失败', err);
      // 失败时保留上次成功加载的结果，不清空
    }
  },

  // ========== 阶段选择 ==========

  // 打开阶段选择弹窗
  onOpenPhaseSelector() {
    this.setData({ showPhaseSelector: true });
  },

  // 关闭阶段选择弹窗
  onClosePhaseSelector() {
    this.setData({ showPhaseSelector: false });
  },

  // 阶段已保存
  onPhaseSaved(e) {
    const { index, name } = e.detail;
    this.setData({
      showPhaseSelector: false,
      showSaveTip: true,
      savedPhaseName: name,
      savedPhaseIndex: index,
      currentPhase: name,
    });
    // 同步到后端
    api.updateUserProfile({ stage: index + 1 }).catch(err => {
      console.error('更新学习阶段到后端失败', err);
    });
  },

  // 立即重启（跳转到新模式首页）
  onRestartNow() {
    const mode = phaseMode.getSavedMode();
    this.setData({ showSaveTip: false });
    const targetUrl = mode === 'child' ? '/pages/child/home/index'
                     : mode === 'adult' ? '/pages/adult/home/index'
                     : '/pages/home/index';
    wx.reLaunch({ url: targetUrl });
  },

  // ========== 入口跳转 ==========

  // 班级 → class/index
  onClassEntry() {
    wx.navigateTo({ url: '/pages/class/index/index' });
  },

  // 智能对话 → chat/qa (通过 tab 切换)
  onChatEntry() {
    wx.switchTab({ url: '/pages/chat/qa/index' });
  },

  // 记单词 → memory/word (全屏 oapp 覆盖页)
  onWordEntry() {
    wx.navigateTo({ url: '/pages/memory/word/index' });
  },

  // 错题本 → mistake-book
  onMistakeBookEntry() {
    wx.navigateTo({ url: '/pages/mistake-book/index' });
  },

  // ========== 考试通知 ==========

  // 点击通知项 → 直接进入该试卷答题
  onNoticeTap(e) {
    const examId = e.currentTarget.dataset.id;
    if (examId) {
      wx.navigateTo({ url: `/pages/exam/do-exam/index?examId=${examId}` });
    }
  },

  // 查看全部 → 跳转考试列表页
  onViewAllExams() {
    wx.navigateTo({ url: '/pages/exam/list/index' });
  },

});
