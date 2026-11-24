// 教师端 — 班级详情（学生列表）
const api = require('../../../../utils/api')

Page({
  data: {
    classId: null,
    className: '',
    students: [],
    loading: true,
    searchKey: '',
  },

  onLoad(options) {
    this.setData({
      classId: parseInt(options.classId),
      className: decodeURIComponent(options.className || ''),
    })
    wx.setNavigationBarTitle({ title: this.data.className })
  },

  onShow() {
    this.loadStudents()
  },

  async loadStudents() {
    this.setData({ loading: true })
    try {
      const result = await api.callHttpAPI(
        `/teacher/classes/${this.data.classId}/student-info`, {}, 'GET'
      )
      const studentList = result || []
      const students = Array.isArray(studentList) ? studentList : []
      students.forEach(s => {
        s._avatarChar = (s.student_name || '?')[0]
        s._showAccount = s.created_account || ''
      })
      this.setData({ students })
    } catch (err) {
      console.error('加载学生列表失败', err)
      wx.showToast({ title: '加载学生列表失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  // 导入花名册
  goToImport() {
    wx.navigateTo({
      url: `/pages/teacher/class/import/index?classId=${this.data.classId}&className=${encodeURIComponent(this.data.className)}`
    })
  },

  // 搜索
  onSearchInput(e) {
    this.setData({ searchKey: e.detail.value })
  },

  // 查看学生错题
  goToStudentMistakes(e) {
    const { examNumber, studentName } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/class/student-detail/index?classId=${this.data.classId}&examNumber=${examNumber}&studentName=${encodeURIComponent(studentName)}`
    })
  },

  get filteredStudents() {
    const key = this.data.searchKey.toLowerCase()
    if (!key) return this.data.students
    return this.data.students.filter(s =>
      (s.student_name || '').includes(key) ||
      (s.exam_number || '').includes(key) ||
      (s.student_number || '').includes(key) ||
      (s.created_account || '').includes(key)
    )
  },
})
