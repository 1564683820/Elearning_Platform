// 教师端 — 试卷管理 Tab
const app = getApp()
const api = require('../../../utils/api')

Page({
  data: {
    classes: [],
    currentClassId: null,
    currentClassName: '选择班级',
    exams: [],
    loading: true,
    showClassPicker: false,
    stats: { total: 0, graded: 0, pending: 0 },
  },

  onShow() {
    this.loadClasses()
  },

  async loadClasses() {
    try {
      // 使用教师端 API，与网页端共享同一份班级数据
      const result = await api.getTeacherClasses()
      const classList = result?.classes || result || []
      this.setData({ classes: classList })
      if (classList.length > 0 && !this.data.currentClassId) {
        this.selectClass(classList[0])
        return  // selectClass 内部会调用 loadExams
      }
    } catch (err) {
      console.error('加载班级列表失败', err)
    }
    // 如果已选择班级则刷新试卷列表（比如从创建页返回时）
    if (this.data.currentClassId) {
      this.loadExams()
    } else {
      this.setData({ loading: false })
    }
  },

  selectClass(cls) {
    this.setData({
      currentClassId: cls.id,
      currentClassName: cls.name,
      showClassPicker: false,
    })
    this.loadExams()
  },

  openClassPicker() {
    this.setData({ showClassPicker: !this.data.showClassPicker })
  },

  async loadExams() {
    this.setData({ loading: true })
    try {
      // 不传 class_id，与网页端一致：展示该教师的所有试卷
      // class_id 过滤会导致网页端创建的试卷（class_id 可能为空或不同）在小程序中不显示
      const result = await api.callHttpAPI('/teacher/exam/list', {}, 'GET')
      const exams = result?.items || result?.exams || result || []
      // 计算统计（后端不返回 student_count/graded_count，用 status 区分）
      const graded = exams.filter(e => e.status === 'published').length
      const pending = exams.filter(e => e.status !== 'published').length
      this.setData({ exams, stats: { total: exams.length, graded, pending } })
    } catch (err) {
      console.error('加载试卷列表失败', err)
      wx.showToast({ title: '加载试卷失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  // 新建试卷
  goToCreate() {
    if (!this.data.currentClassId) {
      wx.showToast({ title: '请先选择班级', icon: 'none' })
      return
    }
    wx.navigateTo({
      url: `/pages/teacher/exam/create/index?classId=${this.data.currentClassId}`
    })
  },

  // 进入批卷
  goToScan(e) {
    const { id, title } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/scan/index?examId=${id}&examTitle=${encodeURIComponent(title)}&classId=${this.data.currentClassId}`
    })
  },

  // 进入报告（使用新重写的 exam/detail 报告页，含可视化数据+学生列表）
  goToReport(e) {
    const { id } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/exam/detail/index?examId=${id}`
    })
  },

  // 查看试卷详情
  goToDetail(e) {
    const { id } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/exam/detail/index?examId=${id}`
    })
  },

  // 答题卡（统计行顶部按钮）— 选择固定空白模板或考试专用模板
  goToAnswerSheet() {
    const exams = this.data.exams || []
    const itemList = ['📋 空白答题卡（通用模板）']
    exams.forEach(e => itemList.push(`📝 ${e.title}`))
    wx.showActionSheet({
      itemList,
      success: (res) => {
        if (res.tapIndex === 0) {
          this.downloadBlankAnswerSheet()
        } else {
          const selected = exams[res.tapIndex - 1]
          this.showAnswerSheetOptions(selected)
        }
      },
      fail: () => {}
    })
  },

  // 每个试卷卡片的答题卡按钮 — 跳转到二级页面
  goToAnswerSheetForExam(e) {
    const { id, title } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/exam/answer-sheet/index?examId=${id}&title=${encodeURIComponent(title || '')}`
    })
  },

  // 下载固定空白答题卡 PDF（使用 api.exportGenericAnswerSheetPdf）
  downloadBlankAnswerSheet() {
    wx.showLoading({ title: '生成中...' })
    api.exportGenericAnswerSheetPdf({ title: '空白答题卡', page_size: 'A5' })
      .then(tempFilePath => {
        wx.hideLoading()
        wx.openDocument({
          filePath: tempFilePath,
          fileType: 'pdf',
          success: () => {
            wx.showToast({ title: '空白答题卡，可在右上角菜单中打印或导出' })
          },
          fail: () => {
            wx.showToast({ title: '打开失败', icon: 'none' })
          }
        })
      })
      .catch(err => {
        wx.hideLoading()
        console.error('下载空白答题卡失败', err)
        wx.showToast({ title: '下载失败，请重试', icon: 'none' })
      })
  },

  // 删除试卷
  async deleteExam(e) {
    const { id } = e.currentTarget.dataset
    wx.showModal({
      title: '删除试卷',
      content: '该试卷所有成绩和错题记录将被清除，确认删除？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await api.deleteTeacherExam(id)
            wx.showToast({ title: '已删除' })
            this.loadExams()
          } catch (err) {
            wx.showToast({ title: err.message || '删除失败', icon: 'none' })
          }
        }
      }
    })
  },
})
