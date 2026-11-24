// 教师端 — 新建试卷（2步流程：名称→模板/自定义设置）
const app = getApp()
const api = require('../../../../utils/api')

Page({
  data: {
    classId: null,
    step: 1,
    // 步骤1
    examName: '',
    hasPaperFile: false,
    paperFilePath: '',
    // 步骤2 — 模板
    templates: [],
    selectedTemplateId: null,
    selectedTemplateName: '',
    // 步骤2 — 自定义设置
    questionCount: 20,
    optionCount: 4,
    uniformScore: 5,
    questions: [],
    // 统计
    totalScore: 0,
    singleCount: 0,
    singleTotal: 0,
    questionType: 'single', // single / multiple
    // 创建中
    creating: false,
    // 模板保存
    showSaveTemplate: false,
    saveTemplateName: '',
  },

  onLoad(options) {
    this.setData({ classId: parseInt(options.classId) })
    this.loadTemplates()
    this.initQuestions()
  },

  // 生成选项字母数组
  _makeOptions(count) {
    return Array.from({ length: count }, (_, i) => String.fromCharCode(65 + i))
  },

  initQuestions() {
    this.buildQuestionsFromSettings()
  },

  buildQuestionsFromSettings() {
    const count = this.data.questionCount
    const opts = this._makeOptions(this.data.optionCount)
    const questions = Array.from({ length: count }, (_, i) => ({
      number: i + 1,
      score: this.data.uniformScore,
      type: this.data.questionType,
      optionCount: this.data.optionCount,
      options: [...opts],
      correct_answer: opts[0],
    }))
    this.setData({ questions })
    this.calcStats()
  },

  calcStats() {
    const questions = this.data.questions
    let totalScore = 0
    let singleCount = 0
    let singleTotal = 0
    questions.forEach(q => {
      totalScore += q.score
      if (q.type === 'single') { singleCount++; singleTotal += q.score }
    })
    this.setData({
      totalScore, singleCount, singleTotal,
      multiCount: 0, multiTotal: 0,
    })
  },

  // ===== 步骤1: 试卷名称 =====
  onExamNameInput(e) {
    this.setData({ examName: e.detail.value })
  },

  nextStep1() {
    if (!this.data.examName.trim()) {
      wx.showToast({ title: '请输入试卷名称', icon: 'none' })
      return
    }
    this.setData({ step: 2 })
  },

  // 上传电子版（可选）
  choosePaperFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['jpg', 'jpeg', 'png', 'pdf'],
      success: (res) => {
        const file = res.tempFiles[0]
        if (file.size > 20 * 1024 * 1024) {
          wx.showToast({ title: '文件过大（限20MB）', icon: 'none' })
          return
        }
        this.setData({
          hasPaperFile: true,
          paperFilePath: file.path,
        })
        wx.showToast({ title: '已选择文件: ' + file.name, icon: 'none' })
      }
    })
  },

  removePaperFile() {
    this.setData({ hasPaperFile: false, paperFilePath: '' })
  },

  // ===== 模板系统 =====
  loadTemplates() {
    try {
      const saved = wx.getStorageSync('exam_templates') || []
      this.setData({ templates: saved })
    } catch (e) {
      console.error('加载模板失败', e)
    }
  },

  selectTemplate(e) {
    const { id } = e.currentTarget.dataset
    const template = this.data.templates.find(t => t.id === id)
    if (!template) return
    this.setData({
      selectedTemplateId: id,
      selectedTemplateName: template.name,
      questionCount: template.questionCount,
      optionCount: template.optionCount,
      uniformScore: template.uniformScore,
      questionType: template.questionType,
    })
    this.buildQuestionsFromSettings()
  },

  deselectTemplate() {
    this.setData({ selectedTemplateId: null, selectedTemplateName: '' })
  },

  // 保存当前设置为模板
  openSaveTemplate() {
    this.setData({ showSaveTemplate: true, saveTemplateName: '' })
  },

  closeSaveTemplate() {
    this.setData({ showSaveTemplate: false })
  },

  onTemplateNameInput(e) {
    this.setData({ saveTemplateName: e.detail.value })
  },

  confirmSaveTemplate() {
    const name = this.data.saveTemplateName.trim()
    if (!name) {
      wx.showToast({ title: '请输入模板名称', icon: 'none' })
      return
    }
    try {
      const templates = wx.getStorageSync('exam_templates') || []
      const newTemplate = {
        id: Date.now().toString(),
        name,
        questionCount: this.data.questionCount,
        optionCount: this.data.optionCount,
        uniformScore: this.data.uniformScore,
        questionType: this.data.questionType,
        createTime: new Date().toLocaleString(),
      }
      templates.unshift(newTemplate)
      wx.setStorageSync('exam_templates', templates)
      this.setData({
        templates,
        showSaveTemplate: false,
        selectedTemplateId: newTemplate.id,
        selectedTemplateName: name,
      })
      wx.showToast({ title: '模板已保存' })
    } catch (e) {
      wx.showToast({ title: '保存失败', icon: 'none' })
    }
  },

  deleteTemplate(e) {
    const { id } = e.currentTarget.dataset
    wx.showModal({
      title: '删除模板',
      content: '确认删除该模板？',
      success: (res) => {
        if (res.confirm) {
          try {
            const templates = this.data.templates.filter(t => t.id !== id)
            wx.setStorageSync('exam_templates', templates)
            this.setData({
              templates,
              selectedTemplateId: this.data.selectedTemplateId === id ? null : this.data.selectedTemplateId,
            })
            wx.showToast({ title: '已删除' })
          } catch (e) {
            wx.showToast({ title: '删除失败', icon: 'none' })
          }
        }
      }
    })
  },

  // ===== 步骤2: 自定义设置 =====
  // 题型切换
  onTypeChange(e) {
    const type = e.currentTarget.dataset.value
    this.setData({ questionType: type })
    this.buildQuestionsFromSettings()
  },

  // 题量
  onQuestionCountInput(e) {
    const count = Math.min(Math.max(parseInt(e.detail.value) || 1, 1), 200)
    this.setData({ questionCount: count })
    this.buildQuestionsFromSettings()
  },

  decreaseCount() {
    const count = Math.max(this.data.questionCount - 1, 1)
    this.setData({ questionCount: count })
    this.buildQuestionsFromSettings()
  },

  increaseCount() {
    const count = Math.min(this.data.questionCount + 1, 200)
    this.setData({ questionCount: count })
    this.buildQuestionsFromSettings()
  },

  // 选项数量
  onOptionCountInput(e) {
    const count = Math.min(Math.max(parseInt(e.detail.value) || 2, 2), 10)
    this.setData({ optionCount: count })
    this.buildQuestionsFromSettings()
  },

  decreaseOptionCount() {
    const count = Math.max(this.data.optionCount - 1, 2)
    this.setData({ optionCount: count })
    this.buildQuestionsFromSettings()
  },

  increaseOptionCount() {
    const count = Math.min(this.data.optionCount + 1, 10)
    this.setData({ optionCount: count })
    this.buildQuestionsFromSettings()
  },

  // 分值
  onScoreInput(e) {
    const score = Math.max(parseInt(e.detail.value) || 1, 1)
    this.setData({ uniformScore: score })
    this.buildQuestionsFromSettings()
  },

  // 完成创建
  async confirmCreate() {
    this.setData({ creating: true })
    try {
      // 先构建 choice_questions JSON
      const opts = this._makeOptions(this.data.optionCount)
      const choiceQuestions = this.data.questions.map((q) => ({
        question_number: q.number,
        section: this.data.examName || '试卷',
        question_type: 'single_choice',
        correct_answer: 'A',
        option_count: this.data.optionCount,
        options: opts,
        score: q.score,
      }))

      const payload = {
        class_id: this.data.classId,
        title: this.data.examName.trim(),
        question_count: this.data.questionCount,
        total_score: this.data.totalScore,
        questions: this.data.questions.map(q => ({
          number: q.number,
          score: q.score,
          type: q.type,
          options: opts,
          correct_answer: 'A',
        })),
        choice_questions: choiceQuestions,
      }

      const res = await api.callHttpAPI('/teacher/exam/manual-save', payload, 'POST')
      const examId = res?.exam_id

      wx.showToast({ title: '创建完成' })

      setTimeout(() => {
        if (examId) {
          // 回到试卷列表页
          wx.navigateBack({ delta: 1 })
        } else {
          wx.navigateBack()
        }
      }, 1000)
    } catch (err) {
      wx.showToast({ title: err.message || '创建失败', icon: 'none' })
    } finally {
      this.setData({ creating: false })
    }
  },

  // 返回上一步
  prevStep() {
    if (this.data.step > 1) {
      this.setData({ step: this.data.step - 1 })
    }
  },
})
