// 学生端 — 答题页（上下分屏：上区大题/文章，下区小题+选项）
const { getExamDetail, doExam } = require('../../../utils/api');

Page({
  data: {
    examId: null,
    exam: {},
    questions: [],
    answers: {},
    remainingSeconds: 0,
    submitting: false,
    timer: null,
    currentIndex: 0,
    currentQuestion: {},         // 当前题目对象（同步到 data）
    currentAnswer: '',           // 当前非阅读题的已选答案
    currentSubAnswers: [],       // 当前阅读题各子题的已选答案
    answeredCount: 0,            // 已作答数
    totalSubCount: 0,            // 总小题数（含阅读子题）
    readingPassage: '',          // 阅读题文章文本（兼容 passage/stem）
    hasSubQuestions: false,      // 是否有子题
  },

  // 同步当前题目、当前答案、已作答数到 data（供 WXML 绑定）
  syncDisplay() {
    const questions = this.data.questions;
    const answers = this.data.answers || {};
    const idx = this.data.currentIndex;
    const q = questions[idx] || {};

    // 计算已作答数：普通题检查 answers[i]，阅读子题检查 answers[i_j]
    let answeredCount = 0;
    questions.forEach((qq, qi) => {
      if (qq.type === 'reading' && qq.sub_questions) {
        qq.sub_questions.forEach((sq, si) => {
          if (answers[`${qi}_${si}`] && answers[`${qi}_${si}`] !== '') {
            answeredCount++;
          }
        });
      } else {
        if (answers[qi] && answers[qi] !== '') {
          answeredCount++;
        }
      }
    });

    // 计算总小题数（含阅读子题）
    let totalSubCount = 0;
    questions.forEach((qq) => {
      if (qq.type === 'reading' && qq.sub_questions) {
        totalSubCount += qq.sub_questions.length;
      } else {
        totalSubCount += 1;
      }
    });

    if (q.type === 'reading') {
      // 阅读题：兜底兼容 passage 缺失时用 stem，子题缺失时降级为普通题
      const readingPassage = q.passage || q.stem || '';
      const subQuestions = (q.sub_questions && q.sub_questions.length > 0) ? q.sub_questions : [];
      const hasSubQuestions = subQuestions.length > 0;

      if (hasSubQuestions) {
        // 有子题：收集各子题答案
        const subAnswers = [];
        subQuestions.forEach((sq, si) => {
          subAnswers.push(answers[`${idx}_${si}`] || '');
        });
        this.setData({
          currentQuestion: q,
          currentAnswer: '',
          currentSubAnswers: subAnswers,
          answeredCount,
          totalSubCount,
          readingPassage,
          hasSubQuestions: true,
        });
      } else {
        // 无子题：作为普通题展示（上区不显示文章，下区显示 stem+options）
        this.setData({
          currentQuestion: q,
          currentAnswer: answers[idx] || '',
          currentSubAnswers: [],
          answeredCount,
          totalSubCount,
          readingPassage,
          hasSubQuestions: false,
        });
      }
    } else {
      this.setData({
        currentQuestion: q,
        currentAnswer: answers[idx] || '',
        currentSubAnswers: [],
        answeredCount,
        totalSubCount,
        readingPassage: '',
        hasSubQuestions: false,
      });
    }
  },

  onLoad(options) {
    const examId = options.examId || '';
    this.setData({ examId });
    this.loadExam(examId);
  },

  onUnload() {
    if (this.data.timer) {
      clearInterval(this.data.timer);
    }
  },

  async loadExam(examId) {
    try {
      const exam = await getExamDetail(examId);
      const questions = exam.questions || [];

      // 不再展平阅读题 sub_questions，保持原始结构
      // 为每个题目补充默认字段
      const normalized = questions.map((q) => ({
        ...q,
        passage: q.passage || '',
        stem: q.stem || '',
        sub_questions: q.sub_questions || [],
      }));

      this.setData({
        exam,
        questions: normalized,
        currentIndex: 0,
        remainingSeconds: (exam.duration_minutes || 60) * 60,
      });
      this.syncDisplay();
      this.startTimer();
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  startTimer() {
    const timer = setInterval(() => {
      let sec = this.data.remainingSeconds - 1;
      if (sec <= 0) {
        sec = 0;
        clearInterval(timer);
        wx.showToast({ title: '时间到！自动提交', icon: 'none' });
        this.submitExam();
      }
      this.setData({ remainingSeconds: sec });
    }, 1000);
    this.setData({ timer });
  },

  formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  },

  // 题型中文标签
  getTypeLabel(type) {
    const labels = { choice: '选择题', fill: '填空题', translation: '翻译题', writing: '写作题', reading: '阅读题' };
    return labels[type] || type || '未知题型';
  },

  // ========== 上下导航 ==========

  onPrev() {
    if (this.data.currentIndex > 0) {
      this.setData({ currentIndex: this.data.currentIndex - 1 });
      this.syncDisplay();
    }
  },

  onNext() {
    if (this.data.currentIndex < this.data.questions.length - 1) {
      this.setData({ currentIndex: this.data.currentIndex + 1 });
      this.syncDisplay();
    }
  },

  // ========== 选项选择 ==========

  // 普通题（非阅读）选择选项
  selectOption(e) {
    const opt = e.currentTarget.dataset.opt;
    const idx = this.data.currentIndex;
    this.setData({ [`answers[${idx}]`]: opt }, () => this.syncDisplay());
  },

  // 阅读子题选择选项
  selectSubOption(e) {
    const opt = e.currentTarget.dataset.opt;
    const sub = e.currentTarget.dataset.sub;
    const idx = this.data.currentIndex;
    this.setData({ [`answers[${idx}_${sub}]`]: opt }, () => this.syncDisplay());
  },

  onFillInput(e) {
    const idx = this.data.currentIndex;
    this.setData({ [`answers[${idx}]`]: e.detail.value }, () => this.syncDisplay());
  },

  onTextInput(e) {
    const idx = this.data.currentIndex;
    this.setData({ [`answers[${idx}]`]: e.detail.value }, () => this.syncDisplay());
  },

  // ========== 提交 ==========

  async submitExam() {
    if (this.data.submitting) return;
    const confirmed = await new Promise(resolve => {
      wx.showModal({
        title: '确认提交',
        content: `还有${this.data.questions.reduce((sum, q, qi) => {
          if (q.type === 'reading' && q.sub_questions) {
            return sum + q.sub_questions.length;
          }
          return sum + 1;
        }, 0) - this.data.answeredCount}题未作答，确定提交吗？`,
        success: (res) => resolve(res.confirm),
      });
    });
    if (!confirmed) return;

    this.setData({ submitting: true });
    try {
      // 构造提交答案列表：阅读题子题合并为单个答案字符串，方便后端处理
      const answers = [];
      this.data.questions.forEach((q, i) => {
        if (q.type === 'reading' && q.sub_questions && q.sub_questions.length > 0) {
          const subParts = [];
          q.sub_questions.forEach((sq, si) => {
            const ans = this.data.answers[`${i}_${si}`] || '';
            subParts.push(`第${sq.question_number || si + 1}题:${ans || '未作答'}`);
          });
          answers.push({
            question_index: i,
            type: q.type,
            question: q.stem || q.passage || '',
            answer: subParts.join(' | '),
            score: q.score,
          });
        } else {
          answers.push({
            question_index: i,
            type: q.type,
            question: q.stem,
            answer: this.data.answers[i] || '',
            score: q.score,
          });
        }
      });

      await doExam(this.data.examId, answers);
      if (this.data.timer) clearInterval(this.data.timer);
      wx.redirectTo({
        url: `/pages/exam/result/index?examId=${this.data.examId}`
      });
    } catch (err) {
      wx.showToast({ title: '提交失败: ' + (err.message || ''), icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  },
});
