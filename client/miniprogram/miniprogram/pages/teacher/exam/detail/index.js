// 教师端 — 试卷报告页（可视化数据 + 学生列表）
const app = getApp()
const api = require('../../../../utils/api')

Page({
  data: {
    examId: null,
    exam: null,
    report: null,
    loading: true,
    // 核心指标
    avgScore: 0, maxScore: 0, minScore: 0,
    totalStudents: 0, gradedStudents: 0,
    singleScoreRate: 0, multiScoreRate: 0,
    // 分布
    distribution: [],
    questionAccuracy: [],
    topWrongQuestions: [],
    multiErrorStats: null,
    // 学生列表（按成绩降序）
    studentList: [],
    selectedQuestion: null,
  },

  onLoad(options) {
    const { examId } = options
    // 注意: Snowflake ID 超过 JS 安全整数范围，必须保留字符串形式，不能用 parseInt
    this.setData({ examId: String(examId || '') })
    this.loadData()
  },

  onShow() {
    if (this.data.examId && !this.data.loading) {
      this.loadData()
    }
  },

  async loadData() {
    if (!this.data.examId) return
    this.setData({ loading: true })
    try {
      // 并行加载试卷信息和报告数据
      const [exam, report] = await Promise.all([
        api.callHttpAPI(`/teacher/exam/${this.data.examId}`, {}, 'GET').catch(() => null),
        api.callHttpAPI(`/teacher/exam/${this.data.examId}/report`, {}, 'GET').catch(() => null),
      ])

      // 处理报告数据
      const avgScore = report?.avg_score || report?.average_score || 0
      const maxScore = report?.max_score || 0
      const minScore = report?.min_score || 0
      const totalStudents = report?.total_students || 0
      const gradedStudents = report?.graded_students || report?.total_graded || 0
      const distribution = report?.distribution || report?.score_distribution || []
      const questionAccuracy = report?.question_accuracy || report?.detail?.accuracy || []
      const topWrong = report?.top_wrong_questions || report?.wrong_question_top || []
      const multiStats = report?.multi_choice_errors || report?.multi_error_stats || null
      const singleScoreRate = report?.single_score_rate !== undefined ? report?.single_score_rate :
                              (report?.single_total_score > 0 ? Math.round((report?.single_earned_score / report?.single_total_score) * 100) : 0)
      const multiScoreRate = report?.multi_score_rate !== undefined ? report?.multi_score_rate :
                             (report?.multi_total_score > 0 ? Math.round((report?.multi_earned_score / report?.multi_total_score) * 100) : 0)

      // 处理学生列表（按成绩降序）
      let rawStudents = report?.students || report?.student_scores || []
      // 按成绩降序排序
      rawStudents = [...rawStudents].sort((a, b) => (b.score || 0) - (a.score || 0))

      const studentList = rawStudents.map(s => ({
        ...s,
        _avatarChar: (s.student_name || '?')[0],
        _class_name: s.class_name || s.className || '',
        _status: (s.score !== undefined && s.score !== null && s.score !== '') ? '已批改' : '未批改',
        _displayScore: (s.score !== undefined && s.score !== null && s.score !== '') ? s.score : '-',
      }))

      this.setData({
        exam,
        report,
        avgScore, maxScore, minScore,
        totalStudents, gradedStudents,
        singleScoreRate, multiScoreRate,
        distribution, questionAccuracy,
        topWrongQuestions: topWrong.slice(0, 5),
        multiErrorStats: multiStats,
        studentList,
        loading: false,
      })

      // 渲染图表
      this.renderDistributionChart()
      this.renderAccuracyChart()
    } catch (err) {
      console.error('加载报告数据失败', err)
      wx.showToast({ title: '加载失败', icon: 'none' })
      this.setData({ loading: false })
    }
  },

  // 成绩分布柱状图
  renderDistributionChart() {
    const dist = this.data.distribution
    if (!dist || dist.length === 0) return
    wx.createSelectorQuery()
      .select('#distributionChart')
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0]) return
        const canvas = res[0].node
        const ctx = canvas.getContext('2d')
        const dpr = wx.getWindowInfo().pixelRatio
        const width = res[0].width
        const height = res[0].height
        canvas.width = width * dpr
        canvas.height = height * dpr
        ctx.scale(dpr, dpr)
        const colors = ['#E74C3C', '#F59E0B', '#3B82F6', '#5B9E6F', '#8B5CF6']
        const labels = dist.map(d => d.range || d.label || '')
        const values = dist.map(d => d.count || 0)
        const maxVal = Math.max(...values, 1)
        const pad = { top: 30, right: 20, bottom: 40, left: 40 }
        const chartW = width - pad.left - pad.right
        const chartH = height - pad.top - pad.bottom
        const barW = Math.min(chartW / labels.length * 0.6, 60)
        ctx.clearRect(0, 0, width, height)
        ctx.fillStyle = '#1F2937'
        ctx.font = 'bold 14px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('成绩分布', width / 2, 18)
        labels.forEach((label, i) => {
          const x = pad.left + (chartW / labels.length) * i + (chartW / labels.length - barW) / 2
          const barH = (values[i] / maxVal) * chartH
          const y = pad.top + chartH - barH
          ctx.fillStyle = colors[i % colors.length]
          ctx.beginPath()
          ctx.roundRect(x, y, barW, barH, 4)
          ctx.fill()
          ctx.fillStyle = '#374151'
          ctx.font = '11px sans-serif'
          ctx.textAlign = 'center'
          ctx.fillText(values[i], x + barW / 2, y - 6)
          ctx.fillStyle = '#9CA3AF'
          ctx.font = '10px sans-serif'
          ctx.fillText(label, x + barW / 2, pad.top + chartH + 16)
        })
      })
  },

  // 各题正确率
  renderAccuracyChart() {
    const qa = this.data.questionAccuracy
    if (!qa || qa.length === 0) return
    wx.createSelectorQuery()
      .select('#accuracyChart')
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0]) return
        const canvas = res[0].node
        const ctx = canvas.getContext('2d')
        const dpr = wx.getWindowInfo().pixelRatio
        const width = res[0].width
        const height = res[0].height
        canvas.width = width * dpr
        canvas.height = height * dpr
        ctx.scale(dpr, dpr)
        const items = qa.slice(0, 20)
        const labels = items.map(d => `${d.question_number || d.number || ''}题`)
        const values = items.map(d => (d.accuracy || d.rate || 0) * 100)
        const types = items.map(d => d.type || d.question_type || 'single')
        const pad = { top: 30, right: 20, bottom: 40, left: 40 }
        const chartW = width - pad.left - pad.right
        const chartH = height - pad.top - pad.bottom
        const barW = Math.min(Math.max(chartW / labels.length * 0.5, 8), 30)
        ctx.clearRect(0, 0, width, height)
        ctx.fillStyle = '#1F2937'
        ctx.font = 'bold 14px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('各题正确率', width / 2, 18)
        labels.forEach((label, i) => {
          const x = pad.left + (chartW / labels.length) * i + (chartW / labels.length - barW) / 2
          const barH = Math.max((values[i] / 100) * chartH, 1)
          const y = pad.top + chartH - barH
          ctx.fillStyle = types[i] === 'multiple' ? '#F59E0B' : '#5B9E6F'
          if (values[i] < 60) ctx.fillStyle = '#E74C3C'
          ctx.beginPath()
          ctx.roundRect(x, y, barW, barH, 3)
          ctx.fill()
          ctx.fillStyle = values[i] < 60 ? '#E74C3C' : '#374151'
          ctx.font = '9px sans-serif'
          ctx.textAlign = 'center'
          ctx.fillText(Math.round(values[i]) + '%', x + barW / 2, y - 4)
          if (i % 2 === 0 || labels.length <= 10) {
            ctx.fillStyle = '#9CA3AF'
            ctx.font = '8px sans-serif'
            ctx.fillText(label, x + barW / 2, pad.top + chartH + 14)
          }
        })
      })
  },

  // 点击薄弱题
  onQuestionTap(e) {
    const { questionNumber } = e.currentTarget.dataset
    wx.showLoading({ title: '加载中...' })
    api.callHttpAPI(`/teacher/exam/${this.data.examId}/report/question/${questionNumber}`, {}, 'GET')
      .then(detail => {
        wx.hideLoading()
        this.setData({ selectedQuestion: detail || null })
      })
      .catch(err => {
        wx.hideLoading()
        console.error('加载单题详情失败', err)
        wx.showToast({ title: '加载失败', icon: 'none' })
      })
  },

  closeQuestionDetail() {
    this.setData({ selectedQuestion: null })
  },

  // 查看学生错题
  goToStudentDetail(e) {
    const { studentId, studentName } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/class/student-detail/index?studentId=${studentId}&examId=${this.data.examId}&studentName=${encodeURIComponent(studentName || '')}`
    })
  },
})
