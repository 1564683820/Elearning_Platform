// 教师端 — 学生错题详情
const api = require('../../../../utils/api')

Page({
  data: {
    studentName: '',
    examNumber: '',
    examId: null,
    classId: null,
    mistakes: [],
    loading: true,
    examTitle: '',
    totalScore: 0,
    correctCount: 0,
    wrongCount: 0,
    hasPaperImage: false,
  },

  onLoad(options) {
    const { classId, examNumber, studentName, examId } = options
    this.setData({
      classId: parseInt(classId),
      examNumber,
      studentName: decodeURIComponent(studentName || ''),
      // 注意: Snowflake ID 超过 JS 安全整数范围，必须保留字符串形式
      examId: String(examId || ''),
    })
    this.loadMistakes()
  },

  async loadMistakes() {
    this.setData({ loading: true })
    try {
      // 先查班级花名册获取 student_id
      const students = await api.callHttpAPI(
        `/teacher/classes/${this.data.classId}/student-info`, {}, 'GET'
      )
      const studentList = students?.items || students || []
      const student = studentList.find(s => s.exam_number === this.data.examNumber)
      if (!student) {
        wx.showToast({ title: '未找到该学生', icon: 'none' })
        this.setData({ loading: false })
        return
      }
      this.setData({ studentName: student.name || this.data.studentName })

      // 获取错题
      const mistakeRes = await api.callHttpAPI(
        `/teacher/classes/${this.data.classId}/student-info/${this.data.examNumber}/exam-mistakes`,
        {}, 'GET'
      )
      const mistakes = mistakeRes?.items || mistakeRes?.mistakes || mistakeRes || []
      
      // 如果有 examId，获取试卷详情
      let examTitle = ''
      let totalScore = 0
      if (this.data.examId) {
        try {
          const exam = await api.callHttpAPI(`/teacher/exam/${this.data.examId}`, {}, 'GET')
          examTitle = exam.title || ''
          totalScore = exam.total_score || 0
          this.setData({
            hasPaperImage: !!exam.exam_paper_url,
          })
        } catch (e) {
          // 可选
        }
      }

      this.setData({
        mistakes,
        examTitle,
        totalScore,
        wrongCount: mistakes.length,
        loading: false,
      })
    } catch (err) {
      console.error('加载错题失败', err)
      wx.showToast({ title: '加载错题失败', icon: 'none' })
      this.setData({ loading: false })
    }
  },
})
