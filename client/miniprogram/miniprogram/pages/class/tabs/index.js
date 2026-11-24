// 班级详情 - 3个Tab: 课堂/试卷/成绩
const api = require('../../../utils/api.js');

Page({
  data: {
    classId: '',
    className: '',
    classInfo: null,
    activeTab: 0,       // 0=课堂, 1=试卷, 2=成绩
    tabs: ['课堂', '试卷', '成绩'],
    loading: true,

    // --- 课堂 tab ---
    activeSession: null,
    checkingSession: false,

    // --- 试卷 tab ---
    exams: [],
    examsLoading: false,

    // --- 成绩 tab ---
    gradeStats: null,
    statsLoading: false,
  },

  onLoad(options) {
    const classId = options.classId || '';
    const className = decodeURIComponent(options.className || '班级详情');
    // 合并首个 setData：classId + className + loading 初始状态，仅一次跨进程通信
    this.setData({ classId, className, loading: true });
    // 延迟到下一帧执行异步加载，避免阻塞导航动画渲染
    wx.nextTick(() => {
      this.loadClassInfo().then(() => {
        if (this.data.activeTab === 0) {
          this.checkActiveSession();
        }
      });
    });
  },

  // 每次页面显示时自动刷新课堂状态（从课堂页面返回等场景）
  onShow() {
    // 延迟到下一帧避免阻塞页面切换动效
    if (this.data.activeTab === 0) {
      wx.nextTick(() => this.checkActiveSession());
    }
  },

  // 加载班级基本信息
  async loadClassInfo() {
    try {
      const detail = await api.getMyClassDetail(this.data.classId);
      // 合并 classInfo + loading:false 为一次 setData
      this.setData({
        classInfo: detail,
        loading: false,
      });
    } catch (err) {
      console.error('加载班级信息失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载班级信息失败', icon: 'none' });
    }
  },

  // 切换Tab
  onTabTap(e) {
    const index = parseInt(e.currentTarget.dataset.index);
    if (index === this.data.activeTab) return;
    // 先切换视图，立即响应点击
    this.setData({ activeTab: index });
    // 数据加载延迟到下一帧，避免阻塞 Tab 切换渲染
    wx.nextTick(() => {
      if (index === 0) {
        this.checkActiveSession();
      } else if (index === 1) {
        this.loadClassExams();
      } else if (index === 2) {
        this.loadGradeStats();
      }
    });
  },

  // ==================== 课堂 Tab ====================
  async checkActiveSession() {
    this.setData({ checkingSession: true });
    try {
      const result = await api.getActiveSession(this.data.classId);
      this.setData({
        activeSession: result,
        checkingSession: false,
      });
    } catch (err) {
      console.error('检查课堂状态失败', err);
      this.setData({
        activeSession: null,
        checkingSession: false,
      });
    }
  },

  // 手动刷新课堂状态（点击刷新按钮）
  onRefreshSession() {
    wx.showToast({ title: '刷新中...', icon: 'loading', duration: 1000 });
    this.checkActiveSession();
  },

  // 进入课堂
  onEnterClassroom() {
    const session = this.data.activeSession;
    if (!session || !session.has_active) {
      wx.showToast({ title: '当前没有老师授课', icon: 'none' });
      return;
    }
    wx.navigateTo({
      url: `/pages/class/classroom/index?classId=${this.data.classId}&sessionId=${session.session_id}&pptId=${session.ppt_id}&title=${encodeURIComponent(session.title || '课堂')}`,
    });
  },

  // ==================== 试卷 Tab ====================
  async loadClassExams() {
    this.setData({ examsLoading: true });
    try {
      const result = await api.getExamList({
        class_id: this.data.classId,
        pageSize: 50,
      });
      const items = result?.items || result || [];
      this.setData({ exams: items, examsLoading: false });
    } catch (err) {
      console.error('加载班级试卷失败', err);
      this.setData({ examsLoading: false });
    }
  },

  // 点击试卷
  onExamTap(e) {
    const exam = e.currentTarget.dataset.exam;
    if (!exam) return;

    if (exam.my_submission && exam.my_submission.score != null) {
      // 已提交 → 查看结果
      wx.navigateTo({
        url: `/pages/exam/result/index?examId=${exam.id}`,
      });
    } else {
      // 未提交 → 答题
      wx.navigateTo({
        url: `/pages/exam/do-exam/index?examId=${exam.id}`,
      });
    }
  },

  // ==================== 成绩 Tab ====================
  async loadGradeStats() {
    this.setData({ statsLoading: true });
    try {
      const stats = await api.getGradeStats(this.data.classId);
      this.setData({ gradeStats: stats, statsLoading: false });
    } catch (err) {
      console.error('加载成绩统计失败', err);
      this.setData({ statsLoading: false });
    }
  },

  // 切换到独立成绩页
  onViewGradeDetail() {
    wx.navigateTo({
      url: `/pages/class/grade/index?classId=${this.data.classId}&className=${encodeURIComponent(this.data.className)}`,
    });
  },
});
