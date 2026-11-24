// 教师端 — 扫描结果详情页（单次扫描的逐题详情）
const app = getApp()
const api = require('../../../../utils/api')

Page({
  data: {
    scanData: null,
    studentName: '',
    score: 0,
    maxScore: 0,
    multiScore: 0,
    multiMaxScore: 0,
    answers: [],
    wrongQuestions: [],
    pendingCount: 0,
    correctCount: 0,
    wrongCount: 0,
    // 确认弹窗
    showConfirm: false,
    confirmQuestion: null,
    selectedOption: '',
    // 统计分析摘要
    summary: {
      normal: 0,
      light: 0,
      multi: 0,
      blank: 0,
      uncertain: 0,
      allFilled: 0,
      multiNormal: 0,
      multiPartial: 0,
      multiShort: 0,
      multiExcess: 0,
    },
  },

  onLoad(options) {
    // 从扫描页传递数据（encodeURIComponent(JSON.stringify(scanResult))）
    if (options.data) {
      try {
        const scanData = JSON.parse(decodeURIComponent(options.data))
        this.setDataWithResult(scanData)
      } catch (err) {
        console.error('解析扫描数据失败', err)
        wx.showToast({ title: '数据解析失败', icon: 'none' })
      }
    } else if (options.examId && options.studentId) {
      // 直接从API加载
      this.loadFromApi(options.examId, options.studentId)
    }
  },

  setDataWithResult(scanData) {
    const answers = scanData.answers || []
    const wrongQuestions = scanData.wrong_questions || answers.filter(a => !a.is_correct)

    // 统计各类异常
    const summary = {
      normal: 0, light: 0, multi: 0, blank: 0,
      uncertain: 0, allFilled: 0,
      multiNormal: 0, multiPartial: 0, multiShort: 0, multiExcess: 0,
    }
    let correctCount = 0
    let wrongCount = 0

    // 为每条答案预计算额外展示字段（WXML不支持箭头函数/join/索引）
    answers.forEach(a => {
      // 多选漏选：计算缺失的选项
      if (a.status === 'multi_short') {
        const correct = a.correct || a.correct_answer || []
        const selected = a.selected || []
        a._missedOptions = correct.filter(c => !selected.includes(c)).join('、')
      }
      // WXML不支持 .join()，预计算所有数组拼接文本
      a._filledCirclesText = (a.filled_circles || []).join('、')
      a._selectedText = (a.selected || []).join('、')
      a._correctText = (a.correct || a.correct_answer || []).join('、')
    })

    answers.forEach(a => {
      if (a.is_correct) {
        correctCount++
      } else {
        wrongCount++
      }
      switch (a.status) {
        case 'normal': summary.normal++; break
        case 'light': summary.light++; break
        case 'multi': summary.multi++; break
        case 'blank': summary.blank++; break
        case 'uncertain': summary.uncertain++; break
        case 'all_filled': summary.allFilled++; break
        case 'multi_normal': summary.multiNormal++; break
        case 'multi_partial': summary.multiPartial++; break
        case 'multi_short': summary.multiShort++; break
        case 'multi_excess': summary.multiExcess++; break
        default: {
          if (a.question_type === 'multiple') summary.multiNormal++
          else summary.normal++
        }
      }
    })

    const studentName = scanData.student_name || ''
    this.setData({
      scanData,
      studentName,
      studentAvatarChar: studentName[0] || '?',
      score: scanData.score || 0,
      maxScore: scanData.max_score || 0,
      multiScore: scanData.multi_score || 0,
      multiMaxScore: scanData.multi_max_score || 0,
      answers,
      wrongQuestions,
      pendingCount: scanData.pending_count || 0,
      correctCount,
      wrongCount,
      summary,
    })
  },

  async loadFromApi(examId, studentId) {
    wx.showLoading({ title: '加载中...' })
    try {
      const result = await api.callHttpAPI(
        `/teacher/exam/${examId}/student/${studentId}`, {}, 'GET'
      )
      wx.hideLoading()
      if (result) {
        this.setDataWithResult(result)
      }
    } catch (err) {
      wx.hideLoading()
      console.error('加载学生答卷详情失败', err)
      wx.showToast({ title: '加载失败', icon: 'none' })
    }
  },

  // 显示确认弹窗（multi/uncertain 等异常题）
  openConfirm(e) {
    const { index } = e.currentTarget.dataset
    const question = this.data.answers[index]
    if (!question) return

    const options = question.options || ['A', 'B', 'C', 'D']
    this.setData({
      showConfirm: true,
      confirmQuestion: { ...question, index },
      selectedOption: '',
    })
  },

  closeConfirm() {
    this.setData({ showConfirm: false, confirmQuestion: null })
  },

  onOptionSelect(e) {
    this.setData({ selectedOption: e.currentTarget.dataset.value })
  },

  confirmAnswer() {
    const { confirmQuestion, selectedOption } = this.data
    if (!confirmQuestion || !selectedOption) return

    // 更新本地数据
    const answers = [...this.data.answers]
    const idx = confirmQuestion.index
    answers[idx] = {
      ...answers[idx],
      selected: selectedOption,
      is_correct: selectedOption === (answers[idx].correct || answers[idx].correct_answer),
      status: 'normal',
    }

    // 重新计算
    let score = 0
    let correctCount = 0
    let wrongCount = 0
    answers.forEach(a => {
      if (a.is_correct) {
        score += a.score || a.question_score || 0
        correctCount++
      } else {
        wrongCount++
      }
    })

    this.setData({
      answers,
      score,
      correctCount,
      wrongCount,
      showConfirm: false,
      confirmQuestion: null,
    })

    wx.showToast({ title: `已确认，得分 ${score}`, icon: 'none' })
  },

  // 获取状态文本显示
  getStatusText(status, questionType) {
    const map = {
      'normal': '正常',
      'light': '填涂较浅',
      'multi': '单选多选',
      'blank': '未作答',
      'uncertain': '可能改选',
      'all_filled': '整题涂黑',
      'multi_light': '疑似多选',
      'multi_normal': '多选全对',
      'multi_partial': '部分选错',
      'multi_short': '漏选',
      'multi_excess': '多涂',
    }
    return map[status] || status
  },
})
